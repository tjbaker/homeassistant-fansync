# AGENTS.md

Instructions for AI coding agents working in this repository. This is the only such file: there is no `CLAUDE.md`, `.cursorrules` or Copilot instructions file, and none should be added. Claude Code, Copilot code review, the Copilot cloud agent and CLI, and VS Code all read `AGENTS.md` directly.

## Project Overview

Custom Home Assistant integration for Fanimation FanSync smart fans and lights. It talks to Fanimation's cloud over a WebSocket, uses push updates as the primary mechanism, and falls back to polling.

- **Integration domain**: `fansync`
- **HA minimum version**: 2026.8.0, Python 3.14+ (enforced via `hacs.json`; latest-HA-only policy, no backward compatibility)
- **IoT class**: `cloud_push`
- **Platforms**: `fan`, `light`, `switch`

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
make help           # List every target
```

Run a single test file:

```bash
venv/bin/python -m pytest tests/test_client_recv_reconnect.py -v
```

A local Home Assistant for manual testing runs from `docker-compose.yml` with the integration code mounted:

```bash
make docker-up            # Start at http://localhost:8123
make docker-restart       # Pick up code changes
make docker-logs          # Follow the integration's loggers; FILTER='fansync|websockets' for other logger names
make docker-logs-all      # Follow the whole container log
make docker-status        # Container state and health
make docker-pull          # Pull the pinned image after a version bump
make docker-down          # Stop, keep the config volume
make docker-reset         # Delete the config volume and start fresh
```

Measure how a real fan responds to raw writes (interactive, needs the hardware and someone watching it):

```bash
make probe                      # fan matrix, about ten minutes
make probe ARGS='--lights'      # light matrix: power, brightness, color temperature
make probe ARGS='--list'        # show the cases, no network
make probe ARGS='--cases 1,5,L3 --out probe-report.md'
```

Keep `requirements-dev.txt`, the `docker-compose.yml` image and `hacs.json` on compatible Home Assistant versions. Reinstall the venv (`make install`) after the pinned Home Assistant changes, or local results will differ from CI.

## Code Style

- **Black**: line length 100, target-version py314. **Ruff**: rules `[E, F, I, B, UP]`, known-first-party `custom_components`. **mypy**: `check_untyped_defs = true`. These tools are authoritative; run `make check` rather than reasoning about style.
- **Typing**: every function parameter and return value is annotated, including test functions (`-> None`) and nested helpers. Use `X | None`, not `Optional[X]`. Import ABCs (`Callable`, `Iterable`, `Mapping`) from `collections.abc`.
- **Imports**: standard library, third-party, first-party, as Ruff's isort orders them.
- **License headers**: every Python and YAML file starts with the repository's SPDX + Apache-2.0 header block, copied from an existing file. JSON has none.
- **Comments**: only for non-obvious context, trade-offs, or Home Assistant requirements. Justify every `# type: ignore`.
- **Constants**: magic numbers and strings live in `const.py`.
- **Structure**: small single-purpose functions, early returns, at most three or four levels of nesting. Extract duplicated logic into a helper.
- Use `...` rather than `pass` for empty bodies, a bare `raise` to re-raise, and direct callable references instead of trivial lambdas.
- **Editing and searching**: prefer your dedicated file read, search and edit tools over shell `grep`/`sed`/`cat`/`awk`. It avoids permission prompts from glob and pipe expansion, gives cleaner reviewable diffs, and sidesteps shell-quoting bugs.

## Commits and Pull Requests

- **Conventional Commits**, subject at most 72 characters (commitizen enforces it at `commit-msg`). Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
- **release-please reads the types**: `fix:` is a patch bump and a changelog entry, `feat:` a minor bump. `build:`, `chore:`, `docs:`, `test:`, `ci:` produce no release and no changelog entry.
- **PRs are squash-merged.** The PR title becomes the commit subject and the changelog line, so it must be a correct Conventional Commit. A workflow checks it.
- **Mixed PRs**: when a code fix travels with a dependency or tooling change, use two commits, `fix:` first and `build:` second, so the fix reaches the changelog.
- **Commit bodies** explain why and what changed, wrapped at about 72 characters. Pass multi-line messages with a here-doc (`git commit -F - <<'EOF'`), never several `-m` flags.
- **Attribution trailers**: if your tool adds a `Co-Authored-By` line, use at most one per PR, on the final commit only. Squash merging concatenates every commit message, so a trailer on each commit is repeated in the merged commit.
- **After pushing, watch CI and fix failures** until it is green. PRs from forks need their workflow runs approved before CI starts.
- `hassfest` runs from Home Assistant's master image, so its rules change without notice. A new failure there may have nothing to do with the diff.

