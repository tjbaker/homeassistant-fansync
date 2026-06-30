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

"""Shared base entity for FanSync optimistic-update platforms.

``FanSyncOptimisticEntity`` holds the optimistic-update machinery shared by the
fan and light platforms: a per-key overlay that prevents UI snap-back, a guard
window after each command, and confirmation via push update or polling retry.

Predicate convention: every confirmation predicate receives this device's
per-device status mapping (the value already unwrapped by ``_status_for``),
never the aggregated ``{device_id: status}`` dict.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import FanSyncClient
from .const import (
    CONFIRM_INITIAL_DELAY_SEC,
    CONFIRM_RETRY_ATTEMPTS,
    CONFIRM_RETRY_DELAY_SEC,
    OPTIMISTIC_GUARD_SEC,
)
from .coordinator import FanSyncCoordinator
from .device_utils import confirm_after_initial_delay, create_device_info, module_attrs


class FanSyncOptimisticEntity(CoordinatorEntity[FanSyncCoordinator]):
    """Coordinator entity with shared optimistic-update behavior."""

    # Overlay keys that directly affect HA UI state; subclasses override.
    OVERLAY_KEYS: set[str] = set()

    def __init__(
        self,
        coordinator: FanSyncCoordinator,
        client: FanSyncClient,
        device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = client
        self._device_id = device_id or "unknown"
        # Log under the concrete subclass's module so log namespaces remain
        # custom_components.fansync.fan / .light (preserves existing behavior).
        self._logger = logging.getLogger(type(self).__module__)
        self._retry_attempts = CONFIRM_RETRY_ATTEMPTS
        self._retry_delay = CONFIRM_RETRY_DELAY_SEC
        self._optimistic_until: float | None = None
        self._optimistic_predicate: Callable[[dict[str, object]], bool] | None = None
        # Per-key optimistic overlay to avoid snap-back during short races.
        # key -> (value, expires_at_monotonic)
        self._overlay: dict[str, tuple[int, float]] = {}
        # Flag to signal early termination of confirmation polling when push confirms
        self._confirmed_by_push: bool = False

    def _log_state(self, status: dict[str, object]) -> None:
        """Hook for subclasses to emit per-entity debug state logs (no-op by default)."""

    def _status_for(self, payload: Mapping[str, object]) -> dict[str, object]:
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
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(
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
            except ValueError, TypeError:
                pass
        return int(default)

    async def _retry_update_until(
        self, predicate: Callable[[dict[str, object]], bool]
    ) -> tuple[dict[str, object], bool]:
        """Fetch status until predicate passes or attempts exhausted.

        Returns (status, satisfied). If not satisfied, caller may keep optimistic state.
        Early terminates if push update confirms the change (via _confirmed_by_push flag).
        The predicate always receives this device's per-device status.
        """
        status: dict[str, object] = {}
        for attempt in range(self._retry_attempts):
            # Check if push update already confirmed before polling
            if self._confirmed_by_push:
                # Get final status from coordinator data
                data = self.coordinator.data or {}
                status = data.get(self._device_id, {}) if isinstance(data, dict) else {}
                # Validate predicate in case coordinator data changed between flag set and now
                if predicate(status):
                    if self._logger.isEnabledFor(logging.DEBUG):
                        self._logger.debug(
                            "optimism early confirm d=%s via push update",
                            self._device_id,
                        )
                    return status, True
                # Predicate no longer satisfied, reset flag and continue polling
                self._confirmed_by_push = False

            if attempt == 0 and CONFIRM_INITIAL_DELAY_SEC > 0:
                await asyncio.sleep(CONFIRM_INITIAL_DELAY_SEC)
                # Push may confirm during the initial delay; skip polling if so.
                status, confirmed, ok = confirm_after_initial_delay(
                    confirmed_by_push=self._confirmed_by_push,
                    coordinator_data=self.coordinator.data,
                    device_id=self._device_id,
                    predicate=predicate,
                    logger=self._logger,
                )
                self._confirmed_by_push = confirmed
                if ok:
                    return status, True
            status = await self.client.async_get_status(self._device_id)
            if predicate(status):
                return status, True
            await asyncio.sleep(self._retry_delay)
        return status, False

    async def _apply_with_optimism(
        self,
        optimistic: dict[str, int],
        payload: dict[str, int],
        confirm_pred: Callable[[dict[str, object]], bool],
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
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug(
                "optimism start d=%s optimistic=%s expires_in=%.2fs",
                self._device_id,
                optimistic,
                OPTIMISTIC_GUARD_SEC,
            )
        expires = time.monotonic() + OPTIMISTIC_GUARD_SEC
        for k, v in optimistic.items():
            if k in self.OVERLAY_KEYS:
                self._overlay[k] = (int(v), expires)
        self.coordinator.async_set_updated_data(optimistic_all)
        # Guard against snap-back from interim coordinator refreshes
        self._optimistic_until = expires
        self._optimistic_predicate = confirm_pred
        self._confirmed_by_push = False  # Reset flag for new optimistic update
        try:
            await self.client.async_set(payload, device_id=self._device_id)
        except RuntimeError as exc:
            # Only revert on explicit failure; otherwise keep optimistic state
            # Clear guard first so revert is not ignored
            self._optimistic_until = None
            self._optimistic_predicate = None
            # Clear overlays
            for k in optimistic:
                self._overlay.pop(k, None)
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(
                    "optimism revert d=%s keys=%s overlay_count=%d error=%s",
                    self._device_id,
                    list(optimistic.keys()),
                    len(self._overlay),
                    type(exc).__name__,
                )
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
            for k in optimistic:
                self._overlay.pop(k, None)
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(
                    "optimism confirm d=%s keys=%s overlay_count=%d",
                    self._device_id,
                    list(optimistic.keys()),
                    len(self._overlay),
                )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return super().available and self._device_id in (self.coordinator.data or {})

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        # During a grace window after a set, ignore updates that do not
        # satisfy the optimistic target to avoid UI snap-back.
        if self._optimistic_until is not None and time.monotonic() < self._optimistic_until:
            pred = self._optimistic_predicate
            data = self.coordinator.data or {}
            status = self._status_for(data)
            if callable(pred) and not pred(status):
                if self._logger.isEnabledFor(logging.DEBUG):
                    remaining = (
                        self._optimistic_until - time.monotonic() if self._optimistic_until else 0.0
                    )
                    self._logger.debug(
                        "guard ignore d=%s overlays=%d remaining=%.2fs",
                        self._device_id,
                        len(self._overlay),
                        max(0.0, remaining),
                    )
                return
            # Predicate satisfied (by push or polling); signal early termination of polling.
            # Note: Intended use case is confirmation via push, but this is set whenever
            # the predicate is satisfied during the guard period, regardless of update source.
            self._confirmed_by_push = True
            # Clear the guard
            self._optimistic_until = None
            self._optimistic_predicate = None

        # Per-entity debug state logging (subclass hook)
        self._log_state(self._status_for(self.coordinator.data or {}))

        super()._handle_coordinator_update()

    @property
    def device_info(self) -> DeviceInfo:
        return create_device_info(self.client, self._device_id)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        return module_attrs(self.client, self._device_id)
