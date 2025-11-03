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

"""Test enhanced logging for error scenarios."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str) -> str:
    return json.dumps(
        {
            "status": "ok",
            "response": "lst_device",
            "data": [{"owner": "test", "id": device_id}],
        }
    )


async def test_connection_retry_exhaustion_logs_error(
    hass: HomeAssistant, mock_websocket, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that retry exhaustion logs an ERROR message."""
    caplog.set_level("DEBUG")
    client = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        # All connection attempts fail
        ws_connect.side_effect = TimeoutError("Connection timeout")

        with pytest.raises(TimeoutError, match="Connection timeout"):
            await client.async_connect()

        # Verify DEBUG log shows retry attempts
        retry_logs = [
            r
            for r in caplog.records
            if "ws initial connect/login failed" in r.message and "attempt" in r.message
        ]
        assert len(retry_logs) == 2  # WS_LOGIN_RETRY_ATTEMPTS = 2


async def test_device_list_failure_logs_error(
    hass: HomeAssistant, mock_websocket, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that device list fetch failure logs an ERROR."""
    caplog.set_level("ERROR")
    client = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        # Login succeeds but device list times out
        def recv_generator():
            yield _login_ok()
            raise TimeoutError("Device list timeout")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        with pytest.raises(TimeoutError, match="Device list timeout"):
            await client.async_connect()

        # Verify ERROR log was written
        assert any(
            "Failed to fetch device list" in record.message and "TimeoutError" in record.message
            for record in caplog.records
        )


async def test_json_parse_failure_logs_debug(
    hass: HomeAssistant, mock_websocket, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that JSON parse failures are logged at DEBUG level."""
    caplog.set_level("DEBUG")
    client = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=True)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        # Login succeeds, then send invalid JSON
        def recv_generator():
            yield _login_ok()
            yield _lst_device_ok("dev")
            yield "not valid json {{"  # Invalid JSON
            while True:
                yield TimeoutError("timeout")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await client.async_connect()
        await asyncio.sleep(0.2)  # Let recv_task process invalid JSON

        # Verify DEBUG log for invalid JSON
        assert any("recv: invalid JSON, skipping" in record.message for record in caplog.records)


async def test_device_list_timeout_logging(
    hass: HomeAssistant, mock_websocket, caplog: pytest.LogCaptureFixture
) -> None:
    """Test device list timeout is logged at ERROR and DEBUG levels."""
    caplog.set_level("DEBUG")
    client = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None

        # Login succeeds but device list times out
        def recv_generator():
            yield _login_ok()
            raise TimeoutError("Device list timeout")

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        with pytest.raises(TimeoutError):
            await client.async_connect()

        # Verify both ERROR and DEBUG logs
        error_logs = [
            r
            for r in caplog.records
            if r.levelname == "ERROR" and "Failed to fetch device list" in r.message
        ]
        debug_logs = [
            r
            for r in caplog.records
            if r.levelname == "DEBUG" and "Device list error details" in r.message
        ]
        assert len(error_logs) == 1
        assert len(debug_logs) == 1
