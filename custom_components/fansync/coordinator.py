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
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import FanSyncClient
from .const import (
    ASSUMED_STORE_SAVE_DELAY_SEC,
    ASSUMED_STORE_VERSION,
    DEFAULT_FALLBACK_POLL_SECS,
    DOMAIN,
    MISMATCH_HISTORY_MAX,
    OBSERVED_VALUES_MAX,
    POLL_STATUS_TIMEOUT_SECS,
    STATUS_HISTORY_MAX,
    coerce_status_int,
)
from .device_utils import create_device_info
from .diagnostics_utils import _PROTOCOL_KEY_RE, summarize_status_snapshot

SCAN_INTERVAL = timedelta(seconds=DEFAULT_FALLBACK_POLL_SECS)

# device id -> register -> [assumed value, stale cloud value]. Loosely typed because
# it is read back from disk and validated on load.
type AssumedStoreData = dict[str, Any]


def _is_power_value(value: object) -> bool:
    """True for the only values an assumed power register can hold."""
    return isinstance(value, int) and not isinstance(value, bool) and value in (0, 1)


def assumed_store(hass: HomeAssistant, entry_id: str) -> Store[AssumedStoreData]:
    """Return the on-disk store of assumed power states for one config entry."""
    return Store(hass, ASSUMED_STORE_VERSION, f"{DOMAIN}.assumed.{entry_id}")


