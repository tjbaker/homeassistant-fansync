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

"""Tests for FanSync diagnostics."""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient
from custom_components.fansync.const import DOMAIN
from custom_components.fansync.diagnostics import async_get_config_entry_diagnostics
from custom_components.fansync.metrics import ConnectionMetrics


async def test_diagnostics_returns_metrics(hass: HomeAssistant) -> None:
    """Test that diagnostics returns connection metrics."""
    # Create a mock config entry
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Test FanSync"
    entry.version = 1
    entry.options = {}
    entry.options = {"fallback_poll_seconds": 30}

    # Create mock client with metrics
    client = MagicMock()
    client.device_ids = ["test_device_123"]
    metrics = ConnectionMetrics()
    metrics.is_connected = True
    metrics.total_commands = 100
    metrics.failed_commands = 5
    metrics.timed_out_commands = 3
    metrics.websocket_reconnects = 2
    metrics.websocket_errors = 1
    metrics.push_updates_received = 50
    # Populate recent latencies to calculate avg/max
    metrics.recent_latencies = [100.0, 150.0, 200.0, 500.0]
    client.metrics = metrics

    # Mock get_diagnostics_data method
    def mock_get_diagnostics_data() -> dict[str, Any]:
        return {
            "environment": {
                "python_version": "3.13.0",
                "websockets_version": "15.0.1",
                "httpx_version": "0.27.0",
            },
            "configuration": {
                "verify_ssl": True,
                "enable_push": True,
                "http_timeout_s": None,
                "ws_timeout_s": None,
            },
            "connection_state": {
                "is_connected": metrics.is_connected,
                "has_websocket": True,
                "has_http_client": True,
                "device_count": 1,
            },
            "connection_timing": {
                "last_http_login_ms": 450.0,
                "last_ws_login_ms": 670.0,
            },
            "token_metadata": {
                "format_valid": True,
                "length": 344,
                "expires_in_seconds": 2592000,
                "is_expired": False,
            },
            "connection_failures": [],
            "metrics": {
                "total_commands": metrics.total_commands,
                "failed_commands": metrics.failed_commands,
                "timed_out_commands": metrics.timed_out_commands,
                "websocket_reconnects": metrics.websocket_reconnects,
                "websocket_errors": metrics.websocket_errors,
                "push_updates_received": metrics.push_updates_received,
                "avg_latency_ms": round(metrics.avg_latency_ms, 2),
                "max_latency_ms": round(metrics.max_latency_ms, 2),
                "failure_rate": round(metrics.failure_rate, 3),
                "timeout_rate": round(metrics.timeout_rate, 3),
            },
        }

    client.get_diagnostics_data = mock_get_diagnostics_data

    # Mock device_profile
    def mock_device_profile(device_id: str) -> dict[str, Any]:
        return {
            "esh": {"model": "TestFan 3000", "brand": "TestBrand"},
            "module": {"firmware_version": "1.2.3", "mac_address": "AA:BB:CC:DD:EE:FF"},
        }

    client.device_profile = mock_device_profile

    # Create mock coordinator
    coordinator = MagicMock()
    coordinator.update_interval = None
    coordinator.last_update_success = True
    coordinator.last_exception = None
    coordinator._last_update_start_utc = "2026-02-05T00:00:00+00:00"
    coordinator._last_update_end_utc = "2026-02-05T00:00:01+00:00"
    coordinator._last_update_trigger = "manual"
    coordinator._last_update_timeout_devices = []
    coordinator._last_update_device_count = 1
    coordinator._last_update_success_utc = "2026-02-05T00:00:01+00:00"
    coordinator._last_update_duration_ms = 123.4
    coordinator._last_poll_mismatch_keys = {"test_device_123": ["H00"]}
    coordinator._last_poll_mismatch_history = [
        {
            "timestamp_utc": "2026-02-05T00:00:01+00:00",
            "device_count": 1,
            "mismatch_keys": {"test_device_123": ["H00"]},
        }
    ]
    coordinator._status_history = [
        {
            "timestamp_utc": "2026-02-05T00:00:01+00:00",
            "device_count": 1,
            "summary": {"test_device_123": {"fan": {"power": 1}, "light": {"power": 0}}},
        }
    ]
    coordinator.data = {"test_device_123": {"H00": 1, "H02": 50}}

    # Set up entry.runtime_data
    entry.runtime_data = {
        "client": client,
        "coordinator": coordinator,
        "platforms": ["fan", "light"],
    }

    # Get diagnostics
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Verify structure
    assert "config_entry" in diagnostics
    assert "coordinator" in diagnostics
    assert "environment" in diagnostics
    assert "configuration" in diagnostics
    assert "connection_state" in diagnostics
    assert "connection_timing" in diagnostics
    assert "metrics" in diagnostics
    assert "connection_analysis" in diagnostics
    assert "device_profiles" in diagnostics

    # Verify config entry data
    assert diagnostics["config_entry"]["entry_id"] == "test_entry"
    assert diagnostics["config_entry"]["title"] == "Test FanSync"
    assert diagnostics["config_entry"]["options"]["fallback_poll_seconds"] == 30

    # Verify coordinator data
    assert diagnostics["coordinator"]["last_update_success"] is True
    assert diagnostics["coordinator"]["device_count"] == 1
    assert diagnostics["coordinator"]["last_update_trigger"] == "manual"
    assert diagnostics["coordinator"]["last_poll_mismatch_keys"]["test_device_123"] == ["H00"]
    assert diagnostics["coordinator"]["status_history"][0]["device_count"] == 1

    # Verify device IDs
    assert "test_device_123" in diagnostics["device_ids"]

    # Verify connection metrics
    metrics_data = diagnostics["metrics"]
    assert metrics_data["total_commands"] == 100
    assert metrics_data["failed_commands"] == 5
    assert metrics_data["timed_out_commands"] == 3
    assert metrics_data["websocket_reconnects"] == 2
    assert metrics_data["push_updates_received"] == 50
    # Average of [100, 150, 200, 500] = 237.5
    assert metrics_data["avg_latency_ms"] == 237.5
    assert metrics_data["max_latency_ms"] == 500.0

    # Verify connection analysis
    analysis = diagnostics["connection_analysis"]
    assert analysis["quality"] == "excellent"
    assert len(analysis["issues"]) == 0
    # With timeouts, it will recommend checking WiFi
    assert len(analysis["recommendations"]) > 0

    # Verify device profiles
    assert "test_device_123" in diagnostics["device_profiles"]
    profile = diagnostics["device_profiles"]["test_device_123"]
    assert profile["esh"]["model"] == "TestFan 3000"
    assert profile["module"]["firmware_version"] == "1.2.3"
    # MAC address should be masked for privacy
    assert profile["module"]["mac_address"] == "AA:BB:CC:XX:XX:XX"


