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

"""Update coordinator error path tests.

Forces the client status call to raise and verifies setup proceeds without
crashing, exercising error handling in the coordinator update path.
"""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "fansync"


async def test_coordinator_update_failed(hass: HomeAssistant, patch_client):
    """Coordinator update raises; setup continues and does not crash."""

    # Force client to raise
    async def _raise():
        raise RuntimeError("boom")

    patch_client.async_get_status = _raise

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test8",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
