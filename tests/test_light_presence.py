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
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.const import DOMAIN


def _make_client(status: dict[str, object], device_id: str):
    class _Client:
        def __init__(self, s: dict[str, object], did: str):
            self.status = s
            self.device_id = did

        async def async_connect(self):
            return None

        async def async_disconnect(self):
            return None

        async def async_get_status(self, device_id: str | None = None):
            return self.status

    return _Client(status, device_id)


async def test_light_not_created_when_no_light_keys(hass: HomeAssistant):
    """Do not create light entity if device exposes no light fields."""
    client = _make_client({"H00": 1, "H02": 41, "H06": 0, "H01": 0}, "no-light-device")

    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="no-light-test",
    )
    entry.add_to_hass(hass)

    # Patch both platform imports to use our mock client
    with (
        patch("custom_components.fansync.fan.FanSyncClient", return_value=client),
        patch("custom_components.fansync.light.FanSyncClient", return_value=client),
        patch("custom_components.fansync.FanSyncClient", return_value=client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Fan should exist, light should not
    assert hass.states.get("fan.fansync_fan") is not None
    assert hass.states.get("light.fansync_light") is None


async def test_platforms_stored_and_forwarded_without_light(hass: HomeAssistant, monkeypatch):
    """Platforms should be ['fan'] and forward excludes light when no light keys present."""

    client = _make_client({"H00": 1, "H02": 41, "H06": 0, "H01": 0}, "dev-no-light")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="plat-no-light",
    )
    entry.add_to_hass(hass)

    calls: list[list[str]] = []
    orig = hass.config_entries.async_forward_entry_setups

    async def _spy_forward(e, platforms: list[str]):
        calls.append(platforms)
        return await orig(e, platforms)

    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", _spy_forward)

    with (
        patch("custom_components.fansync.fan.FanSyncClient", return_value=client),
        patch("custom_components.fansync.light.FanSyncClient", return_value=client),
        patch("custom_components.fansync.FanSyncClient", return_value=client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    stored = entry.runtime_data["platforms"]
    assert stored == ["fan"]
    assert calls and calls[-1] == ["fan"]


async def test_platforms_stored_and_forwarded_with_light(hass: HomeAssistant, monkeypatch):
    """Platforms should include light when light keys present."""

    client = _make_client(
        {"H00": 1, "H02": 41, "H06": 0, "H01": 0, "H0B": 1, "H0C": 50},
        "dev-with-light",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="plat-with-light",
    )
    entry.add_to_hass(hass)

    calls: list[list[str]] = []
    orig = hass.config_entries.async_forward_entry_setups

    async def _spy_forward(e, platforms: list[str]):
        calls.append(platforms)
        return await orig(e, platforms)

    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", _spy_forward)

    with (
        patch("custom_components.fansync.fan.FanSyncClient", return_value=client),
        patch("custom_components.fansync.light.FanSyncClient", return_value=client),
        patch("custom_components.fansync.FanSyncClient", return_value=client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    stored = entry.runtime_data["platforms"]
    assert stored == ["fan", "light"]
    assert calls and calls[-1] == ["fan", "light"]


async def test_platforms_fallback_when_first_refresh_deferred(hass: HomeAssistant, monkeypatch):
    """When first refresh defers, platforms should fall back to all PLATFORMS."""

    client = _make_client({"H00": 1, "H02": 41}, "dev")

    # Fake coordinator that simulates first refresh timeout and no data yet
    class _FakeCoordinator:
        def __init__(self, hass, c, config_entry):
            self.hass = hass
            self.client = c
            self.config_entry = config_entry
            self.data = None

        def _update_device_registry(self, device_ids: list[str]) -> None:
            """Stub for device registry update (no-op in this test)."""
            pass

        async def async_config_entry_first_refresh(self):
            raise TimeoutError()

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="plat-deferred",
    )
    entry.add_to_hass(hass)

    calls: list[list[str]] = []
    orig = hass.config_entries.async_forward_entry_setups

    async def _spy_forward(e, platforms: list[str]):
        calls.append(platforms)
        return await orig(e, platforms)

    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", _spy_forward)

    with (
        patch("custom_components.fansync.FanSyncCoordinator", _FakeCoordinator),
        patch("custom_components.fansync.fan.FanSyncClient", return_value=client),
        patch("custom_components.fansync.light.FanSyncClient", return_value=client),
        patch("custom_components.fansync.FanSyncClient", return_value=client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    stored = entry.runtime_data["platforms"]
    assert stored == ["fan", "light"]
    assert calls and calls[-1] == ["fan", "light"]
