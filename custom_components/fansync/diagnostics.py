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

"""Diagnostics support for FanSync."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    shared = hass.data[DOMAIN][entry.entry_id]
    client = shared["client"]
    coordinator = shared["coordinator"]
    platforms = shared.get("platforms", [])

    # Gather connection metrics
    connection_quality = _analyze_connection_quality(client, coordinator)
    metrics_data = client.metrics.to_dict() if hasattr(client, "metrics") else {}

    diagnostics = {
        "config_entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "options": dict(entry.options),
        },
        "client": {
            "device_count": len(client.device_ids) if hasattr(client, "device_ids") else 0,
            "primary_device_id": client.device_id if hasattr(client, "device_id") else None,
            "verify_ssl": client.verify_ssl if hasattr(client, "verify_ssl") else None,
            "push_enabled": (
                client._enable_push if hasattr(client, "_enable_push") else None  # noqa: SLF001
            ),
            "http_timeout_s": (
                client._http_timeout_s
                if hasattr(client, "_http_timeout_s")
                else None  # noqa: SLF001
            ),
            "ws_timeout_s": (
                client._ws_timeout_s if hasattr(client, "_ws_timeout_s") else None  # noqa: SLF001
            ),
        },
        "coordinator": {
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds() if coordinator.update_interval else None
            ),
            "last_update_success": coordinator.last_update_success,
            "device_count": len(coordinator.data) if coordinator.data else 0,
        },
        "platforms_loaded": platforms,
        "metrics": metrics_data,
        "connection_quality": connection_quality,
    }

    return diagnostics


def _analyze_connection_quality(client, coordinator) -> dict[str, Any]:
    """Analyze connection quality and provide recommendations."""
    analysis: dict[str, Any] = {
        "status": "unknown",
        "recommendations": [],
    }

    # Check if we have metrics
    if hasattr(client, "metrics"):
        metrics = client.metrics

        # Determine overall status
        if not metrics.is_connected:
            analysis["status"] = "disconnected"
            analysis["recommendations"].append(
                "Client is not connected. Check network connectivity."
            )
        elif metrics.should_warn_user():
            analysis["status"] = "poor"
            if metrics.timeout_rate > 0.3:
                analysis["recommendations"].append(
                    f"High timeout rate ({metrics.timeout_rate:.1%}). "
                    "Consider increasing WebSocket timeout in Options."
                )
            if metrics.avg_latency_ms > 5000:
                analysis["recommendations"].append(
                    f"High average latency ({metrics.avg_latency_ms:.0f}ms). "
                    "Check network quality or increase timeouts."
                )
        elif metrics.consecutive_failures >= 3:
            analysis["status"] = "degraded"
            analysis["recommendations"].append(
                f"Multiple consecutive failures ({metrics.consecutive_failures}). "
                "Device may be offline or unreachable."
            )
        elif metrics.websocket_reconnects > 10:
            analysis["status"] = "unstable"
            analysis["recommendations"].append(
                f"Frequent reconnections ({metrics.websocket_reconnects} total). "
                "Network connection may be unstable."
            )
        elif coordinator.last_update_success and coordinator.data:
            analysis["status"] = "healthy"
        else:
            analysis["status"] = "initializing"

        # Additional recommendations based on metrics
        if metrics.push_updates_received == 0 and metrics.total_commands > 10:
            analysis["recommendations"].append(
                "No push updates received. Verify push is enabled and device supports it."
            )

    elif not coordinator.last_update_success:
        analysis["status"] = "degraded"
        analysis["recommendations"].append(
            "Last update failed. Check network connectivity and device availability."
        )
    elif coordinator.data:
        analysis["status"] = "healthy"
    else:
        analysis["status"] = "initializing"

    return analysis
