# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from homeassistant.components.fan import FanEntity, FanEntityFeature
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
    KEY_DIRECTION,
    KEY_POWER,
    KEY_PRESET,
    KEY_SPEED,
    OPTIMISTIC_GUARD_SEC,
    PRESET_MODES,
    clamp_percentage,
)
from .coordinator import FanSyncCoordinator

# Only overlay keys that directly affect HA UI state to prevent snap-back
OVERLAY_KEYS = {KEY_POWER, KEY_SPEED, KEY_DIRECTION, KEY_PRESET}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    shared = hass.data[DOMAIN][entry.entry_id]
    coordinator: FanSyncCoordinator = shared["coordinator"]
    client: FanSyncClient = shared["client"]
    # Create one Fan entity per device ID
    device_ids = getattr(client, "device_ids", []) or [client.device_id]
    entities: list[FanSyncFan] = []
    for did in device_ids:
        if not did:
            continue
        entities.append(FanSyncFan(coordinator, client, did))
    async_add_entities(entities)


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

    def __init__(self, coordinator: FanSyncCoordinator, client: FanSyncClient, device_id: str):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = client
        self._device_id = device_id or "unknown"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_fan"
        self._retry_attempts = CONFIRM_RETRY_ATTEMPTS
        self._retry_delay = CONFIRM_RETRY_DELAY_SEC
        self._optimistic_until: float | None = None
        self._optimistic_predicate: Callable[[dict], bool] | None = None
        # Per-key optimistic overlay to avoid snap-back during short races
        # key -> (value, expires_at_monotonic)
        self._overlay: dict[str, tuple[int, float]] = {}

    def _get_with_overlay(self, key: str, default: int) -> int:
        now = time.monotonic()
        entry = self._overlay.get(key)
        if entry is not None:
            value, expires = entry
            if now <= expires:
                return value
            self._overlay.pop(key, None)
        all_status = self.coordinator.data or {}
        status: dict[str, object] = dict(all_status.get(self._device_id, {}))
        raw = status.get(key, default)
        if isinstance(raw, int | str):
            try:
                return int(raw)
            except (ValueError, TypeError):
                pass
        return int(default)

    async def _retry_update_until(self, predicate: Callable[[dict], bool]) -> tuple[dict, bool]:
        """Fetch status until predicate passes or attempts exhausted.

        Returns (status, satisfied). If not satisfied, caller may keep optimistic state.
        """
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
        # Merge optimistic values into this device's status within the
        # coordinator's aggregated mapping
        all_previous = self.coordinator.data or {}
        prev_for_device = (
            all_previous.get(self._device_id, {}) if isinstance(all_previous, dict) else {}
        )
        optimistic_state_for_device = {**prev_for_device, **optimistic}
        optimistic_all = dict(all_previous) if isinstance(all_previous, dict) else {}
        optimistic_all[self._device_id] = optimistic_state_for_device
        # Apply per-key overlays to keep UI stable; use a shared guard window
        expires = time.monotonic() + OPTIMISTIC_GUARD_SEC
        for k, v in optimistic.items():
            if k in OVERLAY_KEYS:
                self._overlay[k] = (int(v), expires)
        self.coordinator.async_set_updated_data(optimistic_all)
        # Guard against snap-back from interim coordinator refreshes
        self._optimistic_until = expires
        self._optimistic_predicate = confirm_pred
        try:
            try:
                await self.client.async_set(payload, device_id=self._device_id)
            except TypeError:
                await self.client.async_set(payload)
        except Exception:
            # Only revert on explicit failure; otherwise keep optimistic state
            # Clear guard first so revert is not ignored
            self._optimistic_until = None
            self._optimistic_predicate = None
            # Clear overlays
            for k in optimistic.keys():
                self._overlay.pop(k, None)
            self.coordinator.async_set_updated_data(all_previous)
            raise
        status, ok = await self._retry_update_until(confirm_pred)
        if ok:
            # Merge confirmed per-device status into aggregated mapping
            new_all = dict(self.coordinator.data or {})
            new_all[self._device_id] = status
            self.coordinator.async_set_updated_data(new_all)
            self._optimistic_until = None
            self._optimistic_predicate = None
            # Clear overlays on confirm
            for k in optimistic.keys():
                self._overlay.pop(k, None)

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
    ):
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
            s: dict,
            ts: int | None = target_speed,
            tp: int | None = target_preset,
        ) -> bool:
            return (
                s.get(KEY_POWER) == 1
                and (ts is None or s.get(KEY_SPEED) == ts)
                and (tp is None or s.get(KEY_PRESET) == tp)
            )

        await self._apply_with_optimism(optimistic, payload, _confirm)

    async def async_turn_off(self, **kwargs):
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

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        # During a grace window after a set, ignore updates that do not
        # satisfy the optimistic target to avoid UI snap-back.
        if self._optimistic_until is not None and time.monotonic() < self._optimistic_until:
            pred = self._optimistic_predicate
            data = self.coordinator.data or {}
            if callable(pred) and not pred(data):
                return
            # Predicate satisfied; clear the guard.
            self._optimistic_until = None
            self._optimistic_predicate = None
        super()._handle_coordinator_update()

    @property
    def device_info(self) -> DeviceInfo:
        device_id = self._device_id or "unknown"
        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="Fanimation",
            model="FanSync",
            name="FanSync",
        )
