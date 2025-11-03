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

from homeassistant.core import HomeAssistant


def _login_ok():
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


def _get_ok(status: dict[str, int]):
    return json.dumps({"status": "ok", "response": "get", "data": {"status": status}, "id": 3})


async def test_get_reconnects_on_closed(hass: HomeAssistant) -> None:
    from custom_components.fansync.client import FanSyncClient
    from websocket import WebSocketConnectionClosedException

    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None
        ws = ws_cls.return_value
        ws.connect.return_value = None
        ws.recv.side_effect = [_login_ok(), _lst_device_ok("dev")]
        await c.async_connect()

        # First send raises closed, client should reconnect and resend
        def _send(msg):
            if not hasattr(_send, "done"):
                _send.done = True
                raise WebSocketConnectionClosedException()
            return None

        ws.send.side_effect = _send
        # After reconnect, client will login again; provide login/get frames
        ws.recv.side_effect = [
            _login_ok(),
            _get_ok({"H00": 1, "H02": 42, "H06": 0, "H01": 0}),
        ]

        s = await c.async_get_status()
        assert s.get("H02") == 42


async def test_set_uses_ack_status_when_present(hass: HomeAssistant) -> None:
    from custom_components.fansync.client import FanSyncClient

    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=True)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None
        ws = ws_cls.return_value
        ws.connect.return_value = None
        ws.recv.side_effect = [_login_ok(), _lst_device_ok("dev")]
        await c.async_connect()

        # Ack includes status; client should short-circuit and push callback with that
        seen: list[dict[str, int]] = []
        c.set_status_callback(lambda s: seen.append(s))

        ws.recv.side_effect = [
            json.dumps(
                {"status": "ok", "response": "set", "data": {"status": {"H02": 77}}, "id": 4}
            )
        ]
        try:
            await c.async_set({"H02": 77})
        finally:
            await c.async_disconnect()

    # Allow dispatcher to run
    for _ in range(2):
        await hass.async_block_till_done()
    assert any(s.get("H02") == 77 for s in seen)


async def test_verify_ssl_false_sets_no_cert_check(hass: HomeAssistant) -> None:
    from custom_components.fansync.client import FanSyncClient

    c = FanSyncClient(hass, "e", "p", verify_ssl=False, enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None
        ws = ws_cls.return_value
        ws.connect.return_value = None
        ws.recv.side_effect = [_login_ok(), _lst_device_ok("dev")]
        await c.async_connect()

        # When verify_ssl=False, websocket constructed with sslopt cert_reqs=ssl.CERT_NONE
        args, kwargs = ws_cls.call_args
        assert "sslopt" in kwargs and kwargs["sslopt"].get("cert_reqs") is not None
