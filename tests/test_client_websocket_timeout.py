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

"""Test WebSocket timeout exception handling in FanSyncClient."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from websocket import WebSocketTimeoutException

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


async def test_websocket_timeout_converts_to_timeout_error(hass: HomeAssistant) -> None:
    """Test that WebSocketTimeoutException is converted to TimeoutError.

    This ensures consistent error handling across the codebase and prevents
    unexpected exceptions from propagating to Home Assistant's websocket API.
    """
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=True, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
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
        ws = ws_cls.return_value
        ws.connect.return_value = None
        ws.recv.side_effect = [_login_ok(), _lst_device_ok("test_device")]

        try:
            await client.async_connect()

            # Simulate WebSocketTimeoutException on recv during get_status
            ws.recv.side_effect = WebSocketTimeoutException("Connection timed out")

            # Verify that WebSocketTimeoutException is converted to TimeoutError
            with pytest.raises(TimeoutError) as exc_info:
                await client.async_get_status()

            # Verify the error message includes context
            assert "WebSocket recv timed out" in str(exc_info.value)

            # Verify metrics recorded the failure
            assert client.metrics.failed_commands == 1
            assert client.metrics.total_commands == 1

        finally:
            await client.async_disconnect()


async def test_websocket_timeout_during_recv_in_get_status(hass: HomeAssistant) -> None:
    """Test WebSocket timeout during recv in get_status is handled gracefully.

    This simulates the real-world scenario where the cloud API is slow and
    the WebSocket recv operation times out while waiting for a response.
    """
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=True, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
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
        ws = ws_cls.return_value
        ws.connect.return_value = None
        ws.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("test_device"),
            # First get_status times out
            WebSocketTimeoutException("Connection timed out"),
        ]

        try:
            await client.async_connect()

            # First call should raise TimeoutError (converted from WebSocketTimeoutException)
            with pytest.raises(TimeoutError):
                await client.async_get_status()

            # Verify metrics
            assert client.metrics.failed_commands == 1
            assert client.metrics.total_commands == 1

        finally:
            await client.async_disconnect()


async def test_other_exceptions_still_propagate(hass: HomeAssistant) -> None:
    """Test that non-timeout exceptions still propagate normally.

    This ensures we're not catching too broadly and only handling
    WebSocketTimeoutException specifically.
    """
    client = FanSyncClient(hass, "test@example.com", "password", verify_ssl=True, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
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
        ws = ws_cls.return_value
        ws.connect.return_value = None
        ws.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("test_device"),
            # Simulate a different exception (not timeout)
            RuntimeError("Connection closed unexpectedly"),
        ]

        try:
            await client.async_connect()

            # RuntimeError should propagate as-is
            with pytest.raises(RuntimeError, match="Connection closed unexpectedly"):
                await client.async_get_status()

            # Verify metrics
            assert client.metrics.failed_commands == 1

        finally:
            await client.async_disconnect()
