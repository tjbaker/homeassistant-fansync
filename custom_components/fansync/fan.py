# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import FanSyncClient
from .const import (
    DOMAIN,
    KEY_DIRECTION,
    KEY_POWER,
    KEY_PRESET,
    KEY_SPEED,
    PRESET_MODES,
    clamp_percentage,
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
    async_add_entities([FanSyncFan(coordinator, client)])

class FanSyncFan(CoordinatorEntity[FanSyncCoordinator], FanEntity):
    _attr_has_entity_name = False
    _attr_name = "fan"
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.DIRECTION
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.TURN_ON
    )
    _attr_preset_modes = list(PRESET_MODES.values())

    def __init__(self, coordinator: FanSyncCoordinator, client: FanSyncClient):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = client
        device_id = client.device_id or "unknown"
        self._attr_unique_id = f"{DOMAIN}_{device_id}_fan"

    @property
    def is_on(self) -> bool:
        status = self.coordinator.data or {}
        return status.get(KEY_POWER, 0) == 1

    @property
    def percentage(self) -> int | None:
        status = self.coordinator.data or {}
        return status.get(KEY_SPEED, 0)

    @property
    def current_direction(self) -> str:
        status = self.coordinator.data or {}
        return "forward" if status.get(KEY_DIRECTION, 0) == 0 else "reverse"

    @property
    def preset_mode(self) -> str | None:
        status = self.coordinator.data or {}
        return PRESET_MODES.get(status.get(KEY_PRESET, 0))

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ):
        data = {KEY_POWER: 1}
        if percentage is not None:
            data[KEY_SPEED] = clamp_percentage(percentage)
        if preset_mode is not None:
            inv = {v: k for k, v in PRESET_MODES.items()}
            data[KEY_PRESET] = inv.get(preset_mode, 0)
        await self.client.async_set(data)
        # Push latest status into coordinator
        status = await self.client.async_get_status()
        self.coordinator.async_set_updated_data(status)

    async def async_turn_off(self, **kwargs):
        await self.client.async_set({KEY_POWER: 0, KEY_SPEED: 1})
        status = await self.client.async_get_status()
        self.coordinator.async_set_updated_data(status)

    async def async_set_percentage(self, percentage: int) -> None:
        await self.client.async_set({KEY_POWER: 1, KEY_SPEED: clamp_percentage(percentage)})
        status = await self.client.async_get_status()
        self.coordinator.async_set_updated_data(status)

    async def async_set_direction(self, direction: str) -> None:
        await self.client.async_set(
            {
                KEY_POWER: 1,
                KEY_DIRECTION: 0 if direction == "forward" else 1,
            }
        )
        status = await self.client.async_get_status()
        self.coordinator.async_set_updated_data(status)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        inv = {v: k for k, v in PRESET_MODES.items()}
        await self.client.async_set({KEY_POWER: 1, KEY_PRESET: inv.get(preset_mode, 0)})
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
