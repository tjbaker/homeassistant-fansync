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
from unittest.mock import patch, AsyncMock

from homeassistant.core import HomeAssistant


def _login_ok():
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


def _push_status(status: dict[str, int]) -> str:
    return json.dumps({"status": "ok", "response": "evt", "data": {"status": status}, "id": 999})


async def test_client_push_loop_invokes_callback(hass: HomeAssistant):
    from custom_components.fansync.client import FanSyncClient

    seen: list[dict[str, int]] = []

    c = FanSyncClient(hass, "e@example.com", "p", verify_ssl=True, enable_push=True)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None
        ws = ws_connect.return_value
        ws.connect.return_value = None

        # Return login, device list, then a push event
        def recv_generator():
            yield _login_ok()
            yield _lst_device_ok("dev")
            yield _push_status({"H00": 1, "H02": 44, "H06": 0, "H01": 0})
            while True:
                yield TimeoutError("timeout")
                yield TimeoutError("timeout")
                yield json.dumps({"status": "ok", "response": "evt", "data": {}})

        ws.recv.side_effect = recv_generator()

        c.set_status_callback(lambda s: seen.append(s))
        await c.async_connect()

        try:
            # Allow thread to run once via event loop iterations
            for _ in range(3):
                await hass.async_block_till_done()

            assert any(s.get("H02") == 44 for s in seen)
        finally:
            await c.async_disconnect()
