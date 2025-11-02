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

"""Test diagnostics platform."""

from unittest.mock import MagicMock

import pytest

from custom_components.fansync.const import DOMAIN
from custom_components.fansync.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.asyncio
async def test_diagnostics_returns_metrics(hass):
    """Test diagnostics returns connection metrics and quality analysis."""
    # Create mock client with metrics
    mock_client = MagicMock()
    mock_client.device_id = "device123"
    mock_client.device_ids = ["device123"]
    mock_client.verify_ssl = True
    mock_client._enable_push = True  # noqa: SLF001
    mock_client._http_timeout_s = 20  # noqa: SLF001
    mock_client._ws_timeout_s = 30  # noqa: SLF001

    # Add metrics
    mock_client.metrics = MagicMock()
    mock_client.metrics.total_commands = 42
    mock_client.metrics.failed_commands = 2
    mock_client.metrics.timed_out_commands = 1
    mock_client.metrics.websocket_reconnects = 0
    mock_client.metrics.push_updates_received = 15
    mock_client.metrics.is_connected = True
    mock_client.metrics.consecutive_failures = 0
    mock_client.metrics.recent_latencies = [150.0, 200.0, 180.0]
    mock_client.metrics.avg_latency_ms = 176.7
    mock_client.metrics.max_latency_ms = 200.0
    mock_client.metrics.failure_rate = 0.048
    mock_client.metrics.timeout_rate = 0.024
    mock_client.metrics.should_warn_user.return_value = False
    mock_client.metrics.to_dict.return_value = {
        "total_commands": 42,
        "failed_commands": 2,
        "timed_out_commands": 1,
        "websocket_reconnects": 0,
        "push_updates_received": 15,
        "is_connected": True,
        "consecutive_failures": 0,
        "recent_latencies": [150.0, 200.0, 180.0],
        "max_latency_samples": 20,
        "websocket_errors": 0,
        "avg_latency_ms": 176.7,
        "max_latency_ms": 200.0,
        "failure_rate": 0.048,
        "timeout_rate": 0.024,
        "should_warn": False,
    }

    # Create mock coordinator
    mock_coordinator = MagicMock()
    mock_coordinator.update_interval = MagicMock()
    mock_coordinator.update_interval.total_seconds.return_value = 60.0
    mock_coordinator.last_update_success = True
    mock_coordinator.data = {"device123": {"H00": 1, "H02": 50}}

    # Create mock config entry
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.version = 1
    mock_entry.options = {"fallback_poll_seconds": 60}

    # Setup hass data
    hass.data[DOMAIN] = {
        "test_entry": {
            "client": mock_client,
            "coordinator": mock_coordinator,
            "platforms": ["fan"],
        }
    }

    # Call diagnostics
    diag = await async_get_config_entry_diagnostics(hass, mock_entry)

    # Verify structure
    assert "config_entry" in diag
    assert "client" in diag
    assert "coordinator" in diag
    assert "metrics" in diag
    assert "connection_quality" in diag

    # Verify metrics included
    assert diag["metrics"]["total_commands"] == 42
    assert diag["metrics"]["failed_commands"] == 2
    assert diag["metrics"]["push_updates_received"] == 15
    assert diag["metrics"]["is_connected"] is True

    # Verify connection quality analysis
    assert diag["connection_quality"]["status"] == "healthy"
    assert len(diag["connection_quality"]["recommendations"]) == 0


@pytest.mark.asyncio
async def test_diagnostics_warns_on_poor_connection(hass):
    """Test diagnostics warns when connection quality is poor."""
    # Create mock client with poor metrics
    mock_client = MagicMock()
    mock_client.device_id = "device123"
    mock_client.device_ids = ["device123"]
    mock_client.verify_ssl = True
    mock_client._enable_push = True  # noqa: SLF001
    mock_client._http_timeout_s = 20  # noqa: SLF001
    mock_client._ws_timeout_s = 30  # noqa: SLF001

    # Add poor metrics
    mock_client.metrics = MagicMock()
    mock_client.metrics.total_commands = 10
    mock_client.metrics.timed_out_commands = 4  # 40% timeout rate
    mock_client.metrics.avg_latency_ms = 6000.0  # 6 seconds
    mock_client.metrics.timeout_rate = 0.4
    mock_client.metrics.is_connected = True
    mock_client.metrics.consecutive_failures = 0
    mock_client.metrics.websocket_reconnects = 2
    mock_client.metrics.push_updates_received = 0
    mock_client.metrics.should_warn_user.return_value = True
    mock_client.metrics.to_dict.return_value = {
        "total_commands": 10,
        "timed_out_commands": 4,
        "avg_latency_ms": 6000.0,
        "timeout_rate": 0.4,
        "should_warn": True,
    }

    # Create mock coordinator
    mock_coordinator = MagicMock()
    mock_coordinator.update_interval = None
    mock_coordinator.last_update_success = True
    mock_coordinator.data = {"device123": {"H00": 1}}

    # Create mock config entry
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.version = 1
    mock_entry.options = {}

    # Setup hass data
    hass.data[DOMAIN] = {
        "test_entry": {
            "client": mock_client,
            "coordinator": mock_coordinator,
            "platforms": ["fan"],
        }
    }

    # Call diagnostics
    diag = await async_get_config_entry_diagnostics(hass, mock_entry)

    # Verify connection quality warns
    assert diag["connection_quality"]["status"] == "poor"
    assert len(diag["connection_quality"]["recommendations"]) >= 1
    # Should recommend increasing timeout
    recommendations_text = " ".join(diag["connection_quality"]["recommendations"])
    assert "timeout" in recommendations_text.lower()
