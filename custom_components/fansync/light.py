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
import time  # noqa: F401  retained as a module-level patch seam for tests
from typing import Any

from homeassistant.components.light import (
    DEFAULT_MAX_KELVIN,
    DEFAULT_MIN_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import UpdateFailed

from .client import FanSyncClient
from .const import (
    CONFIRM_INITIAL_DELAY_SEC,  # noqa: F401  retained as a patch seam for tests
    DOMAIN,
    KEY_LIGHT_BRIGHTNESS,
    KEY_LIGHT_COLOR_TEMP,
    KEY_LIGHT_POWER,
    ha_brightness_to_pct,
    lightless_signal,
    pct_to_ha_brightness,
    resolve_light_color_temp_presets,
    resolve_lightless_devices,
    snap_color_temp_kelvin,
)
from .coordinator import FanSyncCoordinator
from .device_utils import cloud_lightless_devices, profile_model
from .entity import FanSyncOptimisticEntity

# Only overlay keys that directly affect HA UI state to prevent snap-back
OVERLAY_KEYS = {KEY_LIGHT_POWER, KEY_LIGHT_BRIGHTNESS, KEY_LIGHT_COLOR_TEMP}

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
    entities: list[FanSyncLight] = []

    # Wait briefly for coordinator data if not already present; this handles race conditions
    # when light platform setup runs before first coordinator refresh completes.
    data = coordinator.data
    if not isinstance(data, dict) or not data:
        try:
            # Use a short timeout to avoid blocking setup indefinitely
            await asyncio.wait_for(coordinator.async_request_refresh(), timeout=5.0)
            data = coordinator.data or {}
        except TimeoutError, UpdateFailed:
            # If refresh times out or fails, fall back to empty dict
            data = {}

    # Devices with no physical light: the user's per-device option plus devices
    # the cloud marks lightless (properties.hideLightDimmer, see issue #199).
    all_ids = getattr(client, "device_ids", []) or (list(data) if isinstance(data, dict) else [])
    lightless = resolve_lightless_devices(entry.options, all_ids) | cloud_lightless_devices(
        client, all_ids
    )

    def _has_light_channel(status: object) -> bool:
        return isinstance(status, dict) and (
            KEY_LIGHT_POWER in status or KEY_LIGHT_BRIGHTNESS in status
        )

    def _make(did: str, status: dict[str, object]) -> FanSyncLight:
        model = profile_model(client, did)
        presets = resolve_light_color_temp_presets(model, status)
        return FanSyncLight(coordinator, client, did, color_temp_presets=presets)

    # Create a light entity per device that reports light capability and that the
    # user has not marked as lightless.
    active: dict[str, FanSyncLight] = {}
    if isinstance(data, dict):
        for did, status in data.items():
            if did not in lightless and _has_light_channel(status):
                active[did] = _make(did, status)
                entities.append(active[did])

    async_add_entities(entities)

    async def _on_lightless_changed(new_lightless: set[str]) -> None:
        """Add or remove Light entities in place when the lightless set changes."""
        ent_reg = er.async_get(hass)
        for did in list(active):
            if did not in new_lightless:
                continue
            entity = active.pop(did)
            if entity.entity_id and ent_reg.async_get(entity.entity_id):
                # Removing the registry entry makes the platform remove the entity.
                ent_reg.async_remove(entity.entity_id)
            else:
                await entity.async_remove()
        current = coordinator.data or {}
        added: list[FanSyncLight] = []
        if isinstance(current, dict):
            for did, status in current.items():
                if did in new_lightless or did in active or not _has_light_channel(status):
                    continue
                active[did] = _make(did, status)
                added.append(active[did])
        if added:
            async_add_entities(added)

    entry.async_on_unload(
        async_dispatcher_connect(hass, lightless_signal(entry.entry_id), _on_lightless_changed)
    )


class FanSyncLight(FanSyncOptimisticEntity, LightEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "light"

    OVERLAY_KEYS = OVERLAY_KEYS

    def __init__(
        self,
        coordinator: FanSyncCoordinator,
        client: FanSyncClient,
        device_id: str,
        color_temp_presets: tuple[int, ...] | None = None,
    ):
        super().__init__(coordinator, client, device_id)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_light"
        # Each device carries its own model-specific preset list; None or empty
        # means the light is brightness-only.
        self._color_temp_presets: tuple[int, ...] = ()
        # Last H04 value that was within the resolved preset range. Reported
        # instead of a transient off-preset reading so state never advertises a
        # Kelvin value outside the entity's own min/max bounds.
        self._last_valid_color_temp: int | None = None
        self._set_color_temp_presets(color_temp_presets)

    def _set_color_temp_presets(self, color_temp_presets: tuple[int, ...] | None) -> bool:
        """Apply a device's CCT profile and return whether it changed."""
        presets = tuple(color_temp_presets or ())
        changed = presets != self._color_temp_presets
        self._color_temp_presets = presets
        self._supports_color_temp = bool(presets)
        if self._supports_color_temp:
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_min_color_temp_kelvin = min(self._color_temp_presets)
            self._attr_max_color_temp_kelvin = max(self._color_temp_presets)
        else:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_min_color_temp_kelvin = DEFAULT_MIN_KELVIN
            self._attr_max_color_temp_kelvin = DEFAULT_MAX_KELVIN
        return changed

    def _refresh_color_temp_profile(self) -> bool:
        """Re-evaluate CCT support after a late profile or status update.

        Uses the same rule as entity setup. Support is only ever upgraded: once
        a preset profile has been resolved, a transient off-preset H04 reading
        must not strip the capability (which would flap the entity registry).
        """
        model = profile_model(self.client, self._device_id)
        status = self._status_for(self.coordinator.data or {})
        presets = resolve_light_color_temp_presets(model, status)
        if presets is None:
            return False
        return self._set_color_temp_presets(presets)

    @property
    def is_on(self) -> bool:
        return self._get_with_overlay(KEY_LIGHT_POWER, 0) == 1

    @property
    def brightness(self) -> int | None:
        val = self._get_with_overlay(KEY_LIGHT_BRIGHTNESS, 0)
        return pct_to_ha_brightness(val)

    @property
    def color_temp_kelvin(self) -> int | None:
        if not self._supports_color_temp:
            return None
        lo, hi = min(self._color_temp_presets), max(self._color_temp_presets)
        value = self._get_with_overlay(KEY_LIGHT_COLOR_TEMP, lo)
        if lo <= value <= hi:
            self._last_valid_color_temp = value
            return value
        if self._last_valid_color_temp is not None:
            return self._last_valid_color_temp
        return lo

    async def async_turn_on(
        self,
        brightness: int | None = None,
        color_temp_kelvin: int | None = None,
        **kwargs: Any,
    ) -> None:
        optimistic = {KEY_LIGHT_POWER: 1}
        payload = {KEY_LIGHT_POWER: 1}
        if brightness is not None:
            pct = ha_brightness_to_pct(brightness)
            optimistic[KEY_LIGHT_BRIGHTNESS] = pct
            payload[KEY_LIGHT_BRIGHTNESS] = pct
        if color_temp_kelvin is not None and self._supports_color_temp:
            kelvin = snap_color_temp_kelvin(color_temp_kelvin, self._color_temp_presets)
            optimistic[KEY_LIGHT_COLOR_TEMP] = kelvin
            payload[KEY_LIGHT_COLOR_TEMP] = kelvin

        previous = self._previous_values(payload)

        def _confirm(s: dict[str, object]) -> bool:
            return self._write_applied(s, payload, previous)

        await self._apply_with_optimism(optimistic, payload, _confirm)

    async def async_turn_off(self, **kwargs: Any) -> None:
        optimistic = {KEY_LIGHT_POWER: 0}
        payload = {KEY_LIGHT_POWER: 0}
        await self._apply_with_optimism(
            optimistic,
            payload,
            lambda s: s.get(KEY_LIGHT_POWER) == 0,
        )

    def _log_state(self, status: dict[str, object]) -> None:
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "state update d=%s power=%s brightness=%s color_temp=%s",
                self._device_id,
                status.get(KEY_LIGHT_POWER),
                status.get(KEY_LIGHT_BRIGHTNESS),
                status.get(KEY_LIGHT_COLOR_TEMP),
            )

    def _handle_coordinator_update(self) -> None:
        # Resolve capabilities before the base class writes state, so a profile
        # change never publishes a stale intermediate state.
        self._refresh_color_temp_profile()
        super()._handle_coordinator_update()

    @property
    def icon(self) -> str | None:
        return "mdi:ceiling-light"
