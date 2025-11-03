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

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

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

    # Create mock client with metrics
    client = MagicMock()
    client.device_ids = ["test_device_123"]
    metrics = ConnectionMetrics()
    metrics.is_connected = True
    metrics.total_commands = 100
    metrics.failed_commands = 5
    metrics.timed_out_commands = 3
    metrics.websocket_reconnects = 2
    metrics.push_updates_received = 50
    # Populate recent latencies to calculate avg/max
    metrics.recent_latencies = [100.0, 150.0, 200.0, 500.0]
    client.metrics = metrics

    # Mock device_profile
    def mock_device_profile(device_id):
        return {
            "esh": {"model": "TestFan 3000", "brand": "TestBrand"},
            "module": {"firmware_version": "1.2.3", "mac_address": "AA:BB:CC:DD:EE:FF"},
        }

    client.device_profile = mock_device_profile
    client._device_profile = {"test_device_123": {}}

    # Create mock coordinator
    coordinator = MagicMock()
    coordinator.update_interval = None
    coordinator.last_update_success = True
    coordinator.data = {"test_device_123": {"H00": 1, "H02": 50}}

    # Set up hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    # Get diagnostics
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Verify structure
    assert "config_entry" in diagnostics
    assert "coordinator" in diagnostics
    assert "client" in diagnostics
    assert "connection_metrics" in diagnostics
    assert "connection_analysis" in diagnostics
    assert "device_profiles" in diagnostics

    # Verify config entry data
    assert diagnostics["config_entry"]["entry_id"] == "test_entry"
    assert diagnostics["config_entry"]["title"] == "Test FanSync"

    # Verify coordinator data
    assert diagnostics["coordinator"]["last_update_success"] is True
    assert diagnostics["coordinator"]["device_count"] == 1

    # Verify client data
    assert diagnostics["client"]["device_count"] == 1
    assert "test_device_123" in diagnostics["client"]["device_ids"]

    # Verify connection metrics
    metrics_data = diagnostics["connection_metrics"]
    assert metrics_data["is_connected"] is True
    assert metrics_data["total_commands"] == 100
    assert metrics_data["successful_commands"] == 95
    assert metrics_data["failed_commands"] == 5
    assert metrics_data["timed_out_commands"] == 3
    assert metrics_data["websocket_reconnects"] == 2
    assert metrics_data["push_updates_received"] == 50
    # Average of [100, 150, 200, 500] = 237.5
    assert metrics_data["average_latency_ms"] == 237.5
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


async def test_diagnostics_warns_on_poor_connection(hass: HomeAssistant) -> None:
    """Test that diagnostics identifies poor connection quality."""
    # Create a mock config entry
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Test FanSync"
    entry.version = 1

    # Create mock client with poor metrics
    client = MagicMock()
    client.device_ids = ["test_device_456"]
    metrics = ConnectionMetrics()
    metrics.is_connected = True
    metrics.total_commands = 100
    metrics.failed_commands = 40  # 40% failure rate
    metrics.timed_out_commands = 30  # 30% timeout rate
    metrics.websocket_reconnects = 15  # Frequent reconnects
    # High latencies
    metrics.recent_latencies = [5000.0] * 10  # avg = 5000ms (very high)
    client.metrics = metrics

    client.device_profile = MagicMock(return_value={})
    client._device_profile = {}

    # Create mock coordinator
    coordinator = MagicMock()
    coordinator.update_interval = None
    coordinator.last_update_success = False
    coordinator.data = {}

    # Set up hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
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

    # Create mock client that's disconnected
    client = MagicMock()
    client.device_ids = []
    client.metrics = ConnectionMetrics()
    client.metrics.is_connected = False
    client.metrics.total_commands = 0

    client.device_profile = MagicMock(return_value={})
    client._device_profile = {}

    # Create mock coordinator
    coordinator = MagicMock()
    coordinator.update_interval = None
    coordinator.last_update_success = False
    coordinator.data = None

    # Set up hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    # Get diagnostics
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Verify it doesn't crash and provides useful info
    assert diagnostics["connection_metrics"]["is_connected"] is False
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

    # Create mock client with no commands yet
    client = MagicMock()
    client.device_ids = ["test_device"]
    client.metrics = ConnectionMetrics()
    client.metrics.is_connected = True
    client.metrics.total_commands = 0  # No commands sent yet

    client.device_profile = MagicMock(return_value={})
    client._device_profile = {}

    # Create mock coordinator
    coordinator = MagicMock()
    coordinator.update_interval = None
    coordinator.last_update_success = True
    coordinator.data = {}

    # Set up hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    # Get diagnostics
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Verify it handles no data gracefully
    assert diagnostics["connection_metrics"]["average_latency_ms"] == 0.0
    analysis = diagnostics["connection_analysis"]
    assert analysis["quality"] == "no_data"
