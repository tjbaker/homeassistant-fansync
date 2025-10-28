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
