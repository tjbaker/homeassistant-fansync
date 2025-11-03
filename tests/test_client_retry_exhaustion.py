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

"""Test connection retry exhaustion scenarios."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


@pytest.mark.asyncio
async def test_connect_retry_exhaustion_timeout(hass: HomeAssistant) -> None:
    """Test that connection fails after exhausting retries due to timeouts."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()

        # Make all WebSocket connection attempts timeout
        ws_connect.side_effect = TimeoutError("Connection timeout")

        # Should fail after max retries (2 attempts: initial + 1 retry)
        with pytest.raises(TimeoutError):
            await client.async_connect()

        # Verify it tried multiple times (initial + 1 retry = 2 total)
        assert ws_connect.call_count == 2


@pytest.mark.asyncio
async def test_connect_retry_exhaustion_oserror(hass: HomeAssistant) -> None:
    """Test that connection fails after exhausting retries due to OSError."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()

        # Make all WebSocket connection attempts fail with OSError
        ws_connect.side_effect = OSError("Connection refused")

        # Should fail after max retries (2 attempts: initial + 1 retry)
        with pytest.raises(OSError, match="Connection refused"):
            await client.async_connect()

        # Verify it tried multiple times
        assert ws_connect.call_count == 2


@pytest.mark.asyncio
async def test_connect_retry_success_on_second_attempt(hass: HomeAssistant, mock_websocket) -> None:
    """Test that connection succeeds on retry after initial failure."""
    import json

    client = FanSyncClient(hass, "e", "p", enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()

        # First attempt fails, second succeeds
        mock_websocket.recv.side_effect = [
            json.dumps({"status": "ok", "response": "login", "id": 1}),
            json.dumps(
                {
                    "status": "ok",
                    "response": "lst_device",
                    "data": [{"device": "id"}],
                    "id": 2,
                }
            ),
        ]
        ws_connect.side_effect = [TimeoutError("Timeout"), mock_websocket]

        # Should succeed on second attempt
        await client.async_connect()

        # Verify it tried twice
        assert ws_connect.call_count == 2

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_connect_retry_with_backoff(hass: HomeAssistant, mock_websocket) -> None:
    """Test that retry uses exponential backoff between attempts."""
    import json
    import time

    client = FanSyncClient(hass, "e", "p", enable_push=False)

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
        patch("custom_components.fansync.client.asyncio.sleep") as mock_sleep,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()
        mock_sleep.return_value = None

        # First attempt fails, second succeeds
        mock_websocket.recv.side_effect = [
            json.dumps({"status": "ok", "response": "login", "id": 1}),
            json.dumps(
                {
                    "status": "ok",
                    "response": "lst_device",
                    "data": [{"device": "id"}],
                    "id": 2,
                }
            ),
        ]
        ws_connect.side_effect = [TimeoutError("Timeout"), mock_websocket]

        # Should succeed on second attempt
        await client.async_connect()

        # Verify backoff was called (once after first failure)
        assert mock_sleep.call_count >= 1

        await client.async_disconnect()
