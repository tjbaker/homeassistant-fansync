# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import FanSyncClient
from .const import (
    DOMAIN,
    KEY_LIGHT_BRIGHTNESS,
    KEY_LIGHT_POWER,
    ha_brightness_to_pct,
    pct_to_ha_brightness,
)
from .coordinator import FanSyncCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    shared = hass.data[DOMAIN][entry.entry_id]
    coordinator: FanSyncCoordinator = shared["coordinator"]
    client: FanSyncClient = shared["client"]
    # Only add a light entity if the device reports light capabilities
    status = coordinator.data
    if not status:
        status = await client.async_get_status()
        coordinator.async_set_updated_data(status)
    if not isinstance(status, dict):
        return
    if KEY_LIGHT_POWER in status or KEY_LIGHT_BRIGHTNESS in status:
        async_add_entities([FanSyncLight(coordinator, client)])

class FanSyncLight(CoordinatorEntity[FanSyncCoordinator], LightEntity):
    _attr_has_entity_name = False
    _attr_name = "light"
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator: FanSyncCoordinator, client: FanSyncClient):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = client
        device_id = client.device_id or "unknown"
        self._attr_unique_id = f"{DOMAIN}_{device_id}_light"

    @property
    def is_on(self) -> bool:
        status = self.coordinator.data or {}
        return status.get(KEY_LIGHT_POWER, 0) == 1

    @property
    def brightness(self) -> int | None:
        status = self.coordinator.data or {}
        val = status.get(KEY_LIGHT_BRIGHTNESS, 0)
        return pct_to_ha_brightness(val)

    async def async_turn_on(self, brightness: int | None = None, **kwargs):
        data = {KEY_LIGHT_POWER: 1}
        if brightness is not None:
            pct = ha_brightness_to_pct(brightness)
            data[KEY_LIGHT_BRIGHTNESS] = pct
        await self.client.async_set(data)
        status = await self.client.async_get_status()
        self.coordinator.async_set_updated_data(status)

    async def async_turn_off(self, **kwargs):
        await self.client.async_set({KEY_LIGHT_POWER: 0})
        status = await self.client.async_get_status()
        self.coordinator.async_set_updated_data(status)

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self) -> DeviceInfo:
        device_id = self.client.device_id or "unknown"
        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="Fanimation",
            model="FanSync",
            name="FanSync",
        )
