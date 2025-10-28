# SPDX-License-Identifier: Apache-2.0
# Copyright 2025 Trevor Baker, all rights reserved.

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
