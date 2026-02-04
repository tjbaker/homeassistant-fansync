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
from unittest.mock import patch, AsyncMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


async def test_get_reconnects_on_closed_socket(hass: HomeAssistant, mock_websocket):
    """Test that async_get_status reconnects on closed socket error."""
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)
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
            """Generator for reconnect scenario."""
            # Initial connect: login, list
            yield _login_ok()
            yield _lst_device_ok("id")
            # Wait for get request to be sent (login=1, lst=2, get=3)
            while len(mock_websocket.sent_requests) < 3:
                yield TimeoutError("waiting for get request")

            # Wait for reconnection requests (login=4, lst=5 not sent)
            # _ensure_ws_connected only sends Login (id=1 hardcoded).
            # So next request is Login.
            while len(mock_websocket.sent_requests) < 4:
                yield TimeoutError("waiting for reconnect login")

            yield _login_ok()

            # Now we are reconnected, the retry will send the get request again (count 5)
            while len(mock_websocket.sent_requests) < 5:
                yield TimeoutError("waiting for retry get")

            get_request_id = mock_websocket.sent_requests[4]["id"]
            # Then get response with dynamic ID
            yield json.dumps(
                {
                    "status": "ok",
                    "response": "get",
                    "data": {"status": {"H00": 1, "H02": 33}},
                    "id": get_request_id,
                }
            )
            # Keep recv loop alive
            while True:
                yield TimeoutError("timeout")
                yield TimeoutError("timeout")
                yield json.dumps({"status": "ok", "response": "evt", "data": {}})

        mock_websocket.recv.side_effect = recv_generator()

        # Only the first send (the get request) should fail; subsequent sends (login) should work
        send_calls = {"count": 0}

        async def _send(payload):
            send_calls["count"] += 1
            # Track request so recv_generator knows when to proceed
            mock_websocket.sent_requests.append(json.loads(payload))
            # 1=login, 2=list, 3=get (the one we want to fail)
            if send_calls["count"] == 3:
                raise OSError("closed")
            return None

        mock_websocket.send.side_effect = _send
        ws_connect.return_value = mock_websocket

        await c.async_connect()
        try:
            status = await c.async_get_status()
            assert status.get("H02") == 33
        finally:
            await c.async_disconnect()


async def test_set_reconnects_on_closed_socket(hass: HomeAssistant, mock_websocket):
    """Test that async_set reconnects on closed socket error."""
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)
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
            """Generator for reconnect scenario."""
            # Initial connect: login, list
            yield _login_ok()
            yield _lst_device_ok("id")
            # Wait for set request to be sent (login=1, lst=2, set=3)
            while len(mock_websocket.sent_requests) < 3:
                yield TimeoutError("waiting for set request")

            # Wait for reconnection login (4)
            while len(mock_websocket.sent_requests) < 4:
                yield TimeoutError("waiting for reconnect login")

            yield _login_ok()

            # Wait for retry set (5)
            while len(mock_websocket.sent_requests) < 5:
                yield TimeoutError("waiting for retry set")

            set_request_id = mock_websocket.sent_requests[4]["id"]
            # Then set response with dynamic ID
            yield json.dumps(
                {
                    "status": "ok",
                    "response": "set",
                    "data": {"status": {"H00": 1, "H02": 44}},
                    "id": set_request_id,
                }
            )
            # Keep recv loop alive
            while True:
                yield TimeoutError("timeout")
                yield TimeoutError("timeout")
                yield json.dumps({"status": "ok", "response": "evt", "data": {}})

        mock_websocket.recv.side_effect = recv_generator()

        # Only the first send (the set request) should fail; subsequent sends (login) should work
        send_calls = {"count": 0}

        async def _send(payload):
            send_calls["count"] += 1
            # Track request so recv_generator knows when to proceed
            mock_websocket.sent_requests.append(json.loads(payload))
            # 1=login, 2=list, 3=set (the one we want to fail)
            if send_calls["count"] == 3:
                raise OSError("closed")
            return None

        mock_websocket.send.side_effect = _send
        ws_connect.return_value = mock_websocket

        await c.async_connect()
        try:
            # We need to capture the callback to verify the status update from the set response
            callback_status = {}

            def on_status(s):
                callback_status.update(s)

            c.set_status_callback(on_status)

            await c.async_set({"H02": 44})

            # Allow time for callback processing (it's scheduled with call_soon)
            await asyncio.sleep(0.1)

            assert callback_status.get("H02") == 44
        finally:
            await c.async_disconnect()
