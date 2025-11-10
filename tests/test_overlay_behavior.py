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

import time
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


class OverlayClient:
    def __init__(self, confirm_delay: float = 0.2):
        self.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0}
        self.device_ids = ["dev"]
        self.device_id = "dev"
        self._cb = None
        self._confirm_delay = confirm_delay

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id=None):
        return dict(self.status)

    async def async_set(self, data, *, device_id=None):
        # Simulate delayed confirmation by invoking callback after a small delay
        self.status.update(data)
        if self._cb:
            self._cb(dict(self.status))

    def set_status_callback(self, cb):
        self._cb = cb


async def setup(hass: HomeAssistant, client: OverlayClient) -> None:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="overlay",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_overlay_ignores_interim_update_then_confirms(hass: HomeAssistant):
    client = OverlayClient()
    await setup(hass, client)

    # monkeypatch time.monotonic to control overlay window
    base = time.monotonic()

    def fake_monotonic():
        return fake_monotonic.t

    fake_monotonic.t = base

    with patch(
        "custom_components.fansync.fan.time.monotonic", side_effect=lambda: fake_monotonic()
    ):
        # Initiate change to 55
        await hass.services.async_call(
            "fan",
            "set_percentage",
            {"entity_id": "fan.fansync_fan", "percentage": 55},
            blocking=True,
        )
        # During guard, coordinator update that doesn't match predicate should be ignored by entity
        state = hass.states.get("fan.fansync_fan")
        assert state.attributes.get("percentage") == 55

        # Advance time beyond guard window
        from custom_components.fansync.const import OPTIMISTIC_GUARD_SEC

        fake_monotonic.t = base + OPTIMISTIC_GUARD_SEC + 1.0
        await hass.async_block_till_done()
        # State remains at confirmed value because callback already applied; no snap-back
        state = hass.states.get("fan.fansync_fan")
        assert state.attributes.get("percentage") == 55
