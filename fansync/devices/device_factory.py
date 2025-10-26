# SPDX-License-Identifier: GPL-2.0-only

import re

from fansync.devices.device import Device
from fansync.models import GetDeviceResponse, InfoModel

"""
Fan/Light parameters specified in the information model 
FAN_DIRECTION
FAN_HOME_SHIELD
FAN_LEARN_LOAD
FAN_LIGHT
FAN_LIGHT_CCT
FAN_MODE
FAN_POWER
FAN_POWER_AND_SPEED
LIGHT_HOME_SHIELD
LIGHT_POWER
LIGHT_POWER_AND_DIMMER
LIGHT_TURN_OFF_TIMER
LIGHT_TURN_ON_TIMER
"""



class DeviceFactory:
    def __init__(self, info_model: dict[str, dict]):
        # self._info_model: dict[str, dict] = info_model
        self._regex_to_model: list[(str, InfoModel)] = []

        for _key, value in info_model.items():
            info_model: InfoModel = InfoModel(**value)
            for family_member in info_model.informationModel.familyMembers:
                regex = re.compile(family_member)
                self._regex_to_model.append((regex,info_model))

            for c in info_model.informationModel.components.keys():
                if not c:
                    print("not present")

                print(c)

    def get_device(self, device_response: GetDeviceResponse) -> Device | None:

        found_model: InfoModel | None = None
        for regex, info_model in self._regex_to_model:
            if regex.match(device_response.data.profile.esh.model):
                print(info_model)
                found_model = info_model
                continue

        if not found_model:
            return None






