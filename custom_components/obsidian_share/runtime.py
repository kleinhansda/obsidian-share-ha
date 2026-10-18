"""Laufzeitobjekt pro Config-Eintrag: Rechte, Links, Rendern."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import posixpath
import time
from urllib.parse import quote

from homeassistant.auth.models import User
from homeassistant.components.http.auth import async_sign_path
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import share_token
from .const import API_BASE, CONF_EDITORS, CONF_EXTERNAL_URL, CONF_READERS
from .render import MODE_PANEL, MODE_PUBLIC, Rendered, public_page, render_note
from .vault import NotFound, Vault, VaultError, is_shared, split_frontmatter

PANEL_IMAGE_TTL = timedelta(hours=2)


@dataclass
class ShareRuntime:
    """Alles, was Views und Aktionen brauchen."""

    hass: HomeAssistant
    entry: ConfigEntry
    vault: Vault
    key: bytes
    store: Store

    # -- Rechte ------------------------------------------------------------

    def can_edit(self, user: User | None) -> bool:
        if user is None or not user.is_active:
            return False
        return user.is_admin or user.id in self.entry.options.get(CONF_EDITORS, [])

    def can_read(self, user: User | None) -> bool:
        if self.can_edit(user):
            return True
        return bool(user and user.is_active and user.id in self.entry.options.get(CONF_READERS, []))

    # -- Links -------------------------------------------------------------

    def base_url(self) -> str:
        if url := (self.entry.options.get(CONF_EXTERNAL_URL) or "").strip():
            return url.rstrip("/")
        try:
            return get_url(self.hass, prefer_external=True, allow_cloud=False).rstrip("/")
        except NoURLAvailableError:
            return ""

    def make_link(self, rel: str, days: int | None) -> tuple[str, int | None]:
        expires = int(time.time() + days * 86400) if days else None
        token = share_token.encode(self.key, rel, expires)
        return f"{self.base_url()}{API_BASE}/s/{token}", expires

    async def async_rotate_key(self) -> None:
        self.key = share_token.new_key()
        await self.store.async_save({"key": self.key.hex()})

    # -- Öffentlich --------------------------------------------------------

    def _load_public(self, token: str) -> tuple[str, Rendered, int | None] | None:
        """Blockierend: Token prüfen, Notiz laden, Freigabe prüfen, rendern."""
        decoded = share_token.decode(self.key, token, time.time())
        if decoded is None:
            return None
        rel, expires = decoded
        try:
            text, _ = self.vault.read_note(rel)
        except VaultError:
            return None
        meta, _ = split_frontmatter(text)
        if not is_shared(meta):
            return None
        rendered = render_note(
            text,
            note_rel=rel,
            index=self.vault.file_index(),
            mode=MODE_PUBLIC,
            image_url=lambda i, _rel: f"{API_BASE}/s/{token}/img/{i}",
        )
        return rel, rendered, expires

    async def async_public_page(self, token: str) -> str | None:
        loaded = await self.hass.async_add_executor_job(self._load_public, token)
        if loaded is None:
            return None
        rel, rendered, expires = loaded
        expires_text = None
        if expires:
            expires_text = dt_util.as_local(
                datetime.fromtimestamp(expires, dt_util.UTC)
            ).strftime("%d.%m.%Y %H:%M")
        title = posixpath.splitext(posixpath.basename(rel))[0]
        return public_page(title, rendered, expires_text)

    def _load_public_image(self, token: str, idx: int) -> tuple[bytes, str] | None:
        loaded = self._load_public(token)
        if loaded is None:
            return None
        _, rendered, _ = loaded
        if not 0 <= idx < len(rendered.embeds):
            return None
        try:
            return self.vault.read_image(rendered.embeds[idx])
        except VaultError:
            return None

    async def async_public_image(self, token: str, idx: int) -> tuple[bytes, str] | None:
        return await self.hass.async_add_executor_job(self._load_public_image, token, idx)

    # -- Panel -------------------------------------------------------------

    def _load_panel(self, rel: str):
        text, etag = self.vault.read_note(rel)
        return text, etag, self.vault.file_index()

    async def async_panel_note(self, rel: str) -> dict:
        """Notiz fürs Panel: Rohtext, ETag, HTML. Wirft NotFound."""
        text, etag, index = await self.hass.async_add_executor_job(self._load_panel, rel)

        def image_url(_idx: int, img_rel: str) -> str:
            # Signierte URL, weil <img> keinen Auth-Header senden kann
            return async_sign_path(
                self.hass, f"{API_BASE}/file?path={quote(img_rel, safe='')}", PANEL_IMAGE_TTL
            )

        rendered = render_note(
            text, note_rel=rel, index=index, mode=MODE_PANEL, image_url=image_url
        )
        meta, _ = split_frontmatter(text)
        return {
            "path": rel,
            "text": text,
            "etag": etag,
            "html": rendered.html,
            "toc": rendered.toc,
            "shared": is_shared(meta),
        }


__all__ = ["NotFound", "ShareRuntime"]
