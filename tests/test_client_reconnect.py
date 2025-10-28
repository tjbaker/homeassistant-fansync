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

import json
from unittest.mock import patch

from websocket import WebSocketConnectionClosedException

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


def _get_ok(status: dict[str, int]) -> str:
    return json.dumps({"status": "ok", "response": "get", "data": {"status": status}, "id": 3})


async def test_disconnect_on_unload(hass: HomeAssistant):
    c = FanSyncClient(hass, "e", "p", enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()
        ws = ws_cls.return_value
        ws.connect.return_value = None
        ws.recv.side_effect = [_login_ok(), _lst_device_ok("id")]
        await c.async_connect()

        await c.async_disconnect()

    ws.close.assert_called_once()


async def test_set_retries_on_closed_socket(hass: HomeAssistant):
    c = FanSyncClient(hass, "e", "p", enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()
        ws = ws_cls.return_value
        ws.connect.return_value = None
        # Connect sequence
        ws.recv.side_effect = [_login_ok(), _lst_device_ok("id")]
        await c.async_connect()

        # First send raises closed; on retry, we need a login and get ack
        def _send(payload):
            if isinstance(_send.first, bool) and _send.first:
                _send.first = False
                raise WebSocketConnectionClosedException("closed")
            return None

        _send.first = True  # type: ignore[attr-defined]
        ws.send.side_effect = _send
        # after reconnect: login ok, then set ack
        ws.recv.side_effect = [
            _login_ok(),
            json.dumps({"status": "ok", "response": "set", "id": 4}),
        ]

        await c.async_set({"H02": 10})
        await c.async_disconnect()

    assert ws.send.call_count >= 2
