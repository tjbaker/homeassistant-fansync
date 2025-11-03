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

import logging
import time
from unittest.mock import Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.client import FanSyncClient


class LogClient:
    def __init__(self):
        self.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0}
        self.device_ids = ["dev"]
        self.device_id = "dev"
        self._cb = None

    async def async_connect(self):
        return None

    async def async_disconnect(self):
        return None

    async def async_get_status(self, device_id=None):
        return dict(self.status)

    async def async_set(self, data, *, device_id=None):
        self.status.update(data)
        # Provide ack-with-status behavior
        return dict(self.status)

    def set_status_callback(self, cb):
        self._cb = cb


async def setup(hass: HomeAssistant, client: LogClient) -> None:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="log-debug",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.fansync.FanSyncClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_fan_emits_debug_logs(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    client = LogClient()
    await setup(hass, client)

    class FakeMonotonic:
        def __init__(self, t: float):
            self.t = t

        def __call__(self) -> float:
            return self.t

    base = time.monotonic()
    fake_monotonic = FakeMonotonic(base)

    with patch("custom_components.fansync.fan.time.monotonic", side_effect=fake_monotonic):
        await hass.services.async_call(
            "fan",
            "set_percentage",
            {"entity_id": "fan.fan", "percentage": 55},
            blocking=True,
        )

        # During guard, coordinator updates that don't satisfy predicate are ignored
        assert any("optimism start" in r.getMessage() for r in caplog.records)
        # Advance beyond guard and ensure handler logs guard ignore at least once
        fake_monotonic.t = base + 1.0
        await hass.async_block_till_done()

    # Ensure confirm path also logs
    assert any("optimism confirm" in r.getMessage() for r in caplog.records)


async def test_client_logs_ack_status(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=True)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http_inst = http_cls.return_value
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock(return_value=None)
        mock_resp.json = Mock(return_value={"token": "t"})
        http_inst.post.return_value = mock_resp
        ws = ws_cls.return_value
        ws.connect.return_value = None
        # login, list, then set ACK with embedded status (no subsequent get response provided)
        ws.recv.side_effect = [
            # login ok
            '{"status": "ok", "response": "login", "id": 1}',
            # list devices
            '{"status": "ok", "response": "lst_device", "data": [{"device": "id"}], "id": 2}',
            # set ack with status
            '{"status": "ok", "response": "set", "id": 4, "data": {"status": {"H00": 1, "H02": 33}}}',
        ]
        await c.async_connect()
        try:
            await c.async_set({"H02": 33})
            await hass.async_block_till_done()
        finally:
            await c.async_disconnect()

    msgs = [r.getMessage() for r in caplog.records]
    assert any("set start" in m for m in msgs)
    # The recv_loop processes the set ack and logs it
    assert any("recv set ack with status" in m for m in msgs)
