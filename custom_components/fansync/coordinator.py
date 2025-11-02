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

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import FanSyncClient
from .const import DEFAULT_FALLBACK_POLL_SECS, POLL_STATUS_TIMEOUT_SECS

SCAN_INTERVAL = timedelta(seconds=DEFAULT_FALLBACK_POLL_SECS)


class FanSyncCoordinator(DataUpdateCoordinator[dict[str, dict[str, object]]]):
    def __init__(self, hass: HomeAssistant, client: FanSyncClient):
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name="fansync",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

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
                try:
                    s = await asyncio.wait_for(
                        self.client.async_get_status(), POLL_STATUS_TIMEOUT_SECS
                    )
                except TimeoutError as exc:
                    raise UpdateFailed(
                        f"Status fetch timed out after {POLL_STATUS_TIMEOUT_SECS} seconds"
                    ) from exc
                did = self.client.device_id or "unknown"
                statuses[did] = s
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
                return statuses

            # Run per-device status in parallel with timeouts; tolerate partial failures
            async def _get(did: str):
                try:
                    # Use a timeout aligned with the client's WS timeout, with a small buffer.
                    try:
                        val = self.client.ws_timeout_seconds()
                    except AttributeError:
                        timeout_s = POLL_STATUS_TIMEOUT_SECS
                    else:
                        if asyncio.iscoroutine(val):
                            val = await val
                        timeout_s = max(POLL_STATUS_TIMEOUT_SECS, int(val) + 2)
                    return did, await asyncio.wait_for(self.client.async_get_status(did), timeout_s)
                except TimeoutError:
                    # Warn on per-device timeout; we'll tolerate partial failures
                    self.logger.warning(
                        "status fetch timed out for device %s after %d seconds",
                        did,
                        timeout_s,
                    )
                    return did, None

            results = await asyncio.gather(*(_get(d) for d in ids))
            for did, s in results:
                if isinstance(s, dict):
                    statuses[did] = s
            # Debug: log mismatches for multi-device
            current = self.data or {}
            if isinstance(current, dict):
                for did, s in statuses.items():
                    prev = current.get(did, {})
                    if isinstance(prev, dict) and isinstance(s, dict) and prev != s:
                        if self.logger.isEnabledFor(logging.DEBUG):
                            self.logger.debug(
                                "poll mismatch d=%s changed_keys=%s", did, _changed_keys(prev, s)
                            )
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("poll sync done devices=%d", len(statuses))
            if not statuses:
                raise UpdateFailed(
                    f"All {len(ids)} device(s) failed (ids={ids}); "
                    "check network connectivity and device availability"
                )
            return statuses
        except TimeoutError as err:
            raise UpdateFailed(
                f"Coordinator update timed out after {POLL_STATUS_TIMEOUT_SECS} seconds"
            ) from err
        except UpdateFailed:
            raise


def _changed_keys(prev: dict[str, object], new: dict[str, object]) -> list[str]:
    changed = {k for k in set(prev) | set(new) if prev.get(k) != new.get(k)}
    return sorted(changed)
