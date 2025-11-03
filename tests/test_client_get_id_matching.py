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
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


def _get_resp(status: dict[str, int], *, id_val: int) -> str:
    return json.dumps({"status": "ok", "response": "get", "id": id_val, "data": {"status": status}})


async def test_get_matches_by_request_id(hass: HomeAssistant, mock_websocket) -> None:
    """Test that async_get_status correctly matches responses by request ID."""
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)

    def recv_generator():
        """Generator that provides responses with matching and mismatched IDs."""
        # Initial connection
        yield _login_ok()
        yield _lst_device_ok("dev")
        # Wait for get request
        while len(mock_websocket.sent_requests) < 3:
            yield TimeoutError("waiting for get request")
        # First response with wrong ID (should be ignored by recv loop)
        yield _get_resp({"H02": 11}, id_val=999)
        # Second response with correct ID (should be used)
        get_request_id = mock_websocket.sent_requests[2]["id"]
        yield _get_resp({"H02": 22}, id_val=get_request_id)
        # Keep recv loop alive
        while True:
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            yield json.dumps({"status": "ok", "response": "evt", "data": {}})

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status = lambda: None
        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await c.async_connect()
        try:
            status = await c.async_get_status("dev")
            assert status.get("H02") == 22
        finally:
            await c.async_disconnect()
