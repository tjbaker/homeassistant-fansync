# Diagnostic Build - diag1 Branch

**Issue Reference**: [#71 - Problems on UniFi networks](https://github.com/tjbaker/homeassistant-fansync/issues/71)

## Problem Statement

Users on UniFi and Asus router networks experience WebSocket connection timeouts:
- ✅ HTTP authentication succeeds (~400-500ms)
- ✅ WebSocket handshake succeeds (HTTP 101)
- ✅ PING/PONG keepalives work
- ❌ WebSocket login frame receives no response (times out after 15s)

## Root Cause Analysis

After analysis of logs and reverse engineering, identified **missing session cookie** as primary suspect:
- HTTP login returns `Set-Cookie: sid=...` 
- **We were not extracting or forwarding this cookie to WebSocket**
- Server likely ties WebSocket session to HTTP session via cookie

## Diagnostic Improvements Implemented

###  1. **Session Cookie Extraction & Forwarding** (HIGH PRIORITY)

```python
# Extract session cookie from HTTP response
token, session_cookie = await self.hass.async_add_executor_job(
    self._http_login, url, headers, json_data
)

# Forward cookie on WebSocket upgrade
ws_headers = {"Cookie": f"sid={session_cookie}"}
```

**Why**: Server may require session binding via cookie. This is the most likely fix.

### 2. **Exact Android App User-Agent**

```python
ws_headers = {
    "User-Agent": "okhttp/4.9.0",  # Exact Android app UA
    "X-Requested-With": "com.fanimation.fanSyncW",
    "Origin": "http://localhost",
}
```

**Why**: Match mobile app exactly to avoid server filtering.

### 3. **Disable permessage-deflate Extension**

```python
ws = await websockets.connect(
    url,
    ssl=self._ssl_context,
    additional_headers=ws_headers,
    extensions=[],  # Disable all extensions
)
```

**Why**: Some servers mishandle WebSocket compression extensions.

### 4. **Receive-Before-Send Check** (Optional)

```python
# Only enabled with FANSYNC_CHECK_SERVER_HELLO=1
check_hello = os.getenv("FANSYNC_CHECK_SERVER_HELLO") == "1"
if check_hello and _LOGGER.isEnabledFor(logging.DEBUG):
    try:
        server_hello = await asyncio.wait_for(ws.recv(), timeout=0.1)
        _LOGGER.debug("Server sent initial message: %s", server_hello[:200])
    except TimeoutError:
        _LOGGER.debug("No server hello (expected)")
```

**Why**: Some WebSocket backends send initial hello/nonce. Disabled by default to avoid test interference.

### 5. **Enhanced Diagnostic Logging**

```python
_LOGGER.debug("WS upgrade headers: UA=%s Cookie=%s", ua, cookie_present)
_LOGGER.debug("WS connected (%.0fms). Extensions: %s State: %s", ...)
_LOGGER.debug("Sending WebSocket login (token len: %d, msg len: %d)", ...)
_LOGGER.debug("Login response received (%.0fms wait, %d bytes)", ...)
```

**Why**: Provides detailed visibility into connection process for troubleshooting.

## Troubleshooting Flow

**Primary Fix** (most likely): Session cookie + exact UA + disable extensions  
**Secondary Diagnostic** (only if primary fails): Server hello check via env var

```
┌─────────────────────────────────────────────────┐
│ Step 1-3: Test Primary Fixes                   │
│  - Session cookie forwarding                    │
│  - Exact Android app User-Agent                 │
│  - Disable WebSocket extensions                 │
└─────────────────────────────────────────────────┘
                    │
                    ├── ✅ Success? → Report & merge!
                    │
                    └── ❌ Still fails?
                            │
                            ▼
┌─────────────────────────────────────────────────┐
│ Step 4: Enable Server Hello Check              │
│  - Set FANSYNC_CHECK_SERVER_HELLO=1            │
│  - Capture logs showing server behavior         │
│  - Determine if protocol change occurred        │
└─────────────────────────────────────────────────┘
```

## Testing Instructions for User

### Step 1: Install Diagnostic Build

```bash
cd /config/custom_components
rm -rf fansync
git clone -b diag1 https://github.com/tjbaker/homeassistant-fansync.git fansync
```

### Step 2: Enable Debug Logging

```yaml
logger:
  logs:
    custom_components.fansync.client: debug
```

### Step 3: Test Connection

1. Restart Home Assistant
2. Try FanSync integration setup
3. Check logs for new diagnostic output

### Step 4: (Optional) Enable Server Hello Check - ONLY IF STEP 3 FAILS

**⚠️ Only use this if the session cookie fix doesn't work!**

This is a secondary diagnostic tool that checks if the server sends an unexpected
initial message before the login frame. It's disabled by default because:
- Adds 0.1s overhead to every connection
- Most servers don't send initial messages
- Primary fixes (cookie + UA + extensions) should resolve UniFi issues

**When to use**: Only if maintainer requests it after reviewing failed logs.

**How to enable**:

**Docker/Container:**
```yaml
# docker-compose.yml or Home Assistant OS
environment:
  - FANSYNC_CHECK_SERVER_HELLO=1
```

**HA Core (venv):**
```bash
# Add to systemd service or startup script
export FANSYNC_CHECK_SERVER_HELLO=1
systemctl restart home-assistant
```

**Temporary Testing:**
```bash
# In HA container/shell
export FANSYNC_CHECK_SERVER_HELLO=1
ha core restart
```

**What it does**: Waits 0.1s for server hello message before sending login.
If server sends unexpected message, logs it for analysis.

## Expected Log Output (Success)

```
DEBUG http login ms=441 verify_ssl=True session_cookie=present
DEBUG WS upgrade headers: UA=okhttp/4.9.0 Cookie=present
DEBUG WS connected (120ms). Extensions: [] State: OPEN
DEBUG Sending WebSocket login (token len: 318, msg len: 362)
DEBUG Login sent. Waiting for response (timeout: 10s)...
DEBUG Login response received (245ms wait, 156 bytes)
DEBUG ws connect+login ms=450
```

## What to Report Back

Please provide:
1. **Full debug logs** (especially lines with "WS upgrade headers", "session_cookie")
2. **Did it work?** Yes/No
3. **Network details**: UniFi model (UDM, UDM-Pro, USG, etc.)
4. **UniFi settings**: DPI enabled? IPS/IDS enabled?
5. **Mobile hotspot test**: Does it work on mobile hotspot?

## Technical Details

### Files Modified

- `custom_components/fansync/client.py`:
  - Modified `_http_login()` to return `(token, session_cookie)` tuple
  - Updated `async_connect()` to extract and forward session cookie
  - Added exact Android app User-Agent (`okhttp/4.9.0`)
  - Disabled WebSocket extensions (`extensions=[]`)
  - Added optional server hello check (env var controlled)
  - Enhanced diagnostic logging throughout connection process
  - Applied same fixes to `_ensure_ws_connected()` (reconnection path)

- `tests/test_client_mobile_headers.py`:
  - Updated test to expect `User-Agent: okhttp/4.9.0` in headers

### Quality Assurance

✅ **All 149 tests pass** (6 skipped)  
✅ **No linting errors** (Ruff)  
✅ **Proper formatting** (Black)  
✅ **No type errors** (Mypy)

### Backward Compatibility

- Non-breaking changes only
- Tests run same as before
- Diagnostic features are additions, not changes
- Server hello check disabled by default

## Next Steps

1. User tests diagnostic build on UniFi network
2. If session cookie fix works → merge to main
3. If still fails → analyze new diagnostic logs for next iteration
4. Consider adding HTTP-only fallback mode if WebSocket remains problematic

## References

- [Issue #71](https://github.com/tjbaker/homeassistant-fansync/issues/71)
- [WEBSOCKET_TIMEOUT_TROUBLESHOOTING.md](WEBSOCKET_TIMEOUT_TROUBLESHOOTING.md)
- Android app reverse engineering (User-Agent, headers)

