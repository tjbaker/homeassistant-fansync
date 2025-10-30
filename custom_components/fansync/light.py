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
    CONFIRM_RETRY_ATTEMPTS,
    CONFIRM_RETRY_DELAY_SEC,
    DOMAIN,
    KEY_LIGHT_BRIGHTNESS,
    KEY_LIGHT_POWER,
    OPTIMISTIC_GUARD_SEC,
    ha_brightness_to_pct,
    pct_to_ha_brightness,
)
from .coordinator import FanSyncCoordinator
from .device_utils import create_device_info, module_attrs

# Only overlay keys that directly affect HA UI state to prevent snap-back
OVERLAY_KEYS = {KEY_LIGHT_POWER, KEY_LIGHT_BRIGHTNESS}

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    shared = hass.data[DOMAIN][entry.entry_id]
    coordinator: FanSyncCoordinator = shared["coordinator"]
    client: FanSyncClient = shared["client"]
    entities: list[FanSyncLight] = []
    # Ensure coordinator has aggregated data
    data = coordinator.data
    if not data:
        await coordinator.async_request_refresh()
        data = coordinator.data or {}
    # Create a light per device if it reports light keys
    if isinstance(data, dict):
        for did, status in data.items():
            if KEY_LIGHT_POWER in status or KEY_LIGHT_BRIGHTNESS in status:
                entities.append(FanSyncLight(coordinator, client, did))
    async_add_entities(entities)


class FanSyncLight(CoordinatorEntity[FanSyncCoordinator], LightEntity):
    _attr_has_entity_name = False
    _attr_name = "light"
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator: FanSyncCoordinator, client: FanSyncClient, device_id: str):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = client
        self._device_id = device_id or "unknown"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_light"
        self._retry_attempts = CONFIRM_RETRY_ATTEMPTS
        self._retry_delay = CONFIRM_RETRY_DELAY_SEC
        self._optimistic_until: float | None = None
        self._optimistic_predicate: Callable[[dict], bool] | None = None
        # Per-key optimistic overlay
        self._overlay: dict[str, tuple[int, float]] = {}

    def _status_for(self, payload: dict) -> dict[str, object]:
        """Return this device's status mapping from an aggregated payload."""
        if isinstance(payload, dict):
            inner = payload.get(self._device_id, payload)
            if isinstance(inner, dict):
                return inner
        return {}

    def _get_with_overlay(self, key: str, default: int) -> int:
        now = time.monotonic()
        entry = self._overlay.get(key)
        if entry is not None:
            value, expires = entry
            if now <= expires:
                return value
            # Overlay expired without confirmation
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "overlay expired d=%s key=%s value=%s",
                    self._device_id,
                    key,
                    value,
                )
            self._overlay.pop(key, None)
        status = self._status_for(self.coordinator.data or {})
        raw = status.get(key, default)
        if isinstance(raw, int | str):
            try:
                return int(raw)
            except (ValueError, TypeError):
                pass
        return int(default)

    async def _retry_update_until(self, predicate: Callable[[dict], bool]) -> tuple[dict, bool]:
        """Fetch status until predicate passes or attempts exhausted."""
        status: dict = {}
        for _ in range(self._retry_attempts):
            try:
                status = await self.client.async_get_status(self._device_id)
            except TypeError:
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
        all_previous = self.coordinator.data or {}
        prev_for_device = (
            all_previous.get(self._device_id, {}) if isinstance(all_previous, dict) else {}
        )
        optimistic_state_for_device = {**prev_for_device, **optimistic}
        optimistic_all = dict(all_previous) if isinstance(all_previous, dict) else {}
        optimistic_all[self._device_id] = optimistic_state_for_device
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "optimism start d=%s optimistic=%s expires_in=%.2fs",
                self._device_id,
                optimistic,
                OPTIMISTIC_GUARD_SEC,
            )
        expires = time.monotonic() + OPTIMISTIC_GUARD_SEC
        for k, v in optimistic.items():
            if k in OVERLAY_KEYS:
                self._overlay[k] = (int(v), expires)
        self.coordinator.async_set_updated_data(optimistic_all)
        self._optimistic_until = expires
        self._optimistic_predicate = confirm_pred
        try:
            try:
                await self.client.async_set(payload, device_id=self._device_id)
            except TypeError:
                await self.client.async_set(payload)
        except RuntimeError as exc:
            self._optimistic_until = None
            self._optimistic_predicate = None
            for k in optimistic.keys():
                self._overlay.pop(k, None)
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "optimism revert d=%s keys=%s error=%s",
                    self._device_id,
                    list(optimistic.keys()),
                    type(exc).__name__,
                )
            self.coordinator.async_set_updated_data(all_previous)
            raise
        status, ok = await self._retry_update_until(confirm_pred)
        if ok:
            new_all = dict(self.coordinator.data or {})
            new_all[self._device_id] = status
            self.coordinator.async_set_updated_data(new_all)
            self._optimistic_until = None
            self._optimistic_predicate = None
            for k in optimistic.keys():
                self._overlay.pop(k, None)
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "optimism confirm d=%s keys=%s",
                    self._device_id,
                    list(optimistic.keys()),
                )

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

        def _confirm(s: dict, pb: int | None = pct) -> bool:
            my = self._status_for(s)
            return my.get(KEY_LIGHT_POWER) == 1 and (
                pb is None or my.get(KEY_LIGHT_BRIGHTNESS) == pb
            )

        await self._apply_with_optimism(optimistic, payload, _confirm)

    async def async_turn_off(self, **kwargs):
        optimistic = {KEY_LIGHT_POWER: 0}
        payload = {KEY_LIGHT_POWER: 0}
        await self._apply_with_optimism(
            optimistic,
            payload,
            lambda s: self._status_for(s).get(KEY_LIGHT_POWER) == 0,
        )

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        if self._optimistic_until is not None and time.monotonic() < self._optimistic_until:
            pred = self._optimistic_predicate
            data = self.coordinator.data or {}
            if callable(pred) and not pred(data):
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    remaining = (
                        self._optimistic_until - time.monotonic() if self._optimistic_until else 0.0
                    )
                    _LOGGER.debug(
                        "guard ignore d=%s overlays=%d remaining=%.2fs",
                        self._device_id,
                        len(self._overlay),
                        max(0.0, remaining),
                    )
                return
            self._optimistic_until = None
            self._optimistic_predicate = None

        # Log state transitions
        if _LOGGER.isEnabledFor(logging.DEBUG):
            status = self._status_for(self.coordinator.data or {})
            if isinstance(status, dict):
                _LOGGER.debug(
                    "state update d=%s power=%s brightness=%s",
                    self._device_id,
                    status.get(KEY_LIGHT_POWER),
                    status.get(KEY_LIGHT_BRIGHTNESS),
                )

        super()._handle_coordinator_update()

    @property
    def device_info(self) -> DeviceInfo:
        return create_device_info(self.client, self._device_id)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        return module_attrs(self.client, self._device_id)

    @property
    def icon(self) -> str | None:
        return "mdi:ceiling-light"
