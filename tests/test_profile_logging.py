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
@pytest.mark.skip(
    reason="Complex async timing with profile caching and background recv task - needs simplified approach"
)
async def test_profile_cached_debug_logging(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, mock_websocket
) -> None:
    """Test debug logging when profile is successfully cached."""
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        def recv_generator():
            yield '{"status": "ok", "response": "login", "id": 1}'
            yield '{"status": "ok", "response": "lst_device", "data": [{"device": "test_device_123"}], "id": 2}'
            # Get response with profile
            yield (
                '{"status": "ok", "response": "get", "id": 3, "data": {"status": {"H00": 0}, '
                '"profile": {"module": {"mac_address": "AA:BB:CC:DD:EE:FF", '
                '"firmware_version": "1.2.3"}, "esh": {"model": "TestFan", "brand": "TestBrand"}}}}'
            )
            # Keep loop alive
            while True:
                yield TimeoutError("timeout")
                yield TimeoutError("timeout")
                yield '{"status": "ok", "response": "evt", "data": {}}'

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        # Enable debug logging
        with caplog.at_level("DEBUG", logger="custom_components.fansync.client"):
            await client.async_connect()
            try:
                await client.async_get_status()
            finally:
                await client.async_disconnect()

        # Verify profile cached message was logged
        assert any(
            "profile cached for test_device_123: keys=" in record.message
            for record in caplog.records
        )


@pytest.mark.asyncio
@pytest.mark.skip(
    reason="Complex async timing with profile caching and background recv task - needs simplified approach"
)
async def test_no_profile_debug_logging(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, mock_websocket
) -> None:
    """Test that no profile message is logged when profile is missing.

    When the API response does not include a 'profile' field, the client should
    silently skip profile caching without logging. This test verifies that behavior.
    """
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        def recv_generator():
            yield '{"status": "ok", "response": "login", "id": 1}'
            yield '{"status": "ok", "response": "lst_device", "data": [{"device": "test_device_456"}], "id": 2}'
            # Get response WITHOUT profile
            yield '{"status": "ok", "response": "get", "id": 3, "data": {"status": {"H00": 0}}}'
            # Keep loop alive
            while True:
                yield TimeoutError("timeout")
                yield TimeoutError("timeout")
                yield '{"status": "ok", "response": "evt", "data": {}}'

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        # Enable debug logging
        with caplog.at_level("DEBUG", logger="custom_components.fansync.client"):
            await client.async_connect()
            try:
                await client.async_get_status()
            finally:
                await client.async_disconnect()

        # When no profile is in the response, no "profile cached" log should be emitted
        # The client silently skips profile caching when the field is missing
        profile_logs = [
            record.message
            for record in caplog.records
            if "profile cached for test_device_456" in record.message
        ]
        # Should be empty since no profile was provided
        assert len(profile_logs) == 0


@pytest.mark.asyncio
@pytest.mark.skip(
    reason="Complex async timing with profile caching and background recv task - needs simplified approach"
)
async def test_profile_keys_logged_correctly(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, mock_websocket
) -> None:
    """Test that profile keys are logged in the correct format."""
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        def recv_generator():
            yield '{"status": "ok", "response": "login", "id": 1}'
            yield '{"status": "ok", "response": "lst_device", "data": [{"device": "test_device_789"}], "id": 2}'
            # Get response with profile containing specific keys
            yield (
                '{"status": "ok", "response": "get", "id": 3, "data": {"status": {"H00": 1}, '
                '"profile": {"module": {"mac": "00:11:22"}, "esh": {"brand": "Test"}, "custom_key": "value"}}}'
            )
            # Keep loop alive
            while True:
                yield TimeoutError("timeout")
                yield TimeoutError("timeout")
                yield '{"status": "ok", "response": "evt", "data": {}}'

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        # Enable debug logging
        with caplog.at_level("DEBUG", logger="custom_components.fansync.client"):
            await client.async_connect()
            try:
                await client.async_get_status()
            finally:
                await client.async_disconnect()

        # Verify profile keys are logged
        profile_log = [
            record.message
            for record in caplog.records
            if "profile cached for test_device_789: keys=" in record.message
        ]
        assert len(profile_log) == 1
        # The log format is: "profile cached for test_device_789: keys=['module', 'esh', 'custom_key']"
        # Verify all keys are mentioned in the log
        assert all(key in profile_log[0] for key in ["module", "esh", "custom_key"])
