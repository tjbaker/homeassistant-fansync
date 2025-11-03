# AI Code Style Rules for this repository

NOTE: The canonical source for these instructions is .cursorrules in the repo root.
Any changes should be made there; this file syncs automatically via pre-commit hook.

# Style & Formatting
- Use Black/Ruff exactly as configured in pyproject.toml (line length 100, Python 3.13).
- Follow PEP 8 principles; Black/Ruff are authoritative for enforcement.
- Optimize for clarity and readability; prefer explicit types where helpful.
- Prefer union syntax in isinstance checks (e.g., int | str) over tuples.
- Type Annotations:
  - Always add type hints to function/method parameters and return types
  - Use modern Python 3.10+ syntax: `X | None` instead of `Optional[X]`
  - In tests, annotate fixtures: `hass: HomeAssistant`, `caplog: pytest.LogCaptureFixture`
  - Add return types even for simple functions: `-> None`, `-> str`, `-> dict[str, Any]`

# Imports
- Organize imports consistent with Ruff isort settings.
  - known-first-party: ["custom_components"]
  - Do not force single-line imports.
  - Group order: standard library, third-party, first-party.
- Import ABCs (Callable, Iterable, etc.) from collections.abc, not typing.
- Use X | None instead of Optional[X] (modern Python 3.10+ syntax).

# Linting
- Enable Ruff rules: [E, F, I, B, UP] as configured in pyproject.toml.
- Respect per-file ignores from pyproject:
  - tests/**/*.py: [E501, F401, I001]

# License Headers
- All Python and YAML files MUST include the repository-standard license header at the top:
  - SPDX identifier and full Apache-2.0 header block used in this repo.
  - Python: hash-prefixed lines (e.g., `# SPDX-License-Identifier: Apache-2.0`, followed by the Apache block lines).
  - YAML: hash-prefixed lines at the top of the file.
  - Markdown: use an HTML comment block with the same content (recommended for docs like tests/README.md).
- Markdown files must use the lowercase `.md` extension (e.g., `README.md`).
- JSON does not support comments; do not attempt to add headers there.
- Tests are code; apply headers to test files (Python) as well.
- When creating or editing files, ensure the header is present and matches the canonical format already used in the repo.

# Comments
- Keep comments concise and only when adding non-obvious context.
- Explain complex logic, non-obvious patterns, or HA-specific requirements.
- Document type: ignore comments with justification for why they're needed.

# Home Assistant Specifics
- Only support HA 2025.10 and newer, no need for backward compatibility to older versions
- Use HA async patterns (`async_*` methods); avoid blocking I/O in the event loop.
  - Use hass.async_add_executor_job for any blocking operations.
- Prefer CoordinatorEntity for entities with push updates.
  - For push-based entities, set update_interval=None and push via coordinator.async_set_updated_data.
  - Use optimistic updates for user commands and reconcile on push ack to avoid UI snap-back.
- Multi-device model: coordinator data is dict[device_id, dict[str, int | str]], one entity per
  device; entity unique_id must use self._device_id consistently.
- Optimistic overlays: apply per-key overlays immediately; guard ~8s; confirm then clear;
  revert only on explicit failure.

# Testing
- Always add new tests, ensure they pass, and requisite code coverage is met when adding new functionality.
- Use pytest; do not make real network calls. Patch httpx and async websockets at module paths:
  - HTTP: Patch `httpx.Client` at `custom_components.fansync.client.*`
  - WebSocket: Patch `websockets.connect` at `custom_components.fansync.client.websockets.connect` with `new_callable=AsyncMock`
- Coverage focus in CI is custom_components/fansync; target ≥ 75%.
- Include tests for: push callback merge, reconnect paths, config flow (happy/error/duplicate),
  optimistic overlay expiry, and multi-device entity isolation.
- Test debug logging with caplog to verify messages format correctly.
- Ensure tests clean up background async tasks (call async_disconnect on FanSyncClient).
  - This cancels the `_recv_task` (async WebSocket receiver) and closes connections.
- Use Home Assistant's config flow test helpers (hass.config_entries.flow.async_init) instead of
  directly instantiating flow classes.
- Type annotations in tests:
  - Always annotate test function parameters: `hass: HomeAssistant`, `caplog: pytest.LogCaptureFixture`
  - Always add return type `-> None` to async test functions
  - Import HomeAssistant from homeassistant.core
  - Import pytest for LogCaptureFixture type hint

