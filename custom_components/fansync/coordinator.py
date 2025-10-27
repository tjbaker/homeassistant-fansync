# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import FanSyncClient

SCAN_INTERVAL = None  # push-first; no periodic polling


class FanSyncCoordinator(DataUpdateCoordinator):
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
            return await self.client.async_get_status()
        except Exception as err:
            raise UpdateFailed(str(err)) from err
