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

"""Test cleanup error handling during disconnect."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

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
async def test_disconnect_ws_close_exception(hass: HomeAssistant, mock_websocket) -> None:
    """Test that WebSocket close exceptions are handled gracefully during disconnect."""
    client = FanSyncClient(hass, "e", "p", enable_push=True)

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

        def recv_generator():
            yield _login_ok()
            yield _lst_device_ok("id")
            while True:
                yield TimeoutError("timeout")

        mock_websocket.recv.side_effect = recv_generator()
        # Make close() raise an exception
        mock_websocket.close.side_effect = RuntimeError("Close failed")
        ws_connect.return_value = mock_websocket

        await client.async_connect()
        await asyncio.sleep(0.1)  # Let recv loop start

        # Disconnect should handle close exception gracefully
        await client.async_disconnect()

        # Verify client is disconnected despite exception
        assert client._ws is None
        assert client._recv_task is None


@pytest.mark.asyncio
async def test_disconnect_http_close_exception(hass: HomeAssistant, mock_websocket) -> None:
    """Test that HTTP close exceptions are handled gracefully during disconnect."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

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
        # Make HTTP close() raise an exception
        http_inst.close.side_effect = RuntimeError("HTTP close failed")

        mock_websocket.recv.side_effect = [_login_ok(), _lst_device_ok("id")]
        ws_connect.return_value = mock_websocket

        await client.async_connect()

        # Disconnect should handle HTTP close exception gracefully
        await client.async_disconnect()

        # Verify client is disconnected despite exception
        assert client._http is None
        assert client._ws is None


@pytest.mark.asyncio
async def test_disconnect_both_close_exceptions(hass: HomeAssistant, mock_websocket) -> None:
    """Test that both WS and HTTP close exceptions are handled gracefully."""
    client = FanSyncClient(hass, "e", "p", enable_push=True)

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
        http_inst.close.side_effect = RuntimeError("HTTP close failed")

        def recv_generator():
            yield _login_ok()
            yield _lst_device_ok("id")
            while True:
                yield TimeoutError("timeout")

        mock_websocket.recv.side_effect = recv_generator()
        mock_websocket.close.side_effect = RuntimeError("WS close failed")
        ws_connect.return_value = mock_websocket

        await client.async_connect()
        await asyncio.sleep(0.1)  # Let recv loop start

        # Disconnect should handle both close exceptions gracefully
        await client.async_disconnect()

        # Verify client is fully disconnected despite exceptions
        assert client._http is None
        assert client._ws is None
        assert client._recv_task is None


@pytest.mark.asyncio
async def test_disconnect_recv_task_cancel(hass: HomeAssistant, mock_websocket) -> None:
    """Test that recv task is properly cancelled during disconnect."""
    client = FanSyncClient(hass, "e", "p", enable_push=True)

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

        def recv_generator():
            yield _login_ok()
            yield _lst_device_ok("id")
            while True:
                yield TimeoutError("timeout")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await client.async_connect()
        await asyncio.sleep(0.1)  # Let recv loop start

        # Verify task is running
        assert client._recv_task is not None
        assert not client._recv_task.done()

        # Disconnect should cancel the task
        await client.async_disconnect()

        # Verify task was cancelled
        assert client._recv_task is None