# Git / Commits
- Commit message subject MUST be ≤ 72 characters (to avoid GitHub truncation).
- Use Conventional Commits for PR titles and squash-merge subjects (required):
  - Allowed types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
  - Scope is optional; subject in imperative mood
  - Examples: "feat: add optimistic light updates", "fix: prevent UI snap-back"
- Commit message body:
  - Include detailed summary of changes for non-trivial commits
  - Structure multi-part changes with section headings (e.g., "Client:", "Testing:")
  - Explain the "why" and "what", not just the "how"
  - Mention coverage changes, test additions, breaking changes
  - Wrap body lines at ~72 characters
  - For multi-line bodies, prefer a here-doc to stdin with `-F -`, or a file
    with `-F <file>`. Do NOT rely on multiple `-m` flags; ensure a blank line
    between subject and body to preserve formatting. Example:
    ```bash
    git commit --amend -F - <<'EOF'
    feat: add optimistic updates

    - Apply overlay immediately and guard for 8s
    - Reconcile on push ack; revert only on explicit failure
    EOF
    ```
- PR titles must be semantic; a workflow enforces this.

# Debug Logging
- Use DEBUG level for diagnostic information (state changes, timings, reconnects)
- Use INFO for significant events (connection established, device discovered)
- Use WARNING for recoverable errors (retries, fallbacks)
- Use ERROR for failures requiring user attention
- Always guard debug logs with `if _LOGGER.isEnabledFor(logging.DEBUG):` for expensive operations
- Include relevant context: device_id, keys affected, timing info, error types
- Test debug logging paths to ensure messages format correctly

# Error Handling
- Narrow exception catches to specific types (e.g., ValueError, TypeError instead of Exception)
- Use builtin `TimeoutError` (not `asyncio.TimeoutError`) per Python 3.11+ and Ruff UP041
  - `asyncio.TimeoutError` is an alias to builtin `TimeoutError` in Python 3.11+
  - Always use `except TimeoutError:` to catch timeouts from `asyncio.wait_for()`
- Log exceptions with type and message at appropriate level before re-raising or returning error state
- Use RuntimeError for integration-specific errors (connection failures, invalid state)
- In config flow, catch and map exceptions to user-friendly error keys
- Ensure cleanup (async_disconnect) happens in finally blocks or error paths
- For retries, use exponential backoff and log retry attempts at DEBUG level

# Code Organization
- Extract duplicated logic into helper functions/methods.
- Keep functions focused and single-purpose.
- Use descriptive variable names that explain intent.
- Prefer early returns to reduce nesting.
- Group related functionality together (e.g., all optimistic update logic near each other).
- Use constants for magic numbers and strings (define in const.py).
- Avoid deep nesting (max 3-4 levels); extract nested logic into helper functions.

# Observability & Diagnostics
- Track connection metrics (latency, failures, reconnects) for troubleshooting.
- Implement diagnostics platform (async_get_config_entry_diagnostics) for HA integrations.
- Provide actionable recommendations in diagnostics (e.g., "increase timeout").
- Use dataclasses for structured metrics and state tracking.
- Log key metrics at DEBUG level with context (device_id, latency_ms, error types).

# Modern Python Patterns
- Use ellipsis (...) instead of pass for empty exception classes and placeholders.
- Avoid unnecessary lambda wrappers; pass callables directly when possible.
- Remove unused imports (caught by Ruff F401).
- Use appropriate format specifiers: %.0f for floats, %d for ints.
- Prefer direct callable references over lambda: x when lambda just wraps a function.
- Walrus operator (:=) is acceptable but prefer simpler code if formatters conflict.
- Use bare `raise` instead of `raise exc` when re-raising exceptions to preserve tracebacks.
- Extract magic numbers and hardcoded strings to named constants in const.py.

# Performance
- Guard expensive debug operations with `if _LOGGER.isEnabledFor(logging.DEBUG):`.
- Avoid redundant string formatting or data structure operations in hot paths.
- Use dict.get() with defaults instead of key checks when appropriate.
- Prefer list comprehensions over loops for simple transformations (readability permitting).
- Cache expensive computations when safe to do so.

# Async Patterns & Concurrency
- The client uses 100% async/await patterns with no threading
  - Uses `asyncio.Task` for background operations (`_recv_task` for WebSocket receiver)
  - All WebSocket operations use native async: `websockets.connect()`, `ws.send()`, `ws.recv()`
  - All timeouts use `asyncio.wait_for()` with built-in `TimeoutError`
