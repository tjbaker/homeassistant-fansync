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

"""Tests for SSL context caching and WebSocket connection state checking."""

import ssl
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from websockets.protocol import State

from custom_components.fansync.client import FanSyncClient


@pytest.mark.asyncio
async def test_ssl_context_cached_after_first_creation(hass: HomeAssistant) -> None:
    """Test that SSL context is created once and cached."""
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=True)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value.json.return_value = {"token": "test-token"}
        http_inst.post.return_value.raise_for_status.return_value = None

        mock_ws = MagicMock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(
            side_effect=[
                '{"status": "ok", "response": "login", "id": 1}',
                '{"status": "ok", "response": "lst_device", "data": [{"device": "dev1"}], "id": 2}',
            ]
        )
        mock_ws.close = AsyncMock()
        mock_ws.state = State.OPEN
        ws_connect.return_value = mock_ws

        # First connection - should create SSL context
        assert client._ssl_context is None
        await client.async_connect()
        assert client._ssl_context is not None
        assert isinstance(client._ssl_context, ssl.SSLContext)

        # Cache the reference
        cached_context = client._ssl_context

        # Second operation - should reuse cached SSL context
        mock_ws.recv = AsyncMock(
            return_value='{"status": "ok", "response": "get", "id": 3, "data": {"status": {"H00": 1}}}'
        )
        await client.async_get_status()

        # Verify same SSL context instance is used
        assert client._ssl_context is cached_context

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_ssl_context_respects_verify_ssl_flag(hass: HomeAssistant) -> None:
    """Test that SSL context is configured correctly based on verify_ssl flag."""
    # Test with verify_ssl=True
    client_verified = FanSyncClient(hass, "test@example.com", "password", verify_ssl=True)
    context_verified = client_verified._create_ssl_context()
    assert context_verified.check_hostname is True
    assert context_verified.verify_mode == ssl.CERT_REQUIRED

    # Test with verify_ssl=False
    client_unverified = FanSyncClient(hass, "test@example.com", "password", verify_ssl=False)
    context_unverified = client_unverified._create_ssl_context()
    assert context_unverified.check_hostname is False
    assert context_unverified.verify_mode == ssl.CERT_NONE


@pytest.mark.asyncio
async def test_ensure_ws_connected_early_return_when_open(hass: HomeAssistant) -> None:
    """Test that _ensure_ws_connected returns early if connection is already open."""
    client = FanSyncClient(hass, "test@example.com", "password")

    # Create a mock WebSocket that's already open
    mock_ws = MagicMock()
    mock_ws.state = State.OPEN
    mock_ws.close = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock()

    # Set up client with existing connection
    client._ws = mock_ws
    client._token = "existing-token"
    client._http = MagicMock()

    # Call _ensure_ws_connected - should return early without closing/reconnecting
    with patch(
        "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
    ) as ws_connect:
        await client._ensure_ws_connected()

        # Verify WebSocket was NOT closed (early return)
        mock_ws.close.assert_not_called()

        # Verify no new connection was created (early return)
        ws_connect.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_ws_connected_reconnects_when_closed(hass: HomeAssistant) -> None:
    """Test that _ensure_ws_connected reconnects if WebSocket is closed."""
    client = FanSyncClient(hass, "test@example.com", "password")

    # Create a mock WebSocket that's closed
    old_ws = MagicMock()
    old_ws.state = State.CLOSED  # Connection is closed
    old_ws.close = AsyncMock()

    # Set up client with closed connection
    client._ws = old_ws
    client._token = "existing-token"
    client._http = MagicMock()
    client._ssl_context = ssl.create_default_context()  # Pre-cached

    # Create new WebSocket for reconnection
    new_ws = MagicMock()
    new_ws.send = AsyncMock()
    new_ws.recv = AsyncMock(return_value='{"status": "ok", "response": "login", "id": 1}')
    new_ws.close = AsyncMock()
    new_ws.state = State.OPEN

    with patch(
        "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
    ) as ws_connect:
        ws_connect.return_value = new_ws

        await client._ensure_ws_connected()

        # Verify old WebSocket was closed
        old_ws.close.assert_called_once()

        # Verify new connection was created
        ws_connect.assert_called_once()

        # Verify client now uses new WebSocket
        assert client._ws is new_ws


@pytest.mark.asyncio
async def test_ensure_ws_connected_reconnects_when_none(hass: HomeAssistant) -> None:
    """Test that _ensure_ws_connected creates connection when WebSocket is None."""
    client = FanSyncClient(hass, "test@example.com", "password")

    # Set up client with no connection
    assert client._ws is None
    client._token = "existing-token"
    client._http = MagicMock()
    client._ssl_context = ssl.create_default_context()  # Pre-cached

    # Create new WebSocket
    new_ws = MagicMock()
    new_ws.send = AsyncMock()
    new_ws.recv = AsyncMock(return_value='{"status": "ok", "response": "login", "id": 1}')
    new_ws.close = AsyncMock()
    new_ws.state = State.OPEN

    with patch(
        "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
    ) as ws_connect:
        ws_connect.return_value = new_ws

        await client._ensure_ws_connected()

        # Verify new connection was created
        ws_connect.assert_called_once()

        # Verify client now uses new WebSocket
        assert client._ws is new_ws
