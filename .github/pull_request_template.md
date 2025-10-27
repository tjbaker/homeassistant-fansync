Title (Conventional Commit)

- Use a semantic title so release automation can parse it. Examples:
  - feat: add optimistic light updates
  - fix: prevent UI snap-back on interim refresh
  - docs: reorganize README
  - ci: run black via git ls-files in CI

Summary

- What does this change do? Why is it needed?

Checklist

- [ ] Title follows Conventional Commits (type: scope optional: subject)
- [ ] Tests added/updated where appropriate
- [ ] No real network calls in tests (use provided patches/mocks)
- [ ] Formatting/linting pass locally (ruff, black)
- [ ] For HA services: no blocking I/O in event loop

Notes (optional)

- Any migration or user-facing notes?


