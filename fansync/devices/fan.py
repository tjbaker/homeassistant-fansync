# SPDX-License-Identifier: GPL-2.0-only

from bidict import bidict

# Fan-specific protocol mappings (moved from light.py)
field_mapping_ = bidict({
    'FAN_POWER': 'H00',
    'FAN_MODE': 'H01',
    'FAN_PERCENT': 'H02',
    'FAN_DIRECTION': 'H06',
})

fan_mode_ = bidict({
    0: "Normal",
    1: "Fresh Air"
})

fan_direction_ = bidict({
    0: "Forward",
    1: "Reverse"
})


class Fan:
    def __init__(self, output_callback, power_key: str, percent_key: str):
        self._output_callback = output_callback
        self._power_key: str = power_key
        self._power_value: int | None = None
        self._percent_key: str = percent_key
        self._percent_value: int | None = None

    def set_status(self, status: dict[str, int]):
        if self._power_key in status:
            self._power_value = status[self._power_key]
        if self._percent_key in status:
            self._percent_value = status[self._percent_key]

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
