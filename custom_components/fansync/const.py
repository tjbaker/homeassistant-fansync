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

from collections.abc import Iterable, Mapping

DOMAIN = "fansync"
PLATFORMS = ["fan", "light", "switch"]


def lightless_signal(entry_id: str) -> str:
    """Dispatcher signal sent with the new lightless device set when it changes.

    The light platform adds/removes Light entities in place and the per-fan
    "Light installed" switches refresh, so no config-entry reload is needed.
    """
    return f"{DOMAIN}_lightless_{entry_id}"


CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_VERIFY_SSL = "verify_ssl"
CONF_HTTP_TIMEOUT = "http_timeout_seconds"
CONF_WS_TIMEOUT = "ws_timeout_seconds"

# Protocol keys
KEY_POWER = "H00"
KEY_PRESET = "H01"
KEY_SPEED = "H02"
KEY_DIRECTION = "H06"
KEY_LIGHT_POWER = "H0B"
KEY_LIGHT_BRIGHTNESS = "H0C"
KEY_LIGHT_COLOR_TEMP = "H04"
# The app's "Home Away" mode. Turning it on stops the fan; powering the fan on clears it.
KEY_HOME_AWAY = "H0D"

# Warm, natural, cool. Not a continuous range - requested kelvin values are
# snapped to the nearest of these for devices without a model-specific profile.
LIGHT_COLOR_TEMP_PRESETS_KELVIN = (3000, 4000, 5000)

# The known Corke fixture profile has five selectable CCT presets. Model names
# are matched by normalized prefix so size/receiver suffixes (for example
# Corke36-FD6R1L5) do not need individual entries. Unknown models stay on the
# legacy three-preset profile; H04 alone is not enough to infer Corke support.
LIGHT_COLOR_TEMP_MODEL_PRESETS = {
    "corke": (2700, 3000, 3500, 4000, 5000),
}

# Preset modes mapping
PRESET_MODES = {0: "normal", 1: "fresh_air"}


# Optimistic update timing (shared by entities)
# Guard window to prevent UI snap-back while awaiting confirmation
# Push updates (device_change events) are reliable and typically arrive within 1-2 seconds.
# Early termination logic stops polling once push confirms, so this is mainly a safety net.
OPTIMISTIC_GUARD_SEC = 3.0
# The status a device puts in its own acknowledgement of a write it accepted.
DEVICE_ACK_OK = "ok"
# Extra time an unreported power write waits for the device's acknowledgement
# once the optimistic guard has lapsed. A Kute60 was measured answering 1.9 to
# 2.5 seconds after the write, close to the guard itself.
DEVICE_ACK_GRACE_SEC = 5.0
# How many device acknowledgements the client remembers, newest kept.
DEVICE_ACK_HISTORY_MAX = 32
# Confirmation polling attempts and delay between polls
# Push updates typically confirm changes within 1-2 seconds, terminating polling early.
# Initial 0.5s delay before first poll, then 2 poll attempts with 0.5s delays between
# (total up to 1.5s). Push updates typically confirm within the initial delay, avoiding
# polling entirely.
CONFIRM_RETRY_ATTEMPTS = 2
CONFIRM_RETRY_DELAY_SEC = 0.5
CONFIRM_INITIAL_DELAY_SEC = 0.5

# Options: fallback polling
OPTION_FALLBACK_POLL_SECS = "fallback_poll_seconds"
DEFAULT_FALLBACK_POLL_SECS = 60
MIN_FALLBACK_POLL_SECS = 15
MAX_FALLBACK_POLL_SECS = 600
# Options: hide the light entity for fans that have no physical light but still
# advertise a light channel (H0B/H0C) in their status (e.g. some Kute60 units).
# Stored per-device: a list of device_ids whose light entity should be hidden.
OPTION_LIGHTLESS_DEVICES = "lightless_devices"
# Legacy account-wide boolean (0.8.0). Kept only for migration to the per-device
# list above; a mixed multi-fan household could not use it correctly.
OPTION_DISABLE_LIGHT = "disable_light"
DEFAULT_DISABLE_LIGHT = False
# Timeouts
# HTTP timeouts apply to connect/read for login and token refresh
DEFAULT_HTTP_TIMEOUT_SECS = 20
MIN_HTTP_TIMEOUT_SECS = 5
MAX_HTTP_TIMEOUT_SECS = 120

# WebSocket timeout for connect/recv operations
DEFAULT_WS_TIMEOUT_SECS = 30
MIN_WS_TIMEOUT_SECS = 5
MAX_WS_TIMEOUT_SECS = 120


# WebSocket login retry settings
WS_LOGIN_RETRY_ATTEMPTS = 2
WS_LOGIN_RETRY_BACKOFF_SEC = 1.0

# WebSocket receive loop retry settings (consumed by client._recv_loop)
WS_RECV_TIMEOUT_ERROR_THRESHOLD = 3  # Consecutive errors before reconnect
WS_RECV_BACKOFF_INITIAL_SEC = 0.5  # Initial backoff delay
WS_RECV_BACKOFF_MAX_SEC = 5.0  # Maximum backoff delay
WS_RECV_SLEEP_SEC = 0.1  # Sleep between recv attempts

