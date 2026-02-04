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

import pytest
from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok():
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


def _get_ok(status: dict[str, int]):
    return json.dumps({"status": "ok", "response": "get", "data": {"status": status}, "id": 3})


async def test_set_uses_ack_status_when_present(hass: HomeAssistant, mock_websocket) -> None:
    """Test that set commands complete without error when ack is present.

    Note: With async recv_loop architecture, the ack is processed
    by the background task. This test verifies the command completes
    successfully without blocking.
    """
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
            """Generator that simulates WebSocket recv with set ack."""
            yield _login_ok()
            yield _lst_device_ok("dev")
            # Set ack with status (ID 3, no reconnect with state=OPEN)
            yield json.dumps(
                {
                    "status": "ok",
                    "response": "set",
                    "id": 3,
                    "data": {"status": {"H00": 0, "H02": 1}},
                }
            )
            # Keep recv loop alive
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
            await c.async_set({"H00": 0})
            await asyncio.sleep(0.3)
            await hass.async_block_till_done()
        finally:
            await c.async_disconnect()

    assert seen and seen[-1].get("H00") == 0


async def test_verify_ssl_false_sets_no_cert_check(hass: HomeAssistant, mock_websocket) -> None:
    c = FanSyncClient(hass, "e", "p", verify_ssl=False, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
        patch("custom_components.fansync.client.ssl.create_default_context") as ssl_ctx_mock,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        def recv_generator():
            yield _login_ok()
            yield _lst_device_ok("dev")
            while True:
                yield TimeoutError("timeout")
                yield TimeoutError("timeout")
                yield json.dumps({"status": "ok", "response": "evt", "data": {}})

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket
        await c.async_connect()

        try:
            # Verify SSL context was created and configured
            assert ssl_ctx_mock.called
            ssl_context = ssl_ctx_mock.return_value
            assert ssl_context.check_hostname is False
            assert ssl_context.verify_mode == 0  # ssl.CERT_NONE
        finally:
            await c.async_disconnect()
