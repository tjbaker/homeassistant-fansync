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

"""A power write the device acknowledged but never reported is kept.

Measured on a Kute60-FD6R1L5 (firmware 3.2.9): `{"H00": 0}` stops the fan, the
fan acknowledges it, and no report follows, so the cloud returns "on" forever.
0.10.0 sent exactly that write (the Spitfire needs it, issue #249) and then
restored the cloud's value when the guard lapsed: the fan was off and Home
Assistant showed it on, with no way to make it show off.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, flush_store

from custom_components.fansync.client import FanSyncClient
from custom_components.fansync.const import DEVICE_ACK_HISTORY_MAX

DOMAIN = "fansync"
FAN = "fan.fansync_fan"
DEVICE = "test-device"


@pytest.fixture
def fast_confirm():
    with (
        patch("custom_components.fansync.entity.CONFIRM_INITIAL_DELAY_SEC", 0),
        patch("custom_components.fansync.entity.CONFIRM_RETRY_DELAY_SEC", 0),
        patch("custom_components.fansync.entity.OPTIMISTIC_GUARD_SEC", 0.2),
        patch("custom_components.fansync.entity.DEVICE_ACK_GRACE_SEC", 0.2),
    ):
        yield


async def _setup(
    hass: HomeAssistant, unique_id: str, *, entry_id: str | None = None
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": False},
        unique_id=unique_id,
        **({"entry_id": entry_id} if entry_id else {}),
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _kute60(mock_client, *, ack: str | None = "ok") -> list[dict[str, int]]:
    """Make the mock behave like the measured Kute60 and return the writes it receives.

    ``mock_client.status`` is what the cloud returns. A power-only write is applied
    and acknowledged but never reported, so the cloud's copy does not change. A
    write that carries a speed is reported.
    """
    writes: list[dict[str, int]] = []
    mock_client.fan_is_on = mock_client.status["H00"] == 1

    async def _set(data: dict[str, int], *, device_id: str | None = None) -> None:
        writes.append(dict(data))
        if "H00" in data:
            mock_client.fan_is_on = data["H00"] == 1
        if "H02" in data:
            mock_client.status.update(data)

    mock_client.async_set = _set
    mock_client.last_device_ack = lambda device_id: ack
    return writes


async def _turn_off_and_wait(hass: HomeAssistant) -> None:
    await hass.services.async_call("fan", "turn_off", {"entity_id": FAN}, blocking=True)
    await asyncio.sleep(0.35)  # past the guard
    await hass.async_block_till_done()


async def test_acknowledged_unreported_off_stays_off(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    writes = _kute60(mock_client)
    entry = await _setup(hass, "assumed-off")
    coordinator = entry.runtime_data["coordinator"]
    assert hass.states.get(FAN).state == "on"

    await _turn_off_and_wait(hass)

    assert writes == [{"H00": 0}]  # nothing extra is sent to make the fan report
    assert mock_client.fan_is_on is False
    assert mock_client.status["H00"] == 1  # the cloud is stale
    assert hass.states.get(FAN).state == "off"
    assert coordinator.assumed_values() == {DEVICE: {"H00": 0}}

    # A poll returns the cloud's stale value; it must not put the fan back on,
    # and it is not a mismatch worth recording every minute.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "off"
    assert coordinator._last_poll_mismatch_keys == {}


async def test_turn_on_after_assumed_off_writes_power_and_ends_the_assumption(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    writes = _kute60(mock_client)
    entry = await _setup(hass, "assumed-then-on")
    coordinator = entry.runtime_data["coordinator"]
    await _turn_off_and_wait(hass)
    writes.clear()

    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": FAN, "percentage": 35}, blocking=True
    )
    await hass.async_block_till_done()

    # The cloud said "on" all along; the write must still carry power, or a
    # Kute60 refuses the speed and stays off.
    assert writes == [{"H00": 1, "H02": 35}]
    assert mock_client.fan_is_on is True
    assert hass.states.get(FAN).state == "on"
    assert coordinator.assumed_values() == {}
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "on"


@pytest.mark.parametrize("ack", ["error", None])
async def test_off_without_an_ok_from_the_device_is_not_assumed(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm, ack: str | None
) -> None:
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    _kute60(mock_client, ack=ack)
    entry = await _setup(hass, f"not-assumed-{ack}")

    await _turn_off_and_wait(hass)
    await asyncio.sleep(0.25)  # a missing answer is waited for once more
    await hass.async_block_till_done()

    assert hass.states.get(FAN).state == "on"
    assert entry.runtime_data["coordinator"].assumed_values() == {}


async def test_acknowledgement_arriving_after_the_guard_still_counts(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    """Measured on the Kute60: the answer came 1.9 to 2.5 s into a 3 s guard."""
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    _kute60(mock_client, ack=None)
    entry = await _setup(hass, "late-ack")

    await _turn_off_and_wait(hass)  # guard lapsed, no answer yet
    assert hass.states.get(FAN).state == "off"
    mock_client.last_device_ack = lambda device_id: "ok"
    await asyncio.sleep(0.25)
    await hass.async_block_till_done()

    assert hass.states.get(FAN).state == "off"
    assert entry.runtime_data["coordinator"].assumed_values() == {DEVICE: {"H00": 0}}


async def test_a_report_from_the_device_ends_the_assumption(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    """The fan is started from the remote and reports it: the report wins."""
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    _kute60(mock_client)
    entry = await _setup(hass, "assumed-then-push")
    coordinator = entry.runtime_data["coordinator"]
    await _turn_off_and_wait(hass)
    assert hass.states.get(FAN).state == "off"

    mock_client._status_callback(DEVICE, {"H00": 1, "H02": 35})
    await hass.async_block_till_done()

    assert hass.states.get(FAN).state == "on"
    assert coordinator.assumed_values() == {}
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "on"


async def test_reported_off_is_confirmed_not_assumed(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    """A fan that reports a bare power-off (SpitfireV2) never needs the assumption."""
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    mock_client.last_device_ack = lambda device_id: "ok"
    entry = await _setup(hass, "reported-off")

    await _turn_off_and_wait(hass)

    assert hass.states.get(FAN).state == "off"
    assert entry.runtime_data["coordinator"].assumed_values() == {}


async def test_acknowledged_unreported_speed_is_not_assumed(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    """An unreported speed write usually means the fan kept its value; it reverts."""
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}

    async def _ignored(data: dict[str, int], *, device_id: str | None = None) -> None: ...

    mock_client.async_set = _ignored
    mock_client.last_device_ack = lambda device_id: "ok"
    entry = await _setup(hass, "speed-not-assumed")

    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": FAN, "percentage": 27}, blocking=True
    )
    await asyncio.sleep(0.35)
    await hass.async_block_till_done()

    assert hass.states.get(FAN).attributes["percentage"] == 20
    assert entry.runtime_data["coordinator"].assumed_values() == {}


async def test_cloud_read_that_moved_ends_the_assumption(
    hass: HomeAssistant, mock_client, patch_client
) -> None:
    entry = await _setup(hass, "assumed-unit")
    coordinator = entry.runtime_data["coordinator"]
    coordinator.record_observed_status(DEVICE, {"H0B": 1, "H0C": 40})
    coordinator.assume_applied(DEVICE, {"H0B": 0})

    # still the stale value: corrected, and other registers pass through
    assert coordinator.record_observed_status(DEVICE, {"H0B": 1, "H0C": 55}) == {
        "H0B": 0,
        "H0C": 55,
    }
    assert coordinator.last_reported_status(DEVICE)["H0B"] == 0
    # assuming again keeps the original stale value rather than the assumed one
    coordinator.assume_applied(DEVICE, {"H0B": 0})
    assert coordinator.record_observed_status(DEVICE, {"H0B": 1}) == {"H0B": 0}
    # a read without the register leaves the assumption alone
    assert coordinator.record_observed_status(DEVICE, {"H0C": 60}) == {"H0C": 60}
    assert coordinator.assumed_values() == {DEVICE: {"H0B": 0}}
    # the cloud's value moved, so the device has reported since
    assert coordinator.record_observed_status(DEVICE, {"H0B": 0}) == {"H0B": 0}
    assert coordinator.assumed_values() == {}
    assert coordinator.record_observed_status(DEVICE, {"H0B": 1}) == {"H0B": 1}


async def test_client_keeps_the_devices_own_acknowledgement(
    hass: HomeAssistant, mock_websocket
) -> None:
    """A `set` is acknowledged twice with one id; the second answer is the device's."""
    client = FanSyncClient(hass, "e", "p", enable_push=True)
    release_device_ack = asyncio.Event()

    bootstrap = [
        json.dumps({"response": "login", "status": "ok", "id": 1}),
        json.dumps({"response": "lst_device", "data": [{"device": "dev"}], "id": 2}),
        json.dumps({"status": "ok", "response": "set", "id": 3}),  # the cloud
    ]
    calls = 0

    async def _recv() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError  # no server greeting
        if calls - 2 < len(bootstrap):
            return bootstrap[calls - 2]
        if calls - 2 == len(bootstrap):
            await release_device_ack.wait()
            return json.dumps({"status": "error", "response": "set", "id": 3, "code": 200})
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http_cls.return_value.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()
        mock_websocket.recv.side_effect = _recv
        ws_connect.return_value = mock_websocket
        try:
            await client.async_connect()
            assert client.last_device_ack("dev") is None  # nothing written yet
            await client.async_set({"H00": 0})
            assert client.last_device_ack("dev") is None  # only the cloud has answered
            release_device_ack.set()
            for _ in range(20):
                await asyncio.sleep(0.01)
                if client.last_device_ack("dev") is not None:
                    break
            assert client.last_device_ack("dev") == "error"
        finally:
            await client.async_disconnect()


