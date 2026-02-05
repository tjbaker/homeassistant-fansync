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

DOMAIN = "fansync"
PLATFORMS = ["fan", "light"]
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

# Preset modes mapping
PRESET_MODES = {0: "normal", 1: "fresh_air"}


# Optimistic update timing (shared by entities)
# Guard window to prevent UI snap-back while awaiting confirmation
# Push updates (device_change events) are reliable and typically arrive within 1-2 seconds.
# Early termination logic stops polling once push confirms, so this is mainly a safety net.
OPTIMISTIC_GUARD_SEC = 3.0
# Confirmation polling attempts and delay between polls
# Push updates typically confirm changes within 1-2 seconds, terminating polling early.
# These fallback polls (3 × 0.25s = 0.75s) handle edge cases where push is delayed.
CONFIRM_RETRY_ATTEMPTS = 3
CONFIRM_RETRY_DELAY_SEC = 0.25

# Options: fallback polling
OPTION_FALLBACK_POLL_SECS = "fallback_poll_seconds"
DEFAULT_FALLBACK_POLL_SECS = 60
MIN_FALLBACK_POLL_SECS = 15
MAX_FALLBACK_POLL_SECS = 600
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

# WebSocket receive loop retry settings
WS_RECV_TIMEOUT_ERROR_THRESHOLD = 3  # Consecutive errors before reconnect
WS_RECV_BACKOFF_INITIAL_SEC = 0.5  # Initial backoff delay
WS_RECV_BACKOFF_MAX_SEC = 5.0  # Maximum backoff delay
WS_RECV_SLEEP_SEC = 0.1  # Sleep between recv attempts
WS_RECV_LOCK_TIMEOUT_SEC = 0.5  # Timeout for recv_lock acquisition in background loop

# Push update logging (tune higher for quieter logs)
PUSH_LOG_EVERY = 50

# WebSocket request IDs for connection bootstrap (keep stable for compatibility)
# GET_STATUS and SET now use dynamic allocation via _next_request_id
WS_REQUEST_ID_LOGIN = 1
WS_REQUEST_ID_LIST_DEVICES = 2

# WebSocket bounded read settings
WS_GET_RETRY_LIMIT = 5  # Max recv attempts to find get response

# WebSocket fallback timeout (used when _ws_timeout_s is None)
WS_FALLBACK_TIMEOUT_SEC = 10.0

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
