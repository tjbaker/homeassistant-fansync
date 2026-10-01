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

# Development Configuration

This directory contains a pre-configured Home Assistant setup for local Docker development.

**For complete setup and workflow, see [CONTRIBUTING.md](../CONTRIBUTING.md).**

## Quick Reference

Start with `make docker-up`, restart after code changes with `make docker-restart`, and follow the integration's log lines with `make docker-logs` (add `FILTER=websockets`, or any regex on the logger name, to follow something else). `make help` lists every target.

This configuration provides:
- **No authentication** for localhost (trusted network)
- **Fast startup** (minimal recorder, 1-day history)
- **Pre-configured** components (frontend, config, mobile_app, etc.)
- **Debug logging enabled** for FanSync (all modules); `httpx`/`websockets` debug is commented out in `configuration.yaml` and can be enabled for connection problems (note they print the session token)

⚠️ **Security**: For local development ONLY. Never use in production!

## Files

- `configuration.yaml` - Main HA config with trusted network auth
- `automations.yaml`, `scripts.yaml`, `scenes.yaml` - Empty (HA requires these)

## Customization

**Disable debug logging:** Edit `configuration.yaml` and remove the `logs:` section, then `make docker-restart`

**Change location/timezone:** Edit the `homeassistant:` section in `configuration.yaml`

## Known Warnings on HA 2026.9+

**"Confirm new HTTP server configuration"** dialog on first start of a new image: click **Confirm**. The listed values (trusted proxies, X-Forwarded-For, IP banning off) are exactly the `http:` block from `configuration.yaml`. Reverting would bring back the login prompt.

**"The HTTP YAML configuration is deprecated"** repair: click **Ignore**. HA 2026.9 moved `http:` settings to the UI and imported ours into the persistent `ha-config` volume. The YAML block is kept deliberately so `docker compose down -v` still gives a login-free instance; YAML import stops working in HA 2027.2, at which point the block must be removed and the same values set under Settings > System > Network.

**Reset everything:** `make docker-reset` (runs `docker compose down -v` then `up -d`; deletes the config volume)

## Troubleshooting

**http://localhost:8123 refuses the connection although the container is "healthy":** run `make docker-status`. If the PORTS column shows `8123/tcp` instead of `0.0.0.0:8123->8123/tcp`, Docker restarted the container without reattaching its network (the log then shows `OSError: [Errno 19] No such device` from zeroconf and "does not have any enabled IPv4 addresses"). Recreate it with `make docker-down && make docker-up`; the config volume is kept.

For detailed Docker workflow and troubleshooting, see **[CONTRIBUTING.md](../CONTRIBUTING.md)**.

