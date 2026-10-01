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

"""The "Home Away" switch mirrors the Fanimation app's mode (register H0D).

Measured on a Kute60-FD6R1L5 (firmware 3.2.9): turning the mode on stops the
fan, turning it off leaves the fan stopped, and powering the fan on clears the
mode. The fan reports each of those itself.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "fansync"
FAN = "fan.fansync_fan"
DEVICE = "test-device"


@pytest.fixture
def fast_confirm():
    with (
        patch("custom_components.fansync.entity.CONFIRM_INITIAL_DELAY_SEC", 0),
        patch("custom_components.fansync.entity.CONFIRM_RETRY_DELAY_SEC", 0),
    ):
        yield


async def _setup(hass: HomeAssistant, unique_id: str) -> str | None:
    """Set the integration up and return the Home Away switch's entity id, if created."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id=unique_id,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{DOMAIN}_{DEVICE}_home_away")


def _home_away_fan(mock_client) -> list[dict[str, int]]:
    """Make the mock behave like the measured fan and return the writes it receives."""
    writes: list[dict[str, int]] = []

    async def _set(data: dict[str, int], *, device_id: str | None = None) -> None:
        writes.append(dict(data))
        mock_client.status.update(data)
        if data.get("H0D") == 1:
            mock_client.status["H00"] = 0  # the mode stops the fan
        if data.get("H00") == 1:
            mock_client.status["H0D"] = 0  # powering on clears the mode

    mock_client.async_set = _set
    return writes


async def test_switch_only_exists_for_fans_that_report_the_register(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    assert await _setup(hass, "no-home-away") is None


async def test_switch_reflects_the_register(hass: HomeAssistant, mock_client, patch_client) -> None:
    mock_client.status = {"H00": 0, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0, "H0D": 1}
    entity_id = await _setup(hass, "home-away-on")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state.state == "on"
    assert "ip_address" not in state.attributes  # no module details on a mode switch

    # the app turns the mode off; the fan reports it
    mock_client._status_callback(DEVICE, {"H0D": 0})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "off"


async def test_turning_home_away_on_writes_only_its_register_and_the_fan_follows(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0, "H0D": 0}
    writes = _home_away_fan(mock_client)
    entity_id = await _setup(hass, "home-away-turn-on")
    assert hass.states.get(FAN).state == "on"

    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()

    assert writes == [{"H0D": 1}]
    assert hass.states.get(entity_id).state == "on"
    assert hass.states.get(FAN).state == "off"


async def test_turning_home_away_off_leaves_the_fan_stopped(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 0, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0, "H0D": 1}
    writes = _home_away_fan(mock_client)
    entity_id = await _setup(hass, "home-away-turn-off")

    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()

    assert writes == [{"H0D": 0}]
    assert hass.states.get(entity_id).state == "off"
    assert hass.states.get(FAN).state == "off"


async def test_turning_the_fan_on_clears_home_away(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 0, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0, "H0D": 1}
    writes = _home_away_fan(mock_client)
    entity_id = await _setup(hass, "home-away-fan-on")

    await hass.services.async_call("fan", "turn_on", {"entity_id": FAN}, blocking=True)
    await hass.async_block_till_done()

    assert writes == [{"H00": 1, "H02": 20}]  # the fan write never touches the mode
    assert hass.states.get(FAN).state == "on"
    assert hass.states.get(entity_id).state == "off"
