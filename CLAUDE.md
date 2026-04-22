# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Custom Home Assistant integration for Fanimation FanSync smart fans and lights. Uses WebSocket-based cloud push updates as the primary update mechanism with configurable fallback polling.

- **Integration domain**: `fansync`
- **HA minimum version**: 2026.3.0, Python 3.14+
- **IoT class**: `cloud_push`

## Commands

```bash
make venv           # Create virtualenv with Python 3.14
make install        # Install dev requirements
make test           # Run all tests
make coverage       # Run tests with coverage report (75%+ target)
make lint           # Run Ruff linter
make format-check   # Check Black formatting
make type-check     # Run mypy
make check          # Run all checks (coverage + lint + format + type)
```

Run a single test file:
```bash
pytest tests/test_client_recv_reconnect.py -v
```

A local Home Assistant instance for manual testing is available via `docker-compose.yml` with the integration code mounted.

## Code Style

- **Black**: line length 100, target-version py314
- **Ruff**: rules `[E, F, I, B, UP]`, known-first-party `custom_components`
- **mypy**: strict mode with `check_untyped_defs = true`
- **Commits**: Conventional Commits format, max 72 chars subject line (enforced by pre-commit/commitizen)
  - `fix:` → patch bump, appears in changelog; `feat:` → minor bump; `build:`/`chore:`/`docs:`/`test:`/`ci:` → no bump, not in changelog
  - When a PR mixes a code fix with a dep/tooling upgrade, use two commits (`fix:` first, then `build:`) so the fix lands in the changelog
- All code must be fully type-annotated

## Architecture

### Component Roles

| File | Responsibility |
|---|---|
| `__init__.py` | Entry point: creates client + coordinator, registers push callback, manages config entry lifecycle |
| `client.py` | Async WebSocket client — HTTP login (httpx), WebSocket (websockets), token refresh, reauthentication, connection metrics |
| `coordinator.py` | `DataUpdateCoordinator` — push-first with fallback polling, multi-device data management, device registry updates |
| `fan.py` / `light.py` | `CoordinatorEntity` — optimistic updates with confirmation, entity state mapping |
| `config_flow.py` | User + options flows for email/password/timeouts/polling interval |
| `const.py` | Protocol keys (H00=power, H01=preset, H02=speed, H06=direction, H0B/H0C=light), timing constants |
| `metrics.py` | Connection quality tracking — latency, failure/timeout rates |
| `diagnostics.py` | HA diagnostics platform — redacted connection/device info |
| `device_utils.py` | `DeviceInfo` builder, `confirm_after_initial_delay()` for optimistic update confirmation |

### Data Flow

```
ConfigEntry → __init__.py → FanSyncClient (WebSocket)
                                    ↓ push callback
                            FanSyncCoordinator.async_set_updated_data()
                                    ↓
                        FanSyncFan / FanSyncLight entities (CoordinatorEntity)
                                    ↓ user commands
                            client.set_speed() / turn_on() / etc.
```

### Key Patterns

**Modern HA runtime_data pattern** — uses `ConfigEntry.runtime_data` (TypedDict) instead of `hass.data`:
```python
type FanSyncConfigEntry = ConfigEntry[FanSyncRuntimeData]
```

**Push-first coordinator** — WebSocket push updates call `coordinator.async_set_updated_data()` directly; polling is the fallback (default 60s, configurable 15–600s).

**Optimistic updates** — entities apply state changes immediately on user command, hold a 3-second guard window to prevent UI snap-back, then confirm via push or polling retry. State reverts only on explicit failure.

**Multi-device data shape** — coordinator data is `dict[device_id, dict[str, object]]`; each entity filters by its own device_id.

**Async-only** — 100% `async/await`, no threading. The WebSocket receiver runs as a background task (`_recv_task`). Always clean up tasks in `finally` blocks.

**Exception hierarchy for config entries**:
- `ConfigEntryNotReady` → transient failure, HA will retry setup
- `ConfigEntryAuthFailed` → 401/403, triggers reauthentication flow
- `RuntimeError` → connection failure

### Testing

Tests live in `tests/` (59 files). Mock at the import path used in the module under test, not the definition path. Coverage target is ≥75% for `custom_components/fansync`.
