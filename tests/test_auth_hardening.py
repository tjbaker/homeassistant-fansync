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

"""Regression tests for WebSocket/auth hardening.

Covers: token refresh on reconnect after auth failure, serialized reconnects,
malformed get-response validation, and config-flow email normalization.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import data_entry_flow
from homeassistant.core import HomeAssistant
from websockets.protocol import State

from custom_components.fansync.client import FanSyncClient


def _mock_ws(state: State = State.OPEN, recv_response: str | None = None) -> MagicMock:
    ws = MagicMock()
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    ws.state = state
    ws.recv = AsyncMock(return_value=recv_response) if recv_response else AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_reconnect_clears_token_on_login_failure(hass: HomeAssistant) -> None:
    """A failed WS login must drop the token so the next reconnect re-authenticates.

    Without clearing it, ``_token`` stays truthy forever, the refresh branch is
    dead, and a reconnect after token expiry loops indefinitely.
    """
    client = FanSyncClient(hass, "e@x.com", "p")
    client._ws = _mock_ws(state=State.CLOSED)
    client._token = "expired-token"
    client._http = MagicMock()
    import ssl

    client._ssl_context = ssl.create_default_context()

    # New socket whose login response is NOT ok.
    new_ws = _mock_ws(recv_response='{"status": "error", "response": "login"}')

    with patch(
        "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
    ) as ws_connect:
        ws_connect.return_value = new_ws
        with pytest.raises(RuntimeError, match="login failed"):
            await client._ensure_ws_connected()

    # Token cleared → next _ensure_ws_connected() will HTTP-refresh it.
    assert client._token is None


@pytest.mark.asyncio
async def test_concurrent_reconnects_run_once(hass: HomeAssistant) -> None:
    """Two concurrent reconnects must serialize and perform a single reconnect."""
    client = FanSyncClient(hass, "e@x.com", "p")
    client._ws = None
    calls = {"n": 0}
    open_ws = _mock_ws(state=State.OPEN)

    async def fake_reconnect() -> None:
        calls["n"] += 1
        await asyncio.sleep(0)  # let the other coroutine reach the lock
        client._ws = open_ws

    client._reconnect = fake_reconnect  # type: ignore[method-assign]

    await asyncio.gather(client._ensure_ws_connected(), client._ensure_ws_connected())

    # Second caller re-checks under the lock, sees an OPEN socket, and skips.
    assert calls["n"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"status": "error", "id": 5},  # not ok, no data
        {"status": "ok", "id": 5},  # ok but no data
        {"status": "ok", "id": 5, "data": {}},  # ok, data but no status
        {"status": "ok", "id": 5, "data": {"status": "oops"}},  # status not a dict
    ],
)
async def test_get_status_rejects_malformed_response(hass: HomeAssistant, payload: dict) -> None:
    """A malformed/offline get-response raises a clean error, never KeyError."""
    client = FanSyncClient(hass, "e@x.com", "p")
    client._device_id = "dev1"
    client._send_request = AsyncMock(return_value=(payload, 5))  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="Unexpected get response"):
        await client.async_get_status("dev1")


@pytest.mark.asyncio
async def test_get_status_returns_status_on_valid_response(hass: HomeAssistant) -> None:
    """A well-formed response still returns the status mapping."""
    client = FanSyncClient(hass, "e@x.com", "p")
    client._device_id = "dev1"
    good = {"status": "ok", "id": 5, "data": {"status": {"H00": 1, "H02": 40}}}
    client._send_request = AsyncMock(return_value=(good, 5))  # type: ignore[method-assign]

    assert await client.async_get_status("dev1") == {"H00": 1, "H02": 40}


async def test_config_flow_normalizes_email_unique_id(
    hass: HomeAssistant, ensure_fansync_importable
) -> None:
    """Mixed-case/whitespace emails collapse to one normalized unique_id."""
    with (
        patch("custom_components.fansync.config_flow.FanSyncClient") as client_cls,
        patch("custom_components.fansync.FanSyncClient") as mock_setup,
    ):
        instance = client_cls.return_value
        instance.async_connect = AsyncMock(return_value=None)
        instance.async_disconnect = AsyncMock(return_value=None)
        instance.device_ids = ["dev"]
        mock_setup.return_value.async_connect = AsyncMock(side_effect=RuntimeError("no setup"))

        result = await hass.config_entries.flow.async_init(
            "fansync",
            context={"source": "user"},
            data={"email": "  User@Example.COM ", "password": "p", "verify_ssl": True},
        )
        await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    entries = hass.config_entries.async_entries("fansync")
    assert len(entries) == 1
    assert entries[0].unique_id == "user@example.com"
