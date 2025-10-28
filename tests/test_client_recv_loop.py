# SPDX-License-Identifier: Apache-2.0

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


def _push_status(status: dict[str, int]) -> str:
    return json.dumps({"status": "ok", "response": "evt", "data": {"status": status}, "id": 999})


async def test_client_push_loop_invokes_callback(hass: HomeAssistant):
    from custom_components.fansync.client import FanSyncClient

    seen: list[dict[str, int]] = []

    c = FanSyncClient(hass, "e@example.com", "p", verify_ssl=True, enable_push=True)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None
        ws = ws_cls.return_value
        ws.connect.return_value = None
        # Return login, device list, then a push event
        ws.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("dev"),
            _push_status({"H00": 1, "H02": 44, "H06": 0, "H01": 0}),
        ]

        c.set_status_callback(lambda s: seen.append(s))
        await c.async_connect()

    # Allow thread to run once via event loop iterations
    for _ in range(3):
        await hass.async_block_till_done()

    assert any(s.get("H02") == 44 for s in seen)

    # Ensure background thread is stopped to avoid lingering thread error
    await c.async_disconnect()
