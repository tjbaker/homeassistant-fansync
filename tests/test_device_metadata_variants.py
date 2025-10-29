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
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from pytest_homeassistant_custom_component.common import MockConfigEntry


class BaseClient:
    device_ids: list[str]
    device_id: str
    status: dict[str, int]

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id: str | None = None):
        return dict(self.status)

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        self.status.update(data)


class MetaSingleClient(BaseClient):
    def __init__(self):
        self.device_ids = ["alpha"]
        self.device_id = "alpha"
        self.status = {"H00": 1, "H02": 10}
        self._profile = {
            "alpha": {
                "module": {
                    "firmware_version": "1.7.1",
                    "local_ip": "192.0.2.10",
                    "mac_address": "AA:BB:CC:DD:EE:FF",
                },
                "esh": {"brand": "Fanimation", "model": "OdynCustom-FDR1L2"},
            }
        }

    def device_profile(self, device_id: str):
        return self._profile.get(device_id, {})


class MetaMissingClient(BaseClient):
    def __init__(self):
        self.device_ids = ["alpha"]
        self.device_id = "alpha"
        self.status = {"H00": 1}
        self._profile = {"alpha": {}}  # missing module/esh keys

    def device_profile(self, device_id: str):
        return self._profile.get(device_id, {})


class MetaMultiClient(BaseClient):
    def __init__(self):
        self.device_ids = ["alpha", "beta"]
        self.device_id = "alpha"
        self.status = {"H00": 1}
        self._profile = {
            "alpha": {
                "module": {
                    "firmware_version": "1.7.1",
                    "local_ip": "192.0.2.10",
                    "mac_address": "AA:BB:CC:DD:EE:FF",
                },
                "esh": {"brand": "Fanimation", "model": "GlideAire-FDR1L0"},
            },
            "beta": {
                "module": {
                    "firmware_version": "1.6.0",
                    "local_ip": "192.0.2.11",
                    "mac_address": "11:22:33:44:55:66",
                },
                "esh": {"brand": "Fanimation", "model": "OdynCustom-FDR1L2"},
            },
        }

    def device_profile(self, device_id: str):
        return self._profile.get(device_id, {})


async def test_attributes_and_connections_single(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="attr1",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.fansync.FanSyncClient", return_value=MetaSingleClient()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    e_registry = er.async_get(hass)
    d_registry = dr.async_get(hass)

    fan_ent = next(
        e for e in e_registry.entities.values() if e.platform == "fansync" and e.domain == "fan"
    )
    dev = d_registry.async_get(fan_ent.device_id)
    assert dev is not None
    assert dev.model == "OdynCustom-FDR1L2"
    assert dev.sw_version == "1.7.1"
    assert (CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff") in dev.connections

    # Check state attributes for IP and MAC
    state = hass.states.get(fan_ent.entity_id)
    assert state is not None
    assert state.attributes.get("local_ip") == "192.0.2.10"
    assert state.attributes.get("mac_address") == "aa:bb:cc:dd:ee:ff"


async def test_missing_profile_fallbacks(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="attr2",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.fansync.FanSyncClient", return_value=MetaMissingClient()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    e_registry = er.async_get(hass)
    d_registry = dr.async_get(hass)
    fan_ent = next(
        e for e in e_registry.entities.values() if e.platform == "fansync" and e.domain == "fan"
    )
    dev = d_registry.async_get(fan_ent.device_id)
    assert dev is not None
    assert dev.model == "FanSync"  # default
    assert dev.sw_version is None
    # No attributes when module keys missing
    state = hass.states.get(fan_ent.entity_id)
    assert state is not None
    assert "local_ip" not in state.attributes
    assert "mac_address" not in state.attributes


async def test_multi_device_isolation(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="attr3",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.fansync.FanSyncClient", return_value=MetaMultiClient()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    e_registry = er.async_get(hass)
    d_registry = dr.async_get(hass)
    fans = [
        e for e in e_registry.entities.values() if e.platform == "fansync" and e.domain == "fan"
    ]
    assert len(fans) >= 2  # both devices should create fan entities
    # Validate we surface metadata across devices
    ips = set()
    macs = set()
    for ent in fans:
        dev = d_registry.async_get(ent.device_id)
        assert dev is not None
        state = hass.states.get(ent.entity_id)
        assert state is not None
        ip = state.attributes.get("local_ip")
        if isinstance(ip, str):
            ips.add(ip)
        for conn in dev.connections:
            if conn[0] == CONNECTION_NETWORK_MAC:
                macs.add(conn[1])
    # At minimum one IP and both MACs should be present in registry connections
    assert len(ips) >= 1
    assert {"aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"}.issubset(macs)
