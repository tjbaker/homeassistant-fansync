# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


class BranchClient:
    def __init__(self):
        # Fan on 20%, forward, normal; light off
        self.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
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
        # Immediate confirmation path
        self.status.update(data)
        if self._cb:
            self._cb(dict(self.status))

    def set_status_callback(self, cb):
        self._cb = cb


async def setup(hass: HomeAssistant, client: BranchClient) -> None:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="branches",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_fan_turn_on_with_percentage_and_preset(hass: HomeAssistant):
    client = BranchClient()
    client.status.update({"H00": 0})  # start off
    await setup(hass, client)

    await hass.services.async_call(
        "fan",
        "turn_on",
        {"entity_id": "fan.fan", "percentage": 55, "preset_mode": "fresh_air"},
        blocking=True,
    )
    state = hass.states.get("fan.fan")
    assert state.state == "on"
    assert state.attributes.get("percentage") == 55
    assert state.attributes.get("preset_mode") == "fresh_air"


async def test_fan_turn_off_success(hass: HomeAssistant):
    client = BranchClient()
    await setup(hass, client)

    await hass.services.async_call("fan", "turn_off", {"entity_id": "fan.fan"}, blocking=True)
    state = hass.states.get("fan.fan")
    assert state.state == "off"


async def test_fan_set_direction_success(hass: HomeAssistant):
    client = BranchClient()
    await setup(hass, client)

    await hass.services.async_call(
        "fan",
        "set_direction",
        {"entity_id": "fan.fan", "direction": "reverse"},
        blocking=True,
    )
    state = hass.states.get("fan.fan")
    assert state.attributes.get("direction") == "reverse"


async def test_fan_set_preset_mode_success(hass: HomeAssistant):
    client = BranchClient()
    await setup(hass, client)

    await hass.services.async_call(
        "fan",
        "set_preset_mode",
        {"entity_id": "fan.fan", "preset_mode": "fresh_air"},
        blocking=True,
    )
    state = hass.states.get("fan.fan")
    assert state.attributes.get("preset_mode") == "fresh_air"


async def test_light_turn_on_without_brightness(hass: HomeAssistant):
    client = BranchClient()
    await setup(hass, client)

    await hass.services.async_call("light", "turn_on", {"entity_id": "light.light"}, blocking=True)
    state = hass.states.get("light.light")
    assert state.state == "on"


async def test_light_turn_off_success(hass: HomeAssistant):
    client = BranchClient()
    client.status.update({"H0B": 1, "H0C": 50})
    await setup(hass, client)

    await hass.services.async_call("light", "turn_off", {"entity_id": "light.light"}, blocking=True)
    state = hass.states.get("light.light")
    assert state.state == "off"
