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

# FanSync Home Assistant Integration

[![CI](https://github.com/tjbaker/homeassistant-fansync/actions/workflows/ci.yml/badge.svg)](https://github.com/tjbaker/homeassistant-fansync/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/tjbaker/homeassistant-fansync/branch/main/graph/badge.svg)](https://codecov.io/gh/tjbaker/homeassistant-fansync)
[![HACS](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/github/license/tjbaker/homeassistant-fansync)](https://github.com/tjbaker/homeassistant-fansync/blob/main/LICENSE)

Custom Home Assistant integration for Fanimation FanSync devices with cloud push updates, automatic reauthentication, and multi-language support.

**🏆 Quality:** Bronze & Silver tier compliant  
**🌍 Languages:** English, French (Français), Spanish (Español)  
**🔄 Updates:** Real-time cloud push with fallback polling

## Requirements

- **Python:** 3.13+
- **Home Assistant:** 2026.1.0 or newer
- **HACS:** Optional (only if installing via HACS)
- **Account:** Valid Fanimation FanSync account with registered devices

## Features

### Device Control
- **Fan:** On/off, percentage speed (1-100%), direction, preset modes (normal, fresh_air)
- **Light:** On/off, brightness (0-255 with smooth mapping)
- **Real-time Updates:** Cloud push updates for instant state synchronization
- **Fallback Polling:** Configurable polling when push unavailable (default: 60s)


## Installation

### HACS (Recommended)

1) In Home Assistant, go to HACS → Integrations.
2) Click **Explore & Download Repositories**.
3) Search for "FanSync".
4) Click **Download** and confirm.
5) Restart Home Assistant.
6) Add the integration: Settings → Devices & Services → Add integration → "FanSync".

### Manual

1) Copy `custom_components/fansync/` into your Home Assistant `config/custom_components/` directory.
2) Restart Home Assistant.
3) Add the integration: Settings → Devices & Services → Add integration → "FanSync".

## Removal

To remove the FanSync integration:

1) Go to **Settings** → **Devices & Services**
2) Find the **FanSync** integration
3) Click the **three dots (⋮)** menu
4) Select **Delete**
5) Confirm the removal

If installed via HACS:
1) Go to **HACS** → **Integrations**
2) Find **FanSync**
3) Click the **three dots (⋮)** menu
4) Select **Remove**
5) Restart Home Assistant

If installed manually:
1) Remove the integration from the UI (steps 1-5 above)
2) Delete the `config/custom_components/fansync/` directory
3) Restart Home Assistant

## Configuration

| Option      | Description                                                  | Default |
|-------------|--------------------------------------------------------------|---------|
| Email       | FanSync account email                                        | –       |
| Password    | FanSync account password                                     | –       |
| Verify SSL  | Verify HTTPS certificates when connecting to FanSync cloud   | True    |
| HTTP timeout (s) | HTTP connect/read timeout used during login/token refresh     | 20      |
| WebSocket timeout (s) | WebSocket connect/recv timeout for realtime channel         | 30      |


### Options

Push-first updates are used by default. A low-frequency fallback poll can be configured:

| Option                 | Description                                                       | Default |
|------------------------|-------------------------------------------------------------------|---------|
| fallback_poll_seconds  | Poll interval in seconds when push is unavailable (0 disables).  | 60      |
| http_timeout_seconds   | HTTP connect/read timeout (seconds)                               | 20      |
| ws_timeout_seconds     | WebSocket connect/recv timeout (seconds)                          | 30      |

Set via: Settings → Devices & Services → FanSync → Configure → Options.
- Poll interval allowed range: 15–600 seconds (0 disables)
- Timeout ranges: 5–120 seconds (HTTP and WebSocket)

## Reauthentication

If your FanSync credentials expire or become invalid, Home Assistant will automatically prompt you to re-enter your password:

1. A notification will appear: "FanSync requires re-authentication"
2. Click the notification or go to **Settings** → **Devices & Services** → **FanSync**
3. Click **Configure** → **Re-authenticate**
4. Enter your password (email is pre-filled)
5. The integration will reconnect automatically

Your devices and automations remain unchanged during reauthentication.

## Languages

The integration UI is available in multiple languages:
- 🇬🇧 **English** (en)
- 🇫🇷 **French** (Français)
- 🇪🇸 **Spanish** (Español)

The UI language follows your Home Assistant language setting. To change:
1. Go to your **User Profile** (bottom left)
2. Select **Language**
3. Choose your preferred language
4. Refresh the page

