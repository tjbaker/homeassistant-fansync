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

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import UpdateFailed

from .client import FanSyncClient
from .const import (
    CONFIRM_INITIAL_DELAY_SEC,  # noqa: F401  retained as a patch seam for tests
    DOMAIN,
    KEY_LIGHT_BRIGHTNESS,
    KEY_LIGHT_COLOR_TEMP,
    KEY_LIGHT_POWER,
    LIGHT_COLOR_TEMP_PRESETS_KELVIN,
    ha_brightness_to_pct,
    normalize_color_temp_kelvin,
    pct_to_ha_brightness,
    resolve_light_color_temp_presets,
    resolve_lightless_devices,
    snap_color_temp_kelvin,
)
from .coordinator import FanSyncCoordinator
from .device_utils import cloud_lightless_devices
from .entity import FanSyncOptimisticEntity

# Only overlay keys that directly affect HA UI state to prevent snap-back
OVERLAY_KEYS = {KEY_LIGHT_POWER, KEY_LIGHT_BRIGHTNESS, KEY_LIGHT_COLOR_TEMP}

# Coordinator handles all API calls; allow unlimited parallel entity updates (no semaphore)
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


def _get_profile_model(client: object, device_id: str) -> tuple[bool, object]:
    """Return whether the profile is ready and its model, if available."""
    get_profile = getattr(client, "device_profile", None)
    if not callable(get_profile):
        return False, None
    try:
        profile = get_profile(device_id)
    except Exception:
        return False, None
    if not isinstance(profile, dict):
        return False, None
    esh = profile.get("esh")
    if not isinstance(esh, dict):
        return False, None
    return True, esh.get("model")


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

    # Create a light entity per device that reports light capability and that the
    # user has not marked as lightless.
    if isinstance(data, dict):
        for did, status in data.items():
            if did in lightless:
                continue
            if isinstance(status, dict) and (
                KEY_LIGHT_POWER in status or KEY_LIGHT_BRIGHTNESS in status
            ):
                _, model = _get_profile_model(client, did)
                color_temp_presets = resolve_light_color_temp_presets(model, status)
                entities.append(
                    FanSyncLight(
                        coordinator,
                        client,
                        did,
                        supports_color_temp=color_temp_presets is not None,
                        color_temp_presets=color_temp_presets,
                    )
                )

    async_add_entities(entities)


class FanSyncLight(FanSyncOptimisticEntity, LightEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "light"

    OVERLAY_KEYS = OVERLAY_KEYS

    def __init__(
        self,
        coordinator: FanSyncCoordinator,
        client: FanSyncClient,
        device_id: str,
        supports_color_temp: bool = False,
        color_temp_presets: tuple[int, ...] | None = None,
    ):
        super().__init__(coordinator, client, device_id)
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_light"
        # Keep the old constructor keyword working for callers/tests while
        # allowing each device to carry its own model-specific preset list.
        if color_temp_presets is None and supports_color_temp:
            color_temp_presets = LIGHT_COLOR_TEMP_PRESETS_KELVIN
        self._color_temp_presets: tuple[int, ...] = ()
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
            self._attr_min_color_temp_kelvin = None
            self._attr_max_color_temp_kelvin = None
        return changed

    def _refresh_color_temp_profile(self) -> bool:
        """Refresh model-specific CCT support after a late profile update."""
        profile_ready, model = _get_profile_model(self.client, self._device_id)
        if not profile_ready:
            return False
        status = self._status_for(self.coordinator.data or {})
        presets = resolve_light_color_temp_presets(model, status)
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
        return self._get_with_overlay(KEY_LIGHT_COLOR_TEMP, min(self._color_temp_presets))

    async def async_turn_on(
        self, brightness: int | None = None, color_temp_kelvin: int | None = None, **kwargs
    ) -> None:
        optimistic = {KEY_LIGHT_POWER: 1}
        payload = {KEY_LIGHT_POWER: 1}
        if brightness is not None:
            pct = ha_brightness_to_pct(brightness)
            optimistic[KEY_LIGHT_BRIGHTNESS] = pct
            payload[KEY_LIGHT_BRIGHTNESS] = pct
        else:
            pct = None

        kelvin = None
        if color_temp_kelvin is not None and self._supports_color_temp:
            kelvin = snap_color_temp_kelvin(color_temp_kelvin, self._color_temp_presets)
            optimistic[KEY_LIGHT_COLOR_TEMP] = kelvin
            payload[KEY_LIGHT_COLOR_TEMP] = kelvin

        def _confirm(s: dict[str, object], pb: int | None = pct, pk: int | None = kelvin) -> bool:
            return (
                s.get(KEY_LIGHT_POWER) == 1
                and (pb is None or s.get(KEY_LIGHT_BRIGHTNESS) == pb)
                and (pk is None or normalize_color_temp_kelvin(s.get(KEY_LIGHT_COLOR_TEMP)) == pk)
            )

        await self._apply_with_optimism(optimistic, payload, _confirm)

    async def async_turn_off(self, **kwargs) -> None:
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
                "state update d=%s power=%s brightness=%s",
                self._device_id,
                status.get(KEY_LIGHT_POWER),
                status.get(KEY_LIGHT_BRIGHTNESS),
            )

    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()
        if self._refresh_color_temp_profile():
            self.async_write_ha_state()

    @property
    def icon(self) -> str | None:
        return "mdi:ceiling-light"
