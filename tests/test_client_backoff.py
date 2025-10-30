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
from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


async def test_reconnect_on_timeout_and_logging(hass: HomeAssistant, caplog):
    """Test that reconnect triggers on timeouts and logs as expected."""
    from custom_components.fansync.client import FanSyncClient
    from websocket import WebSocketTimeoutException
    import logging

    caplog.set_level(logging.DEBUG)

    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=True)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_ctor,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        # First socket used for initial connect and triggers reconnect
        ws1 = MagicMock()
        ws1.connect.return_value = None
        ws1.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("dev"),
            # trigger reconnect cycle
            WebSocketTimeoutException("t"),
            WebSocketTimeoutException("t"),
            WebSocketTimeoutException("t"),
            _login_ok(),  # reconnect login response
        ]

        # Second socket is created by successful reconnect
        ws2 = MagicMock()
        ws2.timeout = 10
        ws2.recv.return_value = json.dumps({"status": "ok"})

        ws_ctor.side_effect = [ws1, ws2]

        await c.async_connect()

        # Let the background loop run and trigger reconnect
        for _ in range(10):
            await hass.async_block_till_done()

        await c.async_disconnect()

        # Verify we logged timeout errors and at least attempted reconnect handling
        assert any("recv error=WebSocketTimeoutException" in rec.message for rec in caplog.records)
