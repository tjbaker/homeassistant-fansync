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

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {
            "status": "ok",
            "response": "lst_device",
            "data": [{"device": device_id}],
            "id": 2,
        }
    )


def _get_ok(status: dict[str, int] | None = None) -> str:
    if status is None:
        status = {"H00": 1, "H02": 42}
    return json.dumps(
        {
            "status": "ok",
            "response": "get",
            "data": {"status": status},
            "id": 3,
        }
    )


async def test_connect_sets_device_id(hass: HomeAssistant, mock_websocket) -> None:
    c = FanSyncClient(hass, "e@example.com", "p", verify_ssl=True, enable_push=False)
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
        mock_websocket.recv.side_effect = [_login_ok(), _lst_device_ok("dev-123")]
        ws_connect.return_value = mock_websocket
        await c.async_connect()

    assert c.device_id == "dev-123"
    http_cls.assert_called_with(verify=True, timeout=None)


async def test_get_status_returns_mapping(hass: HomeAssistant, mock_websocket) -> None:
    c = FanSyncClient(hass, "e", "p", verify_ssl=False, enable_push=False)
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

        # Generator to provide responses matching request IDs
        def recv_generator():
            """Generator that provides responses based on sent requests."""
            # Initial connection: login (id=1), lst_device (id=2)
            yield _login_ok()
            yield _lst_device_ok("id")
            # Reconnect during get_status: login (id=3)
            yield _login_ok()
            # Get response with dynamic ID
            # Wait for get request to be sent (login=1, lst=2, reconnect_login=3, get=4)
            while len(mock_websocket.sent_requests) < 4:
                yield TimeoutError("waiting for get request")
            get_request_id = mock_websocket.sent_requests[3]["id"]
            yield json.dumps(
                {
                    "status": "ok",
                    "response": "get",
                    "data": {"status": {"H00": 1, "H02": 19}},
                    "id": get_request_id,
                }
            )
            # Keep recv loop alive
            while True:
                yield TimeoutError("timeout")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket
        await c.async_connect()
        try:
            status = await c.async_get_status()
        finally:
            await c.async_disconnect()

    assert status.get("H02") == 19


async def test_async_set_triggers_callback(hass: HomeAssistant, mock_websocket) -> None:
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=True)
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

        # Generator to keep recv loop alive
        def recv_generator():
            """Generator that simulates WebSocket recv with proper message ordering."""
            # Initial connection
            yield _login_ok()
            yield _lst_device_ok("id")
            # Reconnect during async_set (from _ensure_ws_connected)
            yield _login_ok()
            # Wait for set request (login=1, lst=2, reconnect_login=3, set=4)
            while len(mock_websocket.sent_requests) < 4:
                yield TimeoutError("waiting for set request")
            set_request_id = mock_websocket.sent_requests[3]["id"]
            # The set ack with status
            yield json.dumps(
                {
                    "status": "ok",
                    "response": "set",
                    "id": set_request_id,
                    "data": {"status": {"H00": 1, "H02": 55}},
                }
            )
            # Then keep returning timeouts to keep recv loop alive
            while True:
                yield TimeoutError("timeout")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        # Capture callback result
        seen: list[dict[str, int]] = []
        c.set_status_callback(lambda s: seen.append(s))

        await c.async_connect()
        try:
            await c.async_set({"H02": 55})
            # Give recv loop time to process the set ack message
            # Longer sleep needed for async task to process message
            await asyncio.sleep(0.5)
            await hass.async_block_till_done()
            await asyncio.sleep(0.1)  # Extra time for callback
        finally:
            await c.async_disconnect()

    assert seen, f"No callbacks received, seen={seen}"
    assert seen[-1].get("H02") == 55, f"Expected H02=55, got {seen[-1]}"


async def test_async_set_uses_ack_status_when_present(hass: HomeAssistant, mock_websocket) -> None:
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=True)
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

        # Generator to keep recv loop alive
        def recv_generator():
            """Generator that simulates WebSocket recv with proper message ordering."""
            # Initial connection
            yield _login_ok()
            yield _lst_device_ok("id")
            # Reconnect during async_set (from _ensure_ws_connected)
            yield _login_ok()
            # The set ack with status
            yield json.dumps(
                {
                    "status": "ok",
                    "response": "set",
                    "id": 4,
                    "data": {"status": {"H00": 0, "H02": 1}},
                }
            )
            # Then keep returning timeouts to keep recv loop alive
            while True:
                yield TimeoutError("timeout")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        seen: list[dict[str, int]] = []
        c.set_status_callback(lambda s: seen.append(s))

        await c.async_connect()
        try:
            await c.async_set({"H00": 0})
            # Give recv loop time to process the set ack message
            # Longer sleep needed for async task to process message
            await asyncio.sleep(0.5)
            await hass.async_block_till_done()
            await asyncio.sleep(0.1)  # Extra time for callback
        finally:
            await c.async_disconnect()

    # Should have used ACK status directly
    assert seen, f"No callbacks received, seen={seen}"
    assert (
        seen[-1].get("H00") == 0 and seen[-1].get("H02") == 1
    ), f"Expected H00=0, H02=1, got {seen[-1]}"


async def test_connect_ws_login_failure_raises(hass: HomeAssistant, mock_websocket):
    c = FanSyncClient(hass, "e", "p")
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
        mock_websocket.recv.side_effect = [
            json.dumps({"status": "fail", "response": "login", "id": 1})
        ]
        ws_connect.return_value = mock_websocket

        with pytest.raises(RuntimeError):
            await c.async_connect()


async def test_connect_ws_timeout_then_success_retries(hass: HomeAssistant):
    c = FanSyncClient(hass, "e@example.com", "p", verify_ssl=True, enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
        patch("custom_components.fansync.client.asyncio.sleep", return_value=None),
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()

        # First WS instance times out, second succeeds
        ws1 = AsyncMock()
        ws1.send = AsyncMock()
        ws1.recv = AsyncMock(side_effect=TimeoutError("timeout"))
        ws1.close = AsyncMock()

        ws2 = AsyncMock()
        ws2.send = AsyncMock()
        ws2.recv = AsyncMock(side_effect=[_login_ok(), _lst_device_ok("dev-retry")])
        ws2.close = AsyncMock()

        ws_connect.side_effect = [ws1, ws2]

        await c.async_connect()

    assert c.device_id == "dev-retry"


async def test_connect_http_error_bubbles(hass: HomeAssistant):
    c = FanSyncClient(hass, "e", "p")
    with patch("custom_components.fansync.client.httpx.Client") as http_cls:
        http_inst = http_cls.return_value
        http_inst.post.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            await c.async_connect()
