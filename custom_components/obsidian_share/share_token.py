"""Freigabe-Token: AES-GCM-verschlüsselter Notizpfad plus Ablaufdatum.

Der Token ist gleichzeitig Schlüssel und Adresse. Er verrät weder Pfad noch
Ablaufdatum, ist manipulationssicher und wird nirgends gespeichert. Ein neuer
Schlüssel macht alle bisherigen Links ungültig.
"""

from __future__ import annotations

import base64
import binascii
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_AAD = b"obsidian_share/v1"
_NONCE = 12
_TAG = 16
MAX_TOKEN_LEN = 2048


def new_key() -> bytes:
    """Neuen 256-Bit-Schlüssel erzeugen."""
    return AESGCM.generate_key(bit_length=256)


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode(key: bytes, path: str, expires: int | None) -> str:
    """Token für Notizpfad erzeugen; expires = Unix-Zeit oder None."""
    nonce = os.urandom(_NONCE)
    payload = json.dumps(
        {"p": path, "e": int(expires or 0)}, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return _b64e(nonce + AESGCM(key).encrypt(nonce, payload, _AAD))


def decode(key: bytes, token: str, now: float) -> tuple[str, int | None] | None:
    """Token prüfen. Liefert (Pfad, Ablauf) oder None bei jedem Fehler."""
    if not token or len(token) > MAX_TOKEN_LEN:
        return None
    try:
        raw = _b64d(token)
    except (binascii.Error, ValueError):
        return None
    if len(raw) < _NONCE + _TAG + 2:
        return None
    try:
        payload = AESGCM(key).decrypt(raw[:_NONCE], raw[_NONCE:], _AAD)
        data = json.loads(payload)
    except (InvalidTag, ValueError):
        return None
    path = data.get("p") if isinstance(data, dict) else None
    expires = data.get("e") if isinstance(data, dict) else None
    if not isinstance(path, str) or not isinstance(expires, int):
        return None
    if expires and now > expires:
        return None
    return path, (expires or None)
