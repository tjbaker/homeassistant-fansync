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

import logging
from typing import Any

import httpx
import voluptuous as vol
from homeassistant import config_entries

from .client import FanSyncClient
from .const import (
    CONF_EMAIL,
    CONF_HTTP_TIMEOUT,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
    CONF_WS_TIMEOUT,
    DEFAULT_FALLBACK_POLL_SECS,
    DEFAULT_HTTP_TIMEOUT_SECS,
    DEFAULT_WS_TIMEOUT_SECS,
    DOMAIN,
    MAX_FALLBACK_POLL_SECS,
    MAX_HTTP_TIMEOUT_SECS,
    MAX_WS_TIMEOUT_SECS,
    MIN_FALLBACK_POLL_SECS,
    MIN_HTTP_TIMEOUT_SECS,
    MIN_WS_TIMEOUT_SECS,
    OPTION_FALLBACK_POLL_SECS,
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
        vol.Optional(CONF_HTTP_TIMEOUT, default=DEFAULT_HTTP_TIMEOUT_SECS): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_HTTP_TIMEOUT_SECS, max=MAX_HTTP_TIMEOUT_SECS)
        ),
        vol.Optional(CONF_WS_TIMEOUT, default=DEFAULT_WS_TIMEOUT_SECS): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_WS_TIMEOUT_SECS, max=MAX_WS_TIMEOUT_SECS)
        ),
    }
)

_LOGGER = logging.getLogger(__name__)


class FanSyncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

        # Set unique ID early to avoid unnecessary network calls on duplicates
        await self.async_set_unique_id(user_input[CONF_EMAIL])
        self._abort_if_unique_id_configured()

        errors = {}
        client: FanSyncClient | None = None
        try:
            client = FanSyncClient(
                self.hass,
                user_input[CONF_EMAIL],
                user_input[CONF_PASSWORD],
                user_input.get(CONF_VERIFY_SSL, True),
                enable_push=False,
                http_timeout_s=user_input.get(CONF_HTTP_TIMEOUT, DEFAULT_HTTP_TIMEOUT_SECS),
                ws_timeout_s=user_input.get(CONF_WS_TIMEOUT, DEFAULT_WS_TIMEOUT_SECS),
            )
            await client.async_connect()

            # Verify at least one device was discovered
            if not client.device_ids:
                _LOGGER.warning(
                    "Login successful but no devices found for %s", user_input[CONF_EMAIL]
                )
                errors["base"] = "no_devices"

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if getattr(exc, "response", None) else "unknown"
            _LOGGER.error(
                "Authentication failed: HTTP %s - check credentials",
                status,
            )
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("HTTP error details: %s", str(exc))
            errors["base"] = "invalid_auth"
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            _LOGGER.error("Network connection failed: %s", type(exc).__name__)
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("Network error details: %s", str(exc))
            errors["base"] = "cannot_connect"
        except Exception as exc:
            _LOGGER.error(
                "Unexpected error during setup: %s: %s",
                type(exc).__name__,
                str(exc),
            )
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("Full exception:", exc_info=True)
            errors["base"] = "unknown"
        finally:
            # Always clean up validation client to avoid background resources lingering
            if client is not None:
                try:
                    await client.async_disconnect()
                except Exception as exc:
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug(
                            "Exception during client disconnect: %s: %s",
                            type(exc).__name__,
                            str(exc),
                        )

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
            raw_secs = user_input.get(OPTION_FALLBACK_POLL_SECS, DEFAULT_FALLBACK_POLL_SECS)
            secs = int(raw_secs)
            if secs != 0:
                secs = max(MIN_FALLBACK_POLL_SECS, min(MAX_FALLBACK_POLL_SECS, secs))
            # Clamp timeouts with explicit type checks to satisfy static typing
            raw_data = getattr(self.config_entry, "data", {})
            data_defaults = raw_data if isinstance(raw_data, dict) else {}

            http_raw = user_input.get(
                CONF_HTTP_TIMEOUT,
                data_defaults.get(CONF_HTTP_TIMEOUT, DEFAULT_HTTP_TIMEOUT_SECS),
            )
            if isinstance(http_raw, int | float | str):
                http_t = int(http_raw)
            else:
                http_t = int(DEFAULT_HTTP_TIMEOUT_SECS)
            http_t = max(MIN_HTTP_TIMEOUT_SECS, min(MAX_HTTP_TIMEOUT_SECS, http_t))

            ws_raw = user_input.get(
                CONF_WS_TIMEOUT,
                data_defaults.get(CONF_WS_TIMEOUT, DEFAULT_WS_TIMEOUT_SECS),
            )
            if isinstance(ws_raw, int | float | str):
                ws_t = int(ws_raw)
            else:
                ws_t = int(DEFAULT_WS_TIMEOUT_SECS)
            ws_t = max(MIN_WS_TIMEOUT_SECS, min(MAX_WS_TIMEOUT_SECS, ws_t))
            if _LOGGER.isEnabledFor(logging.DEBUG):
                if raw_secs != secs:
                    _LOGGER.debug("options poll interval clamped: %s -> %s", raw_secs, secs)
                else:
                    _LOGGER.debug("options poll interval set: %s", secs)
                _LOGGER.debug("options timeouts set: http=%s ws=%s", http_t, ws_t)
            return self.async_create_entry(
                title="FanSync Options",
                data={
                    OPTION_FALLBACK_POLL_SECS: secs,
                    CONF_HTTP_TIMEOUT: http_t,
                    CONF_WS_TIMEOUT: ws_t,
                },
            )

        current = self.config_entry.options.get(
            OPTION_FALLBACK_POLL_SECS, DEFAULT_FALLBACK_POLL_SECS
        )
        raw_data = getattr(self.config_entry, "data", {})
        data_defaults = raw_data if isinstance(raw_data, dict) else {}
        current_http = self.config_entry.options.get(
            CONF_HTTP_TIMEOUT,
            data_defaults.get(CONF_HTTP_TIMEOUT, DEFAULT_HTTP_TIMEOUT_SECS),
        )
        current_ws = self.config_entry.options.get(
            CONF_WS_TIMEOUT,
            data_defaults.get(CONF_WS_TIMEOUT, DEFAULT_WS_TIMEOUT_SECS),
        )
        schema = vol.Schema(
            {
                vol.Optional(
                    OPTION_FALLBACK_POLL_SECS,
                    default=current,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_FALLBACK_POLL_SECS)),
                vol.Optional(
                    CONF_HTTP_TIMEOUT,
                    default=current_http,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_HTTP_TIMEOUT_SECS, max=MAX_HTTP_TIMEOUT_SECS),
                ),
                vol.Optional(
                    CONF_WS_TIMEOUT,
                    default=current_ws,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_WS_TIMEOUT_SECS, max=MAX_WS_TIMEOUT_SECS),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
