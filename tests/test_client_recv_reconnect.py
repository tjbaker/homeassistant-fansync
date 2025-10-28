# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Trevor Baker, all rights reserved.

from __future__ import annotations

import json
import asyncio
from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


def _push_status(status: dict[str, int]) -> str:
    return json.dumps({"status": "ok", "response": "evt", "data": {"status": status}, "id": 999})


async def test_recv_loop_reconnects_after_timeouts(hass: HomeAssistant):
    from custom_components.fansync.client import FanSyncClient
    from websocket import WebSocketTimeoutException

    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=True)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_ctor,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        # First socket: used for login/list and then times out 3 times in recv loop
        ws1 = MagicMock()
        ws1.connect.return_value = None
        ws1.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("dev"),
            WebSocketTimeoutException("timeout"),
            WebSocketTimeoutException("timeout"),
            WebSocketTimeoutException("timeout"),
        ]
        # Second socket: created by reconnect; returns a push event
        ws2 = MagicMock()
        ws2.timeout = 10
        # Re-login on reconnect, then provide a push event
        ws2.recv.side_effect = [_login_ok(), _push_status({"H02": 33})]

        ws_ctor.side_effect = [ws1, ws2]

        seen: list[dict[str, int]] = []
        c.set_status_callback(lambda s: seen.append(s))

        # Wrap ensure_ws to observe reconnect calls
        with patch.object(c, "_ensure_ws_connected", wraps=c._ensure_ws_connected) as ensure_wrap:
            await c.async_connect()

            # Allow background thread to process exceptions, reconnect and receive push
            for _ in range(20):
                await asyncio.sleep(0.05)
                await hass.async_block_till_done()

            assert ensure_wrap.call_count >= 1
            assert any(s.get("H02") == 33 for s in seen)

        await c.async_disconnect()
