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

# Contributing to Home Assistant FanSync

Thanks for your interest in contributing! Community pull requests and issues are very welcome.

## Code of conduct

- Be respectful and constructive. Assume good intent. We aim for a welcoming and inclusive
  environment for all contributors.

## Getting Started

This guide covers everything you need to contribute: Docker development setup, workflow, code standards, and the PR process.

## How to Contribute

### Open an Issue (with logs)
  - Use GitHub Issues to report bugs, propose features, or ask questions.
  - Prefer attaching the integration diagnostics JSON (Settings → Devices & Services → FanSync → Download Diagnostics).
    It captures connection timing, push counters/last push timestamps, and device info without secrets.
  - Include clear steps to reproduce, expected behavior, and a concise log slice.
  - During initial login (config flow), enable HTTP stack logging so auth errors/timeouts are visible.
    - Developer Tools → Services → `logger.set_level` → Data:
      ```yaml
      custom_components.fansync: debug              # Integration (all modules)
      custom_components.fansync.client: debug       # WebSocket client, connection details
      custom_components.fansync.coordinator: debug  # Data updates, polling, push events
      httpcore: debug                               # HTTP auth/login
      httpx: debug                                  # HTTP client
      websockets: debug                             # WebSocket protocol details
      ```
    - Reproduce the problem, then restore defaults via `logger.set_default_level` (or restart).
    - Persistent alternative (advanced): add to `configuration.yaml` and restart:
      ```yaml
      logger:
        default: info
        logs:
          custom_components.fansync: debug              # Integration (all modules)
          custom_components.fansync.client: debug       # WebSocket client
          custom_components.fansync.coordinator: debug  # Data updates
          httpcore: debug                               # HTTP auth/login
          httpx: debug                                  # HTTP client
          websockets: debug                             # WebSocket protocol
      ```
    - Include:
      - HTTP POST to FanSync session endpoint and response/timeout lines (`httpcore`/`httpx`).
      - After setup: messages from `custom_components.fansync.*` (connect/login timings, reconnects, status updates).
    - Redact sensitive data (email, tokens, IPs) before sharing.
  - Home Assistant docs: https://www.home-assistant.io/docs/configuration/troubleshooting/#enabling-debug-logging

### Submit a Pull Request (PR)

