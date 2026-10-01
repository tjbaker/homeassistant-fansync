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

"""Per-device switches.

``Light installed`` lives on each fan's device page under *Configuration*.
Turning it off records the device in the ``lightless_devices`` option, which
reloads the integration and removes that fan's phantom Light entity (issue
#199). It is the same option as the integration's Configure form, surfaced
where people actually look for it.

``Home Away`` mirrors the Fanimation app's mode of the same name (register
``H0D``) and is only created for fans that report that register.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import FanSyncClient
from .const import (
    DOMAIN,
    KEY_HOME_AWAY,
    OPTION_LIGHTLESS_DEVICES,
    lightless_signal,
    resolve_lightless_devices,
)
from .coordinator import FanSyncCoordinator
from .device_utils import cloud_lightless_devices, create_device_info
from .entity import FanSyncOptimisticEntity

# Light installed only writes config; Home Away writes go through the client,
# which serializes its own requests.
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
    entities: list[SwitchEntity] = [
        FanSyncLightInstalledSwitch(entry, client, did, cloud_lightless=did in cloud_lightless)
        for did in device_ids
    ]
    coordinator: FanSyncCoordinator = entry.runtime_data["coordinator"]
    data = coordinator.data or {}
    entities.extend(
        FanSyncHomeAwaySwitch(coordinator, client, did)
        for did in device_ids
        if KEY_HOME_AWAY in (data.get(did) or {})
    )
    async_add_entities(entities)


class FanSyncHomeAwaySwitch(FanSyncOptimisticEntity, SwitchEntity):
    """The Fanimation app's Home Away mode.

    Measured on a Kute60-FD6R1L5 (firmware 3.2.9): turning the mode on stops
    the fan, turning it off leaves the fan stopped, and powering the fan on
    clears the mode. The fan reports each of those itself, so the fan entity
    follows without any help from here. Only the mode's own register is
    written.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "home_away"

    OVERLAY_KEYS = {KEY_HOME_AWAY}

    def __init__(
        self, coordinator: FanSyncCoordinator, client: FanSyncClient, device_id: str
    ) -> None:
        super().__init__(coordinator, client, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_home_away"

    @property
    def is_on(self) -> bool:
        return self._get_with_overlay(KEY_HOME_AWAY, 0) == 1

    @property
    def icon(self) -> str:
        return "mdi:home-export-outline" if self.is_on else "mdi:home-outline"

    @property
    def extra_state_attributes(self) -> None:
        return None  # the module details belong on the fan, not on a mode switch

    async def _write(self, value: int) -> None:
        payload = {KEY_HOME_AWAY: value}
        previous = self._previous_values(payload)
        await self._apply_with_optimism(
            dict(payload), payload, lambda s: self._write_applied(s, payload, previous)
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._write(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._write(0)


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

    async def async_added_to_hass(self) -> None:
        # The option change is applied in place (no reload), so refresh on the
        # same signal the light platform uses to add/remove Light entities.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, lightless_signal(self._entry.entry_id), self._on_lightless_changed
            )
        )

    @callback
    def _on_lightless_changed(self, _lightless: set[str]) -> None:
        self.async_write_ha_state()

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
        # The options listener in __init__ broadcasts the new lightless set; the
        # light platform adds/removes the Light entity in place and this switch
        # refreshes. The fan never goes unavailable.
        self.hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, OPTION_LIGHTLESS_DEVICES: updated}
        )
