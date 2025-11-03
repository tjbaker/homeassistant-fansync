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

"""Test device profile caching debug logging."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


@pytest.mark.asyncio
async def test_profile_cached_debug_logging(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test debug logging when profile is successfully cached."""
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=False)

    # Mock WebSocket and HTTP responses with profile data
    mock_ws = MagicMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(
        return_value=(
            '{"response": "get", "id": 3, "data": {"status": {"H00": 0}, '
            '"profile": {"module": {"mac_address": "AA:BB:CC:DD:EE:FF", '
            '"firmware_version": "1.2.3"}, "esh": {"model": "TestFan", "brand": "TestBrand"}}}}'
        )
    )
    mock_ws.close = AsyncMock()

    with (
        patch.object(client, "_ws", mock_ws),
        patch.object(client, "_ensure_ws_connected", new_callable=AsyncMock),
    ):
        client._device_id = "test_device_123"

        # Enable debug logging
        with caplog.at_level("DEBUG", logger="custom_components.fansync.client"):
            await client.async_get_status()

        # Verify profile cached message was logged
        assert any(
            "profile cached for test_device_123" in record.message and "keys=" in record.message
            for record in caplog.records
        )


@pytest.mark.asyncio
async def test_no_profile_debug_logging(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that no profile message is logged when profile is missing."""
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=False)

    # Mock WebSocket response WITHOUT profile data
    mock_ws = MagicMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(
        return_value='{"response": "get", "id": 3, "data": {"status": {"H00": 0}}}'
    )
    mock_ws.close = AsyncMock()

    with (
        patch.object(client, "_ws", mock_ws),
        patch.object(client, "_ensure_ws_connected", new_callable=AsyncMock),
    ):
        client._device_id = "test_device_456"

        # Enable debug logging
        with caplog.at_level("DEBUG", logger="custom_components.fansync.client"):
            await client.async_get_status()

        # Verify no "profile cached" message was logged (since there's no profile)
        assert not any(
            "profile cached for test_device_456" in record.message for record in caplog.records
        )


@pytest.mark.asyncio
async def test_profile_keys_logged_correctly(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that profile keys are logged in the correct format."""
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=False)

    # Mock WebSocket with specific profile keys
    mock_ws = MagicMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(
        return_value=(
            '{"response": "get", "id": 3, "data": {"status": {"H00": 1}, '
            '"profile": {"module": {}, "esh": {}, "custom_key": "value"}}}'
        )
    )
    mock_ws.close = AsyncMock()

    with (
        patch.object(client, "_ws", mock_ws),
        patch.object(client, "_ensure_ws_connected", new_callable=AsyncMock),
    ):
        client._device_id = "test_device_789"

        # Enable debug logging
        with caplog.at_level("DEBUG", logger="custom_components.fansync.client"):
            await client.async_get_status()

        # Verify keys are logged as a list
        profile_log = [
            record.message
            for record in caplog.records
            if "profile cached for test_device_789" in record.message
        ]
        assert len(profile_log) == 1
        # Should contain all expected profile keys
        assert all(key in profile_log[0] for key in ["module", "esh", "custom_key"])
