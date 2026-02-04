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

import asyncio
import logging
from datetime import timedelta
from typing import TypedDict

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

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
    KEY_LIGHT_BRIGHTNESS,
    KEY_LIGHT_POWER,
    OPTION_FALLBACK_POLL_SECS,
    PLATFORMS,
    POLL_STATUS_TIMEOUT_SECS,
)
from .coordinator import FanSyncCoordinator

_LOGGER = logging.getLogger(__name__)


class FanSyncRuntimeData(TypedDict):
    """Runtime data stored in ConfigEntry.runtime_data."""

    client: FanSyncClient
    coordinator: FanSyncCoordinator
    platforms: list[str]


# Modern type alias for config entry with runtime data
type FanSyncConfigEntry = ConfigEntry[FanSyncRuntimeData]


# Integration is config-entry only (no YAML config)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _get_client_device_ids(client: FanSyncClient) -> list[str]:
    """Extract device IDs from client, filtering out empty values.

    Returns list of non-empty device IDs from client.device_ids,
    falling back to single client.device_id if device_ids is empty.
    """
    ids = getattr(client, "device_ids", []) or [getattr(client, "device_id", None)]
    return [i for i in ids if i]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FanSyncConfigEntry) -> bool:
    # Build and store a shared client+coordinator for platforms to reuse
    http_timeout = entry.options.get(CONF_HTTP_TIMEOUT, entry.data.get(CONF_HTTP_TIMEOUT))
    ws_timeout = entry.options.get(CONF_WS_TIMEOUT, entry.data.get(CONF_WS_TIMEOUT))
    client = FanSyncClient(
        hass,
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_VERIFY_SSL, True),
        http_timeout_s=http_timeout,
        ws_timeout_s=ws_timeout,
    )
    setup_complete = False
    unsubscribe_options = None
    try:
        try:
            await client.async_connect()
        except httpx.HTTPStatusError as err:
            status = err.response.status_code if getattr(err, "response", None) else None
            if status in (401, 403):
                raise ConfigEntryAuthFailed(
                    "Authentication failed. Please re-enter your FanSync credentials."
                ) from err
            _LOGGER.warning("FanSync setup HTTP error (%s); retrying", status)
            raise ConfigEntryNotReady from err
        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            TimeoutError,
            OSError,
            RuntimeError,
        ) as err:
            _LOGGER.warning("FanSync setup connect failed (%s); retrying", type(err).__name__)
            raise ConfigEntryNotReady from err
        coordinator = FanSyncCoordinator(hass, client, entry)
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
        # Perform first refresh with a guard; proceed even if it times out
        try:
            # Use a first-refresh guard equal to the configured WS timeout
            try:
                _val = client.ws_timeout_seconds()
                if asyncio.iscoroutine(_val):
                    _val = await _val
                first_refresh_timeout = int(_val)
            except Exception:
                first_refresh_timeout = POLL_STATUS_TIMEOUT_SECS
            await asyncio.wait_for(
                coordinator.async_config_entry_first_refresh(), first_refresh_timeout
            )
        except Exception as exc:  # pragma: no cover
            # Log at INFO and let entities hydrate on next push/poll
            _LOGGER.info(
                "Initial refresh deferred (%s); entities will update via push or next poll",
                type(exc).__name__,
            )

        # Determine which platforms to load.
        # If no data yet (first refresh deferred or empty), fall back to all PLATFORMS
        # so that capability platforms (e.g., light) are available once data arrives.
        data_now = coordinator.data
        if not isinstance(data_now, dict) or not data_now:
            platforms = list(PLATFORMS)
        else:
            platforms = ["fan"]
            if any(
                isinstance(s, dict) and (KEY_LIGHT_POWER in s or KEY_LIGHT_BRIGHTNESS in s)
                for s in data_now.values()
            ):
                platforms.append("light")

        # Store runtime data in entry.runtime_data (modern pattern)
        entry.runtime_data = FanSyncRuntimeData(
            client=client,
            coordinator=coordinator,
            platforms=platforms,
        )

        async def _async_options_updated(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
            new_secs = updated_entry.options.get(
                OPTION_FALLBACK_POLL_SECS, DEFAULT_FALLBACK_POLL_SECS
            )
            old = coordinator.update_interval
            coordinator.update_interval = (
                None if new_secs == 0 else timedelta(seconds=int(new_secs))
            )
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("interval changed old=%s new=%s", old, coordinator.update_interval)

            # Apply timeout changes immediately when options are updated
            http_t = updated_entry.options.get(
                CONF_HTTP_TIMEOUT,
                updated_entry.data.get(CONF_HTTP_TIMEOUT, DEFAULT_HTTP_TIMEOUT_SECS),
            )
            ws_t = updated_entry.options.get(
                CONF_WS_TIMEOUT,
                updated_entry.data.get(CONF_WS_TIMEOUT, DEFAULT_WS_TIMEOUT_SECS),
            )
            try:
                await hass.async_add_executor_job(client.apply_timeouts, http_t, ws_t)
            except Exception as exc:  # pragma: no cover
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("apply_timeouts failed: %s", exc)

        unsubscribe_options = entry.add_update_listener(_async_options_updated)

        await hass.config_entries.async_forward_entry_setups(entry, platforms)

        # Update device registry now that entities (and their device entries) exist
        # This ensures device metadata (model, firmware, MAC) is visible in UI
        coordinator._update_device_registry(_get_client_device_ids(client))

        # Log connection success with device count at INFO, details at DEBUG
        ids = _get_client_device_ids(client)
        _LOGGER.info("FanSync connected: %d device(s)", len(ids))
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("connected device_ids=%s", ids)
        setup_complete = True
        return True
    finally:
        if not setup_complete:
            if unsubscribe_options is not None:
                try:
                    unsubscribe_options()
                except Exception as exc:
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug("options cleanup failed: %s", exc)
            if hasattr(entry, "runtime_data"):
                delattr(entry, "runtime_data")
            try:
                await client.async_disconnect()
            except Exception as exc:
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("setup cleanup failed: %s", exc)


async def async_unload_entry(hass: HomeAssistant, entry: FanSyncConfigEntry) -> bool:
    """Unload a config entry."""
    runtime_data: FanSyncRuntimeData = entry.runtime_data
    platforms = runtime_data["platforms"]
    unloaded = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unloaded:
        await runtime_data["client"].async_disconnect()
    return unloaded
