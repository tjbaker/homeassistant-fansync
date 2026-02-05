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

import logging
from typing import cast

import pytest

from custom_components.fansync.device_utils import confirm_after_initial_delay


def test_confirm_after_initial_delay_not_confirmed() -> None:
    """Skip predicate when push confirmation is absent."""

    def predicate(_: dict) -> bool:
        raise AssertionError("predicate should not be called")

    status, confirmed, ok = confirm_after_initial_delay(
        confirmed_by_push=False,
        coordinator_data={"abc": {"k": 1}},
        device_id="abc",
        predicate=predicate,
        logger=logging.getLogger("test.confirm"),
    )

    assert status == {}
    assert confirmed is False
    assert ok is False


def test_confirm_after_initial_delay_predicate_false() -> None:
    """Reset confirmation flag when predicate fails."""

    def predicate(_: dict) -> bool:
        return False

    status, confirmed, ok = confirm_after_initial_delay(
        confirmed_by_push=True,
        coordinator_data={"abc": {"k": 1}},
        device_id="abc",
        predicate=predicate,
        logger=logging.getLogger("test.confirm"),
    )

    assert status == {"k": 1}
    assert confirmed is False
    assert ok is False


def test_confirm_after_initial_delay_predicate_true_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Return confirmed state and emit debug log when predicate passes."""

    def predicate(_: dict) -> bool:
        return True

    logger = logging.getLogger("test.confirm")
    caplog.set_level(logging.DEBUG, logger=logger.name)

    status, confirmed, ok = confirm_after_initial_delay(
        confirmed_by_push=True,
        coordinator_data={"abc": {"k": 1}},
        device_id="abc",
        predicate=predicate,
        logger=logger,
    )

    assert status == {"k": 1}
    assert confirmed is True
    assert ok is True
    assert "optimism early confirm d=abc via push update" in caplog.text


def test_confirm_after_initial_delay_bad_data() -> None:
    """Handle non-dict coordinator data safely."""

    def predicate(_: dict) -> bool:
        return False

    coordinator_data = cast(dict[str, dict[str, object]] | None, "bad-data")
    status, confirmed, ok = confirm_after_initial_delay(
        confirmed_by_push=True,
        coordinator_data=coordinator_data,
        device_id="abc",
        predicate=predicate,
        logger=logging.getLogger("test.confirm"),
    )

    assert status == {}
    assert confirmed is False
    assert ok is False
