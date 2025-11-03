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

## How to contribute

- Open an issue (with logs)
  - Use GitHub Issues to report bugs, propose features, or ask questions.
  - Include clear steps to reproduce, expected behavior, and a concise log slice.
  - During initial login (config flow), enable HTTP stack logging so auth errors/timeouts are visible.
    - Developer Tools → Services → `logger.set_level` → Data:
      ```yaml
      httpcore: debug           # HTTP auth/login
      httpx: debug              # HTTP client
      websockets: debug         # WebSocket connections (v0.3.0+)
      custom_components.fansync: debug  # Integration logic
      ```
    - Reproduce the problem, then restore defaults via `logger.set_default_level` (or restart).
    - Persistent alternative (advanced): add to `configuration.yaml` and restart:
      ```yaml
      logger:
        default: info
        logs:
          httpcore: debug       # HTTP auth/login
          httpx: debug          # HTTP client
          websockets: debug     # WebSocket connections (v0.3.0+)
          custom_components.fansync: debug  # Integration logic
      ```
    - Include:
      - HTTP POST to FanSync session endpoint and response/timeout lines (`httpcore`/`httpx`).
      - After setup: messages from `custom_components.fansync.*` (connect/login timings, reconnects, status updates).
    - Redact sensitive data (email, tokens, IPs) before sharing.
  - Home Assistant docs: https://www.home-assistant.io/docs/configuration/troubleshooting/#enabling-debug-logging

- Submit a pull request (PR)
  - Small, focused PRs are easier to review and merge.
  - Reference any related issue(s) in the PR description (e.g., "Fixes #123").
  - Follow Conventional Commits for PR titles (e.g., feat, fix, docs).

## Development

### Guidelines

- Coding style: Black + Ruff, Python 3.13, modern typing.
- Home Assistant specifics: async patterns, CoordinatorEntity, push-first updates.
- Tests: pytest with no real network calls; coverage enforced in CI.
- Single canonical AI instruction file: `.cursorrules` in repo root (pre-commit syncs it to other locations). Edit only `.cursorrules`.

### Setup

```bash
# Create and activate a virtualenv
python3.13 -m venv venv
source venv/bin/activate

# Install tools
pip install -U pip
pip install -r requirements-dev.txt

# Lint/format
ruff --fix .
black .
```

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

### Commit conventions

- Use Conventional Commits for PR titles and commit subjects: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
- Keep subject ≤ 72 characters.

### Testing and type checking

- See `tests/README.md` for test suite details and patterns.
- Common commands:

```bash
pytest -q --cov=custom_components/fansync
mypy custom_components/fansync --check-untyped-defs
ruff check
black --check .
```

 

## AI assistant guidance

- The canonical rules live in `.cursorrules`. A pre-commit hook syncs content to other locations.
- Edit only `.cursorrules`; do not hand-edit generated copies.

## License and attribution

- This project is licensed under the Apache License, Version 2.0. By contributing, you
  agree your contributions will be licensed under the same terms. See LICENSE for details.

## Getting help

- If you’re unsure how to implement something or where it belongs, open an issue first and we’ll
  discuss the approach together.

Thanks again for helping improve this integration!
