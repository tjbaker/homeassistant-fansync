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


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = entry.runtime_data
    client = runtime_data.get("client")
    coordinator = runtime_data.get("coordinator")

    diagnostics: dict[str, Any] = {
        "config_entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "version": entry.version,
        },
        "home_assistant_version": getattr(hass.config, "version", "unknown"),
        "coordinator": {},
        "client": {},
        "connection_analysis": {},
    }

    # Coordinator diagnostics
    if coordinator:
        diagnostics["coordinator"] = {
            "update_interval": (
                str(coordinator.update_interval) if coordinator.update_interval else None
            ),
            "last_update_success": coordinator.last_update_success,
            "device_count": len(coordinator.data) if coordinator.data else 0,
        }

    # Client diagnostics
    if client:
        try:
            # Use new comprehensive diagnostics method
            if hasattr(client, "get_diagnostics_data"):
                client_diag = client.get_diagnostics_data()
                diagnostics.update(client_diag)

            # Add device IDs
            device_ids = getattr(client, "device_ids", [])
            diagnostics["device_ids"] = device_ids

            # Connection quality analysis
            if hasattr(client, "metrics"):
                metrics = client.metrics
                analysis = _analyze_connection_quality(metrics)
                diagnostics["connection_analysis"] = analysis

            # Device profiles (sanitized)
            if hasattr(client, "device_profile"):
                profiles = {}
                for device_id in device_ids:
                    profile = client.device_profile(device_id)
                    if profile:
                        # Include useful metadata, exclude sensitive data
                        sanitized = {}
                        if "esh" in profile:
                            sanitized["esh"] = {
                                "model": profile["esh"].get("model"),
                                "brand": profile["esh"].get("brand"),
                            }
                        if "module" in profile:
                            # Mask MAC address for privacy (show first 3 octets only)
                            mac = profile["module"].get("mac_address", "")
                            if mac and len(mac.split(":")) >= 3:
                                masked_mac = ":".join(mac.split(":")[:3] + ["XX", "XX", "XX"])
                            else:
                                masked_mac = None
                            sanitized["module"] = {
                                "firmware_version": profile["module"].get("firmware_version"),
                                "mac_address": masked_mac,
                            }
                        profiles[device_id] = sanitized
                diagnostics["device_profiles"] = profiles

        except Exception as err:
            diagnostics["client_error"] = str(err)

    return diagnostics


def _analyze_connection_quality(metrics: Any) -> dict[str, Any]:
    """Analyze connection metrics and provide recommendations."""
    analysis: dict[str, Any] = {
        "quality": "unknown",
        "issues": [],
        "recommendations": [],
    }

    if not metrics.is_connected:
        analysis["quality"] = "disconnected"
        analysis["issues"].append("Not currently connected to FanSync API")
        analysis["recommendations"].append("Check network connectivity and credentials")
        return analysis

    if metrics.total_commands == 0:
        analysis["quality"] = "no_data"
        analysis["issues"].append("No commands have been sent yet")
        return analysis

    # Calculate metrics
    success_rate = 1.0 - metrics.failure_rate
    avg_latency = metrics.avg_latency_ms

    # Determine quality
    if success_rate >= 0.95 and avg_latency < 1000:
        analysis["quality"] = "excellent"
    elif success_rate >= 0.90 and avg_latency < 2000:
        analysis["quality"] = "good"
    elif success_rate >= 0.75 and avg_latency < 5000:
        analysis["quality"] = "fair"
    else:
        analysis["quality"] = "poor"

    # Identify issues
    if success_rate < 0.90:
        failed = metrics.failed_commands
        total = metrics.total_commands
        analysis["issues"].append(
            f"Low success rate: {success_rate:.1%} ({failed}/{total} failures)"
        )

    if metrics.timeout_rate > 0.1:
        timeouts = metrics.timed_out_commands
        total = metrics.total_commands
        analysis["issues"].append(f"High timeout rate: {timeouts} timeouts out of {total} commands")

    if avg_latency > 2000:
        analysis["issues"].append(f"High average latency: {avg_latency:.0f}ms")

    if metrics.websocket_reconnects > 5:
        analysis["issues"].append(
            f"Frequent reconnections: {metrics.websocket_reconnects} reconnects"
        )

    # Provide recommendations
    if avg_latency > 2000:
        analysis["recommendations"].append(
            "Consider increasing WebSocket timeout in integration options"
        )

    if metrics.timed_out_commands > 0:
        analysis["recommendations"].append(
            "Network latency may be high - check WiFi signal strength"
        )

    if metrics.websocket_reconnects > 5:
        analysis["recommendations"].append(
            "Unstable connection - verify network stability and router settings"
        )

    if success_rate < 0.75:
        analysis["recommendations"].append(
            "Poor connection quality - consider restarting Home Assistant or the FanSync device"
        )

    # Note: Recommendations are only added when there are actionable items
    # An empty recommendations list indicates a healthy connection

    return analysis
