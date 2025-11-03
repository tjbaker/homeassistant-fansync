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

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


async def test_set_ack_status_immediate_push(hass: HomeAssistant) -> None:
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=True)
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
        # login, list, then set ACK with status
        ws.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("id"),
            json.dumps(
                {
                    "status": "ok",
                    "response": "set",
                    "id": 4,
                    "data": {"status": {"H00": 1, "H02": 77}},
                }
            ),
        ]

        seen: list[dict[str, int]] = []
        c.set_status_callback(lambda s: seen.append(s))

        await c.async_connect()
        try:
            await c.async_set({"H02": 77})
            await hass.async_block_till_done()
        finally:
            await c.async_disconnect()

    assert seen and seen[-1].get("H02") == 77
