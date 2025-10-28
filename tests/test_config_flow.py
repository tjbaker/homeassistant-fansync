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

"""Tests for the config flow UI interactions and entry creation.

Validates that the initial form shows and that a user-provided configuration
creates a config entry with the provided data.
"""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

DOMAIN = "fansync"


async def test_show_form(hass: HomeAssistant):
    """Show initial config form for the integration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_create_entry(hass: HomeAssistant):
    """Create a config entry from user-provided credentials."""
    user_input = {"email": "user@example.com", "password": "pw", "verify_ssl": False}
    with patch("custom_components.fansync.config_flow.FanSyncClient") as mock_client:
        mock_client.return_value.async_connect = AsyncMock(return_value=None)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=user_input
        )
    assert result["type"] == "create_entry"
    assert result["data"] == user_input