See the **[Pull Request Workflow](#pull-request-workflow)** section below for the complete process.

Quick guidelines:
- Small, focused PRs are easier to review and merge
- Reference any related issue(s) in the PR description (e.g., "Fixes #123")
- Follow Conventional Commits for PR titles (e.g., `feat:`, `fix:`, `docs:`)
- Include tests for new functionality
- Ensure all quality checks pass

## Development Setup

### Quick Start: Docker (Recommended)

The **fastest way** to develop is using Docker Compose - get a local Home Assistant instance running in seconds with your code mounted live.

**Prerequisites:**
- Docker Desktop (Mac/Windows) or Docker + Docker Compose (Linux)
- Your FanSync account credentials (email/password)

**Setup:**

```bash
# Start Home Assistant with your code mounted
make docker-up
```

Every Docker step has a make target that wraps `docker compose`; run `make help` to list them. Use the raw `docker compose` commands if you prefer, or set `COMPOSE="docker-compose"` for the standalone binary.

**Access Home Assistant:**
- Open: http://localhost:8123
- **First time only**: Complete 30-second onboarding (create account, e.g., "dev"/"dev")
- **After onboarding**: No login required! (trusted network config)
- Add FanSync integration: Settings → Devices & Services → Add Integration → "FanSync"
  - **Note**: If you encounter SSL errors, uncheck "Verify SSL certificate" (some Docker environments have certificate trust issues)

**Development workflow:**

```bash
# 1. Edit your code
vim custom_components/fansync/fan.py

# 2. Restart to see changes (~5-10 seconds!)
make docker-restart

# 3. Test in browser at http://localhost:8123

# Follow the integration's log lines
make docker-logs

# Follow other loggers: FILTER is a case-insensitive regex on the logger name
make docker-logs FILTER=websockets
make docker-logs FILTER='fansync|httpx'

# Everything Home Assistant logs
make docker-logs-all

# Fresh start (deletes the config volume, onboarding required again)
make docker-reset
```

| Target | What it does |
|---|---|
| `make docker-up` | Start the container in the background |
| `make docker-restart` | Restart it to pick up code changes |
| `make docker-logs` | Follow records whose logger name matches `FILTER` (default `fansync`), tracebacks included; `FILTER='a\|b'` for other loggers |
| `make docker-logs-all` | Follow the whole log |
| `make docker-status` | Show container state and health |
| `make docker-shell` | Open a shell inside the container |
| `make docker-pull` | Pull the image pinned in `docker-compose.yml` (after a version bump) |
| `make docker-down` | Stop and remove the container, keeping its config volume |
| `make docker-reset` | Delete the config volume and start fresh |

**Debugging:**

Debug logging is **enabled by default** for `custom_components.fansync`, which covers every module (client, coordinator, fan, light, switch).

`httpx` and `websockets` debug logging is present but commented out in `dev-config/configuration.yaml`. Enable those two only for login or connection problems: they are very noisy, and `websockets` prints the login token and session cookie, so trim logs before posting them.

View logs with:
```bash
make docker-logs                              # the integration's loggers
make docker-logs FILTER='fansync|websockets'  # several loggers
make docker-logs FILTER=homeassistant.setup   # any other logger
make docker-logs-all                          # the whole Home Assistant log
```

How `FILTER` works:
- It is a case-insensitive regular expression matched against the **logger name** only, the bracketed field of each record such as `[custom_components.fansync.client]`. The default is `fansync`.
- Core lines that merely mention the word in their message are not shown. The loader's "custom integration fansync" warning and the entity registry's "Registered new fan.fansync entity" come from other loggers; use `make docker-logs-all` or a wider `FILTER` to see them.
- Lines that continue a matching record are kept, so a traceback from the integration prints in full.
- An empty value, `make docker-logs FILTER=`, shows everything.
- Do not pipe `docker compose logs` through `grep fansync` yourself: every line is prefixed with the container name `ha-fansync-dev`, so that matches everything.

To change logging, edit the `logs:` map in `dev-config/configuration.yaml`, then `make docker-restart`.

### Probing how a fan behaves

Fans do not agree about the same write. One model reports a bare power-off and another applies it silently; one refuses a speed while off and another starts on it. Before changing what the integration writes, or when reporting a device that misbehaves, measure it:

```bash
make probe                                  # fan matrix, about ten minutes
make probe ARGS='--lights'                  # light matrix (L1 to L7), about five minutes
make probe ARGS='--list'                    # show the cases without touching anything
make probe ARGS='--cases 1,5,L3 --out probe-report.md'  # selected cases, save the report
```

`scripts/probe_device.py` logs in the same way the integration does, puts the fan into a verified start state before every case, sends one raw payload, records each acknowledgement and push, reads the cloud's state back, and asks you what the fan is physically doing. It ends with a Markdown report to paste into an issue or PR, and restores the state it found. The report includes what the cloud says about the device (model, firmware, capability flags, every register) so nothing else has to be collected; the owner, device id, display name, MAC and IP are left out.

- It switches the fan on and off and changes speed and direction. Someone has to be in the room to answer its questions.
- The light cases run only with `--lights` (or by name, `--cases L6,L7`) and never touch the fan motor. They switch the light, check whether a brightness or color write turns it on, and sweep brightness and color temperature to find the values the fixture holds. On a fan with no light kit, answer `?` to the questions; the acknowledgements and reports are still recorded.
- Nothing else may control the fan while it runs. Stop the dev container (`make docker-down`) when the script asks, or disable the FanSync integration in your own Home Assistant, and leave the app and remote alone.
- It does not need Docker or Home Assistant. On any computer with git, make and Python 3.14: clone the repository, run `make venv install`, then `make probe`. The bug report template asks for a probe report in the same way.
- Credentials come from `FANSYNC_EMAIL` / `FANSYNC_PASSWORD`, else from the running dev container's config entry, else from a prompt. They are never printed.
- A case whose start state cannot be reached is skipped and marked, not run from a wrong state.

The measured results for each model are recorded under "Device Protocol Rules" in [`AGENTS.md`](AGENTS.md).

### Alternative: Virtual Environment

If you prefer not to use Docker:

```bash
# Create and activate a virtualenv
# Tip: .python-version sets the recommended Python version (3.14.x) for pyenv/mise/uv
python3.14 -m venv venv
source venv/bin/activate

# Install development tools
pip install -U pip
pip install -r requirements-dev.txt
```

Or use Make targets:

```bash
make venv
make install
make check
```

Then manually install Home Assistant Core in development mode (see Home Assistant Core documentation).

### Code Style Guidelines

- **Formatter**: Black (line length 100) + Ruff
- **Type checking**: mypy with strict settings  
- **Python version**: 3.14
- **Home Assistant**: 2026.6+
- **Typing**: Modern syntax (`X | None` instead of `Optional[X]`)
- **Async patterns**: Always use `async/await`, never block the event loop
- **HA patterns**: CoordinatorEntity, push-first updates, optimistic UI
- **Error handling**: Narrow exception catches, proper logging levels
- **Testing**: pytest, no real network calls, ≥75% coverage target
- **AI instructions**: Single canonical file: `AGENTS.md`

### Pre-commit

This repository uses pre-commit to enforce style and commit message conventions.

Hooks configured (see `.pre-commit-config.yaml`):
- ruff (with `--fix`) and ruff-format
- black (line length 100)
- commitizen check (runs at `commit-msg` stage; enforces Conventional Commits and ≤ 72-char subject)

Install and enable hooks:
```bash
pre-commit install
pre-commit install --hook-type commit-msg
```

Run hooks manually on all files:
```bash
pre-commit run --all-files
```

Update hook versions:
```bash
pre-commit autoupdate
```

### Commit Conventions

We use **Conventional Commits** for all PR titles and commit subjects:

**Format**: `<type>: <description>`

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style (formatting, no logic change)
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `test`: Add or update tests
- `build`: Build system changes
- `ci`: CI configuration changes
- `chore`: Maintenance tasks
- `revert`: Revert previous commit

**Rules**:
- Subject must be ≤ 72 characters
- Use imperative mood ("add feature" not "added feature")
- Include detailed body for non-trivial changes
- Reference issues in body (e.g., "Fixes #123")

**Examples**:
```bash
feat: add optimistic light updates
fix: prevent WebSocket reconnect loop
docs: update Docker development guide
test: add coverage for config flow errors
```

### Testing and Quality Checks

See **[tests/README.md](tests/README.md)** for comprehensive test patterns and suite details.

**Quick commands**:

```bash
# Run tests with coverage
python -m pytest -q --cov=custom_components/fansync

# Type checking
python -m mypy custom_components/fansync --check-untyped-defs

# Linting
python -m ruff check .

# Formatting check
python -m black --check --line-length 100 custom_components/ tests/

# Run all checks
make check
```

## Pull Request Workflow

Follow this process for contributing code changes:

### 1. Before You Start

- Check existing issues and PRs to avoid duplicates
- For significant changes, **open an issue first** to discuss the approach
- Review the **[Development Setup](#development-setup)** section above

### 2. Development

```bash
# Fork the repo and clone your fork
git clone https://github.com/YOUR_USERNAME/homeassistant-fansync.git
cd homeassistant-fansync

# Create a feature branch
git checkout -b feat/your-feature-name

# Set up Docker environment (see Development Setup section)
make docker-up

# Make your changes, test locally
make docker-restart  # After each change

# Add tests for new functionality
# See tests/README.md for test patterns
```

### 3. Before Submitting

Ensure all quality checks pass:

```bash
# Run full test suite with coverage
python -m pytest --cov=custom_components/fansync --cov-report=term-missing

# Check code style and types
python -m ruff check .
python -m black --check --line-length 100 custom_components/ tests/
python -m mypy custom_components/fansync --check-untyped-defs
```

### 4. Submit PR

```bash
# Commit with conventional commit format
git add .
git commit -m "feat: add new awesome feature"

# Push to your fork
git push origin feat/your-feature-name
```

Then open a PR on GitHub:
- Use a clear, descriptive title following **Conventional Commits** format
- Fill out the PR template completely
- Reference any related issues (e.g., "Fixes #123")
- Describe what changed and why
- Include screenshots/logs if relevant

### 5. Review Process

- Maintainers will review your PR and may request changes
- Address feedback by pushing new commits to your branch
- Once approved, your PR will be **squash merged** to main
- The PR title becomes the commit message, so make it clear!

### 6. After Merge

- Your changes will be included in the next release
- Releases are automated via **Release Please** based on commit types:
  - `feat:` → minor version bump (0.X.0)
  - `fix:` → patch version bump (0.0.X)
  - `feat!:` or `fix!:` → major version bump (X.0.0)
- Changelog is auto-generated from commit messages

## AI Assistant Guidance

- Agent instructions live in [`AGENTS.md`](AGENTS.md), the one file every tool reads. It covers commands, code style, commit conventions, architecture, and the device protocol rules.
- There are no tool-specific copies (`CLAUDE.md`, `.cursorrules`, Copilot instructions) and no sync hook. Claude Code, Copilot and VS Code read `AGENTS.md` directly; edit it when conventions change.

## License and attribution

- This project is licensed under the Apache License, Version 2.0. By contributing, you
  agree your contributions will be licensed under the same terms. See LICENSE for details.

## Getting help

- If you’re unsure how to implement something or where it belongs, open an issue first and we’ll
  discuss the approach together.

Thanks again for helping improve this integration!
