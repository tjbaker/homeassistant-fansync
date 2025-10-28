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

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


class ClientWithCallback:
    def __init__(self):
        self.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0}
        self.device_id = "setup-device"
        self._cb = None
        self.connected = False
        self.disconnected = False

    async def async_connect(self):
        self.connected = True

    async def async_disconnect(self):
        self.disconnected = True

    async def async_get_status(self, device_id: str | None = None):
        return dict(self.status)

    async def async_set(self, data, *, device_id: str | None = None):
        self.status.update(data)

    def set_status_callback(self, cb):
        self._cb = cb


async def test_setup_registers_callback_and_unload_disconnects(hass: HomeAssistant):
    client = ClientWithCallback()
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="setup-test",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Fan entity should exist and reflect initial status
    state = hass.states.get("fan.fan")
    assert state is not None
    assert state.attributes.get("percentage") == 20
    # Ensure callback was registered
    assert client._cb is not None

    # Trigger push status
    client._cb({"H00": 1, "H02": 55, "H06": 0, "H01": 0})  # type: ignore[misc]
    await hass.async_block_till_done()
    state = hass.states.get("fan.fan")
    assert state.attributes.get("percentage") == 55

    # Unload entry should disconnect client
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert client.disconnected is True
