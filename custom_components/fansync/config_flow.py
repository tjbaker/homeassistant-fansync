# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Trevor Baker, all rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#   http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries

from .client import FanSyncClient
from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
    DEFAULT_FALLBACK_POLL_SECS,
    DOMAIN,
    MAX_FALLBACK_POLL_SECS,
    MIN_FALLBACK_POLL_SECS,
    OPTION_FALLBACK_POLL_SECS,
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)


class FanSyncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
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

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return FanSyncOptionsFlowHandler(config_entry)


class FanSyncOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        # Support both new and older HA versions
        try:
            super().__init__(config_entry)  # type: ignore[call-arg]
        except TypeError:
            self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            # Clamp value into allowed range; 0 disables polling
            secs = int(user_input.get(OPTION_FALLBACK_POLL_SECS, DEFAULT_FALLBACK_POLL_SECS))
            if secs != 0:
                secs = max(MIN_FALLBACK_POLL_SECS, min(MAX_FALLBACK_POLL_SECS, secs))
            return self.async_create_entry(
                title="FanSync Options", data={OPTION_FALLBACK_POLL_SECS: secs}
            )

        current = self.config_entry.options.get(
            OPTION_FALLBACK_POLL_SECS, DEFAULT_FALLBACK_POLL_SECS
        )
        schema = vol.Schema(
            {
                vol.Optional(
                    OPTION_FALLBACK_POLL_SECS,
                    default=current,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_FALLBACK_POLL_SECS)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
