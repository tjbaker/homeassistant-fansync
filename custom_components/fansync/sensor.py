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

"""Read-only sensors.

``Error`` shows the fault the fan's receiver reports in register ``H0E``
(under voltage, stalled fault, over temperature and so on). It only reads the
register and writes nothing to the fan, and is only created for fans whose
status contains it.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import FanSyncClient
from .const import DOMAIN, KEY_ERROR, coerce_status_int, error_state
from .coordinator import FanSyncCoordinator
from .device_utils import create_device_info

# Coordinator-driven, read-only: nothing to serialize.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: FanSyncClient = entry.runtime_data["client"]
    coordinator: FanSyncCoordinator = entry.runtime_data["coordinator"]
    device_ids = [d for d in (getattr(client, "device_ids", []) or [client.device_id]) if d]
    data = coordinator.data or {}
    async_add_entities(
        FanSyncErrorSensor(coordinator, client, did)
        for did in device_ids
        if KEY_ERROR in (data.get(did) or {})
    )


class FanSyncErrorSensor(CoordinatorEntity[FanSyncCoordinator], SensorEntity):
    """The fault code in H0E, as text (``none`` when the fan reports no fault)."""

    _attr_has_entity_name = True
    _attr_translation_key = "error"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(
        self, coordinator: FanSyncCoordinator, client: FanSyncClient, device_id: str
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_error"

    @property
    def device_info(self) -> DeviceInfo:
        return create_device_info(self._client, self._device_id)

    @property
    def available(self) -> bool:
        return super().available and self._device_id in (self.coordinator.data or {})

    def _code(self) -> int | None:
        status = (self.coordinator.data or {}).get(self._device_id) or {}
        return coerce_status_int(status.get(KEY_ERROR))

    @property
    def native_value(self) -> str | None:
        return error_state(self._code())

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        code = self._code()
        return None if code is None else {"error_code": code}
