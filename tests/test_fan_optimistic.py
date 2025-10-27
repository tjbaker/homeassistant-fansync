# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


class FailingClient:
    def __init__(self):
        # Start with fan on at 20%, forward, normal preset
        self.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0}
        self.device_id = "optimistic-fail"

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self):
        return dict(self.status)

    async def async_set(self, data: dict[str, int]):
        # Simulate backend failure
        raise RuntimeError("boom")


async def setup_entry_with_client(hass: HomeAssistant, client) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="optimistic-test",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.fan.FanSyncClient", return_value=client), \
         patch("custom_components.fansync.light.FanSyncClient", return_value=client), \
         patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_set_percentage_reverts_on_error(hass: HomeAssistant):
    client = FailingClient()
    await setup_entry_with_client(hass, client)

    # Precondition
    state = hass.states.get("fan.fan")
    assert state.attributes.get("percentage") == 20

    with pytest.raises(RuntimeError):
        await hass.services.async_call(
            "fan",
            "set_percentage",
            {"entity_id": "fan.fan", "percentage": 55},
            blocking=True,
        )
    await hass.async_block_till_done()

    # After failure, state should be reverted to previous (20%)
    state = hass.states.get("fan.fan")
    assert state.attributes.get("percentage") == 20


async def test_set_direction_reverts_on_error(hass: HomeAssistant):
    client = FailingClient()
    await setup_entry_with_client(hass, client)

    # Precondition
    state = hass.states.get("fan.fan")
    assert state.attributes.get("direction") == "forward"

    with pytest.raises(RuntimeError):
        await hass.services.async_call(
            "fan",
            "set_direction",
            {"entity_id": "fan.fan", "direction": "reverse"},
            blocking=True,
        )
    await hass.async_block_till_done()

    # After failure, state should be reverted to previous (forward)
    state = hass.states.get("fan.fan")
    assert state.attributes.get("direction") == "forward"


