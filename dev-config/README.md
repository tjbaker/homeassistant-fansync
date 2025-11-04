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

This configuration provides:
- **No authentication** for localhost (trusted network)
- **Fast startup** (minimal recorder, 1-day history)
- **Pre-configured** components (frontend, config, mobile_app, etc.)
- **Debug logging enabled** for FanSync, httpcore, httpx, and websockets

⚠️ **Security**: For local development ONLY. Never use in production!

## Files

- `configuration.yaml` - Main HA config with trusted network auth
- `automations.yaml`, `scripts.yaml`, `scenes.yaml` - Empty (HA requires these)

## Customization

**Disable debug logging:** Edit `configuration.yaml` and remove the `logs:` section, then `docker compose restart`

**Change location/timezone:** Edit the `homeassistant:` section in `configuration.yaml`

**Reset everything:** `docker compose down -v && docker compose up -d`

For detailed Docker workflow and troubleshooting, see **[CONTRIBUTING.md](../CONTRIBUTING.md)**.

