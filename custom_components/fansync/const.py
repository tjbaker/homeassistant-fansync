# SPDX-License-Identifier: GPL-2.0-only

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
OPTIMISTIC_GUARD_SEC = 12.0
# Confirmation polling attempts and delay between polls
CONFIRM_RETRY_ATTEMPTS = 20
CONFIRM_RETRY_DELAY_SEC = 0.25


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
