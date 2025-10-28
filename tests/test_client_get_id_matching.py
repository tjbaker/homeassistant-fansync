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


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


def _get_resp(status: dict[str, int], *, id_val: int) -> str:
    return json.dumps({"status": "ok", "response": "get", "id": id_val, "data": {"status": status}})


async def test_get_matches_by_request_id(hass: HomeAssistant):
    from custom_components.fansync.client import FanSyncClient

    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_ctor,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        ws = ws_ctor.return_value
        ws.connect.return_value = None
        # Connect/login/list first
        ws.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("dev"),
        ]

        await c.async_connect()

        # Now for the get call, feed a mismatched-id reply first, then the correct reply
        ws.recv.side_effect = [
            _get_resp({"H02": 11}, id_val=999),
            _get_resp({"H02": 22}, id_val=3),
        ]

        status = await c.async_get_status("dev")
        assert status.get("H02") == 22
