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


async def test_recv_backoff_increases_then_resets(hass: HomeAssistant):
    from custom_components.fansync.client import FanSyncClient
    from websocket import WebSocketTimeoutException

    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=True)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_ctor,
        patch("custom_components.fansync.client.time.sleep") as sleep_mock,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        # First socket used for initial connect
        ws1 = MagicMock()
        ws1.connect.return_value = None
        ws1.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("dev"),
            # trigger reconnect cycle
            WebSocketTimeoutException("t"),
            WebSocketTimeoutException("t"),
            WebSocketTimeoutException("t"),
        ]

        # Second socket is created by successful reconnect; provide a benign frame to settle
        ws2 = MagicMock()
        ws2.timeout = 10
        ws2.recv.side_effect = [json.dumps({"status": "ok", "response": "evt", "data": {}})]

        ws_ctor.side_effect = [ws1, ws2]

        # Make ensure_ws_connected fail once (to cause backoff), then succeed
        original_ensure = FanSyncClient._ensure_ws_connected

        def flaky_ensure(self):  # type: ignore[no-redef]
            if not hasattr(self, "_test_failures"):
                self._test_failures = 1  # type: ignore[attr-defined]
            if self._test_failures > 0:  # type: ignore[attr-defined]
                self._test_failures -= 1  # type: ignore[attr-defined]
                raise RuntimeError("fail connect")
            return original_ensure(self)

        with patch.object(FanSyncClient, "_ensure_ws_connected", new=flaky_ensure):
            await c.async_connect()

        # Let the background loop run and hit the failure path
        for _ in range(10):
            await hass.async_block_till_done()

        # We expect at least one backoff sleep call (0.5 seconds)
        calls = [args[0][0] for args in sleep_mock.call_args_list if args[0]]
        assert any(abs(v - 0.5) < 1e-6 for v in calls)

        await c.async_disconnect()
