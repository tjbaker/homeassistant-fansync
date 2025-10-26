# Test Suite

This directory contains the pytest-based test suite for the FanSync custom component.

## Structure
- `conftest.py`: shared fixtures (e.g., mocked client and enabling custom integrations).
- `test_config_flow.py`: UI flow and entry creation.
- `test_config_flow_unique.py`: unique ID behavior (prevents duplicate entries).
- `test_client_ssl.py`: verifies HTTP client SSL verification behavior.
- `test_fan.py`: fan entity lifecycle and basic services.
- `test_fan_extra.py`: additional fan behaviors (direction, presets, bounds, turn_off).
- `test_light.py`: light lifecycle and brightness mapping.
- `test_light_bounds.py`: brightness edge cases.
- `test_coordinator_error.py`: coordinator error handling path.

## Running
From the project root:
```bash
pytest -q
```

## Guidelines
- Prefer fixtures in `conftest.py` to keep tests focused and fast.
- Avoid real network calls; patch client interactions via the provided fixtures.
- When adding new features, include tests that cover happy-path, edge cases, and error handling.
- Keep names descriptive and follow PEP 8.

## Attribution
Protocol samples and inspiration were informed by the upstream `rotinom/fansync` project.
See: https://github.com/rotinom/fansync
