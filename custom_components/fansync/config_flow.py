# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from .client import FanSyncClient
from .const import CONF_EMAIL, CONF_PASSWORD, CONF_VERIFY_SSL, DOMAIN

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)


class FanSyncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

        # Set unique ID early to avoid unnecessary network calls on duplicates
        await self.async_set_unique_id(user_input[CONF_EMAIL])
        self._abort_if_unique_id_configured()

        errors = {}
        try:
            client = FanSyncClient(
                self.hass,
                user_input[CONF_EMAIL],
                user_input[CONF_PASSWORD],
                user_input.get(CONF_VERIFY_SSL, True),
            )
            await client.async_connect()
        except Exception:
            errors["base"] = "cannot_connect"

        if errors:
            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)

        return self.async_create_entry(title="FanSync", data=user_input)
