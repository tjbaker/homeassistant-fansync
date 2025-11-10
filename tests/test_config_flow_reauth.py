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

"""Test reauth flow for FanSync integration."""

from unittest.mock import AsyncMock, patch

import httpx
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.const import CONF_EMAIL, CONF_PASSWORD, DOMAIN


async def test_reauth_flow_success(hass: HomeAssistant) -> None:
    """Test successful reauth flow."""
    # Create existing config entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old_password",
        },
        unique_id="user@example.com",
    )
    entry.add_to_hass(hass)

    # Start reauth flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    # Mock successful connection with new password
    with (patch("custom_components.fansync.config_flow.FanSyncClient") as mock_client_class,):
        mock_client = mock_client_class.return_value
        mock_client.async_connect = AsyncMock()
        mock_client.async_disconnect = AsyncMock()
        mock_client.device_ids = ["test-device"]

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: "new_password"},
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"

    # Verify password was updated
    await hass.async_block_till_done()
    assert entry.data[CONF_PASSWORD] == "new_password"


async def test_reauth_flow_invalid_credentials(hass: HomeAssistant) -> None:
    """Test reauth flow with invalid credentials."""
    # Create existing config entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old_password",
        },
        unique_id="user@example.com",
    )
    entry.add_to_hass(hass)

    # Start reauth flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    # Mock authentication failure
    with (patch("custom_components.fansync.config_flow.FanSyncClient") as mock_client_class,):
        mock_client = mock_client_class.return_value
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_client.async_connect = AsyncMock(
            side_effect=httpx.HTTPStatusError("Auth failed", request=None, response=mock_response)
        )
        mock_client.async_disconnect = AsyncMock()

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: "wrong_password"},
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "reauth_confirm"
    assert result2["errors"] == {"base": "invalid_auth"}

    # Verify password was NOT updated
    assert entry.data[CONF_PASSWORD] == "old_password"


async def test_reauth_flow_connection_error(hass: HomeAssistant) -> None:
    """Test reauth flow with connection error."""
    # Create existing config entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old_password",
        },
        unique_id="user@example.com",
    )
    entry.add_to_hass(hass)

    # Start reauth flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )

    # Mock connection error
    with (patch("custom_components.fansync.config_flow.FanSyncClient") as mock_client_class,):
        mock_client = mock_client_class.return_value
        mock_client.async_connect = AsyncMock(side_effect=Exception("Connection failed"))
        mock_client.async_disconnect = AsyncMock()

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: "new_password"},
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "reauth_confirm"
    assert result2["errors"] == {"base": "unknown"}
