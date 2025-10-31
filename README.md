# FanSync Home Assistant Integration 

[![CI](https://github.com/tjbaker/homeassistant-fansync/actions/workflows/ci.yml/badge.svg)](https://github.com/tjbaker/homeassistant-fansync/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/tjbaker/homeassistant-fansync/branch/main/graph/badge.svg)](https://codecov.io/gh/tjbaker/homeassistant-fansync)

Custom Home Assistant integration for Fanimation FanSync devices.

## Requirements

- Python 3.13
- Home Assistant Core 2025.10.0 or newer
- HACS (optional; only required if installing via HACS)

## Features

- Fan: on/off, percentage speed, direction, preset modes (normal, fresh_air)
- Light: on/off, brightness (0–100 mapped to 0–255)

## Installation

### HACS

Note: This integration is not in the HACS default registry. Add it as a custom repository:

1) In Home Assistant, go to HACS → Integrations.
2) Click the three-dots menu (⋮) → Custom repositories.
3) In Repository, enter: `https://github.com/tjbaker/homeassistant-fansync`
4) In Category, choose: `Integration` → Add.
5) Back in HACS → Integrations, click Explore & Download Repositories.
6) Search for "FanSync" → Download.
7) Restart Home Assistant.
8) Add the integration: Settings → Devices & Services → Add integration → “FanSync”.

See also: [HACS: Custom repositories](https://hacs.xyz/docs/use/custom_repositories/)

### Manual

1) Copy `custom_components/fansync/` into your Home Assistant `config/custom_components/` directory.
2) Restart Home Assistant.
3) Add the integration: Settings → Devices & Services → Add integration → “FanSync”.

## Configuration

| Option      | Description                                                  | Default |
|-------------|--------------------------------------------------------------|---------|
| Email       | FanSync account email                                        | –       |
| Password    | FanSync account password                                     | –       |
| Verify SSL  | Verify HTTPS certificates when connecting to FanSync cloud   | True    |
| HTTP timeout (s) | HTTP connect/read timeout used during login/token refresh     | 10      |
| WebSocket timeout (s) | WebSocket connect/recv timeout for realtime channel         | 15      |


### Options

Push-first updates are used by default. A low-frequency fallback poll can be configured:

| Option                 | Description                                                       | Default |
|------------------------|-------------------------------------------------------------------|---------|
| fallback_poll_seconds  | Poll interval in seconds when push is unavailable (0 disables).  | 60      |
| http_timeout_seconds   | HTTP connect/read timeout (seconds)                               | 10      |
| ws_timeout_seconds     | WebSocket connect/recv timeout (seconds)                          | 15      |

Set via: Settings → Devices & Services → FanSync → Configure → Options.
- Poll interval allowed range: 15–600 seconds (0 disables)
- Timeout ranges: 5–60 seconds (HTTP and WebSocket)

## Troubleshooting

### Login issues

If setup fails, capture diagnostics so we can help:
- Enable temporary debug logging via `logger.set_level` and reproduce the issue.
- Include HTTP stack (`httpcore`, `httpx`) and `custom_components.fansync` lines.
- Afterwards, restore defaults or restart.

Full instructions (including persistent logging) are in `CONTRIBUTING.md` under “How to contribute → Open an issue (with logs)”.
Reference: Home Assistant docs: https://www.home-assistant.io/docs/configuration/troubleshooting/#enabling-debug-logging

## Contributing

See `CONTRIBUTING.md` for development setup, lint/format, commit conventions, and PR guidance. For detailed test suite info and commands, see `tests/README.md`.

 

## License

Apache-2.0 (see `LICENSE`).

## Acknowledgments

- Reverse‑engineering notes and sample payloads that informed this work were
  originally published in rotinom/fansync:
  https://github.com/rotinom/fansync
