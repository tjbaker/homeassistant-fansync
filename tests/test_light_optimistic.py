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

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


class FailingLightClient:
    def __init__(self, initially_on: bool = False):
        # Include light keys so the light entity is created
        self.status = {
            "H00": 1 if initially_on else 0,  # power
            "H02": 20,  # fan speed
            "H06": 0,  # direction
            "H01": 0,  # preset
            "H0B": 1 if initially_on else 0,  # light power
            "H0C": 50 if initially_on else 0,  # light brightness pct
        }
        self.device_id = "light-optimistic-fail"

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self):
        return dict(self.status)

    async def async_set(self, data: dict[str, int]):
        # Simulate backend failure so the entity must revert optimistic state
        raise RuntimeError("boom")


async def setup_entry_with_client(hass: HomeAssistant, client) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="light-optimistic-test",
    )
    entry.add_to_hass(hass)
    with (
        patch("custom_components.fansync.fan.FanSyncClient", return_value=client),
        patch("custom_components.fansync.light.FanSyncClient", return_value=client),
        patch("custom_components.fansync.FanSyncClient", return_value=client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_light_turn_on_reverts_on_error(hass: HomeAssistant):
    client = FailingLightClient(initially_on=False)
    await setup_entry_with_client(hass, client)

    # Precondition: light off
    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.state == "off"

    # Attempt to turn on should raise and revert to previous state
    with pytest.raises(RuntimeError):
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": "light.fansync_light", "brightness": 128},
            blocking=True,
        )
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state.state == "off"


async def test_light_turn_off_reverts_on_error(hass: HomeAssistant):
    client = FailingLightClient(initially_on=True)
    await setup_entry_with_client(hass, client)

    # Precondition: light on
    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.state == "on"

    # Attempt to turn off should raise and revert to previous state
    with pytest.raises(RuntimeError):
        await hass.services.async_call(
            "light",
            "turn_off",
            {"entity_id": "light.fansync_light"},
            blocking=True,
        )
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state.state == "on"
