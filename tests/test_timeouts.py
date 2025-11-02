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

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.fansync.const import (
    CONF_HTTP_TIMEOUT,
    CONF_WS_TIMEOUT,
    OPTION_FALLBACK_POLL_SECS,
)


async def test_config_flow_passes_default_timeouts(hass, ensure_fansync_importable):
    with patch("custom_components.fansync.config_flow.FanSyncClient") as client_cls:
        instance = client_cls.return_value
        instance.async_connect = AsyncMock(return_value=None)
        instance.async_disconnect = AsyncMock(return_value=None)
        instance.device_ids = ["dev"]

        result = await hass.config_entries.flow.async_init(
            "fansync",
            context={"source": "user"},
            data={"email": "u@example.com", "password": "p", "verify_ssl": True},
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    # Ensure the constructor was given default timeout values
    _, kwargs = client_cls.call_args
    assert kwargs.get("http_timeout_s") == 20
    assert kwargs.get("ws_timeout_s") == 30


async def test_config_flow_passes_custom_timeouts(hass, ensure_fansync_importable):
    with patch("custom_components.fansync.config_flow.FanSyncClient") as client_cls:
        instance = client_cls.return_value
        instance.async_connect = AsyncMock(return_value=None)
        instance.async_disconnect = AsyncMock(return_value=None)
        instance.device_ids = ["dev"]

        result = await hass.config_entries.flow.async_init(
            "fansync",
            context={"source": "user"},
            data={
                "email": "u@example.com",
                "password": "p",
                "verify_ssl": True,
                "http_timeout_seconds": 12,
                "ws_timeout_seconds": 20,
            },
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _, kwargs = client_cls.call_args
    assert kwargs.get("http_timeout_s") == 12
    assert kwargs.get("ws_timeout_s") == 20


async def test_options_flow_sets_timeouts_and_setup_uses_them(hass):
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="timeouts-test",
    )
    entry.add_to_hass(hass)

    # Start options flow
    init = await hass.config_entries.options.async_init(entry.entry_id)
    assert init["type"] == data_entry_flow.FlowResultType.FORM

    # Submit options including timeouts
    finish = await hass.config_entries.options.async_configure(
        init["flow_id"],
        user_input={
            "fallback_poll_seconds": 60,
            "http_timeout_seconds": 14,
            "ws_timeout_seconds": 22,
        },
    )
    assert finish["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert finish["data"]["http_timeout_seconds"] == 14
    assert finish["data"]["ws_timeout_seconds"] == 22

    # Now ensure setup threads these into the client
    with patch("custom_components.fansync.FanSyncClient") as client_cls:
        client = client_cls.return_value
        client.async_connect = AsyncMock(return_value=None)
        client.set_status_callback = lambda cb: None
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    _, kwargs = client_cls.call_args
    assert kwargs.get("http_timeout_s") == 14
    assert kwargs.get("ws_timeout_s") == 22


async def test_options_update_listener_applies_timeouts_runtime(hass):
    entry = MockConfigEntry(
        domain="fansync",
        title="FanSync",
        data={"email": "u@e.com", "password": "p", "verify_ssl": True},
        unique_id="timeouts-apply",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.fansync.FanSyncClient") as client_cls:
        client = client_cls.return_value
        client.async_connect = AsyncMock(return_value=None)
        client.set_status_callback = lambda cb: None
        client.async_disconnect = AsyncMock(return_value=None)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Verify initial setup passed no explicit timeouts
        _, setup_kwargs = client_cls.call_args
        assert setup_kwargs.get("http_timeout_s") is None
        assert setup_kwargs.get("ws_timeout_s") is None

        # When options change, listener should apply timeouts at runtime
        def _apply(ht, wt):  # side effect to mutate client state
            client._http_timeout_s = ht
            client._ws_timeout_s = wt

        client.apply_timeouts = MagicMock(side_effect=_apply)  # type: ignore[attr-defined]
        hass.config_entries.async_update_entry(
            entry,
            options={
                OPTION_FALLBACK_POLL_SECS: 60,
                CONF_HTTP_TIMEOUT: 11,
                CONF_WS_TIMEOUT: 21,
            },
        )
        await hass.async_block_till_done()

    client.apply_timeouts.assert_called_with(11, 21)  # type: ignore[attr-defined]
    assert getattr(client, "_http_timeout_s", None) == 11
    assert getattr(client, "_ws_timeout_s", None) == 21
