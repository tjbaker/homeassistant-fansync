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
    return json.dumps({"response": "login", "status": "ok", "id": 1})


def _lst_device_ok(device_id):
    return json.dumps({"response": "lst_device", "data": [{"device": device_id}], "id": 2})


@pytest.mark.asyncio
async def test_set_ack_with_status_triggers_callback_exactly_once(
    hass: HomeAssistant, mock_websocket
) -> None:
    """Test that set acknowledgments with status data trigger callback exactly once.

    This test verifies that the message routing system correctly prevents duplicate
    callback invocations when a set acknowledgment includes status data. The 'continue'
    statement in _recv_loop after routing to pending requests should prevent the
    response from being processed again by the push update logic.

    Addresses Copilot PR feedback about potential duplicate callbacks.
    """
    client = FanSyncClient(hass, "e", "p", enable_push=True)

    def recv_generator():
        """Generator that provides responses including set ack with status."""
        # Connection bootstrap
        yield _login_ok()
        yield _lst_device_ok("test_device")
        # Set acknowledgment with status data (request ID 3)
        yield json.dumps(
            {
                "status": "ok",
                "response": "set",
                "id": 3,
                "data": {"status": {"H00": 1, "H02": 50}},
            }
        )
        # Keep recv loop alive with timeouts and irrelevant frames
        while True:
            yield TimeoutError("timeout")
            yield json.dumps({"response": "evt", "data": {}})

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
            {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}},
        )()

        # Setup WebSocket mock
        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        # Track callback invocations with detailed logging
        callback_invocations: list[dict[str, int]] = []

        def track_callback(status: dict[str, int]) -> None:
            """Track each callback invocation with the status data."""
            callback_invocations.append(status.copy())

        client.set_status_callback(track_callback)

        try:
            await client.async_connect()

            # Send set command
            await client.async_set({"H00": 1})

            # Give adequate time for message processing
            # - async_set should complete and trigger callback
            # - recv_loop should process the ack and route to pending request
            # - callback should be invoked exactly once
            await asyncio.sleep(0.5)
            await hass.async_block_till_done()
            await asyncio.sleep(0.2)  # Extra time for any potential duplicate

        finally:
            await client.async_disconnect()

    # Verify callback was invoked exactly once
    assert len(callback_invocations) == 1, (
        f"Expected exactly 1 callback invocation, got {len(callback_invocations)}. "
        f"Invocations: {callback_invocations}"
    )

    # Verify the callback received the correct status data
    assert callback_invocations[0] == {"H00": 1, "H02": 50}, (
        f"Expected callback data {{H00: 1, H02: 50}}, " f"got {callback_invocations[0]}"
    )


@pytest.mark.asyncio
async def test_set_ack_without_status_does_not_trigger_callback(
    hass: HomeAssistant, mock_websocket
) -> None:
    """Test that set acknowledgments without status data do not trigger callback.

    This verifies that only set acks with status data trigger the callback,
    and that the absence of status data doesn't cause errors.
    """
    client = FanSyncClient(hass, "e", "p", enable_push=True)

    def recv_generator():
        """Generator that provides set ack without status data."""
        yield _login_ok()
        yield _lst_device_ok("test_device")
        # Set acknowledgment without status data (request ID 3)
        yield json.dumps({"status": "ok", "response": "set", "id": 3})
        # Keep recv loop alive
        while True:
            yield TimeoutError("timeout")

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R",
            (),
            {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}},
        )()

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        callback_invocations: list[dict[str, int]] = []
        client.set_status_callback(lambda s: callback_invocations.append(s))

        try:
            await client.async_connect()
            await client.async_set({"H00": 1})
            await asyncio.sleep(0.5)
            await hass.async_block_till_done()
        finally:
            await client.async_disconnect()

    # Verify no callback was triggered (no status data in ack)
    assert len(callback_invocations) == 0, (
        f"Expected no callback invocations for ack without status, "
        f"got {len(callback_invocations)}"
    )
