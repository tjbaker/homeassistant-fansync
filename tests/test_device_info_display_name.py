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
from pytest_homeassistant_custom_component.common import MockConfigEntry


class NameClient:
    def __init__(self):
        self.device_ids = ["alpha"]
        self.device_id = "alpha"
        self.status = {"H00": 1, "H02": 10, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
        self._props = {"alpha": {"displayName": "Bedroom Fan"}}

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id: str | None = None):
        return dict(self.status)

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        self.status.update(data)

    def device_display_name(self, device_id: str) -> str | None:
        d = self._props.get(device_id, {})
        n = d.get("displayName")
        return n if isinstance(n, str) else None


async def test_device_info_uses_display_name(hass: HomeAssistant):
    client = NameClient()
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="namez",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    e_registry = er.async_get(hass)
    d_registry = dr.async_get(hass)

    # Find one of our entities and then its device
    ent = next(
        e
        for e in e_registry.entities.values()
        if e.platform == "fansync" and e.domain in {"fan", "light"}
    )
    dev = d_registry.async_get(ent.device_id)
    assert dev is not None
    assert dev.manufacturer == "Fanimation"
    assert dev.name == "Bedroom Fan"
