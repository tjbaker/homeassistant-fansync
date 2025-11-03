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
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


async def test_set_ack_status_immediate_push(hass: HomeAssistant, mock_websocket) -> None:
    """Test that set ack with status data triggers push callback."""
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

        def recv_generator():
            """Generator for push ack scenario."""
            # Initial connection
            yield _login_ok()
            yield _lst_device_ok("id")
            # Set ACK with status data (ID 3, no reconnect with state=OPEN)
            yield json.dumps(
                {
                    "status": "ok",
                    "response": "set",
                    "id": 3,
                    "data": {"status": {"H00": 1, "H02": 77}},
                }
            )
            # Keep loop alive
            while True:
                yield TimeoutError("timeout")
                yield TimeoutError("timeout")
                yield json.dumps({"status": "ok", "response": "evt", "data": {}})

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        seen: list[dict[str, int]] = []
        c.set_status_callback(lambda s: seen.append(s))

        await c.async_connect()
        try:
            await c.async_set({"H02": 77})
            # Allow time for recv loop to process the set ack
            await asyncio.sleep(0.2)
            await hass.async_block_till_done()
        finally:
            await c.async_disconnect()

    assert seen and seen[-1].get("H02") == 77, f"Expected H02=77 in {seen}"
