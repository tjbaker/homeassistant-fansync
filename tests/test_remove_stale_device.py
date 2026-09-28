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

"""Deleting a stale device from the device page.

A fan that is no longer in the Fanimation account stays in the device
registry with no entities. Home Assistant only offers "Delete device" when
the integration implements async_remove_config_entry_device, which permits
removal for devices the account no longer lists and refuses it for live ones.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync import async_remove_config_entry_device
from custom_components.fansync.const import DOMAIN


async def _setup(hass: HomeAssistant, mock_client) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="remove-stale",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.FanSyncClient", return_value=mock_client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_stale_device_can_be_deleted_but_live_one_cannot(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    entry = await _setup(hass, mock_client)
    registry = dr.async_get(hass)

    live = registry.async_get_device_by_identifier((DOMAIN, mock_client.device_id), entry.entry_id)
    assert live is not None
    assert await async_remove_config_entry_device(hass, entry, live) is False

    stale = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "old-house-fan")}
    )
    assert await async_remove_config_entry_device(hass, entry, stale) is True

    # this is what HA does after a True: remove the device
    registry.async_remove_device(stale.id)
    assert registry.async_get(stale.id) is None
    assert registry.async_get(live.id) is not None


async def test_removal_refused_when_entry_is_not_loaded(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="not-loaded")
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "whatever")}
    )
    assert await async_remove_config_entry_device(hass, entry, device) is False
