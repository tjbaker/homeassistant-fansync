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
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


def _push_status(status: dict[str, int]) -> str:
    return json.dumps({"status": "ok", "response": "evt", "data": {"status": status}, "id": 999})


async def test_recv_loop_reconnects_after_timeouts(hass: HomeAssistant, mock_websocket):
    """Test that recv loop reconnects after 3 consecutive timeouts."""
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=True)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        def recv_generator():
            """Generator for reconnect scenario."""
            # Initial connection
            yield _login_ok()
            yield _lst_device_ok("dev")
            # Trigger reconnect (3 consecutive timeouts)
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            # Reconnect login
            yield _login_ok()
            # Push event after reconnect
            yield _push_status({"H02": 33})
            # Keep loop alive
            while True:
                yield TimeoutError("timeout")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        seen: list[dict[str, int]] = []
        c.set_status_callback(lambda s: seen.append(s))

        # Wrap ensure_ws to observe reconnect calls
        with patch.object(c, "_ensure_ws_connected", wraps=c._ensure_ws_connected) as ensure_wrap:
            await c.async_connect()

            # Allow background task to process exceptions, reconnect and receive push
            await asyncio.sleep(0.5)
            for _ in range(10):
                await hass.async_block_till_done()

            assert ensure_wrap.call_count >= 1
            assert any(s.get("H02") == 33 for s in seen), f"Expected H02=33 in {seen}"

        await c.async_disconnect()
