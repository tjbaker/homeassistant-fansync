# FanSync Home Assistant Integration 

A Home Assistant custom integration for controlling Fanimation FanSync devices, plus a small Python client and runnable examples.

This project includes:
- `custom_components/fansync/`: Home Assistant integration (fan + light platforms).
- `fansync/`: Low-level client library and websocket helpers.
- `examples/`: Runnable scripts demonstrating login, listing devices, and sending commands.

- `tests/`: Pytest suite for the custom component.

## Quick start

1) Create a Python virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate
pip install -U pip
```

2) Install dev/test dependencies:
```bash
pip install -r requirements-dev.txt
```

3) (Optional) Enable pre-commit hooks:
```bash
pre-commit install
```

4) Run the tests:
```bash
pytest -q
```

## Home Assistant integration

- Copy or link `custom_components/fansync/` into your Home Assistant `config/custom_components/` directory.
- Restart Home Assistant, then add the integration via Settings → Devices & services → Add integration → “FanSync”.
- During setup, provide your FanSync account email and password. You can choose whether to verify SSL (default: on).

### One-click install via HACS

<a href="http://homeassistant.local:8123/hacs/repository?owner=tjbaker&repository=homeassistant-fansync">
  <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.">
</a>

### Configuration options

| Option | Description | Default |
|-------|-------------|---------|
| Email | FanSync account email | – |
| Password | FanSync account password | – |
| Verify SSL | Verify HTTPS certificates when connecting to FanSync cloud | True |

### Features

- Fan: on/off, percentage speed, direction, preset modes (normal, fresh_air)
- Light: on/off, brightness (0–100 mapped to 0–255)

### Notes & limitations

- Multi-device support is limited to the first device returned today. Future versions will create one HA device per FanSync device.

## Examples

- Duplicate the template and add your credentials locally (never commit real secrets):
```bash
cp examples/credentials.example.py credentials.py
# Edit credentials.py and set EMAIL and PASSWORD
```
- Run an example (set PYTHONPATH so the local credentials.py is found instead of Python's stdlib module):
```bash
PYTHONPATH=$(pwd) venv/bin/python examples/test_connection.py
```

Notes:
- `credentials.py` is ignored by git. Do not commit real credentials. Rotate credentials if accidentally exposed.
- See `examples/README.md` for more scripts and tips.

## Project layout

- `custom_components/fansync/`: HA entities, config flow, coordinator, and manifest.
- `fansync/`: Core modules for HTTP and websocket interactions.
- `examples/`: Small scripts that use `fansync` to connect and control devices.
- `tests/`: Pytest-based tests; see `tests/README.md` for suite overview.

## Development

- Linting/formatting is configured via `pyproject.toml` (Ruff + Black).
- Pre-commit hooks can enforce formatting automatically:
```bash
pre-commit install
```
- Run formatters/lint manually:
```bash
ruff --fix .
black .
```

## Security

- Secrets are kept in `credentials.py` (local only). The template `examples/credentials.example.py` is tracked for reference.
- Ensure `credentials.py` is never committed. If it was previously tracked:
```bash
git rm --cached credentials.py
git commit -m "Stop tracking credentials.py"
```
- Rotate any credentials that may have been exposed.

## Attribution

Portions of the original reverse-engineered protocol understanding and sample payloads were informed by the upstream project `rotinom/fansync`. See: https://github.com/rotinom/fansync

## License

GPL-2.0-only (see `LICENSE`). A `NOTICE` file includes attribution.
