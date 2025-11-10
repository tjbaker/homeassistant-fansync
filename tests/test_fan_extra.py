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

"""Additional fan behaviors: direction, presets, percentage bounds, turn_off.

Exercises behaviors beyond the basic lifecycle, including reversing direction,
setting preset modes, clamping percentage to minimum, and ensuring turn_off
maps to the expected minimum speed value in attributes.
"""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "fansync"


async def setup_entry(hass: HomeAssistant, patch_client, entry_id="test3"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id=entry_id,
    )
    entry.add_to_hass(hass)
    # Only set up if not already loaded to avoid OperationNotAllowed
    if entry.state.name == "NOT_LOADED":
        await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_set_direction_and_preset(hass: HomeAssistant, patch_client):
    """Reverse direction and set a preset mode, verifying attributes."""
    await setup_entry(hass, patch_client)

    # Direction reverse
    await hass.services.async_call(
        "fan",
        "set_direction",
        {"entity_id": "fan.fansync_fan", "direction": "reverse"},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("fan.fansync_fan")
    assert state.attributes.get("direction") == "reverse"

    # Preset fresh_air
    await hass.services.async_call(
        "fan",
        "set_preset_mode",
        {"entity_id": "fan.fansync_fan", "preset_mode": "fresh_air"},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("fan.fansync_fan")
    assert state.attributes.get("preset_mode") == "fresh_air"


async def test_percentage_bounds(hass: HomeAssistant, patch_client):
    """Clamp lower bound to 1% and accept 100% as valid max."""
    await setup_entry(hass, patch_client, entry_id="test4")

    # Below min -> coerced to 1
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": "fan.fansync_fan", "percentage": 0}, blocking=True
    )
    await hass.async_block_till_done()
    state = hass.states.get("fan.fansync_fan")
    assert state.attributes.get("percentage") == 1

    # Above max is rejected by HA schema; set to 100 and verify
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": "fan.fansync_fan", "percentage": 100}, blocking=True
    )
    await hass.async_block_till_done()
    state = hass.states.get("fan.fansync_fan")
    assert state.attributes.get("percentage") == 100


async def test_percentage_exits_fresh_air(hass: HomeAssistant, patch_client):
    """Changing percentage exits fresh-air preset and sets preset to normal."""
    await setup_entry(hass, patch_client, entry_id="test6")

    # Start in fresh_air
    await hass.services.async_call(
        "fan",
        "set_preset_mode",
        {"entity_id": "fan.fansync_fan", "preset_mode": "fresh_air"},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("fan.fansync_fan")
    assert state.attributes.get("preset_mode") == "fresh_air"

    # Changing percentage should exit fresh_air -> normal
    await hass.services.async_call(
        "fan",
        "set_percentage",
        {"entity_id": "fan.fansync_fan", "percentage": 50},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("fan.fansync_fan")
    assert state.attributes.get("percentage") == 50
    assert state.attributes.get("preset_mode") == "normal"


async def test_turn_off_preserves_speed(hass: HomeAssistant, patch_client):
    """Turning off preserves last percentage speed while state reads off."""
    await setup_entry(hass, patch_client, entry_id="test5")
    # Capture current speed
    state = hass.states.get("fan.fansync_fan")
    prev_pct = state.attributes.get("percentage")
    await hass.services.async_call(
        "fan", "turn_off", {"entity_id": "fan.fansync_fan"}, blocking=True
    )
    await hass.async_block_till_done()
    state = hass.states.get("fan.fansync_fan")
    assert state.state == "off"
    assert state.attributes.get("percentage") == prev_pct
