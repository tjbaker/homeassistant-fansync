# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Trevor Baker, all rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#   http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


class MultiDeviceClient:
    def __init__(self):
        # dev1 has a light; dev2 is fan-only
        self.status_by_id: dict[str, dict[str, int]] = {
            "dev1": {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 1, "H0C": 50},
            "dev2": {"H00": 1, "H02": 30, "H06": 0, "H01": 0},
        }
        self.device_ids = ["dev1", "dev2"]
        self.device_id = "dev1"
        self._cb = None

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id: str | None = None):
        if device_id is None:
            # Fallback for compatibility; return first device
            return dict(self.status_by_id[self.device_ids[0]])
        return dict(self.status_by_id.get(device_id, {}))

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        did = device_id or self.device_id
        self.status_by_id[did].update(data)

    def set_status_callback(self, cb):
        self._cb = cb


async def setup_entry_with_client(
    hass: HomeAssistant, client: MultiDeviceClient
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="multi-device",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_multi_device_entities_created(hass: HomeAssistant):
    client = MultiDeviceClient()
    await setup_entry_with_client(hass, client)

    registry = er.async_get(hass)
    fan_entries = [
        e for e in registry.entities.values() if e.platform == "fansync" and e.domain == "fan"
    ]
    light_entries = [
        e for e in registry.entities.values() if e.platform == "fansync" and e.domain == "light"
    ]

    assert len(fan_entries) == 2
    assert len(light_entries) == 1

    # Resolve entity_ids
    fan_entity_ids = [e.entity_id for e in fan_entries]
    light_entity_ids = [e.entity_id for e in light_entries]

    # States exist
    for eid in fan_entity_ids:
        assert hass.states.get(eid) is not None
    for eid in light_entity_ids:
        assert hass.states.get(eid) is not None


async def test_multi_device_control_isolated(hass: HomeAssistant):
    client = MultiDeviceClient()
    await setup_entry_with_client(hass, client)

    registry = er.async_get(hass)
    fan_entries = [
        e for e in registry.entities.values() if e.platform == "fansync" and e.domain == "fan"
    ]
    # Map entity_ids by device id using unique_id suffix
    by_device: dict[str, str] = {}
    for e in fan_entries:
        # unique_id format: fansync_<device_id>_fan
        if e.unique_id and e.unique_id.startswith("fansync_") and e.unique_id.endswith("_fan"):
            did = e.unique_id[len("fansync_") : -len("_fan")]
            by_device[did] = e.entity_id

    dev1_eid = by_device["dev1"]
    dev2_eid = by_device["dev2"]

    # Precondition percentages
    assert hass.states.get(dev1_eid).attributes.get("percentage") == 20
    assert hass.states.get(dev2_eid).attributes.get("percentage") == 30

    # Change dev1 to 55%; dev2 should remain at 30%
    await hass.services.async_call(
        "fan",
        "set_percentage",
        {"entity_id": dev1_eid, "percentage": 55},
        blocking=True,
    )

    assert hass.states.get(dev1_eid).attributes.get("percentage") == 55
    assert hass.states.get(dev2_eid).attributes.get("percentage") == 30


class SingleDeviceListClient:
    """Client that exposes empty device_ids to exercise fallback single-device path."""

    def __init__(self):
        self.status = {"H00": 1, "H02": 25, "H06": 0, "H01": 0}
        self.device_ids: list[str] = []
        self.device_id = "only"

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id: str | None = None):
        return dict(self.status)

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        self.status.update(data)


async def test_single_device_fallback_still_works(hass: HomeAssistant):
    client = SingleDeviceListClient()
    await setup_entry_with_client(hass, client)  # type: ignore[arg-type]

    registry = er.async_get(hass)
    fan_entries = [
        e for e in registry.entities.values() if e.platform == "fansync" and e.domain == "fan"
    ]
    assert len(fan_entries) == 1

    eid = fan_entries[0].entity_id
    assert hass.states.get(eid).attributes.get("percentage") == 25

    await hass.services.async_call(
        "fan",
        "set_percentage",
        {"entity_id": eid, "percentage": 45},
        blocking=True,
    )
    assert hass.states.get(eid).attributes.get("percentage") == 45
