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

"""Light color temperature (H04) tests.

H04 was previously undecoded. Confirmed against a live device: switching a
light's color in the Fanimation app between its "warm"/"natural"/"cool" presets
moved H04 between exactly 3000/4000/5000 (Kelvin), with every other key
unchanged. Devices without tunable lights can report other H04 values, so the
confirmed preset values are used as the capability signal. Known Corke models
add two observed presets, 2700 and 3500 K, and use a five-step profile.
"""

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "fansync"


async def test_color_temp_supported_when_device_reports_h04(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """A device reporting H04 gets COLOR_TEMP mode with the observed preset bounds."""
    mock_client.status = {
        "H00": 1,
        "H02": 41,
        "H06": 0,
        "H01": 0,
        "H0B": 1,
        "H0C": 100,
        "H04": 4000,
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test-color-temp",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.attributes.get("supported_color_modes") == ["color_temp"]
    assert state.attributes.get("color_mode") == "color_temp"
    assert state.attributes.get("min_color_temp_kelvin") == 3000
    assert state.attributes.get("max_color_temp_kelvin") == 5000
    assert state.attributes.get("color_temp_kelvin") == 4000


async def test_color_temp_supported_when_device_reports_h04_as_string(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """A string H04 value still enables COLOR_TEMP mode."""
    mock_client.status = {
        "H00": 1,
        "H02": 41,
        "H06": 0,
        "H01": 0,
        "H0B": 1,
        "H0C": 100,
        "H04": "4000",
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test-string-color-temp",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.attributes.get("supported_color_modes") == ["color_temp"]


async def test_color_temp_display_normalizes_integral_float_h04(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """An integral float H04 value displays the device's current preset."""
    mock_client.status = {
        "H00": 1,
        "H02": 41,
        "H06": 0,
        "H01": 0,
        "H0B": 1,
        "H0C": 100,
        "H04": 4000.0,
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test-float-color-temp",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.attributes.get("supported_color_modes") == ["color_temp"]
    assert state.attributes.get("color_temp_kelvin") == 4000


async def test_corke_model_exposes_five_color_temp_presets(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """A Corke model exposes all five presets observed on the live device."""
    mock_client.profile = {"esh": {"model": "Corke36-FD6R1L5"}}
    mock_client.status = {
        "H00": 1,
        "H02": 41,
        "H06": 0,
        "H01": 0,
        "H0B": 1,
        "H0C": 100,
        "H04": 3500,
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test-corke-color-temp",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.attributes.get("min_color_temp_kelvin") == 2700
    assert state.attributes.get("max_color_temp_kelvin") == 5000
    assert state.attributes.get("color_temp_kelvin") == 3500

    assert mock_client._status_callback is not None
    mock_client._status_callback("test-device", {"H00": 1})
    await hass.async_block_till_done()
    assert hass.states.get("light.fansync_light").attributes.get("color_temp_kelvin") == 3500

    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.fansync_light", "color_temp_kelvin": 2700},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert mock_client.status["H04"] == 2700
    assert hass.states.get("light.fansync_light").attributes.get("color_temp_kelvin") == 2700


async def test_late_corke_profile_upgrades_existing_light(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """A profile learned after setup upgrades a Corke light to five presets."""
    mock_client.status = {
        "H00": 1,
        "H02": 41,
        "H06": 0,
        "H01": 0,
        "H0B": 1,
        "H0C": 100,
        "H04": 3500,
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test-late-corke-profile",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.attributes.get("supported_color_modes") == ["brightness"]

    mock_client.profile = {"esh": {"model": "Corke36-FD6R1L5"}}
    await entry.runtime_data["coordinator"].async_request_refresh()
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.attributes.get("supported_color_modes") == ["color_temp"]
    assert state.attributes.get("min_color_temp_kelvin") == 2700
    assert state.attributes.get("max_color_temp_kelvin") == 5000
    assert state.attributes.get("color_temp_kelvin") == 3500


async def test_color_temp_unsupported_when_device_omits_h04(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """A device that never reports H04 stays BRIGHTNESS-only (fixed-temperature light)."""
    # mock_client's default status has no H04.
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test-no-color-temp",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.attributes.get("supported_color_modes") == ["brightness"]
    assert "color_temp_kelvin" not in state.attributes


async def test_color_temp_unsupported_when_device_reports_off_preset_h04(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """A device reporting an off-preset H04 value stays BRIGHTNESS-only."""
    mock_client.status = {
        "H00": 1,
        "H02": 41,
        "H06": 0,
        "H01": 0,
        "H0B": 1,
        "H0C": 100,
        "H04": 3500,
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test-off-preset-color-temp",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.attributes.get("supported_color_modes") == ["brightness"]
    assert "color_temp_kelvin" not in state.attributes


async def test_turn_on_snaps_requested_kelvin_to_nearest_preset(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """A requested kelvin between two presets snaps to the nearer one and reaches the device."""
    mock_client.status = {
        "H00": 1,
        "H02": 41,
        "H06": 0,
        "H01": 0,
        "H0B": 0,
        "H0C": 0,
        "H04": 3000,
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test-snap",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # 4600 is closer to 5000 than to 4000.
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.fansync_light", "color_temp_kelvin": 4600},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state.state == "on"
    assert state.attributes.get("color_temp_kelvin") == 5000
    assert mock_client.status["H04"] == 5000


async def test_turn_on_confirms_when_device_returns_string_h04(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """A string H04 status confirms the optimistic color-temperature update."""
    mock_client.status = {
        "H00": 1,
        "H02": 41,
        "H06": 0,
        "H01": 0,
        "H0B": 1,
        "H0C": 100,
        "H04": 3000,
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id="test-string-color-temp-confirmation",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async def async_set_string_h04(data: dict[str, int], *, device_id: str | None = None) -> None:
        mock_client.status.update(data)
        mock_client.status["H04"] = str(mock_client.status["H04"])

    mock_client.async_set = async_set_string_h04
    mock_client.async_get_status = AsyncMock(return_value=mock_client.status)

    with (
        patch("custom_components.fansync.entity.CONFIRM_INITIAL_DELAY_SEC", 0),
        patch("custom_components.fansync.entity.CONFIRM_RETRY_DELAY_SEC", 0),
    ):
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": "light.fansync_light", "color_temp_kelvin": 4600},
            blocking=True,
        )

    assert mock_client.async_get_status.await_count == 1


async def _setup_light(hass: HomeAssistant, mock_client, unique_id: str) -> MockConfigEntry:
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


async def test_off_preset_push_does_not_downgrade_resolved_color_temp(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """Once CCT support is resolved, a transient off-preset H04 must not remove it.

    Downgrading on every stray reading would flap supported_color_modes and the
    entity registry capabilities.
    """
    mock_client.status = {
        "H00": 1,
        "H02": 41,
        "H06": 0,
        "H01": 0,
        "H0B": 1,
        "H0C": 100,
        "H04": 4000,
    }
    await _setup_light(hass, mock_client, "test-no-downgrade")

    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.attributes.get("supported_color_modes") == ["color_temp"]

    mock_client._status_callback("test-device", {"H04": 0})
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state.attributes.get("supported_color_modes") == ["color_temp"]
    assert state.attributes.get("min_color_temp_kelvin") == 3000
    assert state.attributes.get("max_color_temp_kelvin") == 5000
    # The off-preset reading must not surface as an out-of-range Kelvin state;
    # the last in-range value is reported instead.
    assert state.attributes.get("color_temp_kelvin") == 4000


async def test_late_h04_upgrades_light_without_device_profile(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """A light set up before H04 was reported gains CCT support when it appears.

    The refresh path must apply the same rule as setup even when the client has
    no profile (no `esh` block) for the device.
    """
    mock_client.profile = {}
    mock_client.status = {"H00": 1, "H02": 41, "H06": 0, "H01": 0, "H0B": 1, "H0C": 100}
    await _setup_light(hass, mock_client, "test-late-h04")

    state = hass.states.get("light.fansync_light")
    assert state is not None
    assert state.attributes.get("supported_color_modes") == ["brightness"]

    mock_client._status_callback("test-device", {"H04": 5000})
    await hass.async_block_till_done()

    state = hass.states.get("light.fansync_light")
    assert state.attributes.get("supported_color_modes") == ["color_temp"]
    assert state.attributes.get("color_temp_kelvin") == 5000


async def test_shared_getter_keeps_bool_status_semantics(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    """A JSON boolean register still coerces like an int for non-Kelvin keys."""
    mock_client.status = {"H00": 1, "H02": 41, "H06": 0, "H01": 0, "H0B": 0, "H0C": 100}
    await _setup_light(hass, mock_client, "test-bool-status")

    assert hass.states.get("light.fansync_light").state == "off"

    mock_client._status_callback("test-device", {"H0B": True})
    await hass.async_block_till_done()

    assert hass.states.get("light.fansync_light").state == "on"
