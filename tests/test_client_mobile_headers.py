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

"""Test that WebSocket connections use mobile app headers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    mock_ws = AsyncMock()
    mock_ws.recv.side_effect = [
        json.dumps({"status": "ok", "response": "login", "id": 1}),
        json.dumps({"status": "ok", "response": "lst_device", "data": [], "id": 2}),
    ]
    mock_ws.send = AsyncMock()
    mock_ws.close = AsyncMock()
    return mock_ws


async def test_websocket_uses_mobile_app_headers(hass: HomeAssistant, mock_websocket) -> None:
    """Test that WebSocket connections include mobile app identification headers.

    This test verifies that we send the same headers as the official Android app
    to avoid potential server-side filtering based on User-Agent or missing headers.
    """
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=True, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        # Setup HTTP mock
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"token": "test_token"},
            },
        )()

        # Setup WebSocket mock
        ws_connect.return_value = mock_websocket

        # Connect
        await client.async_connect()

        try:
            # Verify websockets.connect was called with mobile app headers
            assert ws_connect.called, "websockets.connect was not called"

            # Get the actual call arguments
            call_args = ws_connect.call_args

            # Verify the additional_headers parameter
            assert (
                "additional_headers" in call_args.kwargs
            ), "additional_headers not passed to websockets.connect"

            headers = call_args.kwargs["additional_headers"]

            # Verify the Android app package identification header
            assert "X-Requested-With" in headers, "X-Requested-With header missing"
            assert headers["X-Requested-With"] == "com.fanimation.fanSyncW", (
                f"X-Requested-With should be 'com.fanimation.fanSyncW', "
                f"got '{headers['X-Requested-With']}'"
            )

            # Verify the Origin header matches mobile app
            assert "Origin" in headers, "Origin header missing"
            assert (
                headers["Origin"] == "http://localhost"
            ), f"Origin should be 'http://localhost', got '{headers['Origin']}'"

        finally:
            await client.async_disconnect()


async def test_websocket_reconnect_uses_mobile_app_headers(
    hass: HomeAssistant,
) -> None:
    """Test that WebSocket reconnections also use mobile app headers.

    Verifies that the _ensure_ws_connected method (used for reconnections)
    also includes the mobile app headers.
    """
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=True, enable_push=False)

    # Simulate an already-established client (token exists, no websocket)
    client._token = "existing_token"
    client._ws = None  # Force reconnection

    mock_ws = AsyncMock()
    mock_ws.recv.return_value = json.dumps({"status": "ok", "response": "login", "id": 1})
    mock_ws.send = AsyncMock()

    with (
        patch("custom_components.fansync.client.httpx.Client"),
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        ws_connect.return_value = mock_ws

        # Trigger reconnection
        await client._ensure_ws_connected()

        try:
            # Verify headers are included in reconnection
            assert ws_connect.called, "websockets.connect not called during reconnect"

            call_args = ws_connect.call_args
            headers = call_args.kwargs.get("additional_headers", {})

            assert (
                headers.get("X-Requested-With") == "com.fanimation.fanSyncW"
            ), "Mobile app header missing during reconnection"
            assert (
                headers.get("Origin") == "http://localhost"
            ), "Origin header missing during reconnection"

        finally:
            await client.async_disconnect()


async def test_headers_documented_source(hass: HomeAssistant, mock_websocket) -> None:
    """Test that header values match official mobile app headers.

    This test serves as documentation that these headers come from reverse
    engineering the Android app, not arbitrary values we made up.
    """
    client = FanSyncClient(hass, "test@example.com", "password", enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"token": "test_token"},
            },
        )()
        ws_connect.return_value = mock_websocket

        await client.async_connect()

        try:
            headers = ws_connect.call_args.kwargs["additional_headers"]

            # These exact values are from Android app reverse engineering
            # Header: x-requested-with: com.fanimation.fanSyncW
            # Header: origin: http://localhost
            assert headers == {
                "X-Requested-With": "com.fanimation.fanSyncW",
                "Origin": "http://localhost",
            }, (
                "Headers must match official Android app values. "
                "Do not change these without verifying against mobile app traffic."
            )

        finally:
            await client.async_disconnect()
