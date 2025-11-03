# FanSync Home Assistant Integration 

[![CI](https://github.com/tjbaker/homeassistant-fansync/actions/workflows/ci.yml/badge.svg)](https://github.com/tjbaker/homeassistant-fansync/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/tjbaker/homeassistant-fansync/branch/main/graph/badge.svg)](https://codecov.io/gh/tjbaker/homeassistant-fansync)

Custom Home Assistant integration for Fanimation FanSync devices.

## Requirements

- Python 3.13
- Home Assistant Core 2025.10.4 or newer
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
• Issues: [Open or track issues](https://github.com/tjbaker/homeassistant-fansync/issues)
• PRs: [Create a pull request](https://github.com/tjbaker/homeassistant-fansync/pulls)

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

## Troubleshooting

### Quick Diagnostic Steps

If you're experiencing connection or device control issues, follow these steps:

#### 1. Download Diagnostics (Fastest!)

The integration includes comprehensive diagnostics that capture timing, connection state, and error history:

1. Go to **Settings** → **Devices & Services**
2. Find the **FanSync** integration
3. Click the **three dots (⋮)** menu
4. Select **Download Diagnostics**
5. Save the JSON file

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
    httpcore: debug
    httpx: debug
    websockets: debug
```

**Why all these loggers?**
- `custom_components.fansync` - Integration logic, timing, connection flow
- `httpcore` & `httpx` - HTTP authentication, token requests, SSL handshake
- `websockets` - WebSocket connection, login messages, server responses

Then restart Home Assistant and reproduce the issue. Check logs in **Settings** → **System** → **Logs**.

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, lint/format, commit conventions, and PR guidance. For detailed test suite info and commands, see [tests/README.md](tests/README.md).

 

## License

Apache-2.0 (see [LICENSE](LICENSE)).

## Acknowledgments

- Reverse‑engineering notes and sample payloads that informed this work were
  originally published in [rotinom/fansync](https://github.com/rotinom/fansync).
