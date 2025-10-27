#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only


import sys
import time

import httpx
from credentials import EMAIL, PASSWORD

from fansync import HttpApi, Websocket
from fansync.models import ListDevicesResponse

# Mode mapping (FAN_MODE H01): 0=Normal, 1=Fresh Air


def main():
    # Parse mode argument (optional)
    # Usage: set_fan_mode.py [normal|fresh|fresh-air]
    desired = "fresh"
    if len(sys.argv) > 1:
        desired = sys.argv[1].strip().lower()
    if desired in ("fresh", "fresh-air", "fresh_air", "breeze"):
        value = 1
    elif desired in ("normal", "standard"):
        value = 0
    else:
        raise SystemExit("Usage: set_fan_mode.py [normal|fresh|fresh-air]")

    # Auth (disable SSL verification per README)
    http = HttpApi()
    http._session = httpx.Client(verify=False)

    print("Logging in...")
    creds = http.post_session(EMAIL, PASSWORD)
    if not creds:
        raise Exception("Failed to authenticate")
    print("Successfully authenticated!")

    # WebSocket login
    print("Connecting to websocket...")
    ws = Websocket(creds.token)
    ws.connect()
    try:
        ws.login()
        print("Successfully connected to websocket!")

        # Get device
        devices = ws.list_devices()
        if not devices.data:
            raise Exception("No devices found")
        device_id = devices.data[0].device
        print(f"Using device: {devices.data[0].properties.displayName}")

        # Build Device object for get status calls
        device = ListDevicesResponse.Device(
            device=device_id,
            properties=ListDevicesResponse.Properties(
                displayName="Fan", deviceHasBeenConfigured=True
            ),
        )

        # Current status
        info = ws.get_device(device)
        print(f"Initial status: {info.data.status}")

        # Ensure power is ON and set mode (H01)
        ws.set_device(device_id, {"H00": 1, "H01": value})
        time.sleep(1.5)

        # Verify
        info = ws.get_device(device)
        print(f"Final status: {info.data.status}")

    finally:
        ws.close()


if __name__ == "__main__":
    main()
