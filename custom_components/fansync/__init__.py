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
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .client import FanSyncClient
from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
    DEFAULT_FALLBACK_POLL_SECS,
    DOMAIN,
    OPTION_FALLBACK_POLL_SECS,
    PLATFORMS,
)
from .coordinator import FanSyncCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Build and store a shared client+coordinator for platforms to reuse
    client = FanSyncClient(
        hass,
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_VERIFY_SSL, True),
    )
    await client.async_connect()
    coordinator = FanSyncCoordinator(hass, client)
    # Apply options-driven fallback polling
    secs = entry.options.get(OPTION_FALLBACK_POLL_SECS, DEFAULT_FALLBACK_POLL_SECS)
    coordinator.update_interval = None if secs == 0 else timedelta(seconds=int(secs))
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug(
            "setup interval=%s verify_ssl=%s",
            coordinator.update_interval,
            entry.data.get(CONF_VERIFY_SSL, True),
        )

    # Register a push callback if supported by the client
    if hasattr(client, "set_status_callback"):

        def _on_status(status: dict[str, object]) -> None:
            # Merge pushed status for this device into the coordinator's mapping
            did = getattr(client, "device_id", None) or "unknown"
            current = coordinator.data or {}
            merged: dict[str, dict[str, object]] = dict(current)
            merged[did] = status
            coordinator.async_set_updated_data(merged)
            if _LOGGER.isEnabledFor(logging.DEBUG):
                keys = list(status.keys()) if isinstance(status, dict) else []
                _LOGGER.debug("push merge d=%s keys=%s", did, keys)

        client.set_status_callback(_on_status)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    async def _async_options_updated(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        new_secs = updated_entry.options.get(OPTION_FALLBACK_POLL_SECS, DEFAULT_FALLBACK_POLL_SECS)
        old = coordinator.update_interval
        coordinator.update_interval = None if new_secs == 0 else timedelta(seconds=int(new_secs))
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("interval changed old=%s new=%s", old, coordinator.update_interval)

    entry.add_update_listener(_async_options_updated)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if _LOGGER.isEnabledFor(logging.DEBUG):
        try:
            ids = getattr(client, "device_ids", []) or [client.device_id]
        except Exception:  # pragma: no cover
            ids = []
        _LOGGER.debug("connected device_ids=%s", ids)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if data and data.get("client"):
            await data["client"].async_disconnect()
    return unloaded
