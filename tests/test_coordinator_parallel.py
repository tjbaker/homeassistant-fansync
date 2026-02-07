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

from homeassistant.core import HomeAssistant

from custom_components.fansync.coordinator import FanSyncCoordinator


class _ClientStub:
    def __init__(self, device_ids: list[str]):
        self.device_ids = device_ids
        self.device_id = device_ids[0] if device_ids else None

    async def async_get_status(
        self, device_id: str | None = None
    ):  # pragma: no cover - stub replaced in each test
        return {"H00": 1}


async def test_parallel_status_keeps_last_known_for_timeouts(
    hass: HomeAssistant, mock_config_entry
) -> None:
    client = _ClientStub(["d1", "d2"])  # two devices

    async def _get_status(did: str | None = None):
        if did == "d1":
            return {"H00": 1, "H02": 22}
        # Simulate timeout-like failure for d2 by raising directly
        raise TimeoutError()

    client.async_get_status = _get_status  # type: ignore[assignment]
    coord = FanSyncCoordinator(hass, client, mock_config_entry)
    coord.data = {"d1": {"H00": 0}, "d2": {"H00": 1, "H02": 10}}

    data = await coord._async_update_data()
    assert isinstance(data, dict)
    assert "d1" in data and isinstance(data["d1"], dict)
    # d2 timed out; ensure we keep last known data
    assert data["d2"] == {"H00": 1, "H02": 10}


async def test_single_device_timeout_keeps_last_known_state(
    hass: HomeAssistant, mock_config_entry
) -> None:
    client = _ClientStub([])  # single-device path (device_ids empty)

    async def _get_status(_did: str | None = None):
        raise TimeoutError()

    client.async_get_status = _get_status  # type: ignore[assignment]
    coord = FanSyncCoordinator(hass, client, mock_config_entry)

    # Set some initial data
    coord.data = {"dev": {"H00": 1, "H02": 50}}

    # Timeout should return last known data, not raise UpdateFailed
    data = await coord._async_update_data()
    assert data == {"dev": {"H00": 1, "H02": 50}}
