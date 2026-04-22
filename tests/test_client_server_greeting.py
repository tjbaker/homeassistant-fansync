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

"""Tests for server-greeting consumption on WebSocket connect and reconnect.

The Fanimation cloud server may send an unsolicited greeting frame immediately
after the WebSocket upgrade. The client must consume it before sending login,
otherwise both sides wait on each other and the login times out.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient
from custom_components.fansync.const import WS_GREETING_TIMEOUT_SEC


def _http_mock():
    """Return a mock HTTP client instance that succeeds login."""
    return type(
        "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "tok"}}
    )()


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "dev1") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


def _make_ws(recv_responses: list[str | Exception]) -> AsyncMock:
    """Build a mock WebSocket whose recv() returns items from recv_responses in order."""
    ws = AsyncMock()
    ws.close = AsyncMock()

    responses = iter(recv_responses)

    async def _recv() -> str:
        val = next(responses)
        if isinstance(val, Exception):
            raise val
        return val

    ws.recv = AsyncMock(side_effect=_recv)
    ws.send = AsyncMock()
    return ws


async def test_async_connect_no_greeting(hass: HomeAssistant) -> None:
    """Login succeeds when the server sends no greeting (timeout path)."""
    c = FanSyncClient(hass, "e", "p", enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_cls.return_value.post.return_value = _http_mock()
        ws = _make_ws(
            [
                TimeoutError(),  # greeting: no greeting sent by server
                _login_ok(),
                _lst_device_ok(),
                TimeoutError(),  # keep recv loop quiet
            ]
        )
        ws_connect.return_value = ws

        await c.async_connect()
        await c.async_disconnect()

    assert c._last_server_greeting is None
    # login and lst_device were sent (greeting timeout doesn't prevent login)
    assert ws.send.call_count == 2


async def test_async_connect_with_greeting(hass: HomeAssistant) -> None:
    """Greeting is consumed and stored; login succeeds on the next recv."""
    greeting_payload = json.dumps({"type": "hello", "server": "fansync-api"})
    c = FanSyncClient(hass, "e", "p", enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_cls.return_value.post.return_value = _http_mock()
        ws = _make_ws(
            [
                greeting_payload,  # greeting consumed before login
                _login_ok(),
                _lst_device_ok(),
                TimeoutError(),  # keep recv loop quiet
            ]
        )
        ws_connect.return_value = ws

        await c.async_connect()
        await c.async_disconnect()

    assert c._last_server_greeting == greeting_payload
    assert ws.send.call_count == 2  # login + lst_device


async def test_async_connect_greeting_logged_at_info(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Greeting receipt is logged at INFO level."""
    greeting_payload = json.dumps({"type": "hello"})
    c = FanSyncClient(hass, "e", "p", enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
        caplog.at_level(logging.INFO, logger="custom_components.fansync.client"),
    ):
        http_cls.return_value.post.return_value = _http_mock()
        ws = _make_ws([greeting_payload, _login_ok(), _lst_device_ok(), TimeoutError()])
        ws_connect.return_value = ws

        await c.async_connect()
        await c.async_disconnect()

    assert any("greeting" in r.message.lower() for r in caplog.records)


async def test_async_connect_no_greeting_logged_at_debug(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Absence of greeting is logged at DEBUG level."""
    c = FanSyncClient(hass, "e", "p", enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
        caplog.at_level(logging.DEBUG, logger="custom_components.fansync.client"),
    ):
        http_cls.return_value.post.return_value = _http_mock()
        ws = _make_ws([TimeoutError(), _login_ok(), _lst_device_ok(), TimeoutError()])
        ws_connect.return_value = ws

        await c.async_connect()
        await c.async_disconnect()

    assert any("no server greeting" in r.message.lower() for r in caplog.records)


async def test_ensure_ws_connected_no_greeting(hass: HomeAssistant) -> None:
    """Reconnect path: no greeting — login proceeds normally."""
    c = FanSyncClient(hass, "e", "p", enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_cls.return_value.post.return_value = _http_mock()

        # First connection (async_connect): no greeting
        ws1 = _make_ws([TimeoutError(), _login_ok(), _lst_device_ok(), TimeoutError()])
        # Reconnect (_ensure_ws_connected): no greeting
        ws2 = _make_ws([TimeoutError(), _login_ok(), TimeoutError()])

        ws_connect.side_effect = [ws1, ws2]

        await c.async_connect()
        # Force reconnect by nulling _ws
        c._ws = None
        await c._ensure_ws_connected()
        ws_after_reconnect = c._ws
        await c.async_disconnect()

    assert c._last_server_greeting is None
    assert ws_after_reconnect is ws2


async def test_ensure_ws_connected_with_greeting(hass: HomeAssistant) -> None:
    """Reconnect path: greeting consumed and stored; login succeeds."""
    greeting_payload = json.dumps({"type": "hello"})
    c = FanSyncClient(hass, "e", "p", enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_cls.return_value.post.return_value = _http_mock()

        # First connection: no greeting
        ws1 = _make_ws([TimeoutError(), _login_ok(), _lst_device_ok(), TimeoutError()])
        # Reconnect: greeting present
        ws2 = _make_ws([greeting_payload, _login_ok(), TimeoutError()])

        ws_connect.side_effect = [ws1, ws2]

        await c.async_connect()
        c._ws = None
        await c._ensure_ws_connected()
        await c.async_disconnect()

    assert c._last_server_greeting == greeting_payload


async def test_greeting_stored_in_diagnostics(hass: HomeAssistant) -> None:
    """Diagnostics include last_server_greeting."""
    greeting_payload = json.dumps({"type": "hello"})
    c = FanSyncClient(hass, "e", "p", enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_cls.return_value.post.return_value = _http_mock()
        ws = _make_ws([greeting_payload, _login_ok(), _lst_device_ok(), TimeoutError()])
        ws_connect.return_value = ws

        await c.async_connect()
        diag = c.get_diagnostics_data()
        await c.async_disconnect()

    assert diag["last_server_greeting"] == greeting_payload


async def test_ws_greeting_timeout_constant_used(hass: HomeAssistant) -> None:
    """_ws_recv_greeting uses WS_GREETING_TIMEOUT_SEC as its timeout."""
    c = FanSyncClient(hass, "e", "p", enable_push=False)

    timed_out: list[float] = []

    async def fake_wait_for(coro, timeout: float) -> str:
        timed_out.append(timeout)
        coro.close()
        raise TimeoutError()

    ws = AsyncMock()
    ws.recv = AsyncMock(return_value="greeting")

    with patch("custom_components.fansync.client.asyncio.wait_for", side_effect=fake_wait_for):
        result = await c._ws_recv_greeting(ws)

    assert result is None
    assert timed_out == [WS_GREETING_TIMEOUT_SEC]
