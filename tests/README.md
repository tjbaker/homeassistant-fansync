<!--
SPDX-License-Identifier: Apache-2.0
Copyright (c) 2025 Trevor Baker, all rights reserved.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
  http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

## FanSync Test Suite

This directory contains the tests for the FanSync custom integration. The suite focuses on setup UX, error handling, optimistic updates, reconnect paths, and detailed debug logging.

For development setup, style, and commit conventions, see `CONTRIBUTING.md`.

### Quick start

```bash
# Create a virtualenv (first time)
python3.13 -m venv venv

# Activate the repo's virtualenv (macOS/Linux)
source venv/bin/activate

# Upgrade pip and install dev requirements
pip install -U pip
pip install -r requirements-dev.txt

# Run all tests
pytest -q

# Run with coverage (coverage target ≥ 75% for custom_components/fansync)
pytest --cov=custom_components/fansync --cov-report=term-missing

# Type check
mypy custom_components/fansync --check-untyped-defs

# Lint and format checks
ruff check
black --check --line-length 100 --include '\.py$' custom_components/ tests/
```

### Guidelines

- **No real network calls**: Patch HTTP/WebSocket at the integration module paths.
  - Patch `httpx`/client calls at: `custom_components.fansync.client.*`
  - Patch async WebSocket calls at: `custom_components.fansync.client.websockets.connect`
- **Home Assistant helpers**: Use HA test helpers for flows and entries.
  - Config flow: `hass.config_entries.flow.async_init(...)`
  - Avoid directly instantiating flow classes in tests.
- **Cleanup background work**: Ensure background async tasks are stopped.
  - Always call `await client.async_disconnect()` in tests that create a client.
  - This cancels the `_recv_task` (async WebSocket receiver) and closes connections.
- **Debug logging**: Prefer `caplog` to assert log content and levels.
  - Example:
    ```python
    import logging

    caplog.set_level(logging.DEBUG, logger="custom_components.fansync")
    ```
- **Coverage focus**: Emphasize paths in `custom_components/fansync`.
  - Include tests for: push callback merge, reconnect paths, config flow
    (happy/error/duplicate), optimistic overlay expiry, multi-device isolation,
    and debug logging of significant events.
- **Type safety**: Keep `--check-untyped-defs` clean for the integration package.
- **Ruff/Black**: Keep the codebase clean and consistently formatted.

### Useful fixtures and patterns

- `ensure_fansync_importable` (fixture): Ensures the custom component is importable
  in test environments without leaking global sys.path or sys.modules mutations.
  Use it in tests that exercise config flows.

- `caplog`: Assert structured debug logging without depending on exact timings.

- `AsyncMock`/`MagicMock`: Use `AsyncMock` for async operations:
  - Mock `websockets.connect` with `new_callable=AsyncMock`
  - Mock WebSocket `send()`, `recv()`, and `close()` as `AsyncMock`
  - Use `AsyncMock` for client methods like `async_connect` and `async_disconnect`
  - Always `await` async mocks to avoid "coroutine was never awaited" warnings

### Logging assertions

Prefer verifying that key diagnostic messages are present instead of asserting
exact timings or sleep durations. For example, assert that reconnect attempts,
backoff steps, token refresh, and overlay expiry messages appear at
`logging.DEBUG` when applicable.

### Adding new tests

When adding functionality:
- Provide tests that demonstrate behavior and error handling.
- Include debug logging assertions where logs provide diagnostic value.
- Ensure background async tasks are cleaned up (call `await client.async_disconnect()`).
- Mock async WebSocket operations with `AsyncMock` (see "Useful fixtures" above).
- Keep commits Conventional (e.g., `test: add coverage for options flow`).

### Troubleshooting

- If a config flow test cannot import the custom component in isolation, use the
  `ensure_fansync_importable` fixture. In full-suite runs, Home Assistant's test
  harness typically provides the necessary environment automatically.


