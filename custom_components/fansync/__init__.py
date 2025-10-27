# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .client import FanSyncClient
from .const import CONF_EMAIL, CONF_PASSWORD, CONF_VERIFY_SSL, DOMAIN, PLATFORMS
from .coordinator import FanSyncCoordinator


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

    # Register a push callback if supported by the client
    if hasattr(client, "set_status_callback"):

        def _on_status(status: dict[str, object]) -> None:
            # Merge pushed status for this device into the coordinator's mapping
            did = getattr(client, "device_id", None) or "unknown"
            current = coordinator.data or {}
            merged: dict[str, dict[str, object]] = dict(current)
            merged[did] = status
            coordinator.async_set_updated_data(merged)

        client.set_status_callback(_on_status)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if data and data.get("client"):
            await data["client"].async_disconnect()
    return unloaded
