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

from unittest.mock import AsyncMock, patch

from homeassistant import data_entry_flow


async def test_config_flow_creates_entry(hass, ensure_fansync_importable):
    # Use HA flow helpers directly with data to mirror typical happy path
    with patch("custom_components.fansync.config_flow.FanSyncClient") as client_cls:
        instance = client_cls.return_value
        instance.async_connect = AsyncMock(return_value=None)
        instance.async_disconnect = AsyncMock(return_value=None)
        instance.device_ids = ["dev"]

        result = await hass.config_entries.flow.async_init(
            "fansync",
            context={"source": "user"},
            data={"email": "ux@example.com", "password": "p", "verify_ssl": True},
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "FanSync"
    assert result["data"]["email"] == "ux@example.com"
