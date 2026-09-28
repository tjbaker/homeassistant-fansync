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

"""Per-fan "Light installed" configuration switch.

The lightless option used to live only in the integration's Configure form,
which is hard to find. The switch surfaces it on each fan's device page and
writes the same option, so the two stay in sync.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.const import OPTION_LIGHTLESS_DEVICES


class MetaLightClient:
    def __init__(self, device_ids: list[str], metadata: dict[str, dict] | None = None):
        self.device_ids = list(device_ids)
        self.device_id = device_ids[0]
        self._metadata = metadata or {}
        self.status_by_id = {
            d: {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 1, "H0C": 50} for d in device_ids
        }

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id: str | None = None):
        return dict(self.status_by_id.get(device_id or self.device_ids[0], {}))

    async def async_set(self, data, *, device_id: str | None = None):
        self.status_by_id.get(device_id or self.device_id, {}).update(data)

    def set_status_callback(self, cb):
        self._cb = cb

    def device_metadata(self, device_id: str) -> dict:
        return self._metadata.get(device_id, {})


async def _setup(hass: HomeAssistant, client: MetaLightClient, options: dict) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        options=options,
        unique_id="light-installed-switch",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, domain: str, device_id: str, suffix: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        domain, "fansync", f"fansync_{device_id}_{suffix}"
    )


async def _call(hass: HomeAssistant, service: str, entity_id: str, client) -> None:
    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.services.async_call("switch", service, {"entity_id": entity_id}, blocking=True)
        await hass.async_block_till_done()


async def test_switch_exists_per_fan_as_config_entity_and_defaults_on(hass: HomeAssistant) -> None:
    client = MetaLightClient(["dev1", "dev2"])
    await _setup(hass, client, options={})

    for did in ("dev1", "dev2"):
        entity_id = _entity_id(hass, "switch", did, "light_installed")
        assert entity_id is not None
        entry = er.async_get(hass).async_get(entity_id)
        assert entry is not None and entry.entity_category == EntityCategory.CONFIG
        assert hass.states.get(entity_id).state == "on"
        assert _entity_id(hass, "light", did, "light") is not None


async def test_turning_off_hides_that_fans_light_only(hass: HomeAssistant) -> None:
    client = MetaLightClient(["dev1", "dev2"])
    entry = await _setup(hass, client, options={})

    await _call(hass, "turn_off", _entity_id(hass, "switch", "dev1", "light_installed"), client)

    assert entry.options[OPTION_LIGHTLESS_DEVICES] == ["dev1"]
    assert hass.states.get(_entity_id(hass, "switch", "dev1", "light_installed")).state == "off"
    assert hass.states.get(_entity_id(hass, "switch", "dev2", "light_installed")).state == "on"
    assert _entity_id(hass, "light", "dev1", "light") is None
    assert _entity_id(hass, "light", "dev2", "light") is not None


async def test_turning_on_restores_the_light(hass: HomeAssistant) -> None:
    client = MetaLightClient(["dev1"])
    entry = await _setup(hass, client, options={OPTION_LIGHTLESS_DEVICES: ["dev1"]})
    switch = _entity_id(hass, "switch", "dev1", "light_installed")
    assert hass.states.get(switch).state == "off"
    assert _entity_id(hass, "light", "dev1", "light") is None

    await _call(hass, "turn_on", switch, client)

    assert entry.options[OPTION_LIGHTLESS_DEVICES] == []
    assert hass.states.get(switch).state == "on"
    assert _entity_id(hass, "light", "dev1", "light") is not None


async def test_cloud_flagged_fan_is_off_and_cannot_be_turned_on(hass: HomeAssistant) -> None:
    client = MetaLightClient(["dev1"], metadata={"dev1": {"properties": {"hideLightDimmer": True}}})
    entry = await _setup(hass, client, options={})
    switch = _entity_id(hass, "switch", "dev1", "light_installed")
    assert hass.states.get(switch).state == "off"

    with pytest.raises(HomeAssistantError):
        await _call(hass, "turn_on", switch, client)
    # turning off a cloud-flagged fan records nothing; the flag already hides it
    await _call(hass, "turn_off", switch, client)
    assert OPTION_LIGHTLESS_DEVICES not in entry.options
