# SPDX-License-Identifier: GPL-2.0-only
# Copyright 2025 Trevor Baker, all rights reserved.

from typing import Optional

# # Not really a facade.  Trying this whole thing out right now
# class Device:
#
#     def __init__(self, device_factory: DeviceFactory, websocket: ClientConnection, device: ListDevicesResponse.Device):
#         self._ws = websocket
#         self._df = device_factory
#         self._listed_device: ListDevicesResponse.Device = device
#         self._device_state: Optional[GetDeviceResponse] = None
#
#     # Update with data from set_device
#     def set_device_state(self, device_state: GetDeviceResponse):
#         self._device = self._df.


class Sprocket:
    def __init__(self, key: str, val: int = None):
        self._key: str = key
        self._val: int | None = val
        self._enabled: bool = True
        self.on_val_change = []

    def _get_val(self):
        return self._val

    def _set_val(self, val: int):
        if self._val != val:
            self._val = val

            # Invoke all our registered callbacks
            for callback in self.on_val_change:
                callback(self)

    val = property(_get_val, _set_val)

    def _get_enabled(self):
        return self._enabled

    def _set_enabled(self, val: bool):
        self._enabled = val

    enabled = property(_get_enabled, _set_enabled)


class Light:
    def turn_on(self):
        pass

    def turn_off(self):
        pass

    def set_percent(self):
        pass

    def get_percent(self):
        pass

    def is_on(self):
        pass


class Fan:
    def turn_on(self):
        pass

    def turn_off(self):
        pass

    def set_percent(self):
        pass

    def get_percent(self):
        pass

    def is_on(self):
        pass
