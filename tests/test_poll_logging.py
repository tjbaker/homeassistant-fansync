# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Trevor Baker, all rights reserved.

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant

from custom_components.fansync.coordinator import FanSyncCoordinator


class DummyClient:
    def __init__(self):
        self.device_id = "dev"
        self.device_ids: list[str] = []  # single-device path
        self.async_get_status = AsyncMock()


async def test_poll_logs_mismatch_single_device(hass: HomeAssistant, caplog):
    caplog.set_level(logging.DEBUG)
    client = DummyClient()
    coord = FanSyncCoordinator(hass, client)

    # Seed current data with one value
    coord.async_set_updated_data({"dev": {"H02": 20}})
    # Next poll returns different value
    client.async_get_status.return_value = {"H02": 33}

    result = await coord._async_update_data()

    assert result == {"dev": {"H02": 33}}
    msgs = [r.getMessage() for r in caplog.records]
    assert any("poll sync start" in m for m in msgs)
    assert any("poll mismatch d=dev" in m for m in msgs)
    assert any("poll sync done devices=1" in m for m in msgs)