# Push update logging (tune higher for quieter logs)
PUSH_LOG_EVERY = 50

# Diagnostics history retention
COMMAND_HISTORY_MAX = 50
STATUS_HISTORY_MAX = 10
# Distinct device-reported values kept per register for diagnostics. Enough to
# capture every level of a quantized register; a continuous one just fills up.
OBSERVED_VALUES_MAX = 32
MISMATCH_HISTORY_MAX = 10

# WebSocket request IDs for connection bootstrap (keep stable for compatibility)
# GET_STATUS and SET now use dynamic allocation via _next_request_id
WS_REQUEST_ID_LOGIN = 1
WS_REQUEST_ID_LIST_DEVICES = 2

# WebSocket fallback timeout (used when _ws_timeout_s is None)
WS_FALLBACK_TIMEOUT_SEC = 10.0

# Greeting timeout: how long to wait for a server-initiated frame after WebSocket upgrade.
# Some API versions send a greeting that must be consumed before they respond to login.
# The server either sends the greeting promptly or not at all, so a short window suffices.
WS_GREETING_TIMEOUT_SEC = 2.0

# Coordinator timeouts
# Align with default WS timeout to avoid cancelling in-progress recv operations
POLL_STATUS_TIMEOUT_SECS = 30

# Performance monitoring thresholds
# Warn users when command latency exceeds these thresholds
SLOW_RESPONSE_WARNING_MS = 10000  # 10 seconds - warn about slow cloud responses
SLOW_CONNECTION_WARNING_MS = 5000  # 5 seconds - warn about slow initial connection


def clamp_percentage(value: int) -> int:
    """Clamp percentage to FanSync allowed range [1, 100]."""
    return max(1, min(100, int(value)))


def ha_brightness_to_pct(brightness: int | None) -> int:
    """Map Home Assistant brightness (0-255) to FanSync 1-100."""
    if brightness is None:
        return 100
    pct = int(brightness * 100 / 255)
    return clamp_percentage(max(1, pct))


def pct_to_ha_brightness(pct: int) -> int:
    """Map FanSync 0-100 to Home Assistant brightness (0-255)."""
    return int(int(pct) * 255 / 100)


def coerce_status_int(value: object) -> int | None:
    """Return an int from an API status value, or None if it is not integral.

    Accepts bool (True -> 1), int, integral float, and numeric strings. Used by
    every register getter, so it must stay permissive.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except TypeError, ValueError:
            return None
    return None


def normalize_color_temp_kelvin(value: object) -> int | None:
    """Return a numeric Kelvin value from an API status value.

    Like coerce_status_int but a bool is never a Kelvin value.
    """
    if isinstance(value, bool):
        return None
    return coerce_status_int(value)


def _normalize_model(model: object) -> str:
    """Normalize a FanSync model identifier for prefix matching."""
    if not isinstance(model, str):
        return ""
    return "".join(char for char in model.casefold() if char.isalnum())


def resolve_light_color_temp_presets(
    model: object,
    status: Mapping[str, object],
) -> tuple[int, ...] | None:
    """Resolve the supported CCT presets for one device.

    H04 is present on devices that do not have a tunable light, so presence of
    the key is not sufficient. Known model profiles select their own preset
    list, but the current H04 value must still be one of those presets. The
    known Corke profile provides five presets (2700/3000/3500/4000/5000 K).
    Unknown models use the original three-preset behavior only when H04 is one
    of the known three-preset values; otherwise the light remains
    brightness-only.
    """
    current = normalize_color_temp_kelvin(status.get(KEY_LIGHT_COLOR_TEMP))
    if current is None:
        return None

    normalized_model = _normalize_model(model)
    for prefix, presets in LIGHT_COLOR_TEMP_MODEL_PRESETS.items():
        if normalized_model.startswith(prefix):
            return presets if current in presets else None

    return LIGHT_COLOR_TEMP_PRESETS_KELVIN if current in LIGHT_COLOR_TEMP_PRESETS_KELVIN else None


def snap_color_temp_kelvin(
    kelvin: int,
    presets: Iterable[int] = LIGHT_COLOR_TEMP_PRESETS_KELVIN,
) -> int:
    """Snap a requested kelvin value to the nearest device-supported preset."""
    supported = tuple(presets)
    if not supported:
        raise ValueError("at least one color-temperature preset is required")
    return min(supported, key=lambda preset: abs(preset - kelvin))


def resolve_lightless_devices(options: Mapping[str, object], device_ids: Iterable[str]) -> set[str]:
    """Return the device_ids whose light entity should be hidden.

    Reads the per-device ``OPTION_LIGHTLESS_DEVICES`` list. If that key is not
    set, migrates the legacy account-wide ``OPTION_DISABLE_LIGHT`` boolean
    (0.8.0): when it was enabled, every known device is treated as lightless,
    preserving the old behavior until the user re-picks per device.
    """
    explicit = options.get(OPTION_LIGHTLESS_DEVICES)
    if isinstance(explicit, list):
        return {str(d) for d in explicit if d}
    if options.get(OPTION_DISABLE_LIGHT):
        return {d for d in device_ids if d}
    return set()