## Architecture

### Component Roles

| File | Responsibility |
|---|---|
| `__init__.py` | Entry point: creates client and coordinator, registers the push callback, manages the config entry lifecycle, options listener, stale-device removal |
| `client.py` | Async WebSocket client: HTTP login (httpx), WebSocket (websockets), token refresh, reauthentication, connection metrics |
| `coordinator.py` | `DataUpdateCoordinator`: push-first with fallback polling, multi-device data, device registry updates, device-reported baseline and observed values |
| `entity.py` | `FanSyncOptimisticEntity`: shared optimistic overlay, confirmation and guard-expiry logic for fan and light |
| `fan.py` / `light.py` | Entities: state mapping and the write payload for each command |
| `switch.py` | Per-fan "Light installed" configuration switch and "Home Away" mode switch |
| `config_flow.py` | User, reauth and options flows |
| `const.py` | Protocol keys, timing constants, preset tables, small pure helpers |
| `device_utils.py` | `DeviceInfo` builder, profile and cloud-metadata helpers |
| `metrics.py` | Connection quality tracking |
| `diagnostics.py` / `diagnostics_utils.py` | Diagnostics platform: redacted connection and device info, status snapshots |

### Data Flow

```
ConfigEntry → __init__.py → FanSyncClient (WebSocket)
                                    ↓ push callback (merged into cached status)
                            FanSyncCoordinator.async_set_updated_data()
                                    ↓
                        FanSyncFan / FanSyncLight / switch entities
                                    ↓ user commands
                            client.async_set({register: value, ...})
```

### Key Patterns

- **`runtime_data`**: `ConfigEntry.runtime_data` (a `TypedDict`) holds the client, coordinator and loaded platforms. Never use `hass.data`.
  ```python
  type FanSyncConfigEntry = ConfigEntry[FanSyncRuntimeData]
  ```
- **Push-first coordinator**: pushes may carry only the changed keys and are merged into the cached per-device status. Polling is the fallback (default 60 s, 15 to 600 s, 0 disables).
- **Multi-device data shape**: coordinator data is `dict[device_id, dict[str, object]]`. One entity per device; unique ids are built from the device id.
- **Optimistic updates**: a command applies per-key overlays immediately and arms a 3-second guard (`OPTIMISTIC_GUARD_SEC`). Two confirmation polls follow. The write is confirmed when `_write_applied` holds: every written register echoes its target, or any of them moved off the value the device last reported. A confirming push is honored even if it lands after the last poll. If the guard lapses unconfirmed, a timer restores the device-reported baseline and publishes it. State reverts early only on an explicit failure.
- **Acknowledged power writes are kept**: a `set` is answered twice with the same id, by the cloud and then by the device. `client.last_device_ack()` holds the device's answer. When a write of only power registers (`H00`, `H0B`) lapses unconfirmed and the device answered `ok`, `coordinator.assume_applied()` takes the written value as the device's state, and cloud reads that still return the old value are corrected until the device reports that register or it is written again. If the answer has not arrived when the guard lapses, the entity waits `DEVICE_ACK_GRACE_SEC` once. Speed, brightness and color are never assumed: an unreported write of those usually means the device kept its value. Writing the value already assumed keeps the assumption (`clear_assumed_for_write`); dropping it there made a second "off" show the fan on. Assumptions are saved per config entry (`assumed_store`, `.storage/fansync.assumed.<entry_id>`) and restored at setup, where each survives only while the cloud still returns the stale value it was recorded against. A change made elsewhere during downtime that the cloud reports as that same value cannot be detected.
- **Device-reported baseline**: `coordinator.last_reported_status()` holds what the device itself reported (polls, pushes, confirmation reads). `coordinator.data` also contains optimistic values, so never use it to judge whether a write changed anything.
- **Capabilities resolve one way**: color-temperature support and similar capabilities are upgraded when evidence arrives and never downgraded on a single off-profile reading.
- **Options apply in place**: changing which fans have no light broadcasts a dispatcher signal; the light platform adds or removes entities without reloading the entry.
- **Async only**: 100% `async/await`, no threads. The receiver runs as a background task (`_recv_task`). Cancel tasks and clean up in `finally` blocks.
- **Config entry exceptions**: `ConfigEntryNotReady` for transient failures (HA retries), `ConfigEntryAuthFailed` for 401/403 (starts reauth), `RuntimeError` for connection failures.

