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

"""Error sensor: the fault code in H0E, read-only."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.const import ERROR_CODE_TEXT, error_state

DOMAIN = "fansync"
DEVICE_ID = "test-device"

BASE_STATUS = {"H00": 1, "H02": 50, "H06": 0, "H01": 0, "H0B": 0, "H0C": 50}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test-error-sensor",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _sensor_id(hass: HomeAssistant) -> str | None:
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_{DEVICE_ID}_error")


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (None, None),
        (0, "none"),
        (257, "Under voltage"),
        (265, "Over temperature"),
        (999, "Unknown error 999"),
    ],
)
def test_error_state(code: int | None, expected: str | None) -> None:
    assert error_state(code) == expected


def test_error_codes_cover_the_documented_range() -> None:
    assert sorted(ERROR_CODE_TEXT) == list(range(250, 270))


async def test_error_sensor_reports_none_when_no_fault(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    mock_client.status = {**BASE_STATUS, "H0E": 0}
    await _setup(hass)

    entity_id = _sensor_id(hass)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state.state == "none"
    assert state.attributes["error_code"] == 0


async def test_error_sensor_reports_fault_text(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    mock_client.status = {**BASE_STATUS, "H0E": 265}
    await _setup(hass)

    entity_id = _sensor_id(hass)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state.state == "Over temperature"
    assert state.attributes["error_code"] == 265


async def test_error_sensor_not_created_without_register(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    mock_client.status = dict(BASE_STATUS)
    await _setup(hass)

    assert _sensor_id(hass) is None


async def test_error_sensor_is_diagnostic_and_writes_nothing(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    mock_client.status = {**BASE_STATUS, "H0E": 0}
    writes: list[dict[str, int]] = []
    original = mock_client.async_set

    async def _set(data, *, device_id: str | None = None) -> None:
        writes.append(dict(data))
        await original(data, device_id=device_id)

    mock_client.async_set = _set
    await _setup(hass)

    entity_id = _sensor_id(hass)
    assert entity_id is not None
    entry = er.async_get(hass).async_get(entity_id)
    assert entry is not None
    assert entry.entity_category is not None
    assert entry.entity_category.value == "diagnostic"
    assert writes == []
