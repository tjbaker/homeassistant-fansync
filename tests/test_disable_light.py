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

"""Per-device 'Fan has no light' option suppresses the phantom light entity."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.const import (
    OPTION_DISABLE_LIGHT,
    OPTION_LIGHTLESS_DEVICES,
    resolve_lightless_devices,
)


class LightClient:
    """Multi-device client where every device reports a light channel."""

    def __init__(self, device_ids: list[str]):
        self.device_ids = list(device_ids)
        self.device_id = device_ids[0]
        self.status_by_id = {
            d: {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 1, "H0C": 50} for d in device_ids
        }

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id: str | None = None):
        did = device_id or self.device_ids[0]
        return dict(self.status_by_id.get(did, {}))

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        self.status_by_id.get(device_id or self.device_id, {}).update(data)

    def set_status_callback(self, cb):
        self._cb = cb


async def _setup(hass: HomeAssistant, client: LightClient, options: dict) -> None:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        options=options,
        unique_id="lightless",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def _light_devices(hass: HomeAssistant) -> set[str]:
    """device_ids that have a light entity (unique_id = fansync_<did>_light)."""
    reg = er.async_get(hass)
    out = set()
    for e in reg.entities.values():
        if e.platform == "fansync" and e.domain == "light" and e.unique_id:
            out.add(e.unique_id[len("fansync_") : -len("_light")])
    return out


async def test_light_created_by_default(hass: HomeAssistant) -> None:
    await _setup(hass, LightClient(["dev1"]), options={})
    assert _light_devices(hass) == {"dev1"}


async def test_lightless_device_hides_only_its_light(hass: HomeAssistant) -> None:
    await _setup(hass, LightClient(["dev1"]), options={OPTION_LIGHTLESS_DEVICES: ["dev1"]})
    assert _light_devices(hass) == set()


async def test_per_device_selection_in_multi_fan_household(hass: HomeAssistant) -> None:
    """dev1 marked lightless keeps dev2's light — the core multi-fan fix."""
    await _setup(hass, LightClient(["dev1", "dev2"]), options={OPTION_LIGHTLESS_DEVICES: ["dev1"]})
    assert _light_devices(hass) == {"dev2"}


async def test_legacy_account_wide_bool_migrates_to_all(hass: HomeAssistant) -> None:
    """The 0.8.0 account-wide disable_light=True migrates to every device."""
    await _setup(hass, LightClient(["dev1", "dev2"]), options={OPTION_DISABLE_LIGHT: True})
    assert _light_devices(hass) == set()


def test_resolve_lightless_devices() -> None:
    ids = ["a", "b", "c"]
    # Per-device list wins.
    assert resolve_lightless_devices({OPTION_LIGHTLESS_DEVICES: ["a", "c"]}, ids) == {"a", "c"}
    # Empty list means "none", even if the legacy bool is set.
    assert (
        resolve_lightless_devices({OPTION_LIGHTLESS_DEVICES: [], OPTION_DISABLE_LIGHT: True}, ids)
        == set()
    )
    # Legacy bool with no list migrates to all known devices.
    assert resolve_lightless_devices({OPTION_DISABLE_LIGHT: True}, ids) == {"a", "b", "c"}
    # Nothing set -> none.
    assert resolve_lightless_devices({}, ids) == set()