## Device Protocol Rules

Read this before changing anything an entity writes. These rules were learned from live hardware and one of them from a regression.

**Registers**: `H00` power, `H01` preset (0 normal, 1 fresh air), `H02` speed (1 to 100), `H06` direction (0 forward, 1 reverse), `H0B` light power, `H0C` light brightness (1 to 100), `H04` light color temperature in Kelvin, `H0D` the app's Home Away mode. `H05` and `H0E` are undecoded.

**Home Away (`H0D`)**, measured on the Kute60 only: turning it on stops the fan (`H0D` 1 and `H00` 0 arrive in one report), turning it off leaves the fan stopped, and a power-on write clears it. The fan reports every one of those. The switch writes `{"H0D": x}` alone and is created only for devices whose status contains the register. What the mode does to a real light is not known.

**The cloud**: a `set` is acknowledged twice, first by the cloud and then by the device. A `get` returns what the device last reported, not what was last written. State changes arrive as `device_change` pushes.

**Devices disagree.** The same payload does different things on different fans. The Kute60 column was measured with `make probe` on 2026-10-01, every row from a start state confirmed by eye. The Spitfire column comes from the logs in issue #249 and has not been probed.

| Payload | Kute60-FD6R1L5, fw 3.2.9 | SpitfireV2-FD6R2L5, fw 3.6.7 |
|---|---|---|
| `{"H00": 0}` | applied, never reported (3 of 3) | applied and reported |
| `{"H00": 1}` | applied, never reported (3 of 3) | not measured |
| `{"H00": 0, "H02": n}` | applied and reported; the fan's own ack is `error` | off, then back on |
| `{"H00": 1, "H02": n}` | applied and reported | applied and reported |
| `{"H02": n}` while off | stays off and reports power 0; ack `error` (3 of 3) | starts the fan |
| `{"H00": 1, "H02": 100, "H01": 0}` | applied, never reported (3 of 3) | not measured |
| `{"H00": 1, "H02": 99, "H01": 0}` | applied and reported, as 80 | not measured |
| `{"H06": x}` alone | applied and reported | not measured |
| `{"H01": x}` alone | reported | not measured |
| Speed | holds 20/35/50/65/80/100; a request rounds down, and anything below 20 gives 20 | continuous |

On the Kute60 it is **power changes** that go unreported, unless the same write carries a speed. Speed, direction and preset writes are reported on their own. The three-register write of exactly 100 is a separate, repeatable exception. An earlier version of this file said the Kute60 "only reports after a write that contains `H02`"; that was inferred from logs and the probe disproved it.

**Rules that follow:**

