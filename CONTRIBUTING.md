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
docker compose up -d
```

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
docker compose restart

# 3. Test in browser at http://localhost:8123

# View logs
docker compose logs -f

# Filter for FanSync
docker compose logs -f | grep -i fansync

# Fresh start (removes all data)
docker compose down -v
docker compose up -d
```

**Debugging:**

Debug logging is **enabled by default** for:
- `custom_components.fansync` (all modules: client, coordinator, fan, light)
- `httpcore` (HTTP connections)
- `httpx` (HTTP requests)
- `websockets` (WebSocket protocol)

View logs with:
```bash
docker compose logs -f
# Or filter for FanSync:
docker compose logs -f | grep -i "fansync\|httpcore\|httpx\|websockets"
```

To disable debug logging, edit `dev-config/configuration.yaml` and remove the `logs:` section, then `docker compose restart`.
If you removed the default logging, re-enable it by adding those loggers back to the `logs:` map.

### Alternative: Virtual Environment

If you prefer not to use Docker:

```bash
# Create and activate a virtualenv
# Tip: .python-version sets the recommended Python version (3.13.x) for pyenv/mise/uv
python3.13 -m venv venv
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
- **Python version**: 3.13
- **Home Assistant**: 2026.2+
- **Typing**: Modern syntax (`X | None` instead of `Optional[X]`)
- **Async patterns**: Always use `async/await`, never block the event loop
- **HA patterns**: CoordinatorEntity, push-first updates, optimistic UI
- **Error handling**: Narrow exception catches, proper logging levels
- **Testing**: pytest, no real network calls, ≥75% coverage target
- **AI instructions**: Single canonical file: `.cursorrules` (pre-commit syncs to other locations)

### Pre-commit

This repository uses pre-commit to enforce style and commit message conventions.

Hooks configured (see `.pre-commit-config.yaml`):
- ruff (with `--fix`) and ruff-format
- black (line length 100)
- sync ai instructions (keeps `.github/copilot-instructions.md` in sync with `.cursorrules`)
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
python -m black --check --line-length 100 --include '\.py$' custom_components/ tests/

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
docker compose up -d

# Make your changes, test locally
docker compose restart  # After each change

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
python -m black --check --line-length 100 --include '\.py$' custom_components/ tests/
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

- The canonical rules live in `.cursorrules`. A pre-commit hook syncs content to other locations.
- Edit only `.cursorrules`; do not hand-edit generated copies.

## License and attribution

- This project is licensed under the Apache License, Version 2.0. By contributing, you
  agree your contributions will be licensed under the same terms. See LICENSE for details.

## Getting help

- If you’re unsure how to implement something or where it belongs, open an issue first and we’ll
  discuss the approach together.

Thanks again for helping improve this integration!
