# WebSocket Login Timeout - Troubleshooting Guide

## Problem
Integration setup succeeds with HTTP authentication but times out waiting for WebSocket login response.

## Symptoms
- HTTP login: ✅ Success (~400-500ms)
- WebSocket connection: ✅ Established (~100-200ms)
- WebSocket login: ❌ No response (times out after 30s)
- Diagnostic shows: `last_ws_login_wait_ms: null`, `last_login_response: null`

## Root Cause Analysis

The server **accepts** the WebSocket connection but **never responds** to the login request. This is indicated by:
1. Successful WebSocket handshake (connection OPEN)
2. Active keepalives (PING/PONG working)
3. But zero response to login message with token

## Potential Causes (in order of likelihood)

### 1. Missing Mobile App Headers ⭐ MOST LIKELY
**Problem**: Server filtering requests without official mobile app identification  
**Evidence**: Previous implementation didn't include mobile app headers  
**Fix Applied**: Now uses actual Android app headers:
- `X-Requested-With: com.fanimation.fanSyncW` (Android app package name)
- `Origin: http://localhost` (as used by mobile app)

### 2. Temporary Server Issue
**Problem**: Fanimation cloud service experiencing issues  
**Evidence**: Consistent timeout, server alive (PING/PONG) but not processing login  
**User Action**: Wait and retry later, monitor over time

### 3. Network Filtering
**Problem**: Firewall/proxy allowing connection but blocking/filtering WebSocket messages  
**Evidence**: Would explain why handshake works but login doesn't  
**User Action**: Test from different network

### 4. Token Format Issue
**Problem**: Server silently rejecting token format  
**Evidence Against**: Token is valid, HTTP auth succeeded  
**Unlikely**: Would typically return error response

## Fixes Applied to Integration

### 1. Add Official Mobile App Headers
```python
additional_headers={
    "X-Requested-With": "com.fanimation.fanSyncW",  # Android app package
    "Origin": "http://localhost",                    # Mobile app origin
}
```

### 2. Enhanced Debug Logging
```python
_LOGGER.debug("Sending WebSocket login request (token length: %d)", len(token))
_LOGGER.debug("Waiting for WebSocket login response (timeout: %ds)...", ws_timeout)
```
Provides more visibility into the login process.

### 3. Better Error Messages
Added user-actionable error messages explaining common causes and troubleshooting steps.

## User Troubleshooting Steps

### Step 1: Test with Fixed Integration
1. Update to version with User-Agent fix
2. Try setup again
3. If still fails, proceed to Step 2

### Step 2: Test from Different Network
**Purpose**: Isolate whether it's local network filtering

```bash
# Test from mobile hotspot:
1. Connect Home Assistant device to mobile hotspot
2. Attempt integration setup
3. If works: Your home network is filtering WebSocket
4. If fails: Server-side issue or requires specific headers
```

### Step 3: Check Network Environment
**Questions to answer:**
- Are you on corporate/enterprise network?
- Do you have Unifi Dream Machine or similar enterprise router?
- Is there a proxy between you and internet?
- Does your ISP do transparent proxying?

**Network features that may cause issues:**
- Deep Packet Inspection (DPI)
- WebSocket filtering
- SNI-based filtering
- Application-layer gateways

### Step 4: Test with Increased Timeout
**Purpose**: Rule out slow server response

```yaml
# In integration setup, try:
ws_timeout_seconds: 60  # Double the default 30s
```

If this works, server is just slow (rare).

### Step 5: Capture Full Diagnostic Data
**Enable all debug logging:**
```yaml
logger:
  logs:
    custom_components.fansync: debug
    httpcore: debug
    httpx: debug
    websockets: debug
```

**Look for:**
- Any WebSocket error messages from server
- Connection reset or unexpected close
- SSL/TLS errors
- Any response from server (even errors)

