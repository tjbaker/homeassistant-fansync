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

"""Writes confirm on the value the device settles on, not only an exact echo.

Some controllers quantize a register. A Kute60-FD6R1L5 only holds six speeds
(H02 = 20/35/50/65/80/100, observed by stepping the official app through its
named levels): it accepts any 1-100, snaps to the nearest level, and reports
that back. Before this change such a write never confirmed, burned the retry
polls, and the UI snapped back after the optimistic window. Now the entity
adopts whatever the device settled on, and diagnostics list the distinct
values each device has reported so real levels can be read off a report.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fansync.entity import FanSyncOptimisticEntity

DOMAIN = "fansync"
KUTE60_LEVELS = (20, 35, 50, 65, 80, 100)


def _snap(value: int, levels: tuple[int, ...]) -> int:
    return min(levels, key=lambda level: abs(level - value))


@pytest.fixture
def fast_confirm():
    with (
        patch("custom_components.fansync.entity.CONFIRM_INITIAL_DELAY_SEC", 0),
        patch("custom_components.fansync.entity.CONFIRM_RETRY_DELAY_SEC", 0),
    ):
        yield


def test_write_applied_predicate() -> None:
    applied = FanSyncOptimisticEntity._write_applied
    targets = {"H00": 1, "H02": 87, "H01": 0}
    prev = {"H00": 1, "H02": 20, "H01": 0}
    # exact echo of every register always confirms
    assert applied({"H00": 1, "H02": 87, "H01": 0}, targets, prev)
    # device snapped speed: a register that moved off its prior value confirms
    assert applied({"H00": 1, "H02": 80, "H01": 0}, targets, prev)
    # nothing moved and not an echo: indistinguishable from a stale read
    assert not applied({"H00": 1, "H02": 20, "H01": 0}, targets, prev)
    # a different register moving (power 0 -> 1) proves the write was processed
    assert applied({"H00": 1, "H02": 20, "H01": 0}, targets, {"H00": 0, "H02": 20, "H01": 0})
    # unknown prior values: only an exact echo is trusted
    assert not applied({"H00": 1, "H02": 80, "H01": 0}, targets, {})
    assert applied({"H00": 1, "H02": 87, "H01": 0}, targets, {})
    # missing or garbage never confirms; strings coerce like ints
    assert not applied({"H00": 1, "H01": 0}, targets, prev)
    assert not applied({"H00": 1, "H02": "n/a", "H01": 0}, targets, prev)
    assert applied({"H00": 1, "H02": "80", "H01": 0}, targets, prev)


async def _setup(hass: HomeAssistant, mock_client, unique_id: str) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id=unique_id,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _quantize_client(mock_client, key: str, levels: tuple[int, ...]) -> None:
    """Make the mock device snap writes to ``key`` like a real controller."""

    async def _set(data, *, device_id=None):
        data = dict(data)
        if key in data:
            data[key] = _snap(int(data[key]), levels)
        mock_client.status.update(data)

    mock_client.async_set = _set


async def test_fan_adopts_speed_the_device_settled_on(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    """A quantizing fan confirms on its snapped speed and HA shows that value."""
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    _quantize_client(mock_client, "H02", KUTE60_LEVELS)
    await _setup(hass, mock_client, "test-settled-speed")

    await hass.services.async_call(
        "fan",
        "set_percentage",
        {"entity_id": "fan.fansync_fan", "percentage": 87},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert mock_client.status["H02"] == 80
    state = hass.states.get("fan.fansync_fan")
    assert state is not None
    # Confirmed on the settled value: overlay cleared, no snap-back pending
    assert state.attributes["percentage"] == 80
    fan = hass.data["entity_components"]["fan"].get_entity("fan.fansync_fan")
    assert fan is not None
    assert fan._optimistic_until is None
    assert "H02" not in fan._overlay


async def test_fan_turn_on_with_percentage_adopts_settled_speed(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 0, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    _quantize_client(mock_client, "H02", KUTE60_LEVELS)
    await _setup(hass, mock_client, "test-settled-turn-on")

    await hass.services.async_call(
        "fan",
        "turn_on",
        {"entity_id": "fan.fansync_fan", "percentage": 13},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert mock_client.status == {**mock_client.status, "H00": 1, "H02": 20}
    state = hass.states.get("fan.fansync_fan")
    assert state.state == "on"
    assert state.attributes["percentage"] == 20


async def test_exact_echo_still_confirms_for_continuous_fans(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    await _setup(hass, mock_client, "test-settled-continuous")

    await hass.services.async_call(
        "fan",
        "set_percentage",
        {"entity_id": "fan.fansync_fan", "percentage": 87},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert mock_client.status["H02"] == 87
    assert hass.states.get("fan.fansync_fan").attributes["percentage"] == 87


async def test_light_adopts_color_temp_the_device_settled_on(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    """A light that snaps H04 to its own value confirms and reports that value."""
    mock_client.status = {"H00": 1, "H02": 41, "H06": 0, "H01": 0, "H0B": 1, "H0C": 50, "H04": 3000}
    _quantize_client(mock_client, "H04", (3000, 3800, 5000))
    await _setup(hass, mock_client, "test-settled-cct")

    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.fansync_light", "color_temp_kelvin": 4000},
        blocking=True,
    )
    await hass.async_block_till_done()

    # The integration snapped 4000 to the known preset 4000; the device held 3800.
    assert mock_client.status["H04"] == 3800
    assert hass.states.get("light.fansync_light").attributes["color_temp_kelvin"] == 3800


async def test_light_adopts_brightness_the_device_settled_on(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 1, "H02": 41, "H06": 0, "H01": 0, "H0B": 0, "H0C": 10}
    _quantize_client(mock_client, "H0C", (10, 25, 50, 75, 100))
    await _setup(hass, mock_client, "test-settled-brightness")

    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.fansync_light", "brightness": 150},  # 58% -> device holds 50
        blocking=True,
    )
    await hass.async_block_till_done()

    assert mock_client.status["H0C"] == 50
    assert hass.states.get("light.fansync_light").attributes["brightness"] == 127


async def test_diagnostics_observed_values_track_device_reports_only(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    """Polls and pushes are recorded per register; optimistic writes are not."""
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    _quantize_client(mock_client, "H02", KUTE60_LEVELS)
    entry = await _setup(hass, mock_client, "test-observed")
    coordinator = entry.runtime_data["coordinator"]

    # app pushes for two levels
    for level in (35, 100):
        mock_client._status_callback("test-device", {"H02": level})
    await hass.async_block_till_done()

    # HA asks for 87: optimistic 87 must not be recorded, the settled 80 is
    await hass.services.async_call(
        "fan",
        "set_percentage",
        {"entity_id": "fan.fansync_fan", "percentage": 87},
        blocking=True,
    )
    await hass.async_block_till_done()
    mock_client._status_callback("test-device", {"H02": 80})
    await hass.async_block_till_done()

    observed = coordinator._observed_values["test-device"]
    assert observed["H02"] == [20, 35, 80, 100]
    assert 87 not in observed["H02"]
    assert observed["H00"] == [1]
    assert "H06" in observed and "H0B" in observed


def test_observed_values_are_capped_and_ignore_non_protocol_keys(hass: HomeAssistant) -> None:
    from unittest.mock import MagicMock

    from custom_components.fansync.coordinator import FanSyncCoordinator
    from custom_components.fansync.const import OBSERVED_VALUES_MAX

    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="cap")
    entry.add_to_hass(hass)
    coordinator = FanSyncCoordinator(hass, MagicMock(), entry)

    for i in range(OBSERVED_VALUES_MAX + 10):
        coordinator.record_observed_status("dev", {"H0C": i, "users": ["x"], "H02": "bad"})
    coordinator.record_observed_status("", {"H02": 1})
    coordinator.record_observed_status("dev", "not a mapping")  # type: ignore[arg-type]

    observed = coordinator._observed_values
    assert list(observed) == ["dev"]
    assert len(observed["dev"]["H0C"]) == OBSERVED_VALUES_MAX
    assert "users" not in observed["dev"]
    assert "H02" not in observed["dev"]
