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

"""Circuit breaker pattern for resilient network operations."""

from __future__ import annotations

import time
from enum import Enum


class CircuitState(Enum):
    """States of the circuit breaker."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Too many failures, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures.

    Opens after a threshold of failures within a time window,
    preventing further requests until a timeout period passes.
    Then enters half-open state to test recovery.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: float = 60.0,
        half_open_attempts: int = 1,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: Time to wait before trying again (half-open)
            half_open_attempts: Number of test requests in half-open state
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_attempts = half_open_attempts

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_success_count = 0

    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection.

        Args:
            func: Callable to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func if circuit allows

        Raises:
            CircuitBreakerOpenError: If circuit is open and timeout period hasn't passed
            Exception: Any exception from func (circuit records failure)
        """
        if self.state == CircuitState.OPEN:
            # Check if timeout period has passed
            if time.monotonic() - self.last_failure_time >= self.timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                self.half_open_success_count = 0
            else:
                # Circuit still open, reject request
                raise CircuitBreakerOpenError("Circuit breaker is OPEN, request rejected")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Record successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_success_count += 1
            if self.half_open_success_count >= self.half_open_attempts:
                # Recovered, close circuit
                self.state = CircuitState.CLOSED
                self.failure_count = 0
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def _on_failure(self) -> None:
        """Record failed call."""
        self.last_failure_time = time.monotonic()
        self.failure_count += 1

        if self.state == CircuitState.HALF_OPEN:
            # Failed during test, reopen circuit
            self.state = CircuitState.OPEN
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                # Too many failures, open circuit
                self.state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_success_count = 0


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and rejects a request."""

    ...
