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
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.const import KEY_DIRECTION, KEY_POWER
from custom_components.fansync.coordinator import FanSyncCoordinator
from custom_components.fansync.fan import FanSyncFan


class FailingClient:
    def __init__(self):
        # Start with fan on at 20%, forward, normal preset
        self.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0}
        self.device_id = "optimistic-fail"

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id: str | None = None):
        return dict(self.status)

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        # Simulate backend failure
        raise RuntimeError("boom")


async def setup_entry_with_client(hass: HomeAssistant, client) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="optimistic-test",
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


async def test_set_percentage_reverts_on_error(hass: HomeAssistant):
    client = FailingClient()
    await setup_entry_with_client(hass, client)

    # Precondition
    state = hass.states.get("fan.fansync_fan")
    assert state.attributes.get("percentage") == 20

    with pytest.raises(RuntimeError):
        await hass.services.async_call(
            "fan",
            "set_percentage",
            {"entity_id": "fan.fansync_fan", "percentage": 55},
            blocking=True,
        )
    await hass.async_block_till_done()

    # After failure, state should be reverted to previous (20%)
    state = hass.states.get("fan.fansync_fan")
    assert state.attributes.get("percentage") == 20


async def test_set_direction_reverts_on_error(hass: HomeAssistant):
    client = FailingClient()
    await setup_entry_with_client(hass, client)

    # Precondition
    state = hass.states.get("fan.fansync_fan")
    assert state.attributes.get("direction") == "forward"

    with pytest.raises(RuntimeError):
        await hass.services.async_call(
            "fan",
            "set_direction",
            {"entity_id": "fan.fansync_fan", "direction": "reverse"},
            blocking=True,
        )
    await hass.async_block_till_done()

    # After failure, state should be reverted to previous (forward)
    state = hass.states.get("fan.fansync_fan")
    assert state.attributes.get("direction") == "forward"


async def test_optimistic_guard_uses_device_status(hass: HomeAssistant, mock_config_entry) -> None:
    mock_client = AsyncMock()
    mock_client.device_ids = ["dev1", "dev2"]

    coordinator = FanSyncCoordinator(hass, mock_client, mock_config_entry)
    coordinator.data = {
        "dev1": {KEY_POWER: 1, KEY_DIRECTION: 1},
        "dev2": {KEY_POWER: 1, KEY_DIRECTION: 0},
    }

    fan = FanSyncFan(coordinator, mock_client, "dev1")
    fan.hass = hass
    fan.entity_id = "fan.test"
    fan._optimistic_until = time.monotonic() + 1
    fan._optimistic_predicate = lambda s: s.get(KEY_DIRECTION) == 1

    with patch.object(FanSyncFan, "async_write_ha_state", return_value=None):
        fan._handle_coordinator_update()

    assert fan._confirmed_by_push is True
    assert fan._optimistic_until is None
    assert fan._optimistic_predicate is None
