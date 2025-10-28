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


async def test_light_not_created_when_no_light_keys(hass: HomeAssistant):
    """Do not create light entity if device exposes no light fields."""

    class _Mock:
        def __init__(self):
            # No H0B/H0C keys present
            self.status = {"H00": 1, "H02": 41, "H06": 0, "H01": 0}
            self.device_id = "no-light-device"

        async def async_connect(self):
            return None

        async def async_disconnect(self):
            return None

        async def async_get_status(self, device_id: str | None = None):
            return self.status

        async def async_set(self, data, *, device_id: str | None = None):
            self.status.update(data)

    client = _Mock()

    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="no-light-test",
    )
    entry.add_to_hass(hass)

    # Patch both platform imports to use our mock client
    with (
        patch("custom_components.fansync.fan.FanSyncClient", return_value=client),
        patch("custom_components.fansync.light.FanSyncClient", return_value=client),
        patch("custom_components.fansync.FanSyncClient", return_value=client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Fan should exist, light should not
    assert hass.states.get("fan.fan") is not None
    assert hass.states.get("light.light") is None
