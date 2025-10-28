# Contributing to Home Assistant FanSync

Thanks for your interest in contributing! Community pull requests and issues are very welcome.

## How to contribute

- Open an issue
  - Use GitHub Issues to report bugs, propose features, or ask questions.
  - Include clear steps to reproduce, logs if relevant, and expected behavior.

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
  agree your contributions will be licensed under the same terms. See LICENSE and NOTICE
  for details.

## Code of conduct

- Be respectful and constructive. Assume good intent. We aim for a welcoming and inclusive
  environment for all contributors.

## Getting help

- If you’re unsure how to implement something or where it belongs, open an issue first and we’ll
  discuss the approach together.

Thanks again for helping improve this integration!
