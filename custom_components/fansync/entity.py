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
from collections.abc import Callable, Iterable, Mapping

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import FanSyncClient
from .const import (
    CONFIRM_INITIAL_DELAY_SEC,
    CONFIRM_RETRY_ATTEMPTS,
    CONFIRM_RETRY_DELAY_SEC,
    DEVICE_ACK_GRACE_SEC,
    DEVICE_ACK_OK,
    KEY_LIGHT_POWER,
    KEY_POWER,
    OPTIMISTIC_GUARD_SEC,
    coerce_status_int,
)
from .coordinator import FanSyncCoordinator
from .device_utils import confirm_after_initial_delay, create_device_info, module_attrs


class FanSyncOptimisticEntity(CoordinatorEntity[FanSyncCoordinator]):
    """Coordinator entity with shared optimistic-update behavior."""

    # Overlay keys that directly affect HA UI state; subclasses override.
    OVERLAY_KEYS: set[str] = set()
    # Registers whose unreported, acknowledged writes are taken as applied.
    ASSUMABLE_KEYS: frozenset[str] = frozenset({KEY_POWER, KEY_LIGHT_POWER})

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
        # Timer that publishes the device's state when a guard lapses unconfirmed
        self._guard_expiry_unsub: CALLBACK_TYPE | None = None

    def _log_state(self, status: dict[str, object]) -> None:
        """Hook for subclasses to emit per-entity debug state logs (no-op by default)."""

    def _status_for(self, payload: Mapping[str, object]) -> dict[str, object]:
        """Return this device's status mapping from an aggregated payload."""
        if isinstance(payload, dict):
            inner = payload.get(self._device_id, payload)
            if isinstance(inner, dict):
                return inner
        return {}

    def _device_value(self, key: str) -> int | None:
        """Return the last value the device itself reported for ``key``.

        Reads the coordinator's device-reported baseline, not ``coordinator.data``:
        an unconfirmed optimistic write leaves the requested value in ``data``,
        and using that as the "before" snapshot let the next write confirm on a
        stale read that merely differed from the earlier request.
        """
        reported = getattr(self.coordinator, "last_reported_status", None)
        if not callable(reported):
            return None
        status = reported(self._device_id)
        if not isinstance(status, Mapping):
            return None
        return coerce_status_int(status.get(key))

    def _record_reported(self, status: dict[str, object]) -> dict[str, object]:
        """Feed a confirmation read into the coordinator's device-reported baseline.

        Returns the read as it should be used: the coordinator replaces values
        the cloud holds stale with the ones it has assumed.
        """
        record = getattr(self.coordinator, "record_observed_status", None)
        if not callable(record) or not isinstance(status, Mapping):
            return status
        shown = record(self._device_id, status)
        return shown if isinstance(shown, dict) else status

    def _assume_if_acknowledged(self, payload: Mapping[str, int]) -> None:
        """Keep an unreported power write that the device itself acknowledged.

        A Kute60 turns off on a bare power write, acknowledges it, and reports
        nothing, so the cloud says "on" forever and restoring that put a stopped
        fan back on screen. Only power registers qualify: they have no in-between
        value a device could have settled on instead, which is what an
        unreported speed or brightness write usually means. Nothing is written
        to the device, so no fan can be started or stopped by this.
        """
        if not payload or any(key not in self.ASSUMABLE_KEYS for key in payload):
            return
        ack = getattr(self.client, "last_device_ack", None)
        assume = getattr(self.coordinator, "assume_applied", None)
        if not callable(ack) or not callable(assume):
            return
        if ack(self._device_id) != DEVICE_ACK_OK:
            return
        assume(self._device_id, payload)
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug(
                "optimism assumed d=%s values=%s device acknowledged, never reported",
                self._device_id,
                dict(payload),
            )

    def _needs_write(self, key: str, value: int) -> bool:
        """True unless the device already reports ``value`` for ``key``.

        Writes used to bundle "power on" (and for speed, "preset normal")
        unconditionally. A Kute60 applies a three-register write of speed 100
        but never reports it back, so the cloud, the app and HA all stay stale,
        while the same speed alone or with one companion register reports fine.
        Writing only what has to change sidesteps the quirk and leaves fewer
        registers to confirm. An unknown device value counts as needing the
        write.
        """
        return self._device_value(key) != value

    def _cancel_guard_expiry(self) -> None:
        if self._guard_expiry_unsub is not None:
            self._guard_expiry_unsub()
            self._guard_expiry_unsub = None

    def _awaiting_device_ack(self, payload: Mapping[str, int]) -> bool:
        """True while a power-only write has no acknowledgement from the device yet."""
        if not payload or any(key not in self.ASSUMABLE_KEYS for key in payload):
            return False
        ack = getattr(self.client, "last_device_ack", None)
        return callable(ack) and ack(self._device_id) is None

    def _schedule_guard_expiry(
        self, expires: float, payload: Mapping[str, int], *, may_extend: bool = True
    ) -> None:
        """Publish the device's state the moment an unconfirmed guard lapses.

        When a device settles a request back to the value it already held (a
        fan flooring 27 to the 20 it was at), nothing moved, the write cannot
        be confirmed, and no update arrives to trigger a state write. Without
        this timer the requested value stayed on screen until the next poll,
        a minute later.
        """
        self._cancel_guard_expiry()

        @callback
        def _on_expiry(_now: object) -> None:
            self._guard_expiry_unsub = None
            if self._optimistic_until != expires:
                return  # confirmed since, or a newer write owns the guard
            if may_extend and self._awaiting_device_ack(payload):
                # The device's answer can take about as long as the guard. Hold
                # the requested state a little longer, once, before giving up.
                extended = time.monotonic() + DEVICE_ACK_GRACE_SEC
                self._optimistic_until = extended
                for key, (value, _expires) in list(self._overlay.items()):
                    self._overlay[key] = (value, extended)
                self._schedule_guard_expiry(extended, payload, may_extend=False)
                return
            self._optimistic_until = None
            self._optimistic_predicate = None
            self._overlay.clear()
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(
                    "optimism expired d=%s unconfirmed; showing device state", self._device_id
                )
            self._assume_if_acknowledged(payload)
            # The coordinator cache still holds the optimistic values if the
            # device never pushed. Put the device-reported baseline back so the
            # state write below shows what the device actually holds.
            reported = getattr(self.coordinator, "last_reported_status", None)
            baseline = reported(self._device_id) if callable(reported) else {}
            if isinstance(baseline, Mapping) and baseline:
                all_data = dict(self.coordinator.data or {})
                current = all_data.get(self._device_id, {})
                merged = dict(current) if isinstance(current, dict) else {}
                merged.update(baseline)
                all_data[self._device_id] = merged
                self.coordinator.async_set_updated_data(all_data)
            else:
                self.async_write_ha_state()

        delay = max(0.0, expires - time.monotonic())
        self._guard_expiry_unsub = async_call_later(self.hass, delay, _on_expiry)

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_guard_expiry()
        await super().async_will_remove_from_hass()

    def _previous_values(self, keys: Iterable[str]) -> dict[str, int | None]:
        """Snapshot the device-reported values of ``keys`` before a write."""
        return {k: self._device_value(k) for k in keys}

    @staticmethod
    def _write_applied(
        s: Mapping[str, object],
        targets: Mapping[str, int],
        previous: Mapping[str, int | None],
    ) -> bool:
        """True once the device has applied a multi-register write.

        Some registers are quantized by the controller (e.g. a fan that only
        holds six speeds): the device accepts the request, snaps it to the
        nearest value it supports, and reports that back. Waiting for an exact
        echo of every register would then never confirm. The write counts as
        applied when every written register echoes its target, or when any of
        them reports a value other than what it held before the write, which
        proves the device processed the message and snapped the rest. A read
        where nothing moved cannot be told from a stale one, so it does not
        confirm; the optimistic guard then expires and the device's own value
        shows, as before.
        """
        values = {k: coerce_status_int(s.get(k)) for k in targets}
        if any(v is None for v in values.values()):
            return False
        if all(values[k] == targets[k] for k in targets):
            return True
        return any(previous.get(k) is not None and values[k] != previous[k] for k in targets)

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
        coerced = coerce_status_int(raw)
        if coerced is not None:
            return coerced
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
            status = self._record_reported(await self.client.async_get_status(self._device_id))
            if predicate(status):
                return status, True
            await asyncio.sleep(self._retry_delay)
        # A push can land during the final retry sleep. The update handler has
        # already applied it (and cleared the guard and overlays); honor it here
        # so the write is reported as confirmed rather than timed out.
        if self._confirmed_by_push:
            data = self.coordinator.data or {}
            pushed = data.get(self._device_id, {}) if isinstance(data, dict) else {}
            if predicate(pushed):
                if self._logger.isEnabledFor(logging.DEBUG):
                    self._logger.debug(
                        "optimism late confirm d=%s via push update", self._device_id
                    )
                return pushed, True
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
        self._cancel_guard_expiry()
        for k, v in optimistic.items():
            if k in self.OVERLAY_KEYS:
                self._overlay[k] = (int(v), expires)
        self.coordinator.async_set_updated_data(optimistic_all)
        # Guard against snap-back from interim coordinator refreshes
        self._optimistic_until = expires
        self._optimistic_predicate = confirm_pred
        self._confirmed_by_push = False  # Reset flag for new optimistic update
        # A register being written to a new value is no longer assumed: this
        # write's own outcome decides what it holds.
        clear_assumed = getattr(self.coordinator, "clear_assumed_for_write", None)
        if callable(clear_assumed):
            clear_assumed(self._device_id, payload)
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
            # Drop the guard and overlays *before* publishing, so the state
            # write triggered by the update reads the device's settled values
            # rather than the requested ones (they differ when the device
            # quantizes a register, e.g. a fan snapping 87 to its 80 level).
            self._optimistic_until = None
            self._optimistic_predicate = None
            for k in optimistic:
                self._overlay.pop(k, None)
            # Merge confirmed per-device status into aggregated mapping
            new_all = dict(self.coordinator.data or {})
            new_all[self._device_id] = status
            self.coordinator.async_set_updated_data(new_all)
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(
                    "optimism confirm d=%s keys=%s overlay_count=%d",
                    self._device_id,
                    list(optimistic.keys()),
                    len(self._overlay),
                )
        elif self._optimistic_until == expires:
            self._schedule_guard_expiry(expires, payload)

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
            # Clear the guard and the overlays now. If the confirmation polls have
            # already given up, nobody else will, and the UI would keep showing the
            # requested value instead of what the device settled on until expiry.
            self._optimistic_until = None
            self._optimistic_predicate = None
            self._overlay.clear()

        # Per-entity debug state logging (subclass hook)
        self._log_state(self._status_for(self.coordinator.data or {}))

        super()._handle_coordinator_update()

    @property
    def device_info(self) -> DeviceInfo:
        return create_device_info(self.client, self._device_id)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        return module_attrs(self.client, self._device_id)
