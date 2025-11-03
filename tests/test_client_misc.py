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

"""Miscellaneous client tests.

Note on generator pattern for mock side_effect:
When a generator yields an exception instance (e.g., TimeoutError("msg")),
unittest.mock's AsyncMock automatically RAISES that exception instead of
returning it. This is the correct pattern - do NOT change yield to raise
in the generator, as that would exhaust the generator prematurely.
See: https://docs.python.org/3/library/unittest.mock.html#unittest.mock.Mock.side_effect
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok():
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


def _get_frame(status: dict[str, int]):
    return json.dumps({"status": "ok", "response": "get", "data": {"status": status}, "id": 3})


async def test_no_push_mode_spawns_no_recv_thread(hass: HomeAssistant, mock_websocket):
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None
        mock_websocket.recv.side_effect = [_login_ok(), _lst_device_ok("dev")]
        ws_connect.return_value = mock_websocket
        await c.async_connect()

    # No background task started
    assert c._recv_task is None


async def test_get_timeout_raises(hass: HomeAssistant, mock_websocket):
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        # Generator that provides non-get frames then times out
        def recv_generator():
            yield _login_ok()
            yield _lst_device_ok("dev")
            # Reconnect during get_status
            yield _login_ok()
            # Provide non-get frames, then timeout (no get response ever comes)
            for i in range(5):
                yield json.dumps({"status": "ok", "response": "evt", "data": {"x": i}})
            # Eventually timeout waiting for get response
            yield TimeoutError("timeout")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket
        await c.async_connect()

        try:
            await c.async_get_status()
        except TimeoutError:
            pass
        else:
            raise AssertionError("Expected TimeoutError")


async def test_push_ignores_irrelevant_frames(hass: HomeAssistant, mock_websocket):
    seen: list[dict[str, int]] = []
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
            """Generator for recv loop with irrelevant frames."""
            yield _login_ok()
            yield _lst_device_ok("dev")
            # These should be ignored by recv loop
            yield json.dumps({"status": "ok", "response": "login"})
            yield json.dumps({"status": "ok", "response": "get", "data": {"status": {"H00": 1}}})
            yield json.dumps({"status": "ok", "response": "lst_device", "data": []})
            # This one should trigger callback
            yield json.dumps(
                {"status": "ok", "response": "evt", "data": {"status": {"H00": 1, "H02": 99}}}
            )
            # Keep loop alive
            while True:
                yield TimeoutError("timeout")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        c.set_status_callback(lambda s: seen.append(s))
        await c.async_connect()

        try:
            await asyncio.sleep(0.3)
            await hass.async_block_till_done()
        finally:
            await c.async_disconnect()

    assert seen and seen[-1].get("H02") == 99
