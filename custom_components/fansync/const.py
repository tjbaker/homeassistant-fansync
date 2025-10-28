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
# Increased from 8.0s to 12.0s to accommodate observed device/network latency;
# prevents premature UI snap-back for users with slower confirmation responses.
OPTIMISTIC_GUARD_SEC = 12.0
# Confirmation polling attempts and delay between polls
# Increased retry duration (20 × 0.25s = 5s) is intentional to accommodate
# occasional network/device latency and improve reliability of confirmation.
CONFIRM_RETRY_ATTEMPTS = 20
CONFIRM_RETRY_DELAY_SEC = 0.25

# Fallback polling interval (seconds) when push updates are missing
FALLBACK_POLL_SECONDS = 30


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
