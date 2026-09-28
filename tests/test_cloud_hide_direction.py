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

"""Auto-hide of the direction control on fans the cloud marks not reversible.

Issue #228: the Fanimation app sets ``properties.hideFanDirection: true`` on
devices whose owner told it the fan cannot reverse. That is trusted as a "no
direction" signal; absence or false changes nothing.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.components.fan import ATTR_DIRECTION, FanEntityFeature
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.device_utils import cloud_no_direction_devices


class MetaFanClient:
    """Multi-device client with per-device cloud metadata."""

    def __init__(self, device_ids: list[str], metadata: dict[str, dict] | None = None):
        self.device_ids = list(device_ids)
        self.device_id = device_ids[0]
        self._metadata = metadata or {}
        self.status_by_id = {d: {"H00": 1, "H02": 20, "H06": 0, "H01": 0} for d in device_ids}

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


async def _setup(hass: HomeAssistant, client: MetaFanClient) -> None:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="cloud-hide-direction",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def test_cloud_no_direction_devices_trusts_only_true() -> None:
    """Only hideFanDirection=true marks a device; false/absent/missing do not."""
    client = MetaFanClient(
        ["tagged", "explicit_false", "untagged", "no_meta"],
        metadata={
            "tagged": {"properties": {"hideFanDirection": True}},
            "explicit_false": {"properties": {"hideFanDirection": False}},
            "untagged": {"properties": {"displayName": "Fan"}},
        },
    )
    assert cloud_no_direction_devices(client, client.device_ids) == {"tagged"}


def test_cloud_no_direction_devices_tolerates_broken_client() -> None:
    """A client without device_metadata (or raising) yields no detections."""

    class NoMeta:
        pass

    class Raises:
        def device_metadata(self, device_id: str) -> dict:
            raise RuntimeError("boom")

    assert cloud_no_direction_devices(NoMeta(), ["dev1"]) == set()
    assert cloud_no_direction_devices(Raises(), ["dev1"]) == set()


async def test_tagged_device_loses_direction_feature(hass: HomeAssistant) -> None:
    """hideFanDirection=true drops DIRECTION and the direction attribute for that fan only."""
    client = MetaFanClient(
        ["dev1", "dev2"],
        metadata={"dev1": {"properties": {"hideFanDirection": True}}},
    )
    await _setup(hass, client)

    states = {s.entity_id: s for s in hass.states.async_all("fan")}
    assert len(states) == 2
    by_dir = {
        bool(s.attributes[ATTR_SUPPORTED_FEATURES] & FanEntityFeature.DIRECTION): s
        for s in states.values()
    }
    assert set(by_dir) == {True, False}, "expected one fan with and one without DIRECTION"

    hidden = by_dir[False]
    assert ATTR_DIRECTION not in hidden.attributes
    assert hidden.attributes[ATTR_SUPPORTED_FEATURES] & FanEntityFeature.SET_SPEED

    kept = by_dir[True]
    assert kept.attributes[ATTR_DIRECTION] == "forward"


async def test_false_or_absent_flag_keeps_direction(hass: HomeAssistant) -> None:
    """Devices with hideFanDirection=false or no metadata keep the direction control."""
    client = MetaFanClient(
        ["dev1", "dev2"],
        metadata={"dev1": {"properties": {"hideFanDirection": False}}},
    )
    await _setup(hass, client)

    for state in hass.states.async_all("fan"):
        assert state.attributes[ATTR_SUPPORTED_FEATURES] & FanEntityFeature.DIRECTION
        assert state.attributes[ATTR_DIRECTION] == "forward"
