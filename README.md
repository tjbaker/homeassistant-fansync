# FanSync Home Assistant Integration

[![CI](https://github.com/tjbaker/homeassistant-fansync/actions/workflows/ci.yml/badge.svg)](https://github.com/tjbaker/homeassistant-fansync/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/tjbaker/homeassistant-fansync/branch/main/graph/badge.svg)](https://codecov.io/gh/tjbaker/homeassistant-fansync)

Custom Home Assistant integration for Fanimation FanSync devices. Includes a small Python client and runnable examples.

## Requirements

- Python 3.13
- Home Assistant Core (recent stable)

## Installation

### HACS (recommended)

<a href="http://homeassistant.local:8123/hacs/repository?owner=tjbaker&repository=homeassistant-fansync">
  <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.">
  </a>

### Manual

1) Copy `custom_components/fansync/` into your Home Assistant `config/custom_components/` directory.
2) Restart Home Assistant.
3) Add the integration: Settings → Devices & Services → Add integration → “FanSync”.

## Features

- Fan: on/off, percentage speed, direction, preset modes (normal, fresh_air)
- Light: on/off, brightness (0–100 mapped to 0–255)

## Configuration

| Option      | Description                                                  | Default |
|-------------|--------------------------------------------------------------|---------|
| Email       | FanSync account email                                        | –       |
| Password    | FanSync account password                                     | –       |
| Verify SSL  | Verify HTTPS certificates when connecting to FanSync cloud   | True    |

## Notes & limitations

- Multi-device support currently targets the first device returned. Future versions will create one HA device per FanSync device.

## Examples

Setup and run an example (never commit real credentials):
```bash
python -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements-dev.txt

cp examples/credentials.example.py credentials.py  # edit EMAIL/PASSWORD locally

# Run connection test (ensure local credentials.py is importable)
PYTHONPATH=$(pwd) python examples/test_connection.py
```

## Repository structure

- `custom_components/fansync/`: HA integration (config flow, coordinator, fan/light entities)
- `fansync/`: Low-level client (HTTP/WebSocket)
- `examples/`: Small runnable scripts
- `tests/`: Pytest suite for the integration

## Development

- Formatting and linting: configured via `pyproject.toml` (Black + Ruff)
- Optional pre-commit hooks:
```bash
pre-commit install
```
- Manual checks:
```bash
ruff --fix .
black .
```

## Testing

Run tests with coverage:
```bash
pytest -q --cov=custom_components/fansync
```
CI enforces coverage on the integration code (threshold set in the workflow).

## Security

- Keep secrets in local `credentials.py` (ignored by git). If accidentally committed, remove and rotate credentials:
```bash
git rm --cached credentials.py
git commit -m "Stop tracking credentials.py"
```

## Attribution

Portions of the reverse-engineered protocol and sample payloads were informed by `rotinom/fansync`: https://github.com/rotinom/fansync

## License

GPL-2.0-only (see `LICENSE`). A `NOTICE` file includes attribution.
