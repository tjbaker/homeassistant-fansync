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

"""Test connection metrics."""

from custom_components.fansync.metrics import ConnectionMetrics


def test_metrics_record_command_success() -> None:
    """Test recording successful commands."""
    metrics = ConnectionMetrics()
    metrics.record_command(True, 100.0)
    metrics.record_command(True, 200.0)

    assert metrics.total_commands == 2
    assert metrics.failed_commands == 0
    assert metrics.consecutive_failures == 0
    assert len(metrics.recent_latencies) == 2


def test_metrics_record_command_failure() -> None:
    """Test recording failed commands."""
    metrics = ConnectionMetrics()
    metrics.record_command(False)
    metrics.record_command(False)

    assert metrics.total_commands == 2
    assert metrics.failed_commands == 2
    assert metrics.consecutive_failures == 2


def test_metrics_record_timeout() -> None:
    """Test recording timeouts."""
    metrics = ConnectionMetrics()
    metrics.record_timeout()
    metrics.record_timeout()

    assert metrics.total_commands == 2
    assert metrics.failed_commands == 2
    assert metrics.timed_out_commands == 2
    assert metrics.consecutive_failures == 2


def test_metrics_record_websocket_error() -> None:
    """Test recording WebSocket errors."""
    metrics = ConnectionMetrics()
    metrics.record_websocket_error()
    metrics.record_websocket_error()

    assert metrics.websocket_errors == 2


def test_metrics_record_reconnect() -> None:
    """Test recording reconnections."""
    metrics = ConnectionMetrics()
    metrics.record_reconnect()
    metrics.record_reconnect()

    assert metrics.websocket_reconnects == 2


def test_metrics_record_push_update() -> None:
    """Test recording push updates."""
    metrics = ConnectionMetrics()
    metrics.record_push_update()
    metrics.record_push_update()
    metrics.record_push_update()

    assert metrics.push_updates_received == 3


def test_metrics_avg_latency() -> None:
    """Test average latency calculation."""
    metrics = ConnectionMetrics()

    # Empty should return 0
    assert metrics.avg_latency_ms == 0.0

    # Add samples
    metrics.record_command(True, 100.0)
    metrics.record_command(True, 200.0)

    assert metrics.avg_latency_ms == 150.0


def test_metrics_max_latency() -> None:
    """Test max latency calculation."""
    metrics = ConnectionMetrics()

    # Empty should return 0
    assert metrics.max_latency_ms == 0.0

    # Add samples
    metrics.record_command(True, 100.0)
    metrics.record_command(True, 300.0)
    metrics.record_command(True, 200.0)

    assert metrics.max_latency_ms == 300.0


def test_metrics_failure_rate() -> None:
    """Test failure rate calculation."""
    metrics = ConnectionMetrics()

    # No commands = 0% failure
    assert metrics.failure_rate == 0.0

    # 2 successes, 1 failure = 33.3%
    metrics.record_command(True)
    metrics.record_command(True)
    metrics.record_command(False)

    assert abs(metrics.failure_rate - 0.333) < 0.01


def test_metrics_timeout_rate() -> None:
    """Test timeout rate calculation."""
    metrics = ConnectionMetrics()

    # No commands = 0% timeout
    assert metrics.timeout_rate == 0.0

    # 2 normal, 1 timeout = 33.3%
    metrics.record_command(True)
    metrics.record_command(True)
    metrics.record_timeout()

    assert abs(metrics.timeout_rate - 0.333) < 0.01


def test_metrics_should_warn_user_high_timeout() -> None:
    """Test warning when timeout rate is high."""
    metrics = ConnectionMetrics()

    # Normal rate - no warning
    metrics.record_command(True)
    metrics.record_command(True)
    assert not metrics.should_warn_user()

    # High timeout rate (> 30%) - should warn
    metrics.record_timeout()
    metrics.record_timeout()
    assert metrics.should_warn_user()


def test_metrics_should_warn_user_high_latency() -> None:
    """Test warning when latency is high."""
    metrics = ConnectionMetrics()

    # Normal latency - no warning
    metrics.record_command(True, 100.0)
    assert not metrics.should_warn_user()

    # High latency (> 5000ms avg) - should warn
    metrics.record_command(True, 10000.0)
    assert metrics.should_warn_user()


def test_metrics_to_dict() -> None:
    """Test metrics export to dictionary."""
    metrics = ConnectionMetrics()
    metrics.record_command(True, 100.0)
    metrics.record_command(True, 200.0)
    metrics.record_command(False)
    metrics.record_timeout()
    metrics.record_reconnect()
    metrics.record_push_update()

    result = metrics.to_dict()

    assert result["total_commands"] == 4
    assert result["failed_commands"] == 2
    assert result["timed_out_commands"] == 1
    assert result["websocket_reconnects"] == 1
    assert result["push_updates_received"] == 1
    assert "avg_latency_ms" in result
    assert "max_latency_ms" in result
    assert "failure_rate" in result
    assert "timeout_rate" in result
    assert "should_warn" in result


def test_metrics_latency_sample_limit() -> None:
    """Test that latency samples are limited to max_latency_samples."""
    metrics = ConnectionMetrics()
    metrics.max_latency_samples = 5

    # Add more samples than the limit
    for i in range(10):
        metrics.record_command(True, float(i * 100))

    # Should only keep the last 5
    assert len(metrics.recent_latencies) == 5
    assert metrics.recent_latencies[0] == 500.0  # Oldest kept
    assert metrics.recent_latencies[-1] == 900.0  # Newest
