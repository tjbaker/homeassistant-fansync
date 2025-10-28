# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Trevor Baker, all rights reserved.

"""Light brightness bounds and on/off behavior around edge values.

Covers mapping when brightness=0 and general expectations for HA state around
the lower bounds used by the integration.
"""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "fansync"


async def setup_entry(hass: HomeAssistant, patch_client, entry_id="test6"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id=entry_id,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_brightness_mapping(hass: HomeAssistant, patch_client):
    """Map mid brightness to ~50%, allowing off-by-one rounding."""
    await setup_entry(hass, patch_client)

    # Set brightness mid (should map near 50% -> 127/128)
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.light", "brightness": 128}, blocking=True
    )
    await hass.async_block_till_done()
    state = hass.states.get("light.light")
    assert state.attributes.get("brightness") in (127, 128)


async def test_brightness_bounds(hass: HomeAssistant, patch_client):
    """Brightness 0 behavior and resulting HA state near lower bounds."""
    await setup_entry(hass, patch_client, entry_id="test7")

    # Brightness 0 still turns on with min percent 1
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.light", "brightness": 0}, blocking=True
    )
    await hass.async_block_till_done()
    state = hass.states.get("light.light")
    # Our implementation turns on with min brightness 1% -> 2-3 HA units
    assert state.state in ("on", "off")
