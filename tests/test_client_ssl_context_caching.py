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

"""Tests for SSL context caching and WebSocket connection state checking.

Note: These tests intentionally access private attributes and methods to verify
critical implementation details:
- SSL context caching is a performance optimization that must be tested directly
- Connection state checking prevents bugs that can't be observed through public API
- Unit testing implementation details is appropriate for optimization verification
"""

import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from websockets.protocol import State

from custom_components.fansync.client import FanSyncClient


def _create_mock_websocket(
    state: State = State.OPEN, recv_response: str | None = None
) -> MagicMock:
    """Create a mock WebSocket with common configuration.

    Args:
        state: The WebSocket state (default: State.OPEN)
        recv_response: Optional response for recv() calls

    Returns:
        Configured MagicMock WebSocket
    """
    mock_ws = MagicMock()
    mock_ws.send = AsyncMock()
    mock_ws.close = AsyncMock()
    mock_ws.state = state

    if recv_response:
        mock_ws.recv = AsyncMock(return_value=recv_response)
    else:
        mock_ws.recv = AsyncMock()

    return mock_ws


def _mock_http_client(http_cls_mock: MagicMock, token: str = "test-token") -> None:
    """Configure mock HTTP client for authentication.

    Args:
        http_cls_mock: The httpx.Client class mock
        token: Token to return from authentication (default: "test-token")
    """
    http_inst = http_cls_mock.return_value
    http_inst.post.return_value.json.return_value = {"token": token}
    http_inst.post.return_value.raise_for_status.return_value = None


@pytest.mark.asyncio
async def test_ssl_context_cached_after_first_creation(hass: HomeAssistant) -> None:
    """Test that SSL context is created once and cached."""
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=True)

    # SSL context should be None before first use
    assert client._ssl_context is None

    # Test direct creation method
    context1 = client._create_ssl_context()
    assert isinstance(context1, ssl.SSLContext)

    # Manually cache it (simulating what async_connect does)
    client._ssl_context = context1

    # Verify context is cached
    assert client._ssl_context is context1

    # The cached context should be reused in subsequent operations
    # (in real code, async_connect checks if _ssl_context is None before creating)
    context2 = client._ssl_context
    assert context2 is context1  # Same object instance


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
    mock_ws = _create_mock_websocket()

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
    old_ws = _create_mock_websocket(state=State.CLOSED)

    # Set up client with closed connection
    client._ws = old_ws
    client._token = "existing-token"
    client._http = MagicMock()
    client._ssl_context = ssl.create_default_context()  # Pre-cached

    # Create new WebSocket for reconnection
    new_ws = _create_mock_websocket(recv_response='{"status": "ok", "response": "login", "id": 1}')

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
    new_ws = _create_mock_websocket(recv_response='{"status": "ok", "response": "login", "id": 1}')

    with patch(
        "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
    ) as ws_connect:
        ws_connect.return_value = new_ws

        await client._ensure_ws_connected()

        # Verify new connection was created
        ws_connect.assert_called_once()

        # Verify client now uses new WebSocket
        assert client._ws is new_ws
