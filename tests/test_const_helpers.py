# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from custom_components.fansync.const import (
    clamp_percentage,
    ha_brightness_to_pct,
    pct_to_ha_brightness,
)


def test_clamp_percentage_bounds():
    # FanSync minimum is 1%
    assert clamp_percentage(-5) == 1
    assert clamp_percentage(0) == 1
    assert clamp_percentage(100) == 100
    assert clamp_percentage(150) == 100


def test_brightness_pct_roundtrip_edges():
    # 0 brightness maps to minimum 1% for FanSync
    assert ha_brightness_to_pct(0) == 1
    assert ha_brightness_to_pct(255) == 100
    assert pct_to_ha_brightness(0) == 0
    assert pct_to_ha_brightness(100) == 255
