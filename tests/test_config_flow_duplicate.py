# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from homeassistant import data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_config_flow_duplicate_unique_id(hass):
    # Existing entry with same email unique_id
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "dup@example.com", "password": "p", "verify_ssl": True},
        unique_id="dup@example.com",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init("fansync", context={"source": "user"})
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    # Submitting same email should abort as already_configured
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"email": "dup@example.com", "password": "p", "verify_ssl": True},
    )

    assert result2["type"] == data_entry_flow.FlowResultType.ABORT
    assert result2["reason"] == "already_configured"
