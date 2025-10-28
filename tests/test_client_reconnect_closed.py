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


async def test_get_reconnects_on_closed_socket(hass: HomeAssistant):
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)
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

        # initial connect: login, list
        ws.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("id"),
        ]
        await c.async_connect()

        # First send/recv will raise closed; then on reconnect we get a valid get response
        def _send(_):
            raise WebSocketConnectionClosedException("closed")

        # Only the first send (the get request) should fail; subsequent sends (login) should work
        send_calls = {"count": 0}

        def _send(payload):
            send_calls["count"] += 1
            if send_calls["count"] == 1:
                raise WebSocketConnectionClosedException("closed")
            return None

        ws.send.side_effect = _send
        ws.recv.side_effect = [
            # after reconnecting in ensure_ws_connected: login ok
            _login_ok(),
            # then get response
            json.dumps(
                {
                    "status": "ok",
                    "response": "get",
                    "data": {"status": {"H00": 1, "H02": 33}},
                    "id": 3,
                }
            ),
        ]

        status = await c.async_get_status()
        assert status.get("H02") == 33
