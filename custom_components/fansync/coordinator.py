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
from datetime import timedelta
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import FanSyncClient
from .const import DEFAULT_FALLBACK_POLL_SECS, DOMAIN, POLL_STATUS_TIMEOUT_SECS
from .device_utils import create_device_info

SCAN_INTERVAL = timedelta(seconds=DEFAULT_FALLBACK_POLL_SECS)


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
        # Note: dr.async_get() is @callback decorated, safe to call in __init__
        self._device_registry = dr.async_get(hass)
        # Track which devices have had registry updated to avoid redundant updates
        self._registry_updated: set[str] = set()

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
            # Get the device entry by identifier
            device = self._device_registry.async_get_device(identifiers={(DOMAIN, device_id)})
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
            # Update the device registry entry with new information
            self._device_registry.async_update_device(
                device.id,
                manufacturer=device_info.get("manufacturer"),
                model=device_info.get("model"),
                sw_version=device_info.get("sw_version"),
                merge_connections=device_info.get("connections") or UNDEFINED,
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

    async def _async_update_data(self):
        try:
            # Aggregate status for all devices into a mapping
            statuses: dict[str, dict[str, object]] = {}
            ids = getattr(self.client, "device_ids", [])
            # Debug: mark start of polling sync
            if self.logger.isEnabledFor(logging.DEBUG):
                trigger = "timer" if self.update_interval else "manual"
                self.logger.debug(
                    "poll sync start trigger=%s interval=%s ids=%s",
                    trigger,
                    self.update_interval,
                    ids or [self.client.device_id],
                )
            if not ids:
                # Fallback to single current device with timeout guard
                timeout_s = await self._get_timeout_seconds()
                try:
                    s = await asyncio.wait_for(self.client.async_get_status(), timeout_s)
                    did = self.client.device_id or "unknown"
                    statuses[did] = s
                except TimeoutError:
                    # Keep last known data instead of failing
                    self.logger.warning(
                        "Status fetch timed out after %d seconds; keeping last known state. "
                        "Commands still work; updates resume when connectivity improves",
                        timeout_s,
                    )
                    return self.data or {}
                # Debug: log mismatches vs current coordinator snapshot
                current = self.data or {}
                prev = current.get(did, {}) if isinstance(current, dict) else {}
                if isinstance(prev, dict) and isinstance(s, dict) and prev != s:
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug(
                            "poll mismatch d=%s changed_keys=%s", did, _changed_keys(prev, s)
                        )
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("poll sync done devices=%d", len(statuses))
                # Update device registry with any new profile data
                self._update_device_registry([did])
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
                    return did, None

            results = await asyncio.gather(*(_get(d) for d in ids))
            for did, status in results:
                if isinstance(status, dict):
                    statuses[did] = status
            # Debug: log mismatches for multi-device
            current = self.data or {}
            if isinstance(current, dict):
                for did, status in statuses.items():
                    prev = current.get(did, {})
                    if isinstance(prev, dict) and isinstance(status, dict) and prev != status:
                        if self.logger.isEnabledFor(logging.DEBUG):
                            self.logger.debug(
                                "poll mismatch d=%s changed_keys=%s",
                                did,
                                _changed_keys(prev, status),
                            )
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
                return self.data or {}
            # Update device registry with any new profile data for all devices
            self._update_device_registry(list(statuses.keys()))
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


def _changed_keys(prev: dict[str, object], new: dict[str, object]) -> list[str]:
    changed = {k for k in set(prev) | set(new) if prev.get(k) != new.get(k)}
    return sorted(changed)
