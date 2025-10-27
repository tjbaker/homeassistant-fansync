# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


class ClientWithCallback:
    def __init__(self):
        self.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0}
        self.device_id = "setup-device"
        self._cb = None
        self.connected = False
        self.disconnected = False

    async def async_connect(self):
        self.connected = True

    async def async_disconnect(self):
        self.disconnected = True

    async def async_get_status(self):
        return dict(self.status)

    async def async_set(self, data):
        self.status.update(data)

    def set_status_callback(self, cb):
        self._cb = cb


async def test_setup_registers_callback_and_unload_disconnects(hass: HomeAssistant):
    client = ClientWithCallback()
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="setup-test",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Fan entity should exist and reflect initial status
    state = hass.states.get("fan.fan")
    assert state is not None
    assert state.attributes.get("percentage") == 20
    # Ensure callback was registered
    assert client._cb is not None

    # Trigger push status
    client._cb({"H00": 1, "H02": 55, "H06": 0, "H01": 0})  # type: ignore[misc]
    await hass.async_block_till_done()
    state = hass.states.get("fan.fan")
    assert state.attributes.get("percentage") == 55

    # Unload entry should disconnect client
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert client.disconnected is True


