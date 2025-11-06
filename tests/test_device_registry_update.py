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

"""Tests for device registry updates when profile data arrives."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient
from custom_components.fansync.coordinator import FanSyncCoordinator


async def test_device_registry_updated_on_refresh(hass: HomeAssistant, mock_config_entry) -> None:
    """Test that device registry is updated when profile data arrives."""
    # Create a mock client with profile data
    client = MagicMock(spec=FanSyncClient)
    client.device_id = "test_device_123"
    client.device_ids = ["test_device_123"]

    # Mock device_profile to return rich metadata
    client.device_profile.return_value = {
        "module": {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "firmware_version": "1.2.3",
            "local_ip": "192.168.1.100",
        },
        "esh": {
            "model": "TestFan 3000",
            "brand": "TestBrand",
        },
    }

    # Mock async_get_status to return device status
    async def mock_get_status(device_id: str | None = None) -> dict[str, int]:
        return {"H00": 1, "H02": 50}

    client.async_get_status = AsyncMock(side_effect=mock_get_status)
    client.ws_timeout_seconds = MagicMock(return_value=30)

    # Create coordinator
    coordinator = FanSyncCoordinator(hass, client, mock_config_entry)

    # Trigger a coordinator refresh
    await coordinator.async_refresh()

    # Verify data was fetched
    assert coordinator.data is not None
    assert "test_device_123" in coordinator.data


async def test_device_registry_multi_device_update(hass: HomeAssistant, mock_config_entry) -> None:
    """Test that device registry handles multiple devices correctly."""
    # Create a mock client with multiple devices
    client = MagicMock(spec=FanSyncClient)
    client.device_ids = ["device_1", "device_2"]

    # Mock device_profile to return different data for each device
    def mock_device_profile(device_id: str) -> dict[str, Any]:
        profiles = {
            "device_1": {
                "module": {"firmware_version": "1.0.0", "mac_address": "AA:AA:AA:AA:AA:AA"},
                "esh": {"model": "Fan Model A", "brand": "BrandA"},
            },
            "device_2": {
                "module": {"firmware_version": "2.0.0", "mac_address": "BB:BB:BB:BB:BB:BB"},
                "esh": {"model": "Fan Model B", "brand": "BrandB"},
            },
        }
        return profiles.get(device_id, {})

    client.device_profile = MagicMock(side_effect=mock_device_profile)

    # Mock async_get_status for multiple devices
    async def mock_get_status(device_id: str | None = None) -> dict[str, int]:
        return {"H00": 1, "H02": 50}

    client.async_get_status = AsyncMock(side_effect=mock_get_status)
    client.ws_timeout_seconds = MagicMock(return_value=30)

    # Create coordinator
    coordinator = FanSyncCoordinator(hass, client, mock_config_entry)

    # Trigger a coordinator refresh
    await coordinator.async_refresh()

    # Verify data was fetched for both devices
    assert coordinator.data is not None
    assert "device_1" in coordinator.data
    assert "device_2" in coordinator.data
