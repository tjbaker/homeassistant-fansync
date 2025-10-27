# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from unittest.mock import patch

from homeassistant import data_entry_flow


async def test_config_flow_creates_entry(hass):
    result = await hass.config_entries.flow.async_init("fansync", context={"source": "user"})
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    with patch(
        "custom_components.fansync.config_flow.FanSyncClient.async_connect", return_value=None
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"email": "ux@example.com", "password": "p", "verify_ssl": True},
        )

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == "FanSync"
    assert result2["data"]["email"] == "ux@example.com"
