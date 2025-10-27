# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


class SimpleClient:
    def __init__(self):
        self.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 1, "H0C": 10}
        self.device_ids = ["dev"]
        self.device_id = "dev"
        self._cb = None

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id: str | None = None):
        return dict(self.status)

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        self.status.update(data)
        if self._cb:
            self._cb(dict(self.status))

    def set_status_callback(self, cb):
        self._cb = cb


async def setup_entry_with_client(hass: HomeAssistant, client: SimpleClient) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="success-paths",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_fan_success_confirm_updates_state(hass: HomeAssistant):
    client = SimpleClient()
    await setup_entry_with_client(hass, client)

    # Increase speed to 50
    await hass.services.async_call(
        "fan",
        "set_percentage",
        {"entity_id": "fan.fan", "percentage": 50},
        blocking=True,
    )
    state = hass.states.get("fan.fan")
    assert state.attributes.get("percentage") == 50
    assert state.attributes.get("preset_mode") == "normal"


async def test_light_success_confirm_updates_state(hass: HomeAssistant):
    client = SimpleClient()
    await setup_entry_with_client(hass, client)

    # Turn light on to 128 (~50%)
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.light", "brightness": 128},
        blocking=True,
    )
    state = hass.states.get("light.light")
    assert state.state == "on"
    assert state.attributes.get("brightness") >= 120