async def test_diagnostics_warns_on_poor_connection(hass: HomeAssistant) -> None:
    """Test that diagnostics identifies poor connection quality."""
    # Create a mock config entry
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Test FanSync"
    entry.version = 1
    entry.options = {}

    # Create mock client with poor metrics
    client = MagicMock()
    client.device_ids = ["test_device_456"]
    metrics = ConnectionMetrics()
    metrics.is_connected = True
    metrics.total_commands = 100
    metrics.failed_commands = 40  # 40% failure rate
    metrics.timed_out_commands = 30  # 30% timeout rate
    metrics.websocket_reconnects = 15  # Frequent reconnects
    metrics.websocket_errors = 10
    metrics.push_updates_received = 5
    # High latencies
    metrics.recent_latencies = [5000.0] * 10  # avg = 5000ms (very high)
    client.metrics = metrics

    # Mock get_diagnostics_data method
    def mock_get_diagnostics_data_poor() -> dict[str, Any]:
        return {
            "environment": {
                "python_version": "3.13.0",
                "websockets_version": "15.0.1",
                "httpx_version": "0.27.0",
            },
            "configuration": {
                "verify_ssl": True,
                "enable_push": True,
                "http_timeout_s": None,
                "ws_timeout_s": None,
            },
            "connection_state": {
                "is_connected": metrics.is_connected,
                "has_websocket": True,
                "has_http_client": True,
                "device_count": 1,
            },
            "connection_timing": {
                "last_http_login_ms": 450.0,
                "last_ws_login_ms": 8500.0,  # High latency
            },
            "token_metadata": {
                "format_valid": True,
                "length": 344,
                "expires_in_seconds": 2592000,
                "is_expired": False,
            },
            "connection_failures": [
                {
                    "timestamp": "2025-11-03T12:00:00+00:00",
                    "stage": "ws_login",
                    "error_type": "TimeoutError",
                    "elapsed_ms": 90000.0,
                    "attempt": 1,
                }
            ],
            "metrics": {
                "total_commands": metrics.total_commands,
                "failed_commands": metrics.failed_commands,
                "timed_out_commands": metrics.timed_out_commands,
                "websocket_reconnects": metrics.websocket_reconnects,
                "websocket_errors": metrics.websocket_errors,
                "push_updates_received": metrics.push_updates_received,
                "avg_latency_ms": round(metrics.avg_latency_ms, 2),
                "max_latency_ms": round(metrics.max_latency_ms, 2),
                "failure_rate": round(metrics.failure_rate, 3),
                "timeout_rate": round(metrics.timeout_rate, 3),
            },
        }

    client.get_diagnostics_data = mock_get_diagnostics_data_poor
    client.device_profile = MagicMock(return_value={})

    # Create mock coordinator
    coordinator = MagicMock()
    coordinator.update_interval = None
    coordinator.last_update_success = False
    coordinator.data = {}

    # Set up entry.runtime_data
    entry.runtime_data = {
        "client": client,
        "coordinator": coordinator,
        "platforms": ["fan", "light"],
    }

    # Get diagnostics
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Verify connection analysis shows poor quality
    analysis = diagnostics["connection_analysis"]
    assert analysis["quality"] == "poor"
    assert len(analysis["issues"]) > 0
    assert len(analysis["recommendations"]) > 0

    # Check for specific issues
    issues_text = " ".join(analysis["issues"]).lower()
    assert "success rate" in issues_text or "timeout" in issues_text or "latency" in issues_text

    # Check for recommendations
    recommendations_text = " ".join(analysis["recommendations"]).lower()
    assert (
        "timeout" in recommendations_text
        or "network" in recommendations_text
        or "restart" in recommendations_text
    )


