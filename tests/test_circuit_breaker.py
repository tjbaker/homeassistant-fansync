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

"""Test circuit breaker pattern."""

import time

import pytest

from custom_components.fansync.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)


def test_circuit_breaker_allows_success():
    """Test circuit breaker allows successful calls."""
    breaker = CircuitBreaker(failure_threshold=3)
    result = breaker.call(lambda: "success")
    assert result == "success"
    assert breaker.state == CircuitState.CLOSED


def test_circuit_breaker_opens_after_threshold():
    """Test circuit breaker opens after failure threshold."""
    breaker = CircuitBreaker(failure_threshold=3)

    def raise_error():
        raise ValueError("Test error")

    # Trigger failures
    for _ in range(3):
        with pytest.raises(ValueError):
            breaker.call(raise_error)

    assert breaker.state == CircuitState.OPEN


def test_circuit_breaker_rejects_when_open():
    """Test circuit breaker rejects calls when open."""
    breaker = CircuitBreaker(failure_threshold=2)

    def raise_error():
        raise ValueError("Test error")

    # Open the circuit
    for _ in range(2):
        with pytest.raises(ValueError):
            breaker.call(raise_error)

    # Circuit is open, should reject
    with pytest.raises(CircuitBreakerOpenError):
        breaker.call(lambda: "should reject")


def test_circuit_breaker_enters_half_open():
    """Test circuit breaker enters half-open after timeout."""
    breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=0.1)

    def raise_error():
        raise ValueError("Test error")

    # Open the circuit
    for _ in range(2):
        with pytest.raises(ValueError):
            breaker.call(raise_error)

    assert breaker.state == CircuitState.OPEN

    # Wait for timeout
    time.sleep(0.15)

    # Next call should enter half-open
    result = breaker.call(lambda: "recovery")
    assert result == "recovery"
    assert breaker.state == CircuitState.CLOSED


def test_circuit_breaker_resets_on_success():
    """Test circuit breaker resets failure count on success."""
    breaker = CircuitBreaker(failure_threshold=3)

    def raise_error():
        raise ValueError("Test error")

    # One failure
    with pytest.raises(ValueError):
        breaker.call(raise_error)

    assert breaker.failure_count == 1

    # Success resets count
    breaker.call(lambda: "success")
    assert breaker.failure_count == 0
    assert breaker.state == CircuitState.CLOSED


def test_circuit_breaker_manual_reset():
    """Test manual reset of circuit breaker."""
    breaker = CircuitBreaker(failure_threshold=2)

    def raise_error():
        raise ValueError("Test error")

    # Open the circuit
    for _ in range(2):
        with pytest.raises(ValueError):
            breaker.call(raise_error)

    assert breaker.state == CircuitState.OPEN

    # Manual reset
    breaker.reset()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0

    # Should allow calls again
    result = breaker.call(lambda: "success")
    assert result == "success"
