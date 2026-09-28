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

"""Per-device configuration switches.

``Light installed`` lives on each fan's device page under *Configuration*.
Turning it off records the device in the ``lightless_devices`` option, which
reloads the integration and removes that fan's phantom Light entity (issue
#199). It is the same option as the integration's Configure form, surfaced
where people actually look for it.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import FanSyncClient
from .const import DOMAIN, OPTION_LIGHTLESS_DEVICES, resolve_lightless_devices
from .device_utils import cloud_lightless_devices, create_device_info

# Config writes only; nothing here talks to the cloud
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client: FanSyncClient = entry.runtime_data["client"]
    device_ids = [d for d in (getattr(client, "device_ids", []) or [client.device_id]) if d]
    cloud_lightless = cloud_lightless_devices(client, device_ids)
    async_add_entities(
        FanSyncLightInstalledSwitch(entry, client, did, cloud_lightless=did in cloud_lightless)
        for did in device_ids
    )


class FanSyncLightInstalledSwitch(SwitchEntity):
    """On when the fan is treated as having a light kit."""

    _attr_has_entity_name = True
    _attr_translation_key = "light_installed"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        client: FanSyncClient,
        device_id: str,
        *,
        cloud_lightless: bool,
    ) -> None:
        self._entry = entry
        self._client = client
        self._device_id = device_id
        self._cloud_lightless = cloud_lightless
        self._attr_unique_id = f"{DOMAIN}_{device_id}_light_installed"

    @property
    def device_info(self) -> DeviceInfo:
        return create_device_info(self._client, self._device_id)

    @property
    def icon(self) -> str:
        return "mdi:lightbulb" if self.is_on else "mdi:lightbulb-off"

    def _manual_lightless(self) -> set[str]:
        return resolve_lightless_devices(self._entry.options, [self._device_id])

    @property
    def is_on(self) -> bool:
        if self._cloud_lightless:
            return False
        return self._device_id not in self._manual_lightless()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Mark this fan as having no light; the reload removes its Light entity."""
        if self._cloud_lightless:
            return  # already hidden by the cloud flag; nothing to record
        self._write_lightless(add=True)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Treat this fan as having a light again; the reload restores its Light entity."""
        if self._cloud_lightless:
            raise HomeAssistantError(
                "The Fanimation app marked this fan as having no light kit "
                "(hideLightDimmer); change it there to restore the light."
            )
        self._write_lightless(add=False)

    def _write_lightless(self, *, add: bool) -> None:
        current = [d for d in self._entry.options.get(OPTION_LIGHTLESS_DEVICES, []) or [] if d]
        updated = [d for d in current if d != self._device_id]
        if add:
            updated.append(self._device_id)
        if updated == current:
            return
        _LOGGER.debug("light installed switch d=%s lightless=%s", self._device_id, add)
        # The options listener in __init__ reloads the entry, which adds or
        # removes the Light entity and recreates this switch with the new state.
        self.hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, OPTION_LIGHTLESS_DEVICES: updated}
        )