async def test_diagnostics_handles_disconnected_state(hass: HomeAssistant) -> None:
    """Test that diagnostics handles disconnected state gracefully."""
    # Create a mock config entry
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Test FanSync"
    entry.version = 1
    entry.options = {}

    # Create mock client that's disconnected
    client = MagicMock()
    client.device_ids = []
    metrics = ConnectionMetrics()
    metrics.is_connected = False
    metrics.total_commands = 0
    client.metrics = metrics

    # Mock get_diagnostics_data method
    def mock_get_diagnostics_data_disconnected() -> dict[str, Any]:
        return {
            "environment": {
                "python_version": "3.13.0",
                "websockets_version": "15.0.1",
                "httpx_version": "0.27.0",
            },
            "configuration": {
                "verify_ssl": True,
                "enable_push": True,
                "http_timeout_s": None,
                "ws_timeout_s": None,
            },
            "connection_state": {
                "is_connected": False,
                "has_websocket": False,
                "has_http_client": False,
                "device_count": 0,
            },
            "connection_timing": {
                "last_http_login_ms": None,
                "last_ws_login_ms": None,
            },
            "token_metadata": {},
            "connection_failures": [],
            "metrics": {
                "total_commands": 0,
                "failed_commands": 0,
                "timed_out_commands": 0,
                "websocket_reconnects": 0,
                "websocket_errors": 0,
                "push_updates_received": 0,
                "avg_latency_ms": 0.0,
                "max_latency_ms": 0.0,
                "failure_rate": 0.0,
                "timeout_rate": 0.0,
            },
        }

    client.get_diagnostics_data = mock_get_diagnostics_data_disconnected
    client.device_profile = MagicMock(return_value={})

    # Create mock coordinator
    coordinator = MagicMock()
    coordinator.update_interval = None
    coordinator.last_update_success = False
    coordinator.data = None

    # Set up entry.runtime_data
    entry.runtime_data = {
        "client": client,
        "coordinator": coordinator,
        "platforms": ["fan", "light"],
    }

    # Get diagnostics
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Verify it doesn't crash and provides useful info
    assert diagnostics["connection_state"]["is_connected"] is False
    analysis = diagnostics["connection_analysis"]
    assert analysis["quality"] == "disconnected"
    assert len(analysis["issues"]) > 0
    assert "not currently connected" in analysis["issues"][0].lower()


