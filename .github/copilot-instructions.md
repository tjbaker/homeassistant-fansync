# AI Code Style Rules for this repository

# Style & Formatting
- Use Black/Ruff exactly as configured in pyproject.toml (line length 100, Python 3.13).
- Follow PEP 8 principles; Black/Ruff are authoritative for enforcement.
- Optimize for clarity and readability; prefer explicit types where helpful.
- Prefer union syntax in isinstance checks (e.g., int | str) over tuples.

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
- Only suport HA 2025.10 and newer, no need for backward compatibility to older versions
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
- Use pytest; do not make real network calls. Patch httpx/websocket at module paths (custom_components.fansync.client.*).
- Coverage focus in CI is custom_components/fansync; target ≥ 75%.
- Include tests for: push callback merge, reconnect paths, config flow (happy/error/duplicate),
  optimistic overlay expiry, and multi-device entity isolation.
- Test debug logging with caplog to verify messages format correctly.
- Ensure tests clean up background threads/tasks (call async_disconnect on FanSyncClient).
- Use Home Assistant's config flow test helpers (hass.config_entries.flow.async_init) instead of
  directly instantiating flow classes.

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

# Performance
- Guard expensive debug operations with `if _LOGGER.isEnabledFor(logging.DEBUG):`.
- Avoid redundant string formatting or data structure operations in hot paths.
- Use dict.get() with defaults instead of key checks when appropriate.
- Prefer list comprehensions over loops for simple transformations (readability permitting).
- Cache expensive computations when safe to do so.

# Quality Checklist (before committing)
- [ ] All tests pass (pytest)
- [ ] Code coverage ≥ 75% (pytest --cov)
- [ ] No type errors (mypy custom_components/fansync --check-untyped-defs)
- [ ] No linting errors (ruff check)
- [ ] Code formatted (black --check)
- [ ] Commit message follows Conventional Commits and ≤ 72 char subject
- [ ] Non-trivial changes have detailed commit body
- [ ] New functionality has corresponding tests
- [ ] Debug logging tested with caplog
- [ ] Required headers present in Python/YAML files (SPDX + Apache-2.0)
