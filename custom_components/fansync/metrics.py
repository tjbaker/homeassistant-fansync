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

"""Connection metrics and quality monitoring for FanSync."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ConnectionMetrics:
    """Track connection health and performance metrics."""

    # Command statistics
    total_commands: int = 0
    failed_commands: int = 0
    timed_out_commands: int = 0

    # Latency tracking (milliseconds)
    recent_latencies: list[float] = field(default_factory=list)
    max_latency_samples: int = 20

    # WebSocket statistics
    websocket_reconnects: int = 0
    websocket_errors: int = 0
    push_updates_received: int = 0

    # Connection state
    is_connected: bool = False
    consecutive_failures: int = 0

    def record_command(self, success: bool, latency_ms: float | None = None) -> None:
        """Record a command execution."""
        self.total_commands += 1
        if not success:
            self.failed_commands += 1
            self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0

        if latency_ms is not None:
            self.recent_latencies.append(latency_ms)
            if len(self.recent_latencies) > self.max_latency_samples:
                self.recent_latencies.pop(0)

    def record_timeout(self) -> None:
        """Record a command timeout."""
        self.total_commands += 1
        self.failed_commands += 1
        self.timed_out_commands += 1
        self.consecutive_failures += 1

    def record_reconnect(self) -> None:
        """Record a WebSocket reconnection."""
        self.websocket_reconnects += 1

    def record_websocket_error(self) -> None:
        """Record a WebSocket error."""
        self.websocket_errors += 1

    def record_push_update(self) -> None:
        """Record receiving a push update."""
        self.push_updates_received += 1

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency from recent samples."""
        if not self.recent_latencies:
            return 0.0
        return sum(self.recent_latencies) / len(self.recent_latencies)

    @property
    def max_latency_ms(self) -> float:
        """Get maximum latency from recent samples."""
        if not self.recent_latencies:
            return 0.0
        return max(self.recent_latencies)

    @property
    def failure_rate(self) -> float:
        """Calculate command failure rate."""
        if self.total_commands == 0:
            return 0.0
        return self.failed_commands / self.total_commands

    @property
    def timeout_rate(self) -> float:
        """Calculate command timeout rate."""
        if self.total_commands == 0:
            return 0.0
        return self.timed_out_commands / self.total_commands

    def should_warn_user(self) -> bool:
        """Determine if user should be warned about poor connection quality."""
        # Warn if timeout rate > 30% or average latency > 5 seconds
        return self.timeout_rate > 0.3 or self.avg_latency_ms > 5000

    def to_dict(self) -> dict[str, Any]:
        """Export metrics as dictionary for diagnostics."""
        data = asdict(self)
        # Add computed properties
        data["avg_latency_ms"] = round(self.avg_latency_ms, 2)
        data["max_latency_ms"] = round(self.max_latency_ms, 2)
        data["failure_rate"] = round(self.failure_rate, 3)
        data["timeout_rate"] = round(self.timeout_rate, 3)
        data["should_warn"] = self.should_warn_user()
        return data
