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

import asyncio  # noqa: F401  retained as a module-level patch seam for tests
import logging
import time  # noqa: F401  retained as a module-level patch seam for tests

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import FanSyncClient
from .const import (
    CONFIRM_INITIAL_DELAY_SEC,  # noqa: F401  retained as a patch seam for tests
    DOMAIN,
    KEY_DIRECTION,
    KEY_POWER,
    KEY_PRESET,
    KEY_SPEED,
    PRESET_MODES,
    clamp_percentage,
)
from .coordinator import FanSyncCoordinator
from .entity import FanSyncOptimisticEntity

# Only overlay keys that directly affect HA UI state to prevent snap-back
OVERLAY_KEYS = {KEY_POWER, KEY_SPEED, KEY_DIRECTION, KEY_PRESET}

# Coordinator handles all API calls; allow unlimited parallel entity updates (no semaphore)
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    runtime_data = entry.runtime_data
    coordinator: FanSyncCoordinator = runtime_data["coordinator"]
    client: FanSyncClient = runtime_data["client"]
    # Create one Fan entity per device ID
    device_ids = getattr(client, "device_ids", []) or [client.device_id]
    entities: list[FanSyncFan] = []
    for did in device_ids:
        if not did:
            continue
        entities.append(FanSyncFan(coordinator, client, did))
    async_add_entities(entities)


class FanSyncFan(FanSyncOptimisticEntity, FanEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "fan"
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.DIRECTION
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.TURN_ON
    )
    _attr_preset_modes = list(PRESET_MODES.values())

    OVERLAY_KEYS = OVERLAY_KEYS

    def __init__(self, coordinator: FanSyncCoordinator, client: FanSyncClient, device_id: str):
        super().__init__(coordinator, client, device_id)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_fan"

    @property
    def is_on(self) -> bool:
        return self._get_with_overlay(KEY_POWER, 0) == 1

    @property
    def percentage(self) -> int | None:
        return self._get_with_overlay(KEY_SPEED, 0)

    @property
    def current_direction(self) -> str:
        dir_val = self._get_with_overlay(KEY_DIRECTION, 0)
        return "forward" if dir_val == 0 else "reverse"

    @property
    def preset_mode(self) -> str | None:
        preset_val = self._get_with_overlay(KEY_PRESET, 0)
        return PRESET_MODES.get(preset_val)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ) -> None:
        optimistic = {KEY_POWER: 1}
        payload = {KEY_POWER: 1}
        if percentage is not None:
            target_speed = clamp_percentage(percentage)
            optimistic[KEY_SPEED] = target_speed
            payload[KEY_SPEED] = target_speed
        else:
            target_speed = None
        if preset_mode is not None:
            inv = {v: k for k, v in PRESET_MODES.items()}
            target_preset = inv.get(preset_mode, 0)
            optimistic[KEY_PRESET] = target_preset
            payload[KEY_PRESET] = target_preset
        else:
            target_preset = None

        def _confirm(
            s: dict[str, object],
            ts: int | None = target_speed,
            tp: int | None = target_preset,
        ) -> bool:
            return (
                s.get(KEY_POWER) == 1
                and (ts is None or s.get(KEY_SPEED) == ts)
                and (tp is None or s.get(KEY_PRESET) == tp)
            )

        await self._apply_with_optimism(optimistic, payload, _confirm)

    async def async_turn_off(self, **kwargs) -> None:
        # Toggling power should not change percentage speed
        optimistic = {KEY_POWER: 0}
        payload = {KEY_POWER: 0}
        await self._apply_with_optimism(optimistic, payload, lambda s: s.get(KEY_POWER) == 0)

    async def async_set_percentage(self, percentage: int) -> None:
        target = clamp_percentage(percentage)
        # Adjusting percentage exits fresh-air (breeze) mode -> set preset to normal (0)
        optimistic = {KEY_POWER: 1, KEY_SPEED: target, KEY_PRESET: 0}
        payload = {KEY_POWER: 1, KEY_SPEED: target, KEY_PRESET: 0}
        await self._apply_with_optimism(
            optimistic,
            payload,
            lambda s: s.get(KEY_SPEED) == target and s.get(KEY_PRESET) == 0,
        )

    async def async_set_direction(self, direction: str) -> None:
        target_dir = 0 if direction == "forward" else 1
        optimistic = {KEY_POWER: 1, KEY_DIRECTION: target_dir}
        payload = {KEY_POWER: 1, KEY_DIRECTION: target_dir}
        await self._apply_with_optimism(
            optimistic,
            payload,
            lambda s: s.get(KEY_DIRECTION) == target_dir,
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        inv = {v: k for k, v in PRESET_MODES.items()}
        target_preset = inv.get(preset_mode, 0)
        optimistic = {KEY_POWER: 1, KEY_PRESET: target_preset}
        payload = {KEY_POWER: 1, KEY_PRESET: target_preset}
        await self._apply_with_optimism(
            optimistic,
            payload,
            lambda s: s.get(KEY_PRESET) == target_preset,
        )

    def _log_state(self, status: dict[str, object]) -> None:
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "state update d=%s power=%s speed=%s dir=%s preset=%s",
                self._device_id,
                status.get(KEY_POWER),
                status.get(KEY_SPEED),
                status.get(KEY_DIRECTION),
                status.get(KEY_PRESET),
            )

    @property
    def icon(self) -> str | None:
        return "mdi:ceiling-fan"
