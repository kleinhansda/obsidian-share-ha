"""Dateizugriff auf den Vault. Alle Funktionen sind blockierend (Executor)."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import secrets
from typing import Any

import yaml

NOTE_SUFFIX = ".md"
IMAGE_TYPES: dict[str, str] = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
MAX_NOTE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 15 * 1024 * 1024
TMP_PREFIX = ".os-"
TMP_SUFFIX = ".tmp"

# Frontmatter: "---" Zeile, optionaler Inhalt, "---" Zeile
FM_RE = re.compile(
    r"\A---[ \t]*\r?\n(?:(?P<body>.*?)\r?\n)?---[ \t]*(?:\r?\n|\Z)", re.DOTALL
)
SHARE_LINE_RE = re.compile(r"^ha_share[ \t]*:")


class VaultError(Exception):
    """Basisfehler."""


class NotFound(VaultError):
    """Datei fehlt, liegt außerhalb des Vaults oder ist nicht erlaubt."""


class TooLarge(VaultError):
    """Datei überschreitet die Größengrenze."""


class Conflict(VaultError):
    """Datei wurde seit dem Öffnen verändert."""

    def __init__(self, etag: str) -> None:
        super().__init__("conflict")
        self.etag = etag


def etag_of(data: bytes) -> str:
    """Inhaltsbasierter ETag."""
    return hashlib.sha256(data).hexdigest()[:32]


def _hidden(part: str) -> bool:
    return part.startswith(".")


@dataclass
class FileIndex:
    """Alle sichtbaren Dateien des Vaults, für Wikilinks und Einbettungen."""

    by_name: dict[str, list[str]] = field(default_factory=dict)
    all: set[str] = field(default_factory=set)


class Vault:
    """Abgeschotteter Zugriff auf einen Vault-Ordner."""

    def __init__(self, root: str) -> None:
        self.root = Path(os.path.realpath(root))

    # -- Pfade -------------------------------------------------------------

    def resolve(self, rel: str, suffixes: set[str] | dict[str, str]) -> Path:
        """Relativen Pfad prüfen und als absoluten Pfad im Vault liefern."""
        if not isinstance(rel, str) or not rel or "\x00" in rel:
            raise NotFound
        pure = PurePosixPath(rel.replace("\\", "/"))
        if pure.is_absolute():
            raise NotFound
        if any(p in ("", ".", "..") or _hidden(p) for p in pure.parts):
            raise NotFound
        full = Path(os.path.realpath(self.root.joinpath(*pure.parts)))
        try:
            inside = full.relative_to(self.root)
        except ValueError as err:
            raise NotFound from err
        # Auch nach Auflösen von Symlinks keine versteckten Ordner
        if not inside.parts or any(_hidden(p) for p in inside.parts):
            raise NotFound
        if full.suffix.lower() not in suffixes:
            raise NotFound
        return full

    def rel(self, full: Path) -> str:
        """Absoluten Pfad als Vault-relativen POSIX-Pfad."""
        return full.relative_to(self.root).as_posix()

    def exists(self) -> bool:
        """Vault-Ordner vorhanden?"""
        return self.root.is_dir()

    # -- Auflisten ---------------------------------------------------------

    def _walk(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if not _hidden(d)]
            for name in filenames:
                if not _hidden(name):
                    yield Path(dirpath, name)

    def file_index(self) -> FileIndex:
        """Index aller sichtbaren Dateien (Name klein → Pfade)."""
        index = FileIndex()
        for full in self._walk():
            rel = self.rel(full)
            index.all.add(rel)
            index.by_name.setdefault(full.name.lower(), []).append(rel)
        return index

    def list_notes(self) -> list[dict[str, Any]]:
        """Alle Notizen mit Freigabestatus, sortiert."""
        notes = []
        for full in self._walk():
            if full.suffix.lower() != NOTE_SUFFIX:
                continue
            notes.append({"path": self.rel(full), "shared": self._head_shared(full)})
        notes.sort(key=lambda n: n["path"].casefold())
        return notes

    @staticmethod
    def _head_shared(full: Path) -> bool:
        try:
            with full.open("rb") as fh:
                head = fh.read(16384).decode("utf-8", errors="replace")
        except OSError:
            return False
        meta, _ = split_frontmatter(head)
        return is_shared(meta)

    # -- Lesen/Schreiben ---------------------------------------------------

    def read_note(self, rel: str) -> tuple[str, str]:
        """Notiz lesen → (Text, ETag)."""
        full = self.resolve(rel, {NOTE_SUFFIX})
        data = self._read(full, MAX_NOTE_BYTES)
        return data.decode("utf-8", errors="replace"), etag_of(data)

    def read_image(self, rel: str) -> tuple[bytes, str]:
        """Bild lesen → (Bytes, Content-Type)."""
        full = self.resolve(rel, IMAGE_TYPES)
        return self._read(full, MAX_IMAGE_BYTES), IMAGE_TYPES[full.suffix.lower()]

    @staticmethod
    def _read(full: Path, limit: int) -> bytes:
        try:
            if not full.is_file():
                raise NotFound
            if full.stat().st_size > limit:
                raise TooLarge
            return full.read_bytes()
        except OSError as err:
            raise NotFound from err

    def write_note(self, rel: str, text: str, expected_etag: str) -> str:
        """Notiz atomar schreiben, nur wenn ETag noch passt. Liefert neuen ETag."""
        full = self.resolve(rel, {NOTE_SUFFIX})
        current = self._read(full, MAX_NOTE_BYTES)
        if etag_of(current) != expected_etag:
            raise Conflict(etag_of(current))
        data = text.encode("utf-8")
        if len(data) > MAX_NOTE_BYTES:
            raise TooLarge
        tmp = full.with_name(f"{TMP_PREFIX}{secrets.token_hex(6)}{TMP_SUFFIX}")
        try:
            with tmp.open("xb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            with contextlib.suppress(OSError):
                os.chmod(tmp, full.stat().st_mode & 0o777)
            os.replace(tmp, full)
        finally:
            tmp.unlink(missing_ok=True)
        return etag_of(data)


# -- Frontmatter -----------------------------------------------------------


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """(Metadaten, Body) – Metadaten leer bei fehlendem/kaputtem YAML."""
    match = FM_RE.match(text)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group("body") or "") or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, text[match.end() :]


def is_shared(meta: dict[str, Any]) -> bool:
    """ha_share: true gesetzt?"""
    value = meta.get("ha_share")
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def set_share_flag(text: str, shared: bool) -> str:
    """ha_share im Frontmatter setzen/entfernen, Rest unverändert lassen."""
    newline = "\r\n" if "\r\n" in text else "\n"
    match = FM_RE.match(text)
    if not match:
        if not shared:
            return text
        return f"---{newline}ha_share: true{newline}---{newline}{text}"
    body = match.group("body") or ""
    lines = [ln for ln in body.splitlines() if not SHARE_LINE_RE.match(ln)]
    if shared:
        lines.append("ha_share: true")
    rest = text[match.end() :]
    if not lines:
        return rest
    return f"---{newline}{newline.join(lines)}{newline}---{newline}{rest}"
