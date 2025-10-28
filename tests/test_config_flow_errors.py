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

from unittest.mock import patch

from homeassistant import data_entry_flow


async def test_config_flow_cannot_connect(hass):
    # Start the config flow via Home Assistant to get a mutable context
    result = await hass.config_entries.flow.async_init("fansync", context={"source": "user"})
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    with patch(
        "custom_components.fansync.config_flow.FanSyncClient.async_connect",
        side_effect=Exception("boom"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "e", "password": "p", "verify_ssl": True},
        )

    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["errors"].get("base") == "cannot_connect"