async def test_diagnostics_handles_no_data(hass: HomeAssistant) -> None:
    """Test that diagnostics handles case with no command data."""
    # Create a mock config entry
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Test FanSync"
    entry.version = 1
    entry.options = {}

    # Create mock client with no commands yet
    client = MagicMock()
    client.device_ids = ["test_device"]
    metrics = ConnectionMetrics()
    metrics.is_connected = True
    metrics.total_commands = 0  # No commands sent yet
    client.metrics = metrics

    # Mock get_diagnostics_data method
    def mock_get_diagnostics_data_no_data() -> dict[str, Any]:
        return {
            "environment": {
                "python_version": "3.13.0",
                "websockets_version": "15.0.1",
                "httpx_version": "0.27.0",
            },
            "configuration": {
                "verify_ssl": True,
                "enable_push": True,
                "http_timeout_s": None,
                "ws_timeout_s": None,
            },
            "connection_state": {
                "is_connected": True,
                "has_websocket": True,
                "has_http_client": True,
                "device_count": 1,
            },
            "connection_timing": {
                "last_http_login_ms": 450.0,
                "last_ws_login_ms": 670.0,
            },
            "token_metadata": {
                "format_valid": True,
                "length": 344,
                "expires_in_seconds": 2592000,
                "is_expired": False,
            },
            "connection_failures": [],
            "metrics": {
                "total_commands": 0,
                "failed_commands": 0,
                "timed_out_commands": 0,
                "websocket_reconnects": 0,
                "websocket_errors": 0,
                "push_updates_received": 0,
                "avg_latency_ms": 0.0,
                "max_latency_ms": 0.0,
                "failure_rate": 0.0,
                "timeout_rate": 0.0,
            },
        }

    client.get_diagnostics_data = mock_get_diagnostics_data_no_data
    client.device_profile = MagicMock(return_value={})

    # Create mock coordinator
    coordinator = MagicMock()
    coordinator.update_interval = None
    coordinator.last_update_success = True
    coordinator.data = {}

    # Set up entry.runtime_data
    entry.runtime_data = {
        "client": client,
        "coordinator": coordinator,
        "platforms": ["fan", "light"],
    }

    # Get diagnostics
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Verify it handles no data gracefully
    assert diagnostics["metrics"]["avg_latency_ms"] == 0.0
    analysis = diagnostics["connection_analysis"]
    assert analysis["quality"] == "no_data"


