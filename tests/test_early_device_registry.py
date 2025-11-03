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

"""Test early device registry update on initial setup."""

from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.const import DOMAIN


async def test_device_registry_updated_before_first_refresh(hass: HomeAssistant) -> None:
    """Test that device registry is updated immediately after connection, before first refresh."""
    # Create a mock client with device profile data available immediately
    mock_client = MagicMock()
    mock_client.device_id = "test_device_123"
    mock_client.device_ids = ["test_device_123"]

    def mock_device_profile(device_id: str) -> dict[str, Any]:
        return {
            "esh": {"model": "TestFan-123", "brand": "TestBrand"},
            "module": {"firmware_version": "1.0.0", "mac_address": "AA:BB:CC:DD:EE:FF"},
        }

    mock_client.device_profile = MagicMock(side_effect=mock_device_profile)
    mock_client.ws_timeout_seconds.return_value = 30

    # Make async_connect succeed
    async def mock_connect() -> None:
        pass

    mock_client.async_connect = mock_connect

    # Create config entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password"},
        unique_id="test_early_registry",
    )
    entry.add_to_hass(hass)

    # Mock the coordinator's first refresh to timeout (simulating slow network)
    # This tests that device registry update happens BEFORE the first refresh
    with (
        patch("custom_components.fansync.FanSyncClient", return_value=mock_client),
        patch(
            "custom_components.fansync.FanSyncCoordinator.async_config_entry_first_refresh",
            side_effect=TimeoutError("Simulated timeout"),
        ),
    ):
        # Setup integration
        result = await hass.config_entries.async_setup(entry.entry_id)
        assert result is True
        await hass.async_block_till_done()

        # Verify device was registered even though first refresh timed out
        device_registry = dr.async_get(hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, "test_device_123")})

        # Device should exist with profile data
        assert device is not None
        assert device.model == "TestFan-123"
        assert device.manufacturer == "TestBrand"
        assert device.sw_version == "1.0.0"
        assert (dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff") in device.connections


async def test_early_registry_handles_missing_profile_gracefully(
    hass: HomeAssistant,
) -> None:
    """Test that early device registry update handles missing profile data gracefully."""
    # Create a mock client WITHOUT device profile data
    mock_client = MagicMock()
    mock_client.device_id = "test_device_456"
    mock_client.device_ids = ["test_device_456"]
    mock_client.device_profile.return_value = None  # No profile data available yet
    mock_client.ws_timeout_seconds.return_value = 30

    async def mock_connect() -> None:
        pass

    mock_client.async_connect = mock_connect

    # Mock successful status fetch
    async def mock_get_status(device_id: str | None = None) -> dict[str, int]:
        return {"power": 1, "speed": 3}

    mock_client.async_get_status = mock_get_status

    # Create config entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password"},
        unique_id="test_early_registry_no_profile",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.fansync.FanSyncClient", return_value=mock_client):
        # Setup should succeed even without profile data
        result = await hass.config_entries.async_setup(entry.entry_id)
        assert result is True
        await hass.async_block_till_done()

        # Device should exist but without profile metadata
        device_registry = dr.async_get(hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, "test_device_456")})

        # Device should exist (created by entity setup)
        # but profile fields should be None since no profile data was available
        assert device is not None
        # Model/manufacturer/sw_version will be None since profile wasn't available
        # This is expected behavior - they'll be updated when profile arrives later


async def test_early_registry_handles_exception_gracefully(hass: HomeAssistant) -> None:
    """Test that early device registry update handles exceptions without failing setup."""
    # Create a mock client that raises exception when accessing device_ids
    mock_client = MagicMock()
    mock_client.device_id = None

    # Accessing device_ids raises AttributeError (simulates missing attribute)
    def _raise_device_ids_error(self) -> list[str]:
        raise AttributeError("device_ids not available")

    type(mock_client).device_ids = property(_raise_device_ids_error)
    mock_client.ws_timeout_seconds.return_value = 30

    async def mock_connect() -> None:
        pass

    mock_client.async_connect = mock_connect

    async def mock_get_status(device_id: str | None = None) -> dict[str, int]:
        return {"power": 1, "speed": 3}

    mock_client.async_get_status = mock_get_status

    # Create config entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password"},
        unique_id="test_early_registry_exception",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.fansync.FanSyncClient", return_value=mock_client):
        # Setup should succeed despite exception in early device registry update
        result = await hass.config_entries.async_setup(entry.entry_id)
        assert result is True
        await hass.async_block_till_done()

        # Integration should be loaded successfully
        assert entry.entry_id in hass.data[DOMAIN]
