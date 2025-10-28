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
# Copyright 2025 Trevor Baker, all rights reserved.

"""Tests for unique ID handling in the config flow.

Ensures the first submission creates an entry and a duplicate submission
with the same identifying data is aborted by Home Assistant.
"""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

DOMAIN = "fansync"


async def test_unique_id_and_duplicate(hass: HomeAssistant):
    """First submission creates entry; second with same data aborts."""
    data = {"email": "unique@example.com", "password": "pw", "verify_ssl": True}
    with patch("custom_components.fansync.config_flow.FanSyncClient") as mock_client:
        mock_client.return_value.async_connect = AsyncMock(return_value=None)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=data
        )
    assert result["type"] == "create_entry"

    # Second attempt with same email should abort
    result2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=data
    )
    assert result2["type"] == "abort"
