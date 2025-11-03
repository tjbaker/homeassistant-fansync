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

"""Test device profile caching edge cases during async_get_status."""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


@pytest.mark.asyncio
async def test_profile_caching_success(
    hass: HomeAssistant, mock_websocket, caplog: pytest.LogCaptureFixture
) -> None:
    """Test successful profile caching during get_status."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    def recv_generator():
        """Generator that provides responses in order."""
        # Initial connection: login (id=1), lst_device (id=2)
        yield json.dumps({"response": "login", "status": "ok", "id": 1})
        yield json.dumps(
            {"response": "lst_device", "data": [{"device": "test_device_123"}], "id": 2}
        )
        # Wait for get request to be sent (login=1, lst=2, get=3)
        while len(mock_websocket.sent_requests) < 3:
            yield TimeoutError("waiting for get request")
        get_request_id = mock_websocket.sent_requests[2]["id"]
        # Return get response with profile
        yield json.dumps(
            {
                "response": "get",
                "id": get_request_id,
                "data": {
                    "status": {"H00": 1, "H02": 50},
                    "profile": {
                        "module": {
                            "mac_address": "AA:BB:CC:DD:EE:FF",
                            "firmware_version": "1.2.3",
                        },
                        "esh": {"model": "TestFan", "brand": "TestBrand"},
                    },
                },
            }
        )
        # Keep recv loop alive
        while True:
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            yield json.dumps({"status": "ok", "response": "evt", "data": {}})

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
        caplog.at_level(logging.DEBUG, logger="custom_components.fansync.client"),
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "test_token"}
        http.post.return_value.raise_for_status = lambda: None
        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await client.async_connect()

        status = await client.async_get_status()

        # Verify status was returned
        assert status["H00"] == 1
        assert status["H02"] == 50

        # Verify profile was cached
        profile = client.device_profile("test_device_123")
        assert profile["module"]["mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert profile["module"]["firmware_version"] == "1.2.3"
        assert profile["esh"]["model"] == "TestFan"
        assert profile["esh"]["brand"] == "TestBrand"

        # Verify logging
        assert any(
            "profile cached for test_device_123" in record.message and "keys=" in record.message
            for record in caplog.records
        )

        # Clean up
        await client.async_disconnect()


@pytest.mark.asyncio
async def test_profile_caching_no_profile_in_response(
    hass: HomeAssistant, mock_websocket, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that missing profile in response doesn't cause errors."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    def recv_generator():
        """Generator that provides responses in order."""
        yield json.dumps({"response": "login", "status": "ok", "id": 1})
        yield json.dumps(
            {"response": "lst_device", "data": [{"device": "test_device_456"}], "id": 2}
        )
        while len(mock_websocket.sent_requests) < 3:
            yield TimeoutError("waiting for get request")
        get_request_id = mock_websocket.sent_requests[2]["id"]
        yield json.dumps(
            {
                "response": "get",
                "id": get_request_id,
                "data": {"status": {"H00": 1, "H02": 50}},
                # No "profile" key
            }
        )
        while True:
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            yield json.dumps({"status": "ok", "response": "evt", "data": {}})

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
        caplog.at_level(logging.DEBUG, logger="custom_components.fansync.client"),
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "test_token"}
        http.post.return_value.raise_for_status = lambda: None
        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await client.async_connect()
        status = await client.async_get_status()

        # Verify status was still returned
        assert status["H00"] == 1
        assert status["H02"] == 50

        # Verify no profile was cached
        profile = client.device_profile("test_device_456")
        assert profile == {}

        # Verify no "profile cached" message was logged
        assert not any(
            "profile cached for test_device_456" in record.message for record in caplog.records
        )

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_profile_caching_empty_profile(
    hass: HomeAssistant, mock_websocket, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that empty profile dict is handled correctly."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    def recv_generator():
        """Generator that provides responses in order."""
        yield json.dumps({"response": "login", "status": "ok", "id": 1})
        yield json.dumps(
            {"response": "lst_device", "data": [{"device": "test_device_789"}], "id": 2}
        )
        while len(mock_websocket.sent_requests) < 3:
            yield TimeoutError("waiting for get request")
        get_request_id = mock_websocket.sent_requests[2]["id"]
        yield json.dumps(
            {
                "response": "get",
                "id": get_request_id,
                "data": {
                    "status": {"H00": 0, "H02": 0},
                    "profile": {},  # Empty profile
                },
            }
        )
        while True:
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            yield json.dumps({"status": "ok", "response": "evt", "data": {}})

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
        caplog.at_level(logging.DEBUG, logger="custom_components.fansync.client"),
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "test_token"}
        http.post.return_value.raise_for_status = lambda: None
        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await client.async_connect()
        status = await client.async_get_status()

        # Verify status was returned
        assert status["H00"] == 0

        # Verify empty profile was cached
        profile = client.device_profile("test_device_789")
        assert profile == {}

        # Empty profile should still be logged
        assert any(
            "profile cached for test_device_789" in record.message for record in caplog.records
        )

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_profile_caching_with_keyerror(
    hass: HomeAssistant, mock_websocket, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that KeyError during profile caching is handled gracefully."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    def recv_generator():
        yield json.dumps({"response": "login", "status": "ok", "id": 1})
        yield json.dumps(
            {"response": "lst_device", "data": [{"device": "test_device_error"}], "id": 2}
        )
        while len(mock_websocket.sent_requests) < 3:
            yield TimeoutError("waiting for get request")
        get_request_id = mock_websocket.sent_requests[2]["id"]
        yield json.dumps(
            {
                "response": "get",
                "id": get_request_id,
                "data": {"status": {"H00": 1}},
                # "data" key exists but no profile
            }
        )
        while True:
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            yield json.dumps({"status": "ok", "response": "evt", "data": {}})

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
        caplog.at_level(logging.DEBUG, logger="custom_components.fansync.client"),
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "test_token"}
        http.post.return_value.raise_for_status = lambda: None
        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await client.async_connect()
        # Should not raise exception
        status = await client.async_get_status()

        # Status should still be returned
        assert status["H00"] == 1

        # No profile should be cached
        profile = client.device_profile("test_device_error")
        assert profile == {}

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_profile_caching_with_wrong_type(
    hass: HomeAssistant, mock_websocket, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that non-dict profile is ignored (not cached)."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    def recv_generator():
        yield json.dumps({"response": "login", "status": "ok", "id": 1})
        yield json.dumps(
            {"response": "lst_device", "data": [{"device": "test_device_type_error"}], "id": 2}
        )
        while len(mock_websocket.sent_requests) < 3:
            yield TimeoutError("waiting for get request")
        get_request_id = mock_websocket.sent_requests[2]["id"]
        yield json.dumps(
            {
                "response": "get",
                "id": get_request_id,
                "data": {
                    "status": {"H00": 1, "H02": 25},
                    "profile": "not_a_dict",  # Wrong type - will be ignored
                },
            }
        )
        while True:
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            yield json.dumps({"status": "ok", "response": "evt", "data": {}})

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
        caplog.at_level(logging.DEBUG, logger="custom_components.fansync.client"),
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "test_token"}
        http.post.return_value.raise_for_status = lambda: None
        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await client.async_connect()
        # Should not raise exception
        status = await client.async_get_status()

        # Status should still be returned
        assert status["H00"] == 1

        # Profile should not be cached (wrong type is silently ignored)
        profile = client.device_profile("test_device_type_error")
        assert profile == {}

        # No "profile cached" message since it wasn't a dict
        assert not any(
            "profile cached for test_device_type_error" in record.message
            for record in caplog.records
        )

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_profile_caching_multiple_devices(hass: HomeAssistant, mock_websocket) -> None:
    """Test that profiles are cached separately for different devices."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    def recv_generator():
        yield json.dumps({"response": "login", "status": "ok", "id": 1})
        yield json.dumps({"response": "lst_device", "data": [{"device": "device_1"}], "id": 2})
        # First get request for device_1
        while len(mock_websocket.sent_requests) < 3:
            yield TimeoutError("waiting for first get request")
        yield json.dumps(
            {
                "response": "get",
                "id": mock_websocket.sent_requests[2]["id"],
                "data": {
                    "status": {"H00": 1},
                    "profile": {"module": {"mac_address": "AA:BB:CC:DD:EE:FF"}},
                },
            }
        )
        # Second get request for device_2
        while len(mock_websocket.sent_requests) < 4:
            yield TimeoutError("waiting for second get request")
        yield json.dumps(
            {
                "response": "get",
                "id": mock_websocket.sent_requests[3]["id"],
                "data": {
                    "status": {"H00": 1},
                    "profile": {"module": {"mac_address": "11:22:33:44:55:66"}},
                },
            }
        )
        while True:
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            yield json.dumps({"status": "ok", "response": "evt", "data": {}})

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "test_token"}
        http.post.return_value.raise_for_status = lambda: None
        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await client.async_connect()

        # First device
        client._device_id = "device_1"
        await client.async_get_status()

        # Second device with different profile
        client._device_id = "device_2"
        await client.async_get_status()

        # Verify both profiles are cached separately
        profile_1 = client.device_profile("device_1")
        profile_2 = client.device_profile("device_2")

        assert profile_1["module"]["mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert profile_2["module"]["mac_address"] == "11:22:33:44:55:66"

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_profile_caching_updates_existing(hass: HomeAssistant, mock_websocket) -> None:
    """Test that profile cache is updated if device profile changes."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    def recv_generator():
        yield json.dumps({"response": "login", "status": "ok", "id": 1})
        yield json.dumps({"response": "lst_device", "data": [{"device": "test_device"}], "id": 2})
        # First get request
        while len(mock_websocket.sent_requests) < 3:
            yield TimeoutError("waiting for first get request")
        yield json.dumps(
            {
                "response": "get",
                "id": mock_websocket.sent_requests[2]["id"],
                "data": {
                    "status": {"H00": 1},
                    "profile": {"module": {"firmware_version": "1.0.0"}},
                },
            }
        )
        # Second get request
        while len(mock_websocket.sent_requests) < 4:
            yield TimeoutError("waiting for second get request")
        yield json.dumps(
            {
                "response": "get",
                "id": mock_websocket.sent_requests[3]["id"],
                "data": {
                    "status": {"H00": 1},
                    "profile": {"module": {"firmware_version": "2.0.0"}},
                },
            }
        )
        while True:
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            yield json.dumps({"status": "ok", "response": "evt", "data": {}})

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "test_token"}
        http.post.return_value.raise_for_status = lambda: None
        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await client.async_connect()
        client._device_id = "test_device"

        # First call - initial profile
        await client.async_get_status()

        profile = client.device_profile("test_device")
        assert profile["module"]["firmware_version"] == "1.0.0"

        # Second call - updated profile
        await client.async_get_status()

        # Verify profile was updated
        profile = client.device_profile("test_device")
        assert profile["module"]["firmware_version"] == "2.0.0"

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_profile_retrieval_returns_shallow_copy(hass: HomeAssistant, mock_websocket) -> None:
    """Test that device_profile() returns a shallow copy (top-level keys safe)."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    def recv_generator():
        yield json.dumps({"response": "login", "status": "ok", "id": 1})
        yield json.dumps({"response": "lst_device", "data": [{"device": "test_device"}], "id": 2})
        while len(mock_websocket.sent_requests) < 3:
            yield TimeoutError("waiting for get request")
        yield json.dumps(
            {
                "response": "get",
                "id": mock_websocket.sent_requests[2]["id"],
                "data": {
                    "status": {"H00": 1},
                    "profile": {"module": {"firmware_version": "1.0.0"}, "esh": {"model": "Fan"}},
                },
            }
        )
        while True:
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            yield json.dumps({"status": "ok", "response": "evt", "data": {}})

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "test_token"}
        http.post.return_value.raise_for_status = lambda: None
        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await client.async_connect()
        client._device_id = "test_device"
        await client.async_get_status()

        # Get profile and add a new top-level key
        profile = client.device_profile("test_device")
        profile["new_key"] = "new_value"

        # Get profile again - new_key should NOT be in the cached dict
        profile2 = client.device_profile("test_device")
        assert "new_key" not in profile2
        assert "module" in profile2
        assert "esh" in profile2

        # Verify the original profile still has 2 keys (not 3)
        assert len(profile2) == 2

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_profile_caching_exception_in_try_block(
    hass: HomeAssistant, mock_websocket, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that unexpected exceptions during profile caching are caught and logged."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    def recv_generator():
        yield json.dumps({"response": "login", "status": "ok", "id": 1})
        yield json.dumps(
            {"response": "lst_device", "data": [{"device": "test_device_exception"}], "id": 2}
        )
        while len(mock_websocket.sent_requests) < 3:
            yield TimeoutError("waiting for get request")
        yield json.dumps(
            {
                "response": "get",
                "id": mock_websocket.sent_requests[2]["id"],
                "data": {"status": {"H00": 1}, "profile": {"module": {"fw": "1.0"}}},
            }
        )
        while True:
            yield TimeoutError("timeout")
            yield TimeoutError("timeout")
            yield json.dumps({"status": "ok", "response": "evt", "data": {}})

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
        caplog.at_level(logging.DEBUG, logger="custom_components.fansync.client"),
    ):
        http = http_cls.return_value
        http.post.return_value.json.return_value = {"token": "test_token"}
        http.post.return_value.raise_for_status = lambda: None
        mock_websocket.recv.side_effect = recv_generator()
        ws_connect.return_value = mock_websocket

        await client.async_connect()
        client._device_id = "test_device_exception"

        # Mock the _device_profile dict to raise an exception on assignment
        original_profile_dict = client._device_profile

        def raise_on_setitem(self, key, value):
            raise RuntimeError("Simulated exception during profile caching")

        mock_profile_dict = MagicMock()
        mock_profile_dict.__setitem__ = raise_on_setitem
        client._device_profile = mock_profile_dict

        # Should not raise exception - the try/except should catch it
        status = await client.async_get_status()

        # Verify status was still returned despite caching error
        assert status["H00"] == 1

        # Verify the debug log message for profile cache failure was logged
        assert any(
            "profile cache failed for test_device_exception" in record.message
            for record in caplog.records
        )

        # Restore original dict
        client._device_profile = original_profile_dict

        await client.async_disconnect()


@pytest.mark.asyncio
async def test_profile_retrieval_nonexistent_device(hass: HomeAssistant) -> None:
    """Test that device_profile() returns empty dict for unknown device."""
    client = FanSyncClient(hass, "e", "p", enable_push=False)

    # Request profile for device that was never cached
    profile = client.device_profile("nonexistent_device")

    # Should return empty dict, not raise exception
    assert profile == {}
