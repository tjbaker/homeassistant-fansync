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

"""Push updates for unknown (server-supplied) device ids must be ignored.

Hardening: push_device is server-controlled, so a misbehaving/compromised cloud
could otherwise grow coordinator.data and the diagnostics dicts unboundedly.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str) -> str:
    return json.dumps(
        {"status": "ok", "response": "lst_device", "data": [{"device": device_id}], "id": 2}
    )


def _push_for(device: str, status: dict[str, int]) -> str:
    return json.dumps(
        {"status": "ok", "response": "evt", "device": device, "data": {"status": status}, "id": 999}
    )


async def test_push_for_unknown_device_is_ignored(hass: HomeAssistant) -> None:
    seen: list[tuple[str, dict[str, int]]] = []

    c = FanSyncClient(hass, "e@example.com", "p", verify_ssl=True, enable_push=True)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "t"}
        http.post.return_value.raise_for_status.return_value = None
        ws = ws_connect.return_value

        def recv_generator():
            yield TimeoutError()  # no server greeting
            yield _login_ok()
            yield _lst_device_ok("dev")  # known device set = {"dev"}
            yield _push_for("stranger", {"H02": 99})  # unknown -> must be dropped
            yield _push_for("dev", {"H02": 44})  # known -> delivered
            while True:
                yield TimeoutError("timeout")

        ws.recv.side_effect = recv_generator()
        c.set_status_callback(lambda d, s: seen.append((d, s)))
        await c.async_connect()
        try:
            for _ in range(5):
                await hass.async_block_till_done()

            devices = [d for d, _ in seen]
            assert "stranger" not in devices, "push for unknown device should be dropped"
            assert ("dev", {"H02": 44}) in seen, "push for known device should be delivered"
            # Diagnostics dict must not have grown an entry for the unknown id.
            assert "stranger" not in c._last_push_by_device
        finally:
            await c.async_disconnect()
