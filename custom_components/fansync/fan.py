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
from .device_utils import cloud_no_direction_devices
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
    # Devices the cloud marks as not reversible (properties.hideFanDirection,
    # see issue #228) do not get a direction control.
    no_direction = cloud_no_direction_devices(client, device_ids)
    entities: list[FanSyncFan] = []
    for did in device_ids:
        if not did:
            continue
        entities.append(
            FanSyncFan(coordinator, client, did, supports_direction=did not in no_direction)
        )
    async_add_entities(entities)


BASE_FEATURES = (
    FanEntityFeature.SET_SPEED
    | FanEntityFeature.PRESET_MODE
    | FanEntityFeature.TURN_OFF
    | FanEntityFeature.TURN_ON
)


class FanSyncFan(FanSyncOptimisticEntity, FanEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "fan"
    _attr_supported_features = BASE_FEATURES | FanEntityFeature.DIRECTION
    _attr_preset_modes = list(PRESET_MODES.values())

    OVERLAY_KEYS = OVERLAY_KEYS

    def __init__(
        self,
        coordinator: FanSyncCoordinator,
        client: FanSyncClient,
        device_id: str,
        supports_direction: bool = True,
    ):
        super().__init__(coordinator, client, device_id)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_fan"
        self._supports_direction = supports_direction
        if not supports_direction:
            self._attr_supported_features = BASE_FEATURES

    @property
    def is_on(self) -> bool:
        return self._get_with_overlay(KEY_POWER, 0) == 1

    @property
    def percentage(self) -> int | None:
        return self._get_with_overlay(KEY_SPEED, 0)

    @property
    def current_direction(self) -> str | None:
        if not self._supports_direction:
            return None
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
        payload: dict[str, int] = {}
        if percentage is not None:
            target_speed = clamp_percentage(percentage)
            optimistic[KEY_SPEED] = target_speed
            payload[KEY_SPEED] = target_speed
        if preset_mode is not None:
            inv = {v: k for k, v in PRESET_MODES.items()}
            target_preset = inv.get(preset_mode, 0)
            optimistic[KEY_PRESET] = target_preset
            if self._needs_write(KEY_PRESET, target_preset):
                payload[KEY_PRESET] = target_preset
        # Power always goes when nothing else does (a bare turn_on), otherwise
        # only when the fan is not already on. See _needs_write.
        if not payload or self._needs_write(KEY_POWER, 1):
            payload[KEY_POWER] = 1
        self._with_current_speed(payload)
        previous = self._previous_values(payload)

        def _confirm(s: dict[str, object]) -> bool:
            return self._write_applied(s, payload, previous)

        await self._apply_with_optimism(optimistic, payload, _confirm)

    def _with_current_speed(self, payload: dict[str, int]) -> dict[str, int]:
        """Carry the current speed on writes that turn the fan on or keep it on.

        Probed live on a Kute60-FD6R1L5 (fw 3.2.9): the fan only reports its
        state back to the cloud after a write that contains the speed register.
        Power on alone, or power plus preset, is applied silently, so the cloud,
        the official app and HA all keep the old state. {"H00": 1, "H02":
        <current>} applies and reports.

        Never used for power off. On a SpitfireV2-FD6R2L5 (fw 3.6.7) a speed
        write turns the fan on, so {"H00": 0, "H02": <current>} switched it off
        and straight back on (issue #249). Off is always written alone; the
        Kute60 applies that too, it just does not report it.
        """
        if KEY_SPEED in payload or payload.get(KEY_POWER) == 0:
            return payload
        speed = self._device_value(KEY_SPEED)
        if speed is None:
            speed = self._get_with_overlay(KEY_SPEED, 0)
        if speed > 0:
            payload[KEY_SPEED] = int(speed)
        return payload

    async def async_turn_off(self, **kwargs) -> None:
        # Power alone, never with a speed: on some fans a speed write turns the
        # fan on and would undo the off in the same message (issue #249).
        optimistic = {KEY_POWER: 0}
        payload = {KEY_POWER: 0}
        previous = self._previous_values(payload)
        await self._apply_with_optimism(
            optimistic,
            payload,
            lambda s: self._write_applied(s, payload, previous),
        )

    async def async_set_percentage(self, percentage: int) -> None:
        target = clamp_percentage(percentage)
        # Adjusting percentage exits fresh-air (breeze) mode -> set preset to normal (0)
        optimistic = {KEY_POWER: 1, KEY_SPEED: target, KEY_PRESET: 0}
        payload = {KEY_SPEED: target}
        if self._needs_write(KEY_POWER, 1):
            payload[KEY_POWER] = 1
        if self._needs_write(KEY_PRESET, 0):
            payload[KEY_PRESET] = 0
        previous = self._previous_values(payload)
        await self._apply_with_optimism(
            optimistic,
            payload,
            lambda s: self._write_applied(s, payload, previous),
        )

    async def async_set_direction(self, direction: str) -> None:
        target_dir = 0 if direction == "forward" else 1
        optimistic = {KEY_POWER: 1, KEY_DIRECTION: target_dir}
        payload = {KEY_DIRECTION: target_dir}
        if self._needs_write(KEY_POWER, 1):
            payload[KEY_POWER] = 1
        self._with_current_speed(payload)
        await self._apply_with_optimism(
            optimistic,
            payload,
            lambda s: s.get(KEY_DIRECTION) == target_dir,
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        inv = {v: k for k, v in PRESET_MODES.items()}
        target_preset = inv.get(preset_mode, 0)
        optimistic = {KEY_POWER: 1, KEY_PRESET: target_preset}
        payload = {KEY_PRESET: target_preset}
        if self._needs_write(KEY_POWER, 1):
            payload[KEY_POWER] = 1
        self._with_current_speed(payload)
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
