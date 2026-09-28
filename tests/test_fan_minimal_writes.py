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

"""Speed writes carry only the registers that have to change.

Probed live on a Kute60-FD6R1L5: {"H02": 100} alone, {"H02": 100, "H00": 1}
and {"H02": 100, "H01": 0} each produce a device_change push with H02=100.
The integration's former {"H00": 1, "H02": 100, "H01": 0} is applied by the
fan (it audibly speeds up) but never reported, so the cloud, the app and HA
all stay on the old speed. Writing power and preset only when they differ
from what the device reports sidesteps the quirk.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "fansync"


@pytest.fixture
def fast_confirm():
    with (
        patch("custom_components.fansync.entity.CONFIRM_INITIAL_DELAY_SEC", 0),
        patch("custom_components.fansync.entity.CONFIRM_RETRY_DELAY_SEC", 0),
    ):
        yield


async def _setup(hass: HomeAssistant, mock_client, unique_id: str) -> list[dict]:
    """Set up the entry and return a list that captures every set payload."""
    writes: list[dict] = []
    original = mock_client.async_set

    async def _capture(data, *, device_id=None):
        writes.append(dict(data))
        await original(data, device_id=device_id)

    mock_client.async_set = _capture
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id=unique_id,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return writes


async def _svc(hass: HomeAssistant, service: str, **data) -> None:
    await hass.services.async_call(
        "fan", service, {"entity_id": "fan.fansync_fan", **data}, blocking=True
    )
    await hass.async_block_till_done()


async def test_speed_change_on_running_normal_fan_writes_speed_only(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 1, "H02": 50, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    writes = await _setup(hass, mock_client, "min-speed-only")

    await _svc(hass, "set_percentage", percentage=100)

    assert writes == [{"H02": 100}]
    assert mock_client.status["H02"] == 100
    assert hass.states.get("fan.fansync_fan").attributes["percentage"] == 100


async def test_speed_change_on_off_fan_also_writes_power(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 0, "H02": 50, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    writes = await _setup(hass, mock_client, "min-speed-power")

    await _svc(hass, "set_percentage", percentage=80)

    assert writes == [{"H02": 80, "H00": 1}]
    assert hass.states.get("fan.fansync_fan").state == "on"


async def test_speed_change_in_fresh_air_also_clears_preset(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 1, "H02": 50, "H06": 0, "H01": 1, "H0B": 0, "H0C": 0}
    writes = await _setup(hass, mock_client, "min-speed-preset")

    await _svc(hass, "set_percentage", percentage=80)

    assert writes == [{"H02": 80, "H01": 0}]
    assert hass.states.get("fan.fansync_fan").attributes["preset_mode"] == "normal"


async def test_turn_on_writes_power_only_when_needed(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 1, "H02": 50, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    writes = await _setup(hass, mock_client, "min-turn-on")

    # already on: a bare turn_on still writes power (there is nothing else to send)
    await _svc(hass, "turn_on")
    assert writes[-1] == {"H00": 1}

    # already on with a percentage: speed only
    await _svc(hass, "turn_on", percentage=100)
    assert writes[-1] == {"H02": 100}

    # off with a percentage: speed and power
    mock_client.status["H00"] = 0
    mock_client._status_callback("test-device", {"H00": 0})
    await hass.async_block_till_done()
    await _svc(hass, "turn_on", percentage=65)
    assert writes[-1] == {"H02": 65, "H00": 1}
