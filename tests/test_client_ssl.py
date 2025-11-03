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

"""Client construction and SSL verification behavior tests.

Verifies that the HTTP client is instantiated with the expected verify flag
when the integration is configured with verify_ssl=True.
"""

import json
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


async def test_client_ssl_flag(hass: HomeAssistant, mock_websocket):
    """Ensure FanSyncClient builds HTTPX client with verify=True when configured."""
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)
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

        def recv_generator():
            yield '{"status":"ok","response":"login","id":1}'
            yield '{"status":"ok","response":"lst_device","data":[{"device":"id"}],"id":2}'
            while True:
                yield TimeoutError("timeout")
                yield TimeoutError("timeout")
                yield json.dumps({"status": "ok", "response": "evt", "data": {}})

        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await c.async_connect()
        await c.async_disconnect()
        # Client passes timeout=None to httpx.Client
        http_cls.assert_called_with(verify=True, timeout=None)
