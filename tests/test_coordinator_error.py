# SPDX-License-Identifier: GPL-2.0-only
# Copyright 2025 Trevor Baker, all rights reserved.

"""Update coordinator error path tests.

Forces the client status call to raise and verifies setup proceeds without
crashing, exercising error handling in the coordinator update path.
"""
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "fansync"

async def test_coordinator_update_failed(hass: HomeAssistant, patch_client):
    """Coordinator update raises; setup continues and does not crash."""
    # Force client to raise
    async def _raise():
        raise RuntimeError("boom")
    patch_client.async_get_status = _raise

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test8",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
