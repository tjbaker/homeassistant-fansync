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

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import FanSyncClient
from .const import FALLBACK_POLL_SECONDS

SCAN_INTERVAL = timedelta(seconds=FALLBACK_POLL_SECONDS)


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
                self.logger.debug("poll sync start ids=%s", ids or [self.client.device_id])
            if not ids:
                # Fallback to single current device
                s = await self.client.async_get_status()
                did = self.client.device_id or "unknown"
                statuses[did] = s
                # Debug: log mismatches vs current coordinator snapshot
                current = self.data or {}
                prev = current.get(did, {}) if isinstance(current, dict) else {}
                if isinstance(prev, dict) and isinstance(s, dict) and prev != s:
                    if self.logger.isEnabledFor(logging.DEBUG):
                        changed = {k for k in set(prev) | set(s) if prev.get(k) != s.get(k)}
                        self.logger.debug(
                            "poll mismatch d=%s changed_keys=%s", did, sorted(changed)
                        )
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("poll sync done devices=%d", len(statuses))
                return statuses
            for did in ids:
                s = await self.client.async_get_status(did)
                statuses[did] = s
            # Debug: log mismatches for multi-device
            current = self.data or {}
            if isinstance(current, dict):
                for did, s in statuses.items():
                    prev = current.get(did, {})
                    if isinstance(prev, dict) and isinstance(s, dict) and prev != s:
                        if self.logger.isEnabledFor(logging.DEBUG):
                            changed = {k for k in set(prev) | set(s) if prev.get(k) != s.get(k)}
                            self.logger.debug(
                                "poll mismatch d=%s changed_keys=%s", did, sorted(changed)
                            )
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("poll sync done devices=%d", len(statuses))
            return statuses
        except Exception as err:
            raise UpdateFailed(str(err)) from err