1. **Write only the registers that need to change** (`_needs_write`), judged against the device-reported baseline. Never bundle a register "to be safe".
2. **Power off is always `{"H00": 0}` alone.** Adding a speed to it broke turn-off on the Spitfire in 0.9.0 (issue #249). `_with_current_speed` refuses to touch a power-off payload. A Kute60 never reports that write, so 0.10.0 showed a stopped fan as on; the answer was to keep the acknowledged value (see "Acknowledged power writes are kept"), not to send more.
3. **A write that powers the fan on carries the current speed** (`_with_current_speed`), because a Kute60 does not report a power change otherwise. Direction and preset writes currently carry it too. The probe shows a Kute60 reports those on their own, so that is not required; it is harmless on a running fan, and removing it would be a strict reduction.
4. **Do not generalize from one device.** A payload change must be verified on more than one model, or be a strict reduction in what is sent. Prefer sending less. `scripts/probe_device.py` (`make probe`) runs a fixed matrix of payloads against a fan from verified start states and prints a table of acknowledgements, pushes and what the fan physically did. `make probe ARGS='--lights'` does the same for the light registers, which have not been measured on any device with a light kit yet. Ask owners of other models to run it and paste the table before trusting a claim about "how the fans behave", and update the table above from its output rather than from logs.
5. **Never add a write that could start or stop a fan as a side effect** of improving state reporting. A stale display is a smaller failure than a fan that turns itself back on.
6. **Do not add per-model tables for behavior.** The integration confirms on the value the device settles on instead of predicting it. Small verified tables exist only where the protocol offers no other signal (light color-temperature presets).

**Capability hints** in the cloud's per-device metadata are trusted only when explicitly `true`: `hideLightDimmer` (no light kit) and `hideFanDirection` (not reversible). Absence proves nothing.

## Home Assistant Specifics

- Entities use `_attr_has_entity_name = True` and `_attr_translation_key`, never a hardcoded name. Add the key to every file in `translations/`.
- Device registry lookups are scoped to the config entry: `async_get_device_by_identifier((DOMAIN, device_id), entry_id)`. Update connections with the full set via `new_connections`. Remove devices with `async_remove_device`. The unscoped and merge variants are deprecated and fail under test.
- Do not list a requirement in `manifest.json` that Home Assistant core already ships (for example `httpx`); hassfest rejects it.
- Never block the event loop. Use `await asyncio.sleep()`, never `time.sleep()`, and `hass.async_add_executor_job` only for genuinely synchronous code.
- Diagnostics must redact credentials and tokens. Never log or expose a password, token or session cookie.

## Logging and Error Handling

- **Levels**: DEBUG for diagnostics (state changes, timings, reconnects), INFO for significant events, WARNING for recoverable problems, ERROR for failures the user must act on.
- Guard non-trivial debug logging with `if _LOGGER.isEnabledFor(logging.DEBUG):` and include context such as the device id and the keys involved.
- Catch specific exception types. A broad `except Exception` is acceptable only around optional, defensive lookups, with a comment saying why.
- Use the builtin `TimeoutError`, not `asyncio.TimeoutError`. Black formats multiple exceptions without parentheses (PEP 758): `except TypeError, ValueError:`.
- Keep `try` blocks minimal: wrap the call that can fail and process its result outside the block.

## Testing

- Tests live in `tests/` and use pytest. No real network calls. Coverage for `custom_components/fansync` must stay at or above 75% (`--cov-fail-under=75` in CI).
- **Patch at the import path used by the module under test**, not where the object is defined (`custom_components.fansync.FanSyncClient`, `custom_components.fansync.client.websockets.connect` with `new_callable=AsyncMock`).
- Test through integration setup with a `MockConfigEntry`. Do not instantiate entities directly, and read `entry.runtime_data`, never `hass.data`.
- Find entities and devices through the registries by unique id or identifier, not by guessing entity ids.
- Mock clients need an awaitable `async_disconnect`; tests must not leave background tasks running.
- **A regression test must fail without the fix.** Verify that once, especially for timing-sensitive tests, which can pass vacuously.
- When a change affects what is written to a device, assert the exact payload, and cover both a device that applies writes verbatim and one that does not (quantizes a value, or starts on a speed write).
- Verify behavior changes against the real container (`make docker-up`) when hardware is available. Dry runs and mocks have missed real defects here.

## Reviewing Bot Feedback on a PR

Automated reviewers (Copilot and similar) comment on PRs. Treat each comment as a suggestion to evaluate, not an instruction.

1. Fix failing CI first; that is not debatable.
2. For each bot comment, read the code at that location and decide whether the suggestion is correct and worth doing. Reject suggestions that introduce a bug, break typing, contradict the project's patterns, or are bike-shedding.
3. Apply only what you accepted, run `make check`, and report what was accepted, what was rejected with a one-sentence technical reason for each, and what CI failures were fixed.
4. Leave human review comments for the maintainer unless asked.

## Before Committing

- [ ] `make check` passes: tests, coverage, Ruff, Black, mypy
- [ ] New behavior has tests, and regression tests fail without the fix
- [ ] Type hints on every parameter and return value; no unused imports
- [ ] License header on new Python and YAML files
- [ ] User-facing changes are reflected in `README.md`, and developer-facing ones in `CONTRIBUTING.md` and this file
- [ ] Commit subject is a Conventional Commit of at most 72 characters; the PR title is too
