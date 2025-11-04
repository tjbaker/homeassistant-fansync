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

