#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only


import time

import httpx
from credentials import EMAIL, PASSWORD

from fansync import HttpApi, Websocket
from fansync.models import ListDevicesResponse


def main():
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
                displayName="Fan",
                deviceHasBeenConfigured=True
            )
        )

        # Current status
        info = ws.get_device(device)
        print(f"Initial status: {info.data.status}")

        # 1) Ensure power is ON (H00=1)
        ws.set_device(device_id, {"H00": 1})
        time.sleep(1)

        # 2) Set speed to 45% (H02=45)
        ws.set_device(device_id, {"H02": 45})
        time.sleep(1)

        # Verify
        info = ws.get_device(device)
        print(f"Final status: {info.data.status}")

    finally:
        ws.close()


if __name__ == "__main__":
    main()
