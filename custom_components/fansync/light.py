# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

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
        self._retry_attempts = 5
        self._retry_delay = 0.1
        self._optimistic_until: float | None = None
        self._optimistic_predicate: Callable[[dict], bool] | None = None
        # Per-key optimistic overlay
        self._overlay: dict[str, tuple[int, float]] = {}

    def _get_with_overlay(self, key: str, default: int) -> int:
        now = time.monotonic()
        entry = self._overlay.get(key)
        if entry is not None:
            value, expires = entry
            if now <= expires:
                return value
            self._overlay.pop(key, None)
        status = self.coordinator.data or {}
        return int(status.get(key, default))

    async def _retry_update_until(self, predicate: Callable[[dict], bool]) -> tuple[dict, bool]:
        """Fetch status until predicate passes or attempts exhausted."""
        status: dict = {}
        for _ in range(self._retry_attempts):
            status = await self.client.async_get_status()
            if predicate(status):
                return status, True
            await asyncio.sleep(self._retry_delay)
        return status, False

    async def _apply_with_optimism(
        self,
        optimistic: dict,
        payload: dict,
        confirm_pred: Callable[[dict], bool],
    ) -> None:
        previous = self.coordinator.data or {}
        optimistic_state = {**previous, **optimistic}
        expires = time.monotonic() + 8.0
        for k, v in optimistic.items():
            self._overlay[k] = (int(v), expires)
        self.coordinator.async_set_updated_data(optimistic_state)
        self._optimistic_until = expires
        self._optimistic_predicate = confirm_pred
        try:
            await self.client.async_set(payload)
        except Exception:
            self._optimistic_until = None
            self._optimistic_predicate = None
            for k in optimistic.keys():
                self._overlay.pop(k, None)
            self.coordinator.async_set_updated_data(previous)
            raise
        status, ok = await self._retry_update_until(confirm_pred)
        if ok:
            self.coordinator.async_set_updated_data(status)
            self._optimistic_until = None
            self._optimistic_predicate = None
            for k in optimistic.keys():
                self._overlay.pop(k, None)

    @property
    def is_on(self) -> bool:
        return self._get_with_overlay(KEY_LIGHT_POWER, 0) == 1

    @property
    def brightness(self) -> int | None:
        val = self._get_with_overlay(KEY_LIGHT_BRIGHTNESS, 0)
        return pct_to_ha_brightness(val)

    async def async_turn_on(self, brightness: int | None = None, **kwargs):
        optimistic = {KEY_LIGHT_POWER: 1}
        payload = {KEY_LIGHT_POWER: 1}
        if brightness is not None:
            pct = ha_brightness_to_pct(brightness)
            optimistic[KEY_LIGHT_BRIGHTNESS] = pct
            payload[KEY_LIGHT_BRIGHTNESS] = pct
        else:
            pct = None
        check_brightness = pct is not None
        await self._apply_with_optimism(
            optimistic,
            payload,
            lambda s: s.get(KEY_LIGHT_POWER) == 1
            and (not check_brightness or s.get(KEY_LIGHT_BRIGHTNESS) == pct),
        )

    async def async_turn_off(self, **kwargs):
        optimistic = {KEY_LIGHT_POWER: 0}
        payload = {KEY_LIGHT_POWER: 0}
        await self._apply_with_optimism(
            optimistic,
            payload,
            lambda s: s.get(KEY_LIGHT_POWER) == 0,
        )

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        if self._optimistic_until is not None and time.monotonic() < self._optimistic_until:
            pred = self._optimistic_predicate
            data = self.coordinator.data or {}
            if callable(pred) and not pred(data):
                return
            self._optimistic_until = None
            self._optimistic_predicate = None
        super()._handle_coordinator_update()

    @property
    def device_info(self) -> DeviceInfo:
        device_id = self.client.device_id or "unknown"
        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="Fanimation",
            model="FanSync",
            name="FanSync",
        )
