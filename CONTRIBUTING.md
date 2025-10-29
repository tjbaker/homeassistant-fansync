# Contributing to Home Assistant FanSync

Thanks for your interest in contributing! Community pull requests and issues are very welcome.

## Code of conduct

- Be respectful and constructive. Assume good intent. We aim for a welcoming and inclusive
  environment for all contributors.

## How to contribute

- Open an issue (with debug logging)
  - Use GitHub Issues to report bugs, propose features, or ask questions.
  - Include clear steps to reproduce, expected behavior, and a debug log snippet for this
    integration when reporting bugs.
  - Enable debug logging via the UI: Settings → Devices & Services → FanSync → three‑dot menu →
    Enable debug logging. Reproduce the issue, then Disable debug logging and download the log.
  - Review the log for sensitive data (e.g., email, IPs, tokens) and redact as appropriate before
    attaching to the issue.
  - Home Assistant docs on enabling debug logging:
    https://www.home-assistant.io/docs/configuration/troubleshooting/#enabling-debug-logging

- Submit a pull request (PR)
  - Small, focused PRs are easier to review and merge.
  - Reference any related issue(s) in the PR description (e.g., "Fixes #123").
  - Follow Conventional Commits for PR titles (e.g., feat, fix, docs).

## Development guidelines

- Please read the project README for setup, style, testing, and CI details.
  - Coding style: Black + Ruff, Python 3.13, modern typing.
  - Home Assistant specifics: async patterns, CoordinatorEntity, push-first updates.
  - Tests: pytest with no real network calls; coverage enforced in CI.
- A single canonical AI instruction file lives at `.cursorrules` in the repo root; a pre-commit
  sync copies it to other locations (e.g., GitHub Copilot instructions). Edit only `.cursorrules`.

## License and attribution

- This project is licensed under the Apache License, Version 2.0. By contributing, you
  agree your contributions will be licensed under the same terms. See LICENSE for details.

## Getting help

- If you’re unsure how to implement something or where it belongs, open an issue first and we’ll
  discuss the approach together.

Thanks again for helping improve this integration!