- Never block the Home Assistant event loop
  - All I/O operations must be async (await websockets, httpx async client)
  - Use `hass.async_add_executor_job` only if calling truly synchronous/blocking third-party code
  - Avoid `time.sleep()` - use `await asyncio.sleep()` instead
- Background async task management
  - Store tasks as `self._recv_task: asyncio.Task | None = None`
  - Create tasks with `asyncio.create_task()` or `hass.async_create_task()`
  - Cancel tasks with `task.cancel()` and optionally `await task` to collect CancelledError
  - Always set task references to None after cancellation
- Async exception handling
  - Use built-in `TimeoutError` for `asyncio.wait_for()` timeouts (not `asyncio.TimeoutError`)
  - Catch `OSError` for network errors (replaces old `WebSocketConnectionClosedException`)
  - Use `asyncio.CancelledError` for handling cancelled tasks
  - Always clean up resources (close connections, cancel tasks) in finally blocks
- Async context managers
  - Use `async with` for resources that support it (e.g., `async with websockets.connect() as ws`)
  - Ensure proper cleanup even if exceptions occur
- Testing async code
  - Mock async functions with `AsyncMock` from `unittest.mock`
  - Mock `websockets.connect` with `patch(..., new_callable=AsyncMock)`
  - Mock WebSocket methods (`send`, `recv`, `close`) as `AsyncMock` objects
  - Use `asyncio.sleep(0.1)` in tests to allow background tasks to process messages
  - Always await async mocks to avoid "coroutine was never awaited" warnings

# Running Quality Checks in Cursor Sandbox
When running quality checks in the Cursor sandbox environment, use these exact commands:

**Tests**:
```bash
python -m pytest tests/ -v --tb=short
```

**Coverage** (87% target, minimum 75%):
```bash
python -m pytest tests/ --cov=custom_components/fansync --cov-report=term-missing
```

**Ruff** (linting):
```bash
python -m ruff check .
```

**Black** (formatting) - CRITICAL FOR CURSOR SANDBOX:
```bash
# CORRECT - Black will see all 65 Python files:
python -m black --check --line-length 100 --include '\.py$' custom_components/ tests/

# WRONG - Black will report "No Python files" in sandbox:
# black --check .
# black --check custom_components/ tests/

# The --include pattern is required for Black to work in the Cursor sandbox
```

**Mypy** (type checking):
```bash
python -m mypy custom_components/fansync --check-untyped-defs
```

**Comprehensive check** (run all at once):
```bash
python -m pytest tests/ -q --tb=no && \
python -m ruff check . && \
python -m black --check --line-length 100 --include '\.py$' custom_components/ tests/ && \
python -m mypy custom_components/fansync --check-untyped-defs
```

# Quality Checklist (before committing)
**IMPORTANT**: Run through this checklist before every commit to catch issues early
and reduce review cycles. Items below capture common issues found in code reviews.

## Code Quality
- [ ] All function parameters have type hints (including nested helper functions in tests)
- [ ] All functions have return type annotations (-> None, -> str, -> dict[str, Any])
- [ ] No unused imports (every import is actually used in the file)
- [ ] Public API used consistently (not private attributes like _device_profile)
- [ ] hasattr() checks used for optional methods (not try/except AttributeError)
- [ ] Tuples used for any() when appropriate (not lists)
- [ ] Magic numbers extracted to named constants in const.py
- [ ] Comments explain non-obvious trade-offs and design decisions

## Testing
- [ ] All tests pass (pytest)
- [ ] Code coverage ≥ 75% (pytest --cov)
- [ ] New functionality has corresponding tests
- [ ] Debug logging tested with caplog
- [ ] Test helper functions have type annotations

## Linting & Formatting
- [ ] No type errors (mypy custom_components/fansync --check-untyped-defs)
- [ ] No linting errors (ruff check)
- [ ] Code formatted (black --check --line-length 100 --include '\.py$' custom_components/ tests/)
  - IMPORTANT: Black in Cursor sandbox requires explicit --include pattern and directories
  - Do NOT run "black --check ." or "black --check" without paths - it will report no files
  - Always use: black --check --line-length 100 --include '\.py$' custom_components/ tests/
  - Or check specific files: black --check --line-length 100 file1.py file2.py
- [ ] Required headers present in Python/YAML files (SPDX + Apache-2.0)

## Git & Documentation
- [ ] Commit message follows Conventional Commits and ≤ 72 char subject
- [ ] Non-trivial changes have detailed commit body
- [ ] Docstrings added for complex logic or trade-offs