## Troubleshooting

### Quick Diagnostic Steps

If you're experiencing connection or device control issues, follow these steps:

#### 1. Get Diagnostics (Fastest!)

The integration captures comprehensive diagnostics **even when setup fails**!

**If integration is working:**
1. Go to **Settings** → **Devices & Services**
2. Find the **FanSync** integration
3. Click the **three dots (⋮)** menu
4. Select **Download Diagnostics**
5. Save the JSON file

**If setup fails:**
Diagnostics are automatically logged! Look for:
- Error message in UI shows key metrics: `HTTP: XXXms, WS handshake: XXms, Login wait: XXXms`
- Full diagnostics in logs: Search for "Connection diagnostics (structured)" message
- Copy the entire JSON block from the logs

**What's included** (no passwords or tokens):
- **Connection timing breakdown**:
  - HTTP login duration
  - WebSocket handshake duration (connect only)
  - WebSocket login response wait time
  - Total WebSocket connection time
  - Token refresh attempts count
- **Token metadata**: Format, length, expiry status
- **Login response details**: Last server response (sanitized)
- **Connection failure history**: Recent failures with timestamps and error types
- **Environment info**: Python version, library versions
- **Network metrics**: Latency, timeouts, reconnects, push updates
- **Device configuration**: Device count and settings

**Share this file when reporting issues** - it contains everything needed to diagnose most connection problems!

#### 2. Enable Debug Logging

For more detailed logs, enable debug logging for **all relevant components**:

**Temporary** (via Developer Tools → Services):
```yaml
service: logger.set_level
data:
  custom_components.fansync: debug
  custom_components.fansync.client: debug
  custom_components.fansync.coordinator: debug
  custom_components.fansync.fan: debug
  custom_components.fansync.light: debug
  httpcore: debug
  httpx: debug
  websockets: debug
```

**Persistent** (add to `configuration.yaml`):
```yaml
logger:
  default: info
  logs:
    custom_components.fansync: debug
    custom_components.fansync.client: debug
    custom_components.fansync.coordinator: debug
    custom_components.fansync.fan: debug
    custom_components.fansync.light: debug
    httpcore: debug
    httpx: debug
    websockets: debug
```

**Why all these loggers?**
- `custom_components.fansync.*` - Integration modules (client, coordinator, entities)
- `httpcore` & `httpx` - HTTP authentication, token requests, SSL handshake
- `websockets` - WebSocket connection, login messages, server responses

**Tip**: Start with just `custom_components.fansync: debug` for most issues. Add the module-specific loggers (`client`, `coordinator`, etc.) only if you need more granular detail.

Then restart Home Assistant and reproduce the issue. Check logs in **Settings** → **System** → **Logs**.

**Note**: If setup fails, the integration automatically logs structured diagnostics at ERROR level, so debug logging is optional but helpful for additional context.

### Common Issues

#### Connection Timeout During Setup

**Symptoms**: Integration setup hangs for 90 seconds then fails with "WebSocket connection failed"

**Diagnostics to check**:
- `connection_timing.last_http_login_ms` - HTTP authentication timing (should be < 5000ms)
- `connection_timing.last_ws_connect_ms` - WebSocket handshake timing (should be < 5000ms)
- `connection_timing.last_ws_login_wait_ms` - Time waiting for login response (> 80000ms indicates server not responding)
- `connection_timing.last_ws_login_ms` - Total WebSocket connection time (> 80000ms indicates timeout)
- `last_login_response` - Last login response from server (null if no response received)
- `connection_failures` - Recent failure history with exact error types
- `token_metadata.is_expired` - Token expiration status

