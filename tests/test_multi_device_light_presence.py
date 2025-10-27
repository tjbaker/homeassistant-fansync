# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


class LightPresenceClient:
    def __init__(self):
        self.device_ids = ["with_light", "no_light"]
        self.device_id = "with_light"
        self.status_by_id = {
            "with_light": {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 1, "H0C": 40},
            "no_light": {"H00": 1, "H02": 30, "H06": 0, "H01": 0},
        }

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id: str | None = None):
        if device_id is None:
            return dict(self.status_by_id[self.device_id])
        return dict(self.status_by_id.get(device_id, {}))

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        did = device_id or self.device_id
        self.status_by_id[did].update(data)


async def test_only_devices_with_light_create_light_entities(hass: HomeAssistant):
    client = LightPresenceClient()
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="light-presence",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    light_entries = [
        e for e in registry.entities.values() if e.platform == "fansync" and e.domain == "light"
    ]

    # Exactly one light entity should be present (for with_light)
    assert len(light_entries) == 1
    assert light_entries[0].unique_id.startswith("fansync_with_light_light")
