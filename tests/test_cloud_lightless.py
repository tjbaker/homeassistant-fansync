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

"""Auto-hide of lights on devices the cloud marks lightless (issue #199).

The Fanimation app sets ``properties.hideLightDimmer: true`` on devices whose
owner told it no light kit is installed. That is trusted as a "no light"
signal and unioned with the user's explicit per-device option; absence or
false changes nothing.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.const import OPTION_LIGHTLESS_DEVICES
from custom_components.fansync.device_utils import cloud_lightless_devices


class MetaLightClient:
    """Multi-device client with light channels and per-device cloud metadata."""

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
        did = device_id or self.device_ids[0]
        return dict(self.status_by_id.get(did, {}))

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        self.status_by_id.get(device_id or self.device_id, {}).update(data)

    def set_status_callback(self, cb):
        self._cb = cb

    def device_metadata(self, device_id: str) -> dict:
        return self._metadata.get(device_id, {})


async def _setup(hass: HomeAssistant, client: MetaLightClient, options: dict) -> None:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        options=options,
        unique_id="cloud-lightless",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def _light_devices(hass: HomeAssistant) -> set[str]:
    reg = er.async_get(hass)
    out = set()
    for e in reg.entities.values():
        if e.platform == "fansync" and e.domain == "light" and e.unique_id:
            out.add(e.unique_id[len("fansync_") : -len("_light")])
    return out


def test_cloud_lightless_devices_trusts_only_true() -> None:
    """Only hideLightDimmer=true marks a device; false/absent/missing do not."""
    client = MetaLightClient(
        ["tagged", "explicit_false", "untagged", "no_meta"],
        metadata={
            "tagged": {"properties": {"hideLightDimmer": True}},
            "explicit_false": {"properties": {"hideLightDimmer": False}},
            "untagged": {"properties": {"displayName": "Fan"}},
        },
    )
    assert cloud_lightless_devices(client, client.device_ids) == {"tagged"}


def test_cloud_lightless_devices_tolerates_broken_client() -> None:
    """A client without device_metadata (or raising) yields no detections."""

    class NoMeta:
        pass

    class Raises:
        def device_metadata(self, device_id: str) -> dict:
            raise RuntimeError("boom")

    assert cloud_lightless_devices(NoMeta(), ["dev1"]) == set()
    assert cloud_lightless_devices(Raises(), ["dev1"]) == set()


async def test_cloud_tagged_device_gets_no_light_entity(hass: HomeAssistant) -> None:
    """hideLightDimmer=true auto-hides that device's light; others unaffected."""
    client = MetaLightClient(
        ["dev1", "dev2"],
        metadata={"dev1": {"properties": {"hideLightDimmer": True}}},
    )
    await _setup(hass, client, options={})
    assert _light_devices(hass) == {"dev2"}


async def test_cloud_detection_unions_with_manual_option(hass: HomeAssistant) -> None:
    """Cloud-tagged and manually-selected devices are both hidden."""
    client = MetaLightClient(
        ["dev1", "dev2", "dev3"],
        metadata={"dev1": {"properties": {"hideLightDimmer": True}}},
    )
    await _setup(hass, client, options={OPTION_LIGHTLESS_DEVICES: ["dev2"]})
    assert _light_devices(hass) == {"dev3"}


async def test_false_or_absent_flag_keeps_light(hass: HomeAssistant) -> None:
    """Devices with hideLightDimmer=false or no metadata keep their light."""
    client = MetaLightClient(
        ["dev1", "dev2"],
        metadata={"dev1": {"properties": {"hideLightDimmer": False}}},
    )
    await _setup(hass, client, options={})
    assert _light_devices(hass) == {"dev1", "dev2"}
