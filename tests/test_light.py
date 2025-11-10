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

"""Light entity lifecycle and brightness mapping tests.

Validates initial off state, turning on with brightness, and acceptable rounding
differences from percentage-to-brightness mapping.
"""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "fansync"


async def test_light_entity_lifecycle(hass: HomeAssistant, patch_client):
    """Create light entity, turn on with brightness, verify mapping/rounding."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test2",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Light initial off
    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.state == "off"

    # Turn on with brightness
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.fansync_light", "brightness": 128}, blocking=True
    )
    await hass.async_block_till_done()
    state = hass.states.get("light.fansync_light")
    assert state.state == "on"
    # rounding differences (128 maps to 50.2% => 128 or 127). Accept within 1.
    assert abs(state.attributes.get("brightness") - 128) <= 1


async def test_light_availability(hass: HomeAssistant, patch_client) -> None:
    """Test light entity availability based on device data presence."""
    from custom_components.fansync import DOMAIN

    # Create config entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Initially available (device data exists)
    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.state != "unavailable"

    # Get coordinator and simulate device data missing
    coordinator = entry.runtime_data["coordinator"]
    coordinator.async_set_updated_data({})  # Empty data, device_id not present
    await hass.async_block_till_done()

    # Entity should be unavailable when device data is missing
    state = hass.states.get("light.fansync_light")
    assert state.state == "unavailable"

    # Restore device data (using the correct device_id from the fixture)
    coordinator.async_set_updated_data({"test-device": {"lightPower": 0, "lightBrightness": 0}})
    await hass.async_block_till_done()

    # Entity should be available again
    state = hass.states.get("light.fansync_light")
    assert state.state != "unavailable"
