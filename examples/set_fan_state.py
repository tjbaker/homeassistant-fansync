#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only


import sys
import time

import httpx
from credentials import EMAIL, PASSWORD

from fansync import HttpApi, Websocket
from fansync.models import ListDevicesResponse

# Mappings:
# H00: Power (1=On, 0=Off)
# H01: Fan Mode (0=Normal, 1=Fresh Air)
# H02: Fan Percent (1..100)
# H06: Direction (0=Forward, 1=Reverse)


def parse_args():
    # Usage: set_fan_state.py [direction] [mode] [speed]
    #  direction: forward|reverse (default reverse)
    #  mode: normal|fresh (default normal)
    #  speed: 1..100 (default 20)
    direction = "reverse"
    mode = "normal"
    speed = 20

    if len(sys.argv) > 1:
        direction = sys.argv[1].strip().lower()
    if len(sys.argv) > 2:
        mode = sys.argv[2].strip().lower()
    if len(sys.argv) > 3:
        try:
            speed = int(sys.argv[3])
        except ValueError:
            raise SystemExit("Speed must be an integer 1-100")

    if direction not in ("forward", "reverse"):
        raise SystemExit("direction must be forward|reverse")
    if mode not in ("normal", "fresh", "fresh-air", "fresh_air", "breeze"):
        raise SystemExit("mode must be normal|fresh")
    if not (1 <= speed <= 100):
        raise SystemExit("speed must be 1..100")

    h06 = 0 if direction == "forward" else 1
    h01 = 0 if mode == "normal" else 1
    return h06, h01, speed


def main():
    h06, h01, speed = parse_args()

    # Auth (disable SSL per README)
    http = HttpApi()
    http._session = httpx.Client(verify=False)

    print("Logging in...")
    creds = http.post_session(EMAIL, PASSWORD)
    if not creds:
        raise Exception("Failed to authenticate")
    print("Successfully authenticated!")

    print("Connecting to websocket...")
    ws = Websocket(creds.token)
    ws.connect()
    try:
        ws.login()
        print("Successfully connected to websocket!")

        devices = ws.list_devices()
        if not devices.data:
            raise Exception("No devices found")
        device_id = devices.data[0].device
        print(f"Using device: {devices.data[0].properties.displayName}")

        device = ListDevicesResponse.Device(
            device=device_id,
            properties=ListDevicesResponse.Properties(
                displayName="Fan", deviceHasBeenConfigured=True
            ),
        )

        info = ws.get_device(device)
        print(f"Initial status: {info.data.status}")

        # Send combined set: ensure power on, set direction, mode, and speed
        ws.set_device(device_id, {"H00": 1, "H06": h06, "H01": h01, "H02": speed})
        time.sleep(1.5)

        # Verify; retry once if not applied
        info = ws.get_device(device)
        if not (
            info.data.status.get("H00") == 1
            and info.data.status.get("H06") == h06
            and info.data.status.get("H01") == h01
            and info.data.status.get("H02") == speed
        ):
            ws.set_device(device_id, {"H00": 1, "H06": h06, "H01": h01, "H02": speed})
            time.sleep(1.5)
            info = ws.get_device(device)

        print(f"Final status: {info.data.status}")

    finally:
        ws.close()


if __name__ == "__main__":
    main()
