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


def _get_frame(status: dict[str, int]):
    return json.dumps({"status": "ok", "response": "get", "data": {"status": status}, "id": 3})


async def test_no_push_mode_spawns_no_recv_thread(hass: HomeAssistant):
    from custom_components.fansync.client import FanSyncClient

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

    # No background thread started
    assert c._recv_thread is None  # type: ignore[attr-defined]


async def test_get_timeout_raises(hass: HomeAssistant):
    from custom_components.fansync.client import FanSyncClient

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

        # Provide 5 frames that are not a get response to trigger timeout
        ws.recv.side_effect = [
            json.dumps({"status": "ok", "response": "evt", "data": {"x": 1}}),
            json.dumps({"status": "ok", "response": "evt", "data": {"x": 2}}),
            json.dumps({"status": "ok", "response": "lst_device", "data": []}),
            json.dumps({"status": "ok", "response": "login"}),
            json.dumps({"status": "ok", "response": "evt", "data": {"x": 3}}),
        ]

        try:
            await c.async_get_status()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Expected RuntimeError")


async def test_push_ignores_irrelevant_frames(hass: HomeAssistant):
    from custom_components.fansync.client import FanSyncClient

    seen: list[dict[str, int]] = []
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
        # After connect, supply non-delivery frames only
        ws.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("dev"),
            _get_frame({"H00": 1}),
            json.dumps({"status": "ok", "response": "login"}),
            json.dumps({"status": "ok", "response": "lst_device"}),
        ]
        c.set_status_callback(lambda s: seen.append(s))
        await c.async_connect()

    # Let any background iterations process
    for _ in range(3):
        await hass.async_block_till_done()

    assert seen == []
    await c.async_disconnect()