**Possible causes**:
1. **Firewall blocking WebSocket (wss://)** - Check if HTTP succeeds but WebSocket fails
2. **Server-side issue** - If token is valid but server doesn't respond to WebSocket login
3. **Network restrictions** - Corporate/enterprise networks may block WebSocket protocol

**Solutions**:
- Verify the official Fanimation mobile app works on the same network
- Check firewall rules for `wss://fanimation.apps.exosite.io:443`
- Try from a different network (e.g., mobile hotspot) to rule out local network issues
- Check diagnostics for `connection_failures` to see error patterns

#### Devices Not Responding to Commands

**Symptoms**: Fan/light entities show up but don't respond to commands

**Diagnostics to check**:
- `metrics.timeout_rate` - High timeout rate indicates network latency
- `metrics.avg_latency_ms` - Average command latency (should be < 2000ms)
- `metrics.websocket_reconnects` - Frequent reconnects indicate unstable connection
- `connection_analysis.quality` - Overall connection quality assessment

**Solutions**:
- If `avg_latency_ms > 5000`: Increase WebSocket timeout in integration options
- If `websocket_reconnects > 10`: Check WiFi signal strength and network stability
- If `timeout_rate > 0.3`: Network latency issues - check router/ISP

#### Intermittent Disconnections

**Symptoms**: Integration works but disconnects randomly

**Diagnostics to check**:
- `metrics.websocket_reconnects` - Count of reconnection attempts
- `metrics.push_updates_received` - Push update reliability
- `connection_failures` - Timestamps and patterns of failures

**Solutions**:
- Check `connection_failures` for patterns (time of day, specific error types)
- Verify Home Assistant has stable network connection
- Check for router/firewall idle timeout settings (may disconnect long-running WebSocket)

#### Authentication Failures

**Symptoms**: Notification that "FanSync requires re-authentication" or integration shows as "Authentication Failed"

**What happens automatically**:
- The integration detects expired or invalid credentials (401/403 HTTP errors)
- Home Assistant triggers the reauthentication flow
- You'll see a notification to re-enter your password

**To resolve**:
1. Click the notification or go to **Settings** → **Devices & Services** → **FanSync**
2. Click **Configure** → **Re-authenticate**
3. Enter your password (email is pre-filled)
4. Integration reconnects automatically

**Note**: This is normal if you changed your FanSync password or if the session expired. Your devices and automations are unaffected.

### Reporting Issues

When reporting connection issues, please:

1. **Download and attach diagnostics** (see above) - this is the most important step!
2. Include Home Assistant version and installation type (OS/Container/Core)
3. Describe your network environment (home/corporate, VPN, proxy, etc.)
4. Note if the official Fanimation app works on the same network
5. Include debug logs showing the connection attempt

Use the [Connection Issue template](https://github.com/tjbaker/homeassistant-fansync/issues/new/choose) which guides you through providing all necessary information.

For general contributing guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).  
For detailed test suite info, see [tests/README.md](tests/README.md).

## Development & Contributing

Want to contribute or test changes locally?

### 🚀 Quick Start: Docker Development

Get a local Home Assistant instance running in seconds:

```bash
docker compose up -d              # Start HA with your code mounted
# Access at http://localhost:8123 (no login after first setup!)
# Edit code, then:
docker compose restart            # See changes in ~10 seconds
```

### 🧰 Local Dev (Virtualenv + Make)

If you prefer to run checks outside Docker:

```bash
make venv
make install
make check
```

### 📚 Contributing Guide

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for:
- Complete Docker setup and workflow
- Code standards and conventions
- Pull request process
- Testing guidelines

For test-specific details, see **[tests/README.md](tests/README.md)**.

## Quality & Testing

This integration follows Home Assistant's Integration Quality Scale:

- ✅ **Bronze Tier:** Complete (8/8 requirements)
- ✅ **Silver Tier:** Complete (4/4 requirements)  
- 🔄 **Gold Tier:** In progress (coverage target 95%)

**Test Suite:** coverage and test counts are tracked in CI:
- See the Codecov badge for current coverage
- See the CI workflow for the latest test count

Coverage and test counts are intentionally not hard-coded here to avoid drift.

**Tests cover:**
- Entity functionality (fan, light)
- Push updates and optimistic updates
- Connection handling and retries
- Configuration and options flows
- Reauthentication flows
- Error handling and edge cases

**Run tests locally:**
```bash
make coverage
```

See [QUALITY_SCALE_VERIFICATION.md](QUALITY_SCALE_VERIFICATION.md) for detailed compliance report.

## Support This Project

If you find this integration useful, please consider:

⭐ **Star this repository** on GitHub  
🐛 **Report issues** or suggest features  
🔧 **Contribute** improvements or translations  

And if you'd like to buy me a coffee ☕:

**💙 USDC on Base Network**

<p align="center">
  <img src=".github/donations.png" width="200" alt="Base USDC QR Code" />
</p>

**Address**: `0x7CC11505c5fBb8FB0c52d2f63fd9A44763246397`  
**Network**: Base (not Ethereum mainnet)

*Completely optional! This project is free and open source.* ❤️

 

## License

Apache-2.0 (see [LICENSE](LICENSE)).

## Acknowledgments

- Reverse‑engineering notes and sample payloads that informed this work were
  originally published in [rotinom/fansync](https://github.com/rotinom/fansync).