class FanSyncCoordinator(DataUpdateCoordinator[dict[str, dict[str, object]]]):
    """Coordinator for FanSync integration.

    Manages data fetching and updates for all FanSync devices. Uses push-first
    architecture with WebSocket updates and fallback polling.

    Passing config_entry to DataUpdateCoordinator is the recommended pattern
    for Home Assistant 2026.1+ integrations. This enables new features and
    ensures compatibility with future HA releases.
    """

    def __init__(
        self, hass: HomeAssistant, client: FanSyncClient, config_entry: ConfigEntry
    ) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name="fansync",
            update_interval=SCAN_INTERVAL,
            config_entry=config_entry,
        )
        self.client = client
        # Registry lookups are scoped to this entry: identifiers are no longer
        # globally unique across config entries (HA 2026.9 deprecation).
        self._config_entry_id = config_entry.entry_id
        # Note: dr.async_get() is @callback decorated, safe to call in __init__
        self._device_registry = dr.async_get(hass)
        # Track which devices have had registry updated to avoid redundant updates
        self._registry_updated: set[str] = set()
        self._last_update_start_utc: str | None = None
        self._last_update_end_utc: str | None = None
        self._last_update_trigger: str | None = None
        self._last_update_timeout_devices: list[str] = []
        self._last_update_device_count: int | None = None
        self._last_update_success_utc: str | None = None
        self._last_update_duration_ms: float | None = None
        self._last_poll_mismatch_keys: dict[str, list[str]] = {}
        self._last_poll_mismatch_history: list[dict[str, object]] = []
        self._last_poll_mismatch_history_max = MISMATCH_HISTORY_MAX
        self._status_history: list[dict[str, object]] = []
        self._status_history_max = STATUS_HISTORY_MAX
        # Distinct values each device has actually reported per protocol
        # register (polls and pushes only, never optimistic writes). Shows in
        # diagnostics so quantized registers (e.g. a fan's real speed levels)
        # can be read off a report without guessing.
        self._observed_values: dict[str, dict[str, list[int]]] = {}
        # Last status each device actually reported, merged from polls, pushes
        # and confirmation reads. Unlike ``data`` it is never overwritten by an
        # entity's optimistic write, so it is the right baseline for judging
        # whether a later write moved a register.
        self._last_reported: dict[str, dict[str, object]] = {}
        # Power writes a device acknowledged but never reported, per device and
        # register: (assumed value, the stale value the cloud still holds). The
        # assumed value stands in for the cloud's until the device reports.
        self._assumed: dict[str, dict[str, tuple[int, int | None]]] = {}
        self._assumed_store = assumed_store(hass, config_entry.entry_id)
        self._assumed_dirty = False
        self._next_update_trigger: str | None = "startup"

    def last_reported_status(self, device_id: str) -> dict[str, object]:
        """Return the last device-reported status for a device (may be empty)."""
        return dict(self._last_reported.get(device_id, {}))

    def assume_applied(self, device_id: str, values: Mapping[str, int]) -> None:
        """Take an acknowledged, unreported write as the device's state.

        A Kute60 applies a bare power write, acknowledges it, and never reports
        it, so the cloud keeps the old value indefinitely. The written value
        becomes the baseline, and cloud reads that still return the old value
        are corrected until the device reports that register again.
        """
        assumed = self._assumed.setdefault(device_id, {})
        baseline = self._last_reported.setdefault(device_id, {})
        for key, value in values.items():
            stale = assumed[key][1] if key in assumed else coerce_status_int(baseline.get(key))
            assumed[key] = (value, stale)
            baseline[key] = value
        self._save_assumed()

    def clear_assumed(self, device_id: str, keys: Iterable[str]) -> None:
        """Forget assumptions about registers the device itself has reported."""
        assumed = self._assumed.get(device_id, {})
        present = [key for key in keys if key in assumed]
        for key in present:
            del assumed[key]
        if present:
            self._save_assumed()

    def clear_assumed_for_write(self, device_id: str, payload: Mapping[str, int]) -> None:
        """Forget assumptions that a new write is about to change.

        Writing the value already assumed keeps the assumption. Dropping it
        there let the next cloud read return the stale value, which differs
        from the assumed one and so looked like the device had moved: a second
        "off" turned the display back on.
        """
        assumed = self._assumed.get(device_id, {})
        self.clear_assumed(
            device_id, [k for k, v in payload.items() if k in assumed and assumed[k][0] != v]
        )

    async def async_load_assumed(self) -> None:
        """Restore assumed states saved before a restart.

        Each is kept only while the cloud still returns the stale value it was
        recorded against; the first read that differs drops it. A change made
        elsewhere while Home Assistant was down, and reported as the same value
        the cloud already held, cannot be told apart from no change.
        """
        try:
            stored = await self._assumed_store.async_load()
        except NotImplementedError, HomeAssistantError:
            # Written by a newer version, or unreadable. It is a cache of display
            # state; setup must not fail over it.
            self.logger.warning("Ignoring unreadable FanSync assumed-state file")
            return
        if not isinstance(stored, dict):
            return
        known = set(getattr(self.client, "device_ids", None) or [])
        for device_id, registers in stored.items():
            if not isinstance(registers, dict) or (known and device_id not in known):
                self._assumed_dirty = True  # a fan no longer in the account, or junk
                continue
            for key, pair in registers.items():
                if not isinstance(pair, list) or len(pair) != 2 or not _is_power_value(pair[0]):
                    self._assumed_dirty = True
                    continue
                stale = pair[1] if _is_power_value(pair[1]) else None
                self._assumed.setdefault(device_id, {})[key] = (pair[0], stale)

    async def async_flush_assumed(self) -> None:
        """Write pending changes now. Called on unload, so a reload or a removal
        inside the save delay neither loses a change nor recreates a deleted file."""
        if self._assumed_dirty:
            self._assumed_dirty = False
            await self._assumed_store.async_save(self._assumed_for_store())

    def _save_assumed(self) -> None:
        self._assumed_dirty = True
        self._assumed_store.async_delay_save(self._assumed_for_store, ASSUMED_STORE_SAVE_DELAY_SEC)

    def _assumed_for_store(self) -> AssumedStoreData:
        return {
            did: {key: [value, stale] for key, (value, stale) in per.items()}
            for did, per in self._assumed.items()
            if per
        }

    def assumed_values(self) -> dict[str, dict[str, int]]:
        """Return the assumed value per device and register, for diagnostics."""
        return {
            did: {key: value for key, (value, _stale) in per.items()}
            for did, per in self._assumed.items()
            if per
        }

    def _without_stale(self, device_id: str, status: Mapping[str, object]) -> dict[str, object]:
        """Return a cloud read with assumed values in place of the stale ones.

        A read that differs from the stale value means the device has reported
        since, so the assumption is dropped and the read stands.
        """
        result = dict(status)
        assumed = self._assumed.get(device_id)
        if not assumed:
            return result
        moved = []
        for key, (value, stale) in assumed.items():
            if key not in result:
                continue
            if coerce_status_int(result[key]) == stale:
                result[key] = value
            else:
                moved.append(key)
        self.clear_assumed(device_id, moved)
        return result

    def record_observed_status(
        self, device_id: str, status: Mapping[str, object], *, pushed: bool = False
    ) -> dict[str, object]:
        """Record what a device reported: last-known baseline and value history.

        ``pushed`` marks a report from the device itself, which ends any
        assumption about the registers it carries. A cloud read cannot, because
        the cloud returns its stored value whether or not the device is behind
        it; see ``assume_applied``. Returns the status as it should be shown.
        """
        if not device_id or not isinstance(status, Mapping):
            return {}
        if pushed:
            self.clear_assumed(device_id, [k for k in status if isinstance(k, str)])
            status = dict(status)
        else:
            status = self._without_stale(device_id, status)
        self._last_reported.setdefault(device_id, {}).update(status)
        per_device = self._observed_values.setdefault(device_id, {})
        for key, raw in status.items():
            if not isinstance(key, str) or not _PROTOCOL_KEY_RE.match(key):
                continue
            value = coerce_status_int(raw)
            if value is None:
                continue
            seen = per_device.setdefault(key, [])
            if value in seen or len(seen) >= OBSERVED_VALUES_MAX:
                continue
            seen.append(value)
            seen.sort()
        return status

    async def async_request_refresh(self) -> None:
        """Request a manual refresh and track the trigger for diagnostics."""
        self._next_update_trigger = "manual"
        await super().async_request_refresh()

    def _update_device_registry(self, device_ids: list[str]) -> None:
        """Update device registry with latest profile data from client.

        This ensures device model, firmware, and MAC address are displayed
        correctly even if profile data arrives after entity creation.

        Note: Safe to call from async context. Device registry methods with
        async_ prefix are @callback decorated and run in the event loop.

        Only updates registry when profile data is newly available to avoid
        redundant updates on every coordinator refresh.
        """
        for device_id in device_ids:
            if not device_id:
                continue
            # Skip if already updated and profile data hasn't changed
            if hasattr(self.client, "device_profile"):
                profile = self.client.device_profile(device_id)
            else:
                # Client doesn't have device_profile (e.g., in tests or old client)
                profile = None
            if not profile and device_id in self._registry_updated:
                continue
            if profile and device_id in self._registry_updated:
                # Profile exists and we've already updated - skip redundant update
                # NOTE: This doesn't detect profile changes (e.g., firmware updates).
                # If profile change detection becomes needed, consider storing a hash
                # of relevant fields (model, sw_version, connections) to trigger updates.
                continue
            # Get the device entry by identifier, scoped to this config entry
            device = self._device_registry.async_get_device_by_identifier(
                (DOMAIN, device_id), self._config_entry_id
            )
            if not device:
                continue
            # Build updated device info from current profile data
            device_info = create_device_info(self.client, device_id)
            # Only update if we have actual data to update (check for None, not falsiness)
            if not any(
                (
                    device_info.get("manufacturer") is not None,
                    device_info.get("model") is not None,
                    device_info.get("sw_version") is not None,
                    device_info.get("connections") is not None,
                )
            ):
                continue
            # Update the device registry entry with new information. HA requires
            # the full connection set (merge_connections is deprecated), so union
            # the newly discovered connections with what the device already has.
            new_connections = device_info.get("connections")
            self._device_registry.async_update_device(
                device.id,
                manufacturer=device_info.get("manufacturer"),
                model=device_info.get("model"),
                sw_version=device_info.get("sw_version"),
                new_connections=(
                    device.connections | new_connections if new_connections else UNDEFINED
                ),
            )
            # Mark this device as updated
            self._registry_updated.add(device_id)

    async def _get_timeout_seconds(self) -> int:
        """Get dynamic timeout from client, with fallback to default."""
        try:
            val = self.client.ws_timeout_seconds()
        except AttributeError:
            return POLL_STATUS_TIMEOUT_SECS
        if asyncio.iscoroutine(val):
            val = await val
        return int(val)

    def _log_push_idle_if_needed(self) -> None:
        """Log when polling occurs after a prolonged push idle period."""
        if not self.update_interval or not self.logger.isEnabledFor(logging.DEBUG):
            return
        last_push = getattr(self.client, "_last_push_monotonic", None)
        if isinstance(last_push, float):
            idle_s = time.monotonic() - last_push
            interval_s = self.update_interval.total_seconds()
            if idle_s > interval_s:
                self.logger.debug(
                    "poll sync after push idle_s=%.0f interval_s=%.0f",
                    idle_s,
                    interval_s,
                )

    async def _async_update_data(self) -> dict[str, dict[str, object]]:
        start_monotonic = time.monotonic()
        self._last_update_start_utc = datetime.now(UTC).isoformat()
        self._last_update_end_utc = None
        try:
            # Aggregate status for all devices into a mapping
            statuses: dict[str, dict[str, object]] = {}
            ids = getattr(self.client, "device_ids", [])
            # Debug: mark start of polling sync
            trigger = self._next_update_trigger or ("timer" if self.update_interval else "manual")
            self._next_update_trigger = None
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "poll sync start trigger=%s interval=%s ids=%s",
                    trigger,
                    self.update_interval,
                    ids or [self.client.device_id],
                )
            self._last_update_trigger = trigger
            timeout_devices: list[str] = []
            mismatch_keys: dict[str, list[str]] = {}
            if not ids:
                # Fallback to single current device with timeout guard
                timeout_s = await self._get_timeout_seconds()
                try:
                    s = await asyncio.wait_for(self.client.async_get_status(), timeout_s)
                    did = self.client.device_id or "unknown"
                    statuses[did] = self.record_observed_status(did, s)
                except TimeoutError:
                    # Keep last known data instead of failing
                    self.logger.warning(
                        "Status fetch timed out after %d seconds; keeping last known state. "
                        "Commands still work; updates resume when connectivity improves",
                        timeout_s,
                    )
                    did = self.client.device_id or "unknown"
                    timeout_devices.append(did)
                    self._finalize_update(
                        statuses=statuses,
                        timeout_devices=timeout_devices,
                        mismatch_keys=mismatch_keys,
                        success=False,
                        device_count=1,
                    )
                    return self.data or {}
                # Debug: log mismatches vs current coordinator snapshot
                mismatch_keys = self._compute_mismatch_keys(self.data or {}, statuses)
                self._log_push_idle_if_needed()
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("poll sync done devices=%d", len(statuses))
                self._commit_successful_update(
                    statuses=statuses,
                    timeout_devices=timeout_devices,
                    mismatch_keys=mismatch_keys,
                    device_count=len(statuses),
                )
                return statuses

            # Run per-device status in parallel with timeouts; tolerate partial failures
            async def _get(did: str) -> tuple[str, dict[str, Any] | None]:
                timeout_s = await self._get_timeout_seconds()
                try:
                    return did, await asyncio.wait_for(self.client.async_get_status(did), timeout_s)
                except TimeoutError:
                    # Warn on per-device timeout; we'll tolerate partial failures
                    self.logger.warning(
                        "Status fetch timed out for device %s after %d seconds. "
                        "This may indicate high latency in Fanimation's cloud service. "
                        "Last known state will be kept; updates resume when connectivity improves. "
                        "If timeouts persist, consider increasing WebSocket timeout in Options",
                        did,
                        timeout_s,
                    )
                    timeout_devices.append(did)
                    return did, None
                except httpx.HTTPStatusError:
                    # Auth/HTTP failures (e.g. 401/403 during token refresh) must
                    # reach the outer handler so it can trigger the reauth flow.
                    raise
                except Exception as err:
                    # Tolerate a single device's failure (malformed/offline reply,
                    # transient connection error) without failing the whole refresh
                    # and dropping every entity — including healthy ones — to
                    # unavailable. Keep this device's last known state.
                    self.logger.warning(
                        "Status fetch failed for device %s (%s); keeping last known state",
                        did,
                        type(err).__name__,
                    )
                    timeout_devices.append(did)
                    return did, None

            results = await asyncio.gather(*(_get(d) for d in ids))
            for did, status in results:
                if isinstance(status, dict):
                    # Only what was actually read is recorded. The cached state kept
                    # below for a device that timed out already holds any assumed
                    # value, and treating it as a read would look like the device
                    # had moved and drop the assumption.
                    statuses[did] = self.record_observed_status(did, status)
            # Keep last known state for timed-out devices to avoid entity dropouts.
            current = self.data or {}
            if isinstance(current, dict):
                for did in ids:
                    if did in statuses:
                        continue
                    prev_data = current.get(did)
                    if isinstance(prev_data, dict):
                        statuses[did] = prev_data
            # Debug: log mismatches for multi-device
            mismatch_keys = self._compute_mismatch_keys(current, statuses)
            self._log_push_idle_if_needed()
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("poll sync done devices=%d", len(statuses))
            if not statuses:
                # Keep last known data instead of failing; entities stay available
                self.logger.warning(
                    "All %d device(s) timed out (ids=%s); keeping last known state. "
                    "Commands still work; updates resume when connectivity improves",
                    len(ids),
                    ids,
                )
                self._finalize_update(
                    statuses=statuses,
                    timeout_devices=timeout_devices,
                    mismatch_keys=mismatch_keys,
                    success=False,
                    device_count=len(ids),
                )
                self._append_mismatch_history(mismatch_keys, len(ids))
                return self.data or {}
            self._commit_successful_update(
                statuses=statuses,
                timeout_devices=timeout_devices,
                mismatch_keys=mismatch_keys,
                device_count=len(ids),
            )
            return statuses
        except httpx.HTTPStatusError as err:
            # Handle authentication failures by triggering reauth flow
            if err.response.status_code in (401, 403):
                raise ConfigEntryAuthFailed(
                    "Authentication failed. Please re-enter your credentials in the "
                    "FanSync integration settings."
                ) from err
            # Other HTTP errors are treated as temporary failures
            raise UpdateFailed(f"HTTP error {err.response.status_code}: {err}") from err
        except TimeoutError as err:
            raise UpdateFailed(
                f"Coordinator update timed out after {POLL_STATUS_TIMEOUT_SECS} seconds"
            ) from err
        except UpdateFailed:
            raise
        finally:
            if self._last_update_end_utc is None:
                self._last_update_end_utc = datetime.now(UTC).isoformat()
            self._last_update_duration_ms = round((time.monotonic() - start_monotonic) * 1000, 2)

    def _append_status_history(self, statuses: dict[str, dict[str, object]]) -> None:
        """Store a bounded history of recent status snapshots."""
        entry = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "device_count": len(statuses),
            "summary": summarize_status_snapshot(statuses),
        }
        self._status_history.append(entry)
        if len(self._status_history) > self._status_history_max:
            self._status_history.pop(0)

    def _append_mismatch_history(self, mismatch: dict[str, list[str]], device_count: int) -> None:
        entry = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "device_count": device_count,
            "mismatch_device_count": len(mismatch),
            "mismatch_keys": mismatch,
        }
        self._last_poll_mismatch_history.append(entry)
        if len(self._last_poll_mismatch_history) > self._last_poll_mismatch_history_max:
            self._last_poll_mismatch_history.pop(0)

    def _compute_mismatch_keys(
        self, current: object, statuses: dict[str, dict[str, object]]
    ) -> dict[str, list[str]]:
        """Return per-device changed keys vs the current coordinator snapshot."""
        mismatch: dict[str, list[str]] = {}
        if isinstance(current, dict):
            for did, status in statuses.items():
                prev = current.get(did, {})
                if isinstance(prev, dict) and isinstance(status, dict) and prev != status:
                    changed = _changed_keys(prev, status)
                    mismatch[did] = changed
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug("poll mismatch d=%s changed_keys=%s", did, changed)
        return mismatch

    def _commit_successful_update(
        self,
        *,
        statuses: dict[str, dict[str, object]],
        timeout_devices: list[str],
        mismatch_keys: dict[str, list[str]],
        device_count: int,
    ) -> None:
        """Shared success path: registry refresh, status/mismatch history, finalize."""
        self._update_device_registry(list(statuses.keys()))
        self._append_status_history(statuses)
        self._finalize_update(
            statuses=statuses,
            timeout_devices=timeout_devices,
            mismatch_keys=mismatch_keys,
            success=True,
            device_count=device_count,
        )
        self._append_mismatch_history(mismatch_keys, device_count)

    def _finalize_update(
        self,
        *,
        statuses: dict[str, dict[str, object]],
        timeout_devices: list[str],
        mismatch_keys: dict[str, list[str]],
        success: bool,
        device_count: int | None = None,
    ) -> None:
        self._last_update_timeout_devices = timeout_devices
        self._last_update_device_count = device_count if device_count is not None else len(statuses)
        self._last_poll_mismatch_keys = mismatch_keys
        if success:
            self._last_update_success_utc = datetime.now(UTC).isoformat()
        self._last_update_end_utc = datetime.now(UTC).isoformat()


def _changed_keys(prev: dict[str, object], new: dict[str, object]) -> list[str]:
    changed = {k for k in set(prev) | set(new) if prev.get(k) != new.get(k)}
    return sorted(changed)
