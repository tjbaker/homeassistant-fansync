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

"""The 'Fan has no light' option suppresses the phantom light entity."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.const import OPTION_DISABLE_LIGHT


class LightCapableClient:
    """Single device that reports a light channel (H0B/H0C)."""

    def __init__(self):
        self.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 1, "H0C": 50}
        self.device_ids = ["dev"]
        self.device_id = "dev"

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id: str | None = None):
        return dict(self.status)

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        self.status.update(data)

    def set_status_callback(self, cb):
        self._cb = cb


async def _setup(hass: HomeAssistant, options: dict) -> None:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        options=options,
        unique_id="disable-light",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.FanSyncClient", return_value=LightCapableClient()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def _entities(hass: HomeAssistant, domain: str) -> list[str]:
    reg = er.async_get(hass)
    return [
        e.entity_id for e in reg.entities.values() if e.platform == "fansync" and e.domain == domain
    ]


async def test_light_created_by_default(hass: HomeAssistant) -> None:
    """Without the option, a light-capable device gets a light entity."""
    await _setup(hass, options={})
    assert len(_entities(hass, "fan")) == 1
    assert len(_entities(hass, "light")) == 1


async def test_disable_light_suppresses_light_entity(hass: HomeAssistant) -> None:
    """With disable_light=True, the light entity is not created (fan still is)."""
    await _setup(hass, options={OPTION_DISABLE_LIGHT: True})
    assert len(_entities(hass, "fan")) == 1
    assert len(_entities(hass, "light")) == 0
