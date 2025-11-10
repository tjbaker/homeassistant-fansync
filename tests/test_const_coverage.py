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

"""Test const helper functions for coverage."""

from custom_components.fansync.const import ha_brightness_to_pct


def test_ha_brightness_to_pct_none() -> None:
    """Test ha_brightness_to_pct with None input (line 104)."""
    # When brightness is None, should default to 100%
    assert ha_brightness_to_pct(None) == 100


def test_ha_brightness_to_pct_zero() -> None:
    """Test ha_brightness_to_pct with zero input."""
    # Zero should map to minimum 1%
    assert ha_brightness_to_pct(0) == 1


def test_ha_brightness_to_pct_max() -> None:
    """Test ha_brightness_to_pct with max input."""
    # 255 should map to 100%
    assert ha_brightness_to_pct(255) == 100


def test_ha_brightness_to_pct_mid() -> None:
    """Test ha_brightness_to_pct with mid-range values."""
    # 128 (50% of 255) should map to ~50%
    result = ha_brightness_to_pct(128)
    assert 45 <= result <= 55  # Allow some rounding variance
