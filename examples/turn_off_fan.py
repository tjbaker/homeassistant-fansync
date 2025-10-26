#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only


import time

import httpx
from credentials import EMAIL, PASSWORD

from fansync import HttpApi, Websocket
from fansync.models import ListDevicesResponse


def main():
    """Turn off the fan"""
    # Initialize HTTP API with SSL verification disabled
    http = HttpApi()
    http._session = httpx.Client(verify=False)
    
    print("Logging in...")
    credentials = http.post_session(EMAIL, PASSWORD)
    if not credentials:
        raise Exception("Failed to authenticate!")

    print("Successfully authenticated!")
    print("Connecting to websocket...")
    
    ws = Websocket(credentials.token)
    ws.connect()
    
    try:
        ws.login()
        print("Successfully connected to websocket!")
        
        # Get the first device
        devices = ws.list_devices()
        if not devices.data:
            raise Exception("No devices found!")
        
        device_id = devices.data[0].device
        print(f"Connected to fan: {devices.data[0].properties.displayName}")
        
        # Create a Device object for status checks
        device = ListDevicesResponse.Device(
            device=device_id,
            properties=ListDevicesResponse.Properties(
                displayName="Fan",
                deviceHasBeenConfigured=True
            )
        )
        
        # Get current status
        device_info = ws.get_device(device)
        status = device_info.data.status
        print(f"\nInitial status: {status}")
        
        # First attempt: Set power to 0 and speed to minimum (1)
        print("\nAttempt 1: Setting power to 0 and speed to minimum (1)...")
        data = {
            "H00": 0,  # Fan power
            "H02": 1,  # Fan speed (minimum)
        }
        ws.set_device(device_id, data)
        time.sleep(3)  # Give it more time to process
        
        # Check status
        device_info = ws.get_device(device)
        status = device_info.data.status
        print(f"Status after attempt 1: {status}")
        
        # If still on, try second attempt with speed first
        if status.get("H00") == "1":
            print("\nAttempt 2: Setting speed first, then power...")
            # Set speed to minimum (1)
            ws.set_device(device_id, {"H02": 1})
            time.sleep(3)
            
            # Set power to 0
            ws.set_device(device_id, {"H00": 0})
            time.sleep(3)
            
            # Check status
            device_info = ws.get_device(device)
            status = device_info.data.status
            print(f"Status after attempt 2: {status}")
            
            # If still on, try third attempt with all controls
            if status.get("H00") == "1":
                print("\nAttempt 3: Setting all controls to 0/minimum...")
                data = {
                    "H0D": 0,  # Home/Away
                    "H0C": 0,  # Light brightness
                    "H0B": 0,  # Light power
                    "H06": 0,  # Fan direction
                    "H01": 0,  # Fan mode
                    "H02": 1,  # Fan speed (minimum)
                    "H00": 0,  # Fan power
                }
                ws.set_device(device_id, data)
                time.sleep(3)
                
                # Check status
                device_info = ws.get_device(device)
                status = device_info.data.status
                print(f"Status after attempt 3: {status}")
                
                # If still on, try one last time with speed first
                if status.get("H00") == "1":
                    print("\nAttempt 4: Final attempt with speed first...")
                    # Set speed to minimum (1)
                    ws.set_device(device_id, {"H02": 1})
                    time.sleep(3)
                    
                    # Set power to 0 and speed to minimum together
                    data = {
                        "H02": 1,  # Fan speed (minimum)
                        "H00": 0,  # Fan power
                    }
                    ws.set_device(device_id, data)
                    time.sleep(3)
                    
                    # Final status check
                    device_info = ws.get_device(device)
                    status = device_info.data.status
                    print(f"Status after attempt 4: {status}")
        
        print("\nFinal status check...")
        device_info = ws.get_device(device)
        status = device_info.data.status
        print(f"Final status: {status}")
        
        # Print a summary of what happened
        if status.get("H00") == "1":
            print("\nWARNING: Fan is still on! Please try again or check the fan manually.")
        else:
            print("\nSuccess! Fan has been turned off.")
        
    finally:
        ws.close()

if __name__ == "__main__":
    main()