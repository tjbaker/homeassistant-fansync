#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only


import json
import time

import httpx
from credentials import EMAIL, PASSWORD

from fansync import HttpApi, Websocket


class FanController:
    def __init__(self):
        # Initialize HTTP API with SSL verification disabled
        self.http = HttpApi()
        self.http._session = httpx.Client(verify=False)
        self.ws = None
        self.device_id = None
        self.connected = False

    def connect(self):
        """Connect to the FanSync service and initialize the first found device"""
        print("Logging in...")
        credentials = self.http.post_session(EMAIL, PASSWORD)
        if not credentials:
            raise Exception("Failed to authenticate!")

        print("Successfully authenticated!")
        print("Connecting to websocket...")
        
        self.ws = Websocket(credentials.token)
        self.ws.connect()
        
        try:
            self.ws.login()
            print("Successfully connected to websocket!")
            
            # Get the first device
            devices = self.ws.list_devices()
            if not devices.data:
                raise Exception("No devices found!")
            
            self.device_id = devices.data[0].device
            print(f"Connected to fan: {devices.data[0].properties.displayName}")
            self.connected = True
            
        except Exception as e:
            print(f"Error occurred: {e}")
            if self.ws:
                self.ws.close()
            raise

    def _ensure_connected(self):
        """Ensure we're connected before performing operations"""
        if not self.connected or not self.ws:
            self.connect()

    def set_fan_power(self, on: bool):
        """Turn the fan on or off"""
        self._ensure_connected()
        
        # Get current status first
        current_status = self.get_status()
        print(f"Current status before change: {current_status}")
        
        if not on:
            # When turning off:
            # 1. Set speed to minimum first (required by info-model)
            self.ws.set_device(self.device_id, {"H02": "1"})
            time.sleep(1)
            
            # 2. Set power to 0 and all other controls to their off states
            data = {
                "H00": "0",  # Fan power
                "H01": "0",  # Fan mode
                "H02": "1",  # Fan speed (must be >= 1)
                "H06": "0",  # Fan direction
                "H0B": "0",  # Light power
                "H0C": "0",  # Light brightness
                "H0D": "0",  # Home/Away
            }
            self.ws.set_device(self.device_id, data)
            time.sleep(1)
            
            # 3. Verify the change
            status = self.get_status()
            print(f"Status after first attempt: {status}")
            
            # 4. If still on, try alternative approach
            if status['fan_power']:
                print("Fan still on, trying alternative approach...")
                # Try setting just power and speed
                self.ws.set_device(self.device_id, {"H02": "1"})
                time.sleep(1)
                self.ws.set_device(self.device_id, {"H00": "0"})
                time.sleep(1)
                
                # Check again
                status = self.get_status()
                print(f"Status after second attempt: {status}")
                
                # If still on, try one final approach
                if status['fan_power']:
                    print("Fan still on, trying final approach...")
                    # Try setting all controls to 0/minimum in reverse order
                    for field in ["H0D", "H0C", "H0B", "H06", "H02", "H01", "H00"]:
                        value = "1" if field == "H02" else "0"
                        self.ws.set_device(self.device_id, {field: value})
                        time.sleep(0.5)
                    
                    # Final status check
                    status = self.get_status()
                    print(f"Status after final attempt: {status}")
        else:
            # When turning on:
            # 1. Set power on first
            self.ws.set_device(self.device_id, {"H00": "1"})
            time.sleep(1)
            
            # 2. Then set speed to a moderate value (41%)
            self.ws.set_device(self.device_id, {"H02": "41"})
            time.sleep(1)
            
            # 3. Verify the change
            status = self.get_status()
            print(f"Status after turn on: {status}")
            
            # 4. If not on, try alternative approach
            if not status['fan_power']:
                print("Fan not on, trying alternative approach...")
                # Try setting power and speed together
                self.ws.set_device(self.device_id, {
                    "H00": "1",
                    "H02": "41"
                })
                time.sleep(1)
                
                # Final status check
                status = self.get_status()
                print(f"Status after second attempt: {status}")
        
        print(f"Fan power set to: {'ON' if on else 'OFF'}")
        print(f"Final status: {self.get_status()}")

    def set_fan_speed(self, speed: int):
        """Set fan speed (0-100)"""
        if not 0 <= speed <= 100:
            raise ValueError("Speed must be between 0 and 100")
        
        self._ensure_connected()
        self.ws.set_device(self.device_id, {"H02": str(speed)})
        print(f"Fan speed set to: {speed}%")

    def set_fan_direction(self, reverse: bool):
        """Set fan direction (True for reverse, False for forward)"""
        self._ensure_connected()
        value = "1" if reverse else "0"
        self.ws.set_device(self.device_id, {"H06": value})
        print(f"Fan direction set to: {'REVERSE' if reverse else 'FORWARD'}")

    def set_light_power(self, on: bool):
        """Turn the light on or off"""
        self._ensure_connected()
        
        # Get current status first
        current_status = self.get_status()
        print(f"Current status before change: {current_status}")
        
        value = "1" if on else "0"
        self.ws.set_device(self.device_id, {"H0B": value})
        time.sleep(1)
        
        # Verify the change
        status = self.get_status()
        print(f"Status after change: {status}")
        
        # If the change didn't take, try setting both power and brightness
        if status['light_power'] != on:
            print("Light power change failed, trying with brightness...")
            data = {
                "H0B": value,  # Light power
                "H0C": "0" if not on else "50"  # Light brightness (0 or 50%)
            }
            self.ws.set_device(self.device_id, data)
            time.sleep(1)
            
            # Final status check
            status = self.get_status()
            print(f"Status after second attempt: {status}")
        
        print(f"Light power set to: {'ON' if on else 'OFF'}")

    def set_light_brightness(self, brightness: int):
        """Set light brightness (0-100)"""
        if not 0 <= brightness <= 100:
            raise ValueError("Brightness must be between 0 and 100")
        
        self._ensure_connected()
        
        # Get current status first
        current_status = self.get_status()
        print(f"Current status before change: {current_status}")
        
        # If light is off and we're setting brightness > 0, turn it on first
        if brightness > 0 and not current_status['light_power']:
            print("Light is off, turning it on first...")
            self.set_light_power(True)
            time.sleep(1)
        
        # Set brightness
        self.ws.set_device(self.device_id, {"H0C": str(brightness)})
        time.sleep(1)
        
        # Verify the change
        status = self.get_status()
        print(f"Status after change: {status}")
        
        # If brightness didn't change, try setting both power and brightness
        if status['light_brightness'] != brightness:
            print("Brightness change failed, trying with power...")
            data = {
                "H0B": "1" if brightness > 0 else "0",  # Light power
                "H0C": str(brightness)  # Light brightness
            }
            self.ws.set_device(self.device_id, data)
            time.sleep(1)
            
            # Final status check
            status = self.get_status()
            print(f"Status after second attempt: {status}")
        
        print(f"Light brightness set to: {brightness}%")

    def get_status(self) -> dict:
        """Get the current status of the fan and light"""
        self._ensure_connected()
        # Create a mock Device object with the required device ID and properties
        from fansync.models import ListDevicesResponse
        device = ListDevicesResponse.Device(
            device=self.device_id,
            properties=ListDevicesResponse.Properties(
                displayName="Fan",
                deviceHasBeenConfigured=True
            )
        )
        device_info = self.ws.get_device(device)
        status = device_info.data.status
        
        return {
            "fan_power": str(status.get("H00", "0")) == "1",
            "fan_direction": "REVERSE" if str(status.get("H06", "0")) == "1" else "FORWARD",
            "fan_speed": int(str(status.get("H02", "0"))),
            "light_power": str(status.get("H0B", "0")) == "1",
            "light_brightness": int(str(status.get("H0C", "0")))
        }

    def close(self):
        """Close the connection"""
        if self.ws:
            self.ws.close()
            self.connected = False

def main():
    """Example usage of all controls"""
    controller = FanController()
    
    try:
        # Connect to the fan
        controller.connect()
        
        # Get current status
        print("\nCurrent status:")
        status = controller.get_status()
        print(json.dumps(status, indent=2))
        
        # Example controls
        print("\nDemonstrating controls:")
        
        # Fan controls
        print("\nFan controls:")
        controller.set_fan_power(True)
        time.sleep(2)
        
        print("Setting fan speed to 50%")
        controller.set_fan_speed(50)
        time.sleep(2)
        
        print("Reversing fan direction")
        controller.set_fan_direction(True)
        time.sleep(2)
        
        # Light controls
        print("\nLight controls:")
        controller.set_light_power(True)
        time.sleep(2)
        
        print("Setting light brightness to 75%")
        controller.set_light_brightness(75)
        time.sleep(2)
        
        # Get final status
        print("\nFinal status:")
        status = controller.get_status()
        print(json.dumps(status, indent=2))
        
    finally:
        controller.close()

if __name__ == "__main__":
    main()
