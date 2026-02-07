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

from collections.abc import Mapping

from .const import (
    KEY_DIRECTION,
    KEY_LIGHT_BRIGHTNESS,
    KEY_LIGHT_POWER,
    KEY_POWER,
    KEY_PRESET,
    KEY_SPEED,
)


def summarize_status_snapshot(data: object | None) -> dict[str, dict[str, object]]:
    """Summarize per-device status for diagnostics."""
    summary: dict[str, dict[str, object]] = {}
    if data is None:
        return summary
    if not isinstance(data, Mapping):
        return summary

    for device_id, status in data.items():
        if not isinstance(status, Mapping):
            continue
        status_map = dict(status)
        summary[device_id] = {
            "keys": sorted(status_map.keys()),
            "fan": {
                "power": status_map.get(KEY_POWER),
                "speed": status_map.get(KEY_SPEED),
                "preset": status_map.get(KEY_PRESET),
                "direction": status_map.get(KEY_DIRECTION),
            },
            "light": {
                "power": status_map.get(KEY_LIGHT_POWER),
                "brightness": status_map.get(KEY_LIGHT_BRIGHTNESS),
            },
        }
    return summary
