"""Konstanten für Obsidian Share."""

from typing import Final

DOMAIN: Final = "obsidian_share"
VERSION: Final = "0.2.0"

CONF_VAULT_PATH: Final = "vault_path"
CONF_EDITORS: Final = "editors"
CONF_READERS: Final = "readers"
CONF_EXTERNAL_URL: Final = "external_url"

DEFAULT_VAULT_PATH: Final = "/share/syncthing/obsidian_vault"

API_BASE: Final = "/api/obsidian_share"
STATIC_URL: Final = "/obsidian_share_static"
PANEL_URL_PATH: Final = "obsidian"
PANEL_COMPONENT: Final = "obsidian-share-panel"
PANEL_TITLE: Final = "Obsidian"
PANEL_ICON: Final = "mdi:notebook-outline"

KEY_STORE: Final = f"{DOMAIN}.key"
DATA_HTTP_REGISTERED: Final = f"{DOMAIN}_http_registered"

SERVICE_GET_LINK: Final = "get_link"
SERVICE_ROTATE_KEY: Final = "rotate_key"

MAX_SHARE_DAYS: Final = 3650
