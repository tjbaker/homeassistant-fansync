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
