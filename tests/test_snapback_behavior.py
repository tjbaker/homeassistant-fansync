# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import time
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.const import OPTIMISTIC_GUARD_SEC, pct_to_ha_brightness


class SnapbackClient:
    def __init__(self):
        # Provide both fan and light keys in status for initial entity creation
        self.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 1, "H0C": 20}
        self.device_ids = ["dev"]
        self.device_id = "dev"
        self._cb = None

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id=None):
        return dict(self.status)

    async def async_set(self, data, *, device_id=None):
        # Do not call callback here to simulate slow/absent confirm from backend
        # Status remains whatever the coordinator applied optimistically
        self.status.update(data)

    def set_status_callback(self, cb):
        self._cb = cb


async def setup(hass: HomeAssistant, client: SnapbackClient) -> None:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="snapback",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def make_fake_monotonic(base: float):
    def _fake():
        return _fake.t

    _fake.t = base  # type: ignore[attr-defined]
    return _fake


async def test_fan_snapback_after_guard_expiry(hass: HomeAssistant):
    client = SnapbackClient()
    await setup(hass, client)

    base = time.monotonic()
    fake_monotonic = make_fake_monotonic(base)

    # Initiate optimistic change to 55%
    with patch(
        "custom_components.fansync.fan.time.monotonic", side_effect=lambda: fake_monotonic()
    ):
        await hass.services.async_call(
            "fan",
            "set_percentage",
            {"entity_id": "fan.fan", "percentage": 55},
            blocking=True,
        )
        # During guard, optimistic state should be shown
        state = hass.states.get("fan.fan")
        assert state.attributes.get("percentage") == 55

        # Advance time beyond guard window, then push old backend state (20%)
        fake_monotonic.t = base + OPTIMISTIC_GUARD_SEC + 1.0  # type: ignore[attr-defined]
        if client._cb:
            client._cb({"H00": 1, "H02": 20, "H06": 0, "H01": 0})
        await hass.async_block_till_done()

        # After guard expiry and a non-confirming update, UI should reflect backend (snap-back)
        state = hass.states.get("fan.fan")
        assert state.attributes.get("percentage") == 20


async def test_light_snapback_after_guard_expiry(hass: HomeAssistant):
    client = SnapbackClient()
    await setup(hass, client)

    base = time.monotonic()
    fake_monotonic = make_fake_monotonic(base)

    # Initiate optimistic light on with brightness ~50%
    with patch(
        "custom_components.fansync.light.time.monotonic", side_effect=lambda: fake_monotonic()
    ):
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": "light.light", "brightness": 128},
            blocking=True,
        )
        state = hass.states.get("light.light")
        assert state.attributes.get("brightness") is not None

        # Advance beyond guard window and push old brightness (20%)
        fake_monotonic.t = base + OPTIMISTIC_GUARD_SEC + 1.0  # type: ignore[attr-defined]
        if client._cb:
            client._cb({"H0B": 1, "H0C": 20})
        await hass.async_block_till_done()

        state = hass.states.get("light.light")
        assert state.attributes.get("brightness") == pct_to_ha_brightness(20)
