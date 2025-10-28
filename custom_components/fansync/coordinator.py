# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import FanSyncClient

SCAN_INTERVAL = None  # push-first; no periodic polling


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
            if not ids:
                # Fallback to single current device
                s = await self.client.async_get_status()
                did = self.client.device_id or "unknown"
                statuses[did] = s
                return statuses
            for did in ids:
                s = await self.client.async_get_status(did)
                statuses[did] = s
            return statuses
        except Exception as err:
            raise UpdateFailed(str(err)) from err
