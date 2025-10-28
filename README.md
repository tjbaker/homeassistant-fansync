# FanSync Home Assistant Integration 

[![CI](https://github.com/tjbaker/homeassistant-fansync/actions/workflows/ci.yml/badge.svg)](https://github.com/tjbaker/homeassistant-fansync/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/tjbaker/homeassistant-fansync/branch/main/graph/badge.svg)](https://codecov.io/gh/tjbaker/homeassistant-fansync)

Custom Home Assistant integration for Fanimation FanSync devices.

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


## Development

- Optional pre-commit hooks (recommended):
```bash
pre-commit install
pre-commit install --hook-type commit-msg
```
- Manual checks:
```bash
ruff --fix .
black .
```
- Formatting and linting are configured via `pyproject.toml` (Black + Ruff)
- AI agent instructions: the canonical file is `.cursorrules` in the repo root. A pre-commit
  hook syncs this content into other well-known locations (e.g., `.github/copilot-instructions.md`).
  Only edit `.cursorrules`; the hook will propagate updates as needed.

### Pull requests and commit messages

- Conventional Commit-style PR titles are required for releases, e.g.:
  - `feat: add optimistic light updates`
  - `fix: prevent UI snap-back on interim refresh`
  - `docs: reorganize README`
  - `ci: run black via git ls-files in CI`
  The repo includes a PR template and a semantic PR title check that enforces this.

## Testing

Run tests with coverage:
```bash
pytest -q --cov=custom_components/fansync
```
CI enforces coverage on the integration code (threshold set in the workflow).

## License

Apache-2.0 (see `LICENSE`).

## Acknowledgments

- Reverse‑engineering notes and sample payloads that informed this work were
  originally published in rotinom/fansync:
  https://github.com/rotinom/fansync
  
  No files from that repository are included here; any remaining mistakes are ours.