### Step 6: Compare Working vs Non-Working
**If official Fanimation app works:**
- App uses different protocol/authentication
- App may have special server-side allowlist
- Integration may need additional headers
- Capture traffic from app (advanced) to compare

**If official Fanimation app also fails:**
- Server-side issue affecting region/location
- Temporary outage
- Account-specific issue
- Wait and retry

## What We Can't Do

### ❌ Cannot Guarantee Server Behavior
Fanimation controls the server and can:
- Change protocols without notice
- Implement filtering/rate limiting
- Have regional outages
- Change authentication requirements

## Workarounds (if timeout persists)

### Option 1: HTTP-Only Mode (Future Feature)
Could add config option to skip WebSocket and use HTTP polling only:
- Slower updates (polling vs push)
- Higher latency
- But would work around WebSocket issues

**Implementation needed**: Config flow option + client modifications

### Option 2: Proxy/VPN
If local network is the issue:
- Route HA through VPN
- Use different ISP connection
- Tunnel through cloud server

### Option 3: Wait for Server Fix
If server-side issue:
- Monitor over days/weeks
- Check if pattern (time of day, region)
- May resolve on its own

## Diagnostic Data to Collect

When reporting issue, include:

1. **Full diagnostics JSON** (from error or integration)
2. **Network environment**:
   - Home/corporate network?
   - Router/firewall model?
   - ISP name?
   - VPN in use?
3. **Testing results**:
   - Works from mobile hotspot? Yes/No
   - Works from different location? Yes/No
   - Official Fanimation app works? Yes/No
4. **Timing patterns**:
   - Time of day when tested
   - Consistent failure or intermittent?
   - How long has this been failing?

## Success Indicators

If fix works, you'll see:
```
✅ HTTP login: 400-500ms
✅ WebSocket connect: 100-200ms
✅ WebSocket login: 200-500ms  # ← This will now have a value!
✅ last_login_response: {"status": "ok", ...}  # ← No longer null!
✅ Devices discovered
```

## Next Steps After Fix

1. **Test the updated integration**
2. **Report back results** (worked / still fails)
3. **If still fails**: Try different network
4. **If different network works**: Document your network setup
5. **If nothing works**: May need to capture mobile app traffic (advanced)

## Advanced Debugging (Optional)

### Capture Network Traffic
**⚠️ Warning**: Only for advanced users, may expose credentials

```bash
# On Home Assistant host:
tcpdump -i any -w websocket.pcap 'host fanimation.apps.exosite.io'

# Analyze in Wireshark:
# - Look at WebSocket frames
# - Compare to official app traffic
# - Check for differences in headers/messages
```

### Test Direct WebSocket Connection
**⚠️ Warning**: Requires Python knowledge

```python
import asyncio
import websockets

async def test():
    async with websockets.connect(
        "wss://fanimation.apps.exosite.io/api:1/phone",
        additional_headers={
            "User-Agent": "FanSync/1.0 (compatible; HomeAssistant)",
            "Origin": "https://fanimation.apps.exosite.io",
        }
    ) as ws:
        await ws.send('{"id":1,"request":"login","data":{"token":"YOUR_TOKEN"}}')
        response = await asyncio.wait_for(ws.recv(), timeout=30)
        print(response)

asyncio.run(test())
```

## Updates to Try

1. **v0.6.0+**: Includes official mobile app headers and enhanced logging
2. Headers now match Android app exactly: `X-Requested-With: com.fanimation.fanSyncW`
3. Test from mobile hotspot if home network fails
4. Report results with full diagnostics


## Summary

**Primary Fix**: Added official Android app headers
- `X-Requested-With: com.fanimation.fanSyncW` (Android package name)  
- `Origin: http://localhost` (mobile app origin)  

**Expected Outcome**: Server should now recognize requests as legitimate mobile app  
**Confidence Level**: High (using actual mobile app headers from reverse engineering)  
**If Still Fails**: Network filtering is likely cause, test from different network  
**Fallback**: May need HTTP-only mode (future feature)

