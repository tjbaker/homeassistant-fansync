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

"""Unit tests for diagnostics_utils.summarize_status_snapshot."""

from custom_components.fansync.diagnostics_utils import summarize_status_snapshot


def test_raw_includes_undecoded_protocol_keys() -> None:
    """Undecoded registers (e.g. H04/H05/H0D/H0E) keep their values in `raw`.

    Issue #189: diagnostics listed key names only, so user-supplied before/after
    snapshots could not show which key carried color temperature.
    """
    data = {
        "dev1": {
            "H00": 1,
            "H02": 41,
            "H04": 3500,
            "H05": 0,
            "H0B": 1,
            "H0C": 100,
            "H0D": 0,
            "H0E": 7,
        }
    }
    summary = summarize_status_snapshot(data)
    assert summary["dev1"]["raw"] == data["dev1"]
    # Decoded summaries are unchanged
    assert summary["dev1"]["fan"] == {"power": 1, "speed": 41, "preset": None, "direction": None}
    assert summary["dev1"]["light"] == {"power": 1, "brightness": 100}


def test_raw_excludes_non_protocol_keys() -> None:
    """Only H-register keys are copied verbatim; anything else stays out of `raw`."""
    data = {"dev1": {"H00": 1, "token": "secret", "Hxx": 5, "H123": 9}}
    summary = summarize_status_snapshot(data)
    assert summary["dev1"]["raw"] == {"H00": 1}
    # Non-protocol keys still appear in the key listing for discoverability
    assert summary["dev1"]["keys"] == ["H00", "H123", "Hxx", "token"]


def test_summarize_handles_malformed_input() -> None:
    """Non-mapping payloads and device entries are skipped, not raised."""
    assert summarize_status_snapshot(None) == {}
    assert summarize_status_snapshot("bogus") == {}
    assert summarize_status_snapshot({"dev1": "bogus"}) == {}
