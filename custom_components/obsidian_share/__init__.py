"""Obsidian Share: Notizen aus dem Vault per Link teilen und im HA-Panel lesen/bearbeiten."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError, Unauthorized
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from . import share_token
from .const import (
    CONF_VAULT_PATH,
    DATA_HTTP_REGISTERED,
    DOMAIN,
    KEY_STORE,
    MAX_SHARE_DAYS,
    PANEL_COMPONENT,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    SERVICE_GET_LINK,
    SERVICE_ROTATE_KEY,
    STATIC_URL,
    VERSION,
)
from .runtime import ShareRuntime
from .vault import Vault, VaultError, is_shared, split_frontmatter
from .views import ALL_VIEWS

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type ObsidianShareConfigEntry = ConfigEntry[ShareRuntime]

GET_LINK_SCHEMA = vol.Schema(
    {
        vol.Required("path"): cv.string,
        vol.Optional("days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_SHARE_DAYS)),
    }
)


def _runtime(hass: HomeAssistant) -> ShareRuntime:
    runtime: ShareRuntime | None = hass.data.get(DOMAIN)
    if runtime is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    return runtime


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Aktionen registrieren."""

    async def get_link(call: ServiceCall) -> ServiceResponse:
        runtime = _runtime(hass)
        if call.context.user_id:
            user = await hass.auth.async_get_user(call.context.user_id)
            if not runtime.can_read(user):
                raise Unauthorized
        path: str = call.data["path"]

        def check() -> bool:
            text, _ = runtime.vault.read_note(path)
            return is_shared(split_frontmatter(text)[0])

        try:
            shared = await hass.async_add_executor_job(check)
        except VaultError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="note_not_found",
                translation_placeholders={"path": path},
            ) from err
        if not shared:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="note_not_shared",
                translation_placeholders={"path": path},
            )
        url, expires = runtime.make_link(path, call.data.get("days"))
        return {"url": url, "path": path, "expires": expires}

    async def rotate_key(call: ServiceCall) -> None:
        await _runtime(hass).async_rotate_key()

    hass.services.async_register(
        DOMAIN, SERVICE_GET_LINK, get_link, schema=GET_LINK_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    async_register_admin_service(hass, DOMAIN, SERVICE_ROTATE_KEY, rotate_key)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ObsidianShareConfigEntry) -> bool:
    """Eintrag laden."""
    vault = Vault(entry.data[CONF_VAULT_PATH])
    if not await hass.async_add_executor_job(vault.exists):
        raise ConfigEntryNotReady(f"Vault nicht gefunden: {entry.data[CONF_VAULT_PATH]}")

    # Schlüssel liegt in .storage, nicht im Integrationsordner: Updates per HACS
    # lassen bestehende Links gültig.
    store: Store = Store(hass, 1, KEY_STORE, private=True)
    stored = await store.async_load()
    if stored and "key" in stored:
        key = bytes.fromhex(stored["key"])
    else:
        key = share_token.new_key()
        await store.async_save({"key": key.hex()})

    runtime = ShareRuntime(hass, entry, vault, key, store)
    entry.runtime_data = runtime
    hass.data[DOMAIN] = runtime

    if not hass.data.get(DATA_HTTP_REGISTERED):
        # Views und statische Pfade lassen sich nicht abmelden: nur einmal registrieren
        for view in ALL_VIEWS:
            hass.http.register_view(view(hass))
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "static"), False)]
        )
        hass.data[DATA_HTTP_REGISTERED] = True

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=f"{STATIC_URL}/panel.js?v={VERSION}",
        require_admin=False,
        config={},
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ObsidianShareConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ObsidianShareConfigEntry) -> bool:
    """Eintrag entladen."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    hass.data.pop(DOMAIN, None)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ObsidianShareConfigEntry) -> None:
    """Beim Löschen auch den Schlüssel entfernen (alle Links sind dann ungültig)."""
    await Store(hass, 1, KEY_STORE).async_remove()