async def test_diagnostics_includes_granular_timing(hass: HomeAssistant) -> None:
    """Test that diagnostics include granular timing breakdown after connection."""

    # Helper to generate mock WebSocket responses
    def _login_ok() -> str:
        return json.dumps({"response": "login", "status": "ok", "id": 1})

    def _lst_device_ok() -> str:
        return json.dumps(
            {
                "response": "lst_device",
                "data": [{"device": "test_device", "role": "owner"}],
                "id": 2,
            }
        )

    # Create real client
    client = FanSyncClient(hass, "test@example.com", "password")

    # Mock WebSocket
    mock_ws = AsyncMock()
    mock_ws.state = MagicMock()
    mock_ws.state.name = "OPEN"

    # Generator for recv responses
    def recv_generator():
        yield _login_ok()
        yield _lst_device_ok()
        while True:
            yield TimeoutError("timeout")

    mock_ws.recv.side_effect = recv_generator()
    mock_ws.send = AsyncMock()
    mock_ws.close = AsyncMock()

    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch(
            "custom_components.fansync.client.websockets.connect", new_callable=AsyncMock
        ) as ws_connect,
    ):
        # Mock HTTP client
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"token": "test_token_123"},
            },
        )()

        # Mock WebSocket connection
        ws_connect.return_value = mock_ws

        # Connect
        await client.async_connect()

        # Get diagnostics data directly from client
        diag = client.get_diagnostics_data()

        # Verify structure exists
        assert "connection_timing" in diag
        assert "last_login_response" in diag
        assert "token_metadata" in diag

        timing = diag["connection_timing"]

        # Verify all granular timing fields exist
        assert "last_http_login_ms" in timing
        assert "last_ws_connect_ms" in timing
        assert "last_ws_login_wait_ms" in timing
        assert "last_ws_login_ms" in timing
        assert "token_refresh_count" in timing

        # Verify timing fields are populated (not None) after successful connection
        assert timing["last_http_login_ms"] is not None
        assert timing["last_http_login_ms"] > 0
        assert timing["last_ws_connect_ms"] is not None
        assert timing["last_ws_connect_ms"] > 0
        assert timing["last_ws_login_wait_ms"] is not None
        assert timing["last_ws_login_wait_ms"] > 0
        assert timing["last_ws_login_ms"] is not None
        assert timing["last_ws_login_ms"] > 0

        # Verify token refresh count starts at 0
        assert timing["token_refresh_count"] == 0

        # Verify login response is captured
        assert diag["last_login_response"] is not None
        assert diag["last_login_response"]["status"] == "ok"
        assert diag["last_login_response"]["response"] == "login"
        assert "timestamp" in diag["last_login_response"]

        # Verify token metadata field exists (content depends on token format)
        assert "token_metadata" in diag
        assert isinstance(diag["token_metadata"], dict)

        # Verify timing breakdown makes sense: total >= handshake + login_wait
        # (allowing for small timing discrepancies)
        assert timing["last_ws_login_ms"] >= timing["last_ws_connect_ms"]

        # Cleanup
        await client.async_disconnect()


async def test_diagnostics_redacts_device_metadata(hass: HomeAssistant) -> None:
    """Ensure device metadata redacts sensitive fields."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Test FanSync"
    entry.version = 1
    entry.options = {}

    client = MagicMock()
    client.device_ids = ["test_device_123"]
    client.metrics = ConnectionMetrics()
    client.get_diagnostics_data = MagicMock(return_value={})
    client.device_profile = MagicMock(return_value={})
    client.device_metadata = MagicMock(
        return_value={"owner": "user@example.com", "token": "secret", "device": "x"}
    )

    coordinator = MagicMock()
    coordinator.update_interval = None
    coordinator.last_update_success = True
    coordinator.data = {}

    entry.runtime_data = {"client": client, "coordinator": coordinator, "platforms": ["fan"]}

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    meta = diagnostics["device_metadata"]["test_device_123"]
    assert meta["owner"] == "***"
    assert meta["token"] == "***"
    assert meta["device"] == "x"


async def test_client_diagnostics_extended_fields(hass: HomeAssistant) -> None:
    """Ensure extended client diagnostics are populated."""
    client = FanSyncClient(hass, "user@example.com", "pass", verify_ssl=False)
    loop = asyncio.get_running_loop()
    client._pending_requests = {1: loop.create_future(), 2: loop.create_future()}
    client._last_request_id = 42
    client._last_reconnect_utc = "2026-02-05T00:00:00+00:00"
    client._last_recv_error = "TimeoutError"
    client._last_recv_error_utc = "2026-02-05T00:00:01+00:00"
    client._last_push_by_device = {"dev1": {"utc": "2026-02-05T00:00:02+00:00"}}
    client._last_get_by_device = {"dev1": {"timestamp": "2026-02-05T00:00:03+00:00"}}
    client._last_set_by_device = {"dev1": {"timestamp": "2026-02-05T00:00:04+00:00"}}
    client.metrics.is_connected = True

    diag = client.get_diagnostics_data()
    assert diag["connection_state"]["pending_requests"] == 2
    assert diag["connection_state"]["last_request_id"] == 42
    assert diag["connection_state"]["last_reconnect_utc"] == "2026-02-05T00:00:00+00:00"
    assert diag["connection_state"]["last_recv_error"] == "TimeoutError"
    assert diag["push"]["last_push_by_device"]["dev1"]["utc"] == "2026-02-05T00:00:02+00:00"
    assert diag["last_get_by_device"]["dev1"]["timestamp"] == "2026-02-05T00:00:03+00:00"
    assert diag["last_set_by_device"]["dev1"]["timestamp"] == "2026-02-05T00:00:04+00:00"
