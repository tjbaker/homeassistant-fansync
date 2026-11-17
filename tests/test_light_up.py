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

"""Up light (H09/H0A) on dual-light receivers such as the FD6R1LD5.

Fanimation's information model gives the up light its own power (H09) and
brightness (H0A) registers while both lights share color temperature (H04).
"""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.const import resolve_light_color_temp_presets
from custom_components.fansync.diagnostics_utils import summarize_status_snapshot

DOMAIN = "fansync"
DEVICE_ID = "test-device"

DUAL_LIGHT_STATUS = {
    "H00": 1,
    "H02": 50,
    "H06": 0,
    "H01": 0,
    "H09": 0,
    "H0A": 40,
    "H0B": 1,
    "H0C": 80,
    "H04": 4000,
}


async def _setup(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        options=options or {},
        unique_id="test-up-light",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, suffix: str) -> str | None:
    return er.async_get(hass).async_get_entity_id("light", DOMAIN, f"{DOMAIN}_{DEVICE_ID}_{suffix}")


def _record_writes(mock_client) -> list[dict[str, int]]:
    writes: list[dict[str, int]] = []
    original = mock_client.async_set

    async def _set(data, *, device_id: str | None = None) -> None:
        writes.append(dict(data))
        await original(data, device_id=device_id)

    mock_client.async_set = _set
    return writes


async def test_up_light_created_and_down_light_renamed(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    mock_client.status = dict(DUAL_LIGHT_STATUS)
    await _setup(hass)

    up_id = _entity_id(hass, "up_light")
    down_id = _entity_id(hass, "light")
    assert up_id is not None
    assert down_id is not None
    assert hass.states.get(up_id).attributes["friendly_name"].endswith("Up light")
    assert hass.states.get(down_id).attributes["friendly_name"].endswith("Down light")
    assert hass.states.get(up_id).state == "off"
    assert hass.states.get(down_id).state == "on"


async def test_no_up_light_without_up_registers(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    mock_client.status = {k: v for k, v in DUAL_LIGHT_STATUS.items() if k not in ("H09", "H0A")}
    await _setup(hass)

    assert _entity_id(hass, "up_light") is None
    down_id = _entity_id(hass, "light")
    assert down_id is not None
    assert hass.states.get(down_id).attributes["friendly_name"].endswith("Light")
    assert not hass.states.get(down_id).attributes["friendly_name"].endswith("Down light")


async def test_up_light_writes_only_its_own_registers(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    mock_client.status = dict(DUAL_LIGHT_STATUS)
    await _setup(hass)
    writes = _record_writes(mock_client)
    up_id = _entity_id(hass, "up_light")
    assert up_id is not None

    await hass.services.async_call("light", "turn_on", {"entity_id": up_id}, blocking=True)
    assert writes == [{"H09": 1}]

    writes.clear()
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": up_id, "brightness": 255}, blocking=True
    )
    assert writes == [{"H0A": 100}]

    writes.clear()
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": up_id, "color_temp_kelvin": 3000}, blocking=True
    )
    assert writes == [{"H04": 3000}]

    writes.clear()
    await hass.services.async_call("light", "turn_off", {"entity_id": up_id}, blocking=True)
    assert writes == [{"H09": 0}]


async def test_down_light_does_not_touch_up_registers(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    mock_client.status = dict(DUAL_LIGHT_STATUS)
    await _setup(hass)
    writes = _record_writes(mock_client)
    down_id = _entity_id(hass, "light")
    assert down_id is not None

    await hass.services.async_call("light", "turn_off", {"entity_id": down_id}, blocking=True)
    assert writes == [{"H0B": 0}]
    assert all(not ({"H09", "H0A"} & set(w)) for w in writes)


async def test_color_temp_is_shared_between_lights(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    mock_client.profile = {"esh": {"model": "Kute60-FD6R1LD5"}}
    mock_client.status = {**DUAL_LIGHT_STATUS, "H09": 1}
    await _setup(hass)
    up_id = _entity_id(hass, "up_light")
    down_id = _entity_id(hass, "light")
    assert up_id is not None and down_id is not None
    assert hass.states.get(up_id).attributes["min_color_temp_kelvin"] == 2700
    assert hass.states.get(up_id).attributes["max_color_temp_kelvin"] == 5000

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": up_id, "color_temp_kelvin": 2700}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get(down_id).attributes["color_temp_kelvin"] == 2700


async def test_lightless_option_removes_both_lights(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    mock_client.status = dict(DUAL_LIGHT_STATUS)
    await _setup(hass, {"lightless_devices": [DEVICE_ID]})

    assert _entity_id(hass, "light") is None
    assert _entity_id(hass, "up_light") is None


@pytest.mark.parametrize(
    ("model", "h04", "expected"),
    [
        ("Kute60-FD6R1L5", 2700, (2700, 3000, 3500, 4000, 5000)),
        ("Kute60-FD6R1L5", 3500, (2700, 3000, 3500, 4000, 5000)),
        ("X-FDR1L4", 4000, (2700, 3000, 3500, 4000, 5000)),
        ("X-FD6R1LD5", 3500, (2700, 3000, 3500, 4000, 5000)),
        ("X-FD6R2L5T", 5000, (2700, 3000, 3500, 4000, 5000)),
        ("Corke36-FD6R1L5", 2700, (2700, 3000, 3500, 4000, 5000)),
        ("Corke36", 2700, (2700, 3000, 3500, 4000, 5000)),
        ("X-FDR1L3", 4000, (3000, 4000, 5000)),
        ("Mystery", 4000, (3000, 4000, 5000)),
        (None, 5000, (3000, 4000, 5000)),
    ],
)
def test_presets_follow_the_receiver_code(
    model: object, h04: int, expected: tuple[int, ...]
) -> None:
    assert resolve_light_color_temp_presets(model, {"H04": h04}) == expected


@pytest.mark.parametrize(
    ("model", "h04"),
    [("X-FDR1L3", 2700), ("X-FD6R1L5", 6500), ("Mystery", 3500), ("X-FD6R1L5", None)],
)
def test_presets_need_an_in_profile_h04(model: str, h04: int | None) -> None:
    status = {} if h04 is None else {"H04": h04}
    assert resolve_light_color_temp_presets(model, status) is None


def test_diagnostics_summary_has_up_light_only_when_reported() -> None:
    summary = summarize_status_snapshot(
        {"dual": dict(DUAL_LIGHT_STATUS), "single": {"H0B": 1, "H0C": 50, "H04": 3000}}
    )
    assert summary["dual"]["up_light"] == {"power": 0, "brightness": 40, "color_temp": 4000}
    assert "up_light" not in summary["single"]
