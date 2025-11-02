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

from _pytest.logging import LogCaptureFixture
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_proceeds_when_first_refresh_times_out(
    hass: HomeAssistant, caplog: LogCaptureFixture
) -> None:
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="bound-first-refresh",
    )
    entry.add_to_hass(hass)

    # Minimal client stub
    class _Client:
        def __init__(self):
            self.device_id = "dev"
            self.device_ids = ["dev"]

        async def async_connect(self):
            return None

    with (
        patch("custom_components.fansync.FanSyncClient", return_value=_Client()),
        patch(
            "custom_components.fansync.FanSyncCoordinator.async_config_entry_first_refresh",
            new=AsyncMock(side_effect=TimeoutError()),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Setup should complete even if first refresh times out
    assert hass.states is not None
    # Info log emitted
    assert any("Initial refresh deferred" in rec.message for rec in caplog.records)
