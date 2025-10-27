# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import asyncio
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


class DelayedClient:
    def __init__(self):
        # No light keys to avoid creating a light entity
        self.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0}
        self.device_id = "retry-device"
        self._get_calls = 0
        self._pending: dict[str, int] | None = None

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self):
        self._get_calls += 1
        # Apply pending update on the second get call
        if self._pending and self._get_calls >= 2:
            self.status.update(self._pending)
            self._pending = None
        return self.status

    async def async_set(self, data: dict[str, int]):
        # Do not update immediately; wait until next get
        self._pending = dict(data)


async def setup_entry_with_client(hass: HomeAssistant, client: DelayedClient):
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="retry-test",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.fan.FanSyncClient", return_value=client), \
         patch("custom_components.fansync.light.FanSyncClient", return_value=client), \
         patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_retry_turn_off_updates_ui(hass: HomeAssistant, monkeypatch):
    client = DelayedClient()

    async def fast_sleep(_):
        return None

    monkeypatch.setattr("custom_components.fansync.fan.asyncio.sleep", fast_sleep)
    await setup_entry_with_client(hass, client)

    await hass.services.async_call("fan", "turn_off", {"entity_id": "fan.fan"}, blocking=True)
    await hass.async_block_till_done()

    state = hass.states.get("fan.fan")
    assert state.state == "off"
    # preserves prior speed (20 from DelayedClient)
    assert state.attributes.get("percentage") == 20


async def test_retry_set_percentage_updates_ui(hass: HomeAssistant, monkeypatch):
    client = DelayedClient()

    async def fast_sleep(_):
        return None

    monkeypatch.setattr("custom_components.fansync.fan.asyncio.sleep", fast_sleep)
    await setup_entry_with_client(hass, client)

    await hass.services.async_call(
        "fan",
        "set_percentage",
        {"entity_id": "fan.fan", "percentage": 55},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get("fan.fan")
    assert state.attributes.get("percentage") == 55


async def test_retry_set_direction_updates_ui(hass: HomeAssistant, monkeypatch):
    client = DelayedClient()

    async def fast_sleep(_):
        return None

    monkeypatch.setattr("custom_components.fansync.fan.asyncio.sleep", fast_sleep)
    await setup_entry_with_client(hass, client)

    await hass.services.async_call(
        "fan",
        "set_direction",
        {"entity_id": "fan.fan", "direction": "reverse"},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get("fan.fan")
    assert state.attributes.get("direction") == "reverse"


