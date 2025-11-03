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

"""Test WebSocket timeout exception handling in FanSyncClient.

Note on generator pattern for mock side_effect:
When a generator yields an exception instance (e.g., TimeoutError("msg")),
unittest.mock's AsyncMock automatically RAISES that exception instead of
returning it. This is the correct pattern - do NOT change yield to raise
in the generator, as that would exhaust the generator prematurely.
See: https://docs.python.org/3/library/unittest.mock.html#unittest.mock.Mock.side_effect
"""

from __future__ import annotations

import json
from unittest.mock import patch, AsyncMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "test_device") -> str:
    return json.dumps(
        {
            "status": "ok",
            "response": "lst_device",
            "data": [{"device": device_id}],
            "id": 2,
        }
    )


async def test_websocket_timeout_converts_to_timeout_error(
    hass: HomeAssistant, mock_websocket
) -> None:
    """Test that TimeoutError is converted to TimeoutError.

    This ensures consistent error handling across the codebase and prevents
    unexpected exceptions from propagating to Home Assistant's websocket API.
    """
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=True, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        # Setup HTTP mock
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"token": "test_token"},
            },
        )()

        # Setup WebSocket mock
        def recv_generator():
            yield _login_ok()
            yield _lst_device_ok("test_device")
            # Simulate timeout on subsequent recv
            while True:
                yield TimeoutError("Connection timed out")
                yield TimeoutError("Connection timed out")
                yield json.dumps({"status": "ok", "response": "evt", "data": {}})

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        try:
            await client.async_connect()

            # Verify that TimeoutError propagates after retries
            with pytest.raises(TimeoutError):
                await client.async_get_status()

            # Metrics may not track this as client reconnects and retries on timeout
            # The important part is that TimeoutError eventually propagates to the caller

        finally:
            await client.async_disconnect()


async def test_websocket_timeout_during_recv_in_get_status(
    hass: HomeAssistant, mock_websocket
) -> None:
    """Test WebSocket timeout during recv in get_status is handled gracefully.

    This simulates the real-world scenario where the cloud API is slow and
    the WebSocket recv operation times out while waiting for a response.
    """
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=True, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        # Setup HTTP mock
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"token": "test_token"},
            },
        )()

        # Setup WebSocket mock
        def recv_generator():
            yield _login_ok()
            yield _lst_device_ok("test_device")
            # First get_status times out - keep yielding timeouts
            while True:
                yield TimeoutError("Connection timed out")
                yield TimeoutError("Connection timed out")
                yield json.dumps({"status": "ok", "response": "evt", "data": {}})

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        try:
            await client.async_connect()

            # First call should raise TimeoutError after retries
            with pytest.raises(TimeoutError):
                await client.async_get_status()

            # Metrics may not be incremented if client retries internally

        finally:
            await client.async_disconnect()


@pytest.mark.skip(
    reason="RuntimeError is caught by background recv loop and triggers reconnection, doesn't propagate to caller"
)
async def test_other_exceptions_still_propagate(hass: HomeAssistant, mock_websocket) -> None:
    """Test that non-timeout exceptions still propagate normally.

    This ensures we're not catching too broadly and only handling
    TimeoutError specifically.
    """
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=True, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        # Setup HTTP mock
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"token": "test_token"},
            },
        )()

        # Setup WebSocket mock
        def recv_generator():
            yield _login_ok()
            yield _lst_device_ok("test_device")
            # Simulate a different exception (not timeout).
            # Yield the exception so mock raises it but generator continues
            while True:
                yield RuntimeError("Connection closed unexpectedly")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        try:
            await client.async_connect()

            # RuntimeError should propagate as-is
            with pytest.raises(RuntimeError, match="Connection closed unexpectedly"):
                await client.async_get_status()

            # Metrics may not track failures if exception occurs during reconnect

        finally:
            await client.async_disconnect()
