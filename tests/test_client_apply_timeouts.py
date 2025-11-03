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

"""Test runtime timeout configuration with apply_timeouts()."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


@pytest.mark.asyncio
async def test_apply_timeouts_http_only(hass: HomeAssistant, mock_websocket) -> None:
    """Test applying HTTP timeout at runtime."""
    client = FanSyncClient(hass, "e", "p", http_timeout_s=10, ws_timeout_s=30)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()

        mock_websocket.recv.side_effect = [_login_ok(), _lst_device_ok("id")]
        ws_connect.return_value = mock_websocket

        await client.async_connect()

        # Apply new HTTP timeout - should recreate HTTP client
        client.apply_timeouts(http_timeout_s=20)

        assert client._http_timeout_s == 20
        assert client._ws_timeout_s == 30  # Unchanged

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_apply_timeouts_ws_only(hass: HomeAssistant, mock_websocket) -> None:
    """Test applying WebSocket timeout at runtime."""
    client = FanSyncClient(hass, "e", "p", http_timeout_s=10, ws_timeout_s=30)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()

        mock_websocket.recv.side_effect = [_login_ok(), _lst_device_ok("id")]
        ws_connect.return_value = mock_websocket

        await client.async_connect()

        # Apply new WebSocket timeout
        client.apply_timeouts(ws_timeout_s=60)

        assert client._http_timeout_s == 10  # Unchanged
        assert client._ws_timeout_s == 60

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_apply_timeouts_both(hass: HomeAssistant, mock_websocket) -> None:
    """Test applying both HTTP and WebSocket timeouts at runtime."""
    client = FanSyncClient(hass, "e", "p", http_timeout_s=10, ws_timeout_s=30)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()
        http_inst.close.return_value = None

        mock_websocket.recv.side_effect = [_login_ok(), _lst_device_ok("id")]
        ws_connect.return_value = mock_websocket

        await client.async_connect()

        # Apply both timeouts
        client.apply_timeouts(http_timeout_s=25, ws_timeout_s=45)

        assert client._http_timeout_s == 25
        assert client._ws_timeout_s == 45

        # Verify HTTP client was closed and recreated
        http_inst.close.assert_called_once()

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_apply_timeouts_http_close_exception(hass: HomeAssistant, mock_websocket) -> None:
    """Test that exceptions during HTTP client close are handled gracefully."""
    client = FanSyncClient(hass, "e", "p", http_timeout_s=10, ws_timeout_s=30)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()
        # Make close() raise an exception
        http_inst.close.side_effect = RuntimeError("Close failed")

        mock_websocket.recv.side_effect = [_login_ok(), _lst_device_ok("id")]
        ws_connect.return_value = mock_websocket

        await client.async_connect()

        # Apply timeout - should handle close exception gracefully
        client.apply_timeouts(http_timeout_s=20)

        assert client._http_timeout_s == 20

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_apply_timeouts_before_connect(hass: HomeAssistant) -> None:
    """Test applying timeouts before connection is established."""
    client = FanSyncClient(hass, "e", "p", http_timeout_s=10, ws_timeout_s=30)

    # Apply timeouts before connecting - should work without HTTP client
    client.apply_timeouts(http_timeout_s=15, ws_timeout_s=45)

    assert client._http_timeout_s == 15
    assert client._ws_timeout_s == 45
    assert client._http is None  # No HTTP client to recreate
