#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only


import httpx
from credentials import EMAIL, PASSWORD

from fansync import HttpApi, Websocket


def main():
    # Initialize HTTP API
    h = HttpApi()
    # Disable HTTP SSL verification
    h._session = httpx.Client(verify=False)

    # Login and get credentials
    print("Logging in...")
    credentials = h.post_session(EMAIL, PASSWORD)
    if not credentials:
        print("Failed to authenticate!")
        return

    print("Successfully authenticated!")

    # Connect to websocket
    print("Connecting to websocket...")
    ws = Websocket(credentials.token, verify_ssl=False)
    ws.connect()

    try:
        # Login to websocket
        ws.login()
        print("Successfully connected to websocket!")

        # List devices
        print("\nListing your devices:")
        devices = ws.list_devices()
        for device in devices.data:
            print("\nDevice found:")
            print(f"  Name: {device.properties.displayName}")
            print(f"  ID: {device.device}")
            print(f"  Role: {device.role}")

            # Get detailed device info
            device_info = ws.get_device(device)
            print(f"  Model: {device_info.data.profile.esh.model}")

    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        ws.close()


if __name__ == "__main__":
    main()
