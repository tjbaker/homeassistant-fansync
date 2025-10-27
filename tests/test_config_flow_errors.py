# SPDX-License-Identifier: GPL-2.0-only

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
