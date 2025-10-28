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
# Copyright 2025 Trevor Baker, all rights reserved.

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
    state = hass.states.get("light.light")
    assert state is not None
    assert state.state == "off"

    # Turn on with brightness
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.light", "brightness": 128}, blocking=True
    )
    await hass.async_block_till_done()
    state = hass.states.get("light.light")
    assert state.state == "on"
    # rounding differences (128 maps to 50.2% => 128 or 127). Accept within 1.
    assert abs(state.attributes.get("brightness") - 128) <= 1
