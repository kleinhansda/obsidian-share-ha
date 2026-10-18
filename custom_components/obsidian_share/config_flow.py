"""Einrichtung und Optionen."""

from __future__ import annotations

import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_EDITORS,
    CONF_EXTERNAL_URL,
    CONF_READERS,
    CONF_VAULT_PATH,
    DEFAULT_VAULT_PATH,
    DOMAIN,
)


class ObsidianShareConfigFlow(ConfigFlow, domain=DOMAIN):
    """Vault-Pfad abfragen."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            path = os.path.normpath(user_input[CONF_VAULT_PATH].strip())
            if await self.hass.async_add_executor_job(os.path.isdir, path):
                return self.async_create_entry(title="Obsidian Share", data={CONF_VAULT_PATH: path})
            errors[CONF_VAULT_PATH] = "not_found"
        schema = vol.Schema(
            {vol.Required(CONF_VAULT_PATH, default=DEFAULT_VAULT_PATH): TextSelector()}
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ObsidianShareOptionsFlow()


class ObsidianShareOptionsFlow(OptionsFlow):
    """Rechte und externe URL."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = dict(user_input)
            data[CONF_EXTERNAL_URL] = (data.get(CONF_EXTERNAL_URL) or "").strip()
            return self.async_create_entry(data=data)

        users = [
            u
            for u in await self.hass.auth.async_get_users()
            if not u.system_generated and u.is_active and not u.is_admin
        ]
        valid = {u.id for u in users}
        choices = [SelectOptionDict(value=u.id, label=u.name or u.id) for u in users]
        user_select = SelectSelector(
            SelectSelectorConfig(options=choices, multiple=True, mode=SelectSelectorMode.LIST)
        )
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_EDITORS, default=[u for u in opts.get(CONF_EDITORS, []) if u in valid]
                ): user_select,
                vol.Optional(
                    CONF_READERS, default=[u for u in opts.get(CONF_READERS, []) if u in valid]
                ): user_select,
                vol.Optional(
                    CONF_EXTERNAL_URL,
                    description={"suggested_value": opts.get(CONF_EXTERNAL_URL, "")},
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