def test_device_ack_history_is_bounded(hass: HomeAssistant) -> None:
    client = FanSyncClient(hass, "e", "p")
    for request_id in range(DEVICE_ACK_HISTORY_MAX + 5):
        client._record_device_ack(request_id, "ok")
    client._record_device_ack("not-an-id", "ok")
    client._record_device_ack(True, "ok")
    assert len(client._device_acks) == DEVICE_ACK_HISTORY_MAX
    assert 0 not in client._device_acks
    assert DEVICE_ACK_HISTORY_MAX + 4 in client._device_acks


async def test_turning_off_again_while_assumed_off_stays_off(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    """A second off (a nightly "all fans off" automation) must not undo the first.

    0.11.0 forgot the assumption when the register was written again, then
    read the cloud's stale "on", saw it differ from the assumed "off", and
    took that as the device having changed.
    """
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    writes = _kute60(mock_client)
    entry = await _setup(hass, "assumed-off-twice")
    coordinator = entry.runtime_data["coordinator"]
    await _turn_off_and_wait(hass)
    assert hass.states.get(FAN).state == "off"

    await _turn_off_and_wait(hass)

    assert writes == [{"H00": 0}, {"H00": 0}]
    assert hass.states.get(FAN).state == "off"
    assert coordinator.assumed_values() == {DEVICE: {"H00": 0}}
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "off"


async def test_assumed_off_survives_a_restart(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm, hass_storage
) -> None:
    """Seen on 0.11.0: every restart re-read the cloud and showed a stopped fan as on."""
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    _kute60(mock_client)
    entry = await _setup(hass, "assumed-restart", entry_id="restart-entry")
    await _turn_off_and_wait(hass)
    await flush_store(entry.runtime_data["coordinator"]._assumed_store)
    assert hass_storage[f"{DOMAIN}.assumed.restart-entry"]["data"] == {DEVICE: {"H00": [0, 1]}}

    # A reload is a restart as far as the integration is concerned: new client
    # session, new coordinator, and a first poll that returns the stale "on".
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert mock_client.status["H00"] == 1
    assert hass.states.get(FAN).state == "off"
    assert entry.runtime_data["coordinator"].assumed_values() == {DEVICE: {"H00": 0}}


async def test_restored_assumption_is_dropped_when_the_cloud_moved(
    hass: HomeAssistant, mock_client, patch_client, hass_storage
) -> None:
    """The fan reported while Home Assistant was down: the cloud's value wins."""
    hass_storage[f"{DOMAIN}.assumed.moved-entry"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.assumed.moved-entry",
        "data": {
            DEVICE: {"H0B": [0, 1], "H00": "garbage", "H0D": [True, 1], "H0C": [7, 1]},
            "gone": "garbage",
            "a-fan-no-longer-in-the-account": {"H00": [0, 1]},
        },
    }
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    entry = await _setup(hass, "assumed-moved", entry_id="moved-entry")
    coordinator = entry.runtime_data["coordinator"]

    assert hass.states.get(FAN).state == "on"
    assert coordinator.assumed_values() == {}
    await coordinator.async_flush_assumed()
    assert hass_storage[f"{DOMAIN}.assumed.moved-entry"]["data"] == {}


async def test_unreadable_store_does_not_block_setup(
    hass: HomeAssistant, mock_client, patch_client, hass_storage
) -> None:
    """A file from a newer version makes the store raise; setup carries on without it."""
    hass_storage[f"{DOMAIN}.assumed.newer-entry"] = {
        "version": 99,
        "minor_version": 1,
        "key": f"{DOMAIN}.assumed.newer-entry",
        "data": {DEVICE: {"H00": [0, 1]}},
    }
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    entry = await _setup(hass, "assumed-newer", entry_id="newer-entry")

    assert hass.states.get(FAN).state == "on"
    assert entry.runtime_data["coordinator"].assumed_values() == {}


async def test_a_poll_timeout_keeps_the_assumption(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    """A timed-out device keeps its cached state, which already holds the assumed
    value. Treating that as a read looked like the device had moved."""
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    _kute60(mock_client)
    entry = await _setup(hass, "assumed-timeout")
    coordinator = entry.runtime_data["coordinator"]
    await _turn_off_and_wait(hass)
    working = mock_client.async_get_status

    async def _timeout(device_id: str | None = None) -> dict[str, int]:
        raise TimeoutError

    mock_client.async_get_status = _timeout
    await coordinator.async_refresh()
    mock_client.async_get_status = working
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(FAN).state == "off"
    assert coordinator.assumed_values() == {DEVICE: {"H00": 0}}


async def test_a_failed_write_keeps_the_assumption(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    _kute60(mock_client)
    entry = await _setup(hass, "assumed-failed-write")
    coordinator = entry.runtime_data["coordinator"]
    await _turn_off_and_wait(hass)

    async def _down(data: dict[str, int], *, device_id: str | None = None) -> None:
        raise RuntimeError("socket down")

    mock_client.async_set = _down
    with pytest.raises(RuntimeError):
        await hass.services.async_call("fan", "turn_on", {"entity_id": FAN}, blocking=True)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(FAN).state == "off"
    assert coordinator.assumed_values() == {DEVICE: {"H00": 0}}


async def test_reload_right_after_an_off_keeps_it(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm
) -> None:
    """The save is delayed; unloading must not leave it behind."""
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    _kute60(mock_client)
    entry = await _setup(hass, "assumed-quick-reload", entry_id="quick-reload-entry")
    with patch("custom_components.fansync.coordinator.ASSUMED_STORE_SAVE_DELAY_SEC", 3600):
        await _turn_off_and_wait(hass)
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get(FAN).state == "off"


async def test_removing_the_entry_deletes_the_stored_assumptions(
    hass: HomeAssistant, mock_client, patch_client, fast_confirm, hass_storage
) -> None:
    mock_client.status = {"H00": 1, "H02": 20, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
    _kute60(mock_client)
    entry = await _setup(hass, "assumed-remove", entry_id="remove-entry")
    await _turn_off_and_wait(hass)
    await flush_store(entry.runtime_data["coordinator"]._assumed_store)
    assert f"{DOMAIN}.assumed.remove-entry" in hass_storage

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert f"{DOMAIN}.assumed.remove-entry" not in hass_storage
