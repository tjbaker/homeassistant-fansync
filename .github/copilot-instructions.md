# GitHub Copilot Instructions (Home Assistant FanSync)

This repository contains a Home Assistant custom integration. Use these instructions to guide code suggestions, refactors, and tests.

## Style & Formatting
- Python 3.13. Line length 100.
- Use Black and Ruff exactly as configured in `pyproject.toml`.
- Prefer explicit, readable code and modern typing (e.g., `X | None`, not `Optional[X]`).
- Import ABCs like `Callable` from `collections.abc`, not `typing`.

## Imports
- Organize imports per Ruff isort settings.
- Group order: standard library, third-party, first-party (`fansync`, `custom_components`).

## Linting
- Respect Ruff rules: [E, F, I, B, UP].
- Use union syntax in `isinstance` checks, e.g., `int | str`.
- Avoid `assert False`; raise `AssertionError()` or structure tests with `pytest.raises`.

## Home Assistant specifics
- Use asynchronous patterns (`async_*`); avoid blocking I/O in the event loop.
- For blocking needs, use `hass.async_add_executor_job`.
- Prefer `CoordinatorEntity` for entities with push updates.
- Push-first pattern: the coordinator is push-driven (`update_interval=None`).
- Optimistic updates:
  - Apply per-key overlays immediately to prevent UI snap-back.
  - Confirm via short retry window; clear overlays on confirm; revert on explicit failures.
- Multi-device support:
  - `FanSyncClient` exposes `device_ids` and allows `device_id` in `async_get_status`/`async_set`.
  - The coordinator stores `dict[device_id, status]` and aggregates per device.
  - Platforms create one entity per `device_id`; `unique_id` uses `self._device_id` consistently.

## Testing
- Use `pytest`; do not make real network calls.
- Patch at module paths under `custom_components.fansync.client.*`.
- Focus coverage on `custom_components/fansync/`; CI target ≥ 75%.
- Provide tests for:
  - Optimistic updates (success and revert paths) and overlay behavior.
  - Client reconnect, ack short-circuit, no-push mode, bounded get timeouts.
  - Config flow: happy path, cannot_connect, duplicate unique_id.
  - Multi-device entity creation and isolation; light presence per device.

## Commits & PRs
- Use Conventional Commits for PR titles and squash-merge subjects.
  - Allowed types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
  - Examples: `feat: add optimistic light updates`, `fix: prevent UI snap-back`.
- Keep commit subject ≤ 72 characters; wrap body at ~72 chars.
- Release automation via `release-please` runs on merges to `main`.

## CI expectations
- Workflow runs Ruff, Black, mypy, and pytest with coverage.
- Codecov uploads on pushes to `main` (token required).

## Patterns to prefer
- Guarded optimistic updates with small retry windows.
- Early returns over deep nesting.
- Minimal, high-signal comments; explain non-obvious rationale.
- Robust casting of coordinator data values (e.g., `int | str` to `int`).

## Patterns to avoid
- Blocking I/O in the event loop.
- Broad `except Exception` without meaningful handling; avoid swallowing errors silently.
- Divergent `unique_id` or identifiers; always base on `self._device_id`.

## When suggesting changes
- Maintain HA async and entity lifecycles.
- Keep compatibility with tests; if adjusting client signatures, update fakes/mocks accordingly.
- Ensure new code passes Ruff/Black/mypy/pytest locally.
