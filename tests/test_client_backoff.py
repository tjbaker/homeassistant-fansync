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
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


async def test_reconnect_on_timeout_and_logging(hass: HomeAssistant, caplog, mock_websocket):
    """Test that reconnect triggers on timeouts and logs as expected."""
    caplog.set_level(logging.DEBUG)

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
            """Generator that triggers reconnect after 3 consecutive timeouts."""
            yield _login_ok()
            yield _lst_device_ok("dev")
            # Trigger reconnect cycle (3 consecutive timeouts)
            yield TimeoutError("t")
            yield TimeoutError("t")
            yield TimeoutError("t")
            # Reconnect login response
            yield _login_ok()
            # Keep loop alive
            while True:
                yield TimeoutError("timeout")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await c.async_connect()

        # Let the background loop run and trigger reconnect
        await asyncio.sleep(0.5)
        for _ in range(10):
            await hass.async_block_till_done()

        await c.async_disconnect()

        # Verify we logged timeout errors and at least attempted reconnect handling
        assert any("recv error=TimeoutError" in rec.message for rec in caplog.records)
