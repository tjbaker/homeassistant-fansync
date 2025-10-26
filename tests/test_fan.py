# SPDX-License-Identifier: GPL-2.0-only
# Copyright 2025 Trevor Baker, all rights reserved.

"""End-to-end fan entity lifecycle tests.

Covers entity creation, basic state validation, and service calls for turning
off and setting a new percentage speed.
"""
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "fansync"

async def test_fan_entity_lifecycle(hass: HomeAssistant, patch_client):
    """Create fan entity and exercise turn_off and set_percentage services."""
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

    # Fan state
    state = hass.states.get("fan.fan")
    assert state is not None
    assert state.state == "on"
    assert state.attributes.get("percentage") == 41

    # Turn off
    await hass.services.async_call("fan", "turn_off", {"entity_id": "fan.fan"}, blocking=True)
    await hass.async_block_till_done()
    state = hass.states.get("fan.fan")
    assert state.state == "off"

    # Set percentage
    await hass.services.async_call("fan", "set_percentage", {"entity_id": "fan.fan", "percentage": 20}, blocking=True)
    await hass.async_block_till_done()
    state = hass.states.get("fan.fan")
    assert state.attributes.get("percentage") == 20
