# SPDX-License-Identifier: GPL-2.0-only


from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr, field_serializer

from fansync.devices.light import field_mapping_ as field_mapping_


class InfoModel(BaseModel):
    class InformationModel(BaseModel):
        scheduleLayout: dict[str, list[str]]
        familyMembers: list[str]
        deviceId: str
        familyName: str
        components: dict[str, dict]

    timestamp: int
    size: int
    lastModified: int
    name: str
    informationModel: InformationModel


class HttpCredentials(BaseModel):
    email: SecretStr
    password: SecretStr


class Credentials(BaseModel):
    id: int
    token: SecretStr


class Request(BaseModel):
    id: int
    request: str


class SetRequest(Request):
    request: str = "set"
    device: str
    data: dict[str, int]


class Response(BaseModel):
    id: int
    status: str


class WsResponse(Response):
    response: str


class ProvisionTokenRequest(Request):
    class Data(BaseModel):
        expires_in: int = 2592000  # 30 days in seconds(?)

    request: str = "provision_token"
    data: Data


class ProvisionTokenResponse(WsResponse):
    class Data(BaseModel):
        token: str
        expires_in: int

    data: Data


class LoginRequest(Request):
    class Data(BaseModel):
        token: SecretStr

        @field_serializer("token", when_used="json")
        def dump_secret(self, v):
            return v.get_secret_value()

    request: str = "login"
    data: Data


# This is weird. It's a special "Response" not related to the "Response" hierarchy
class LoginResponse(BaseModel):
    id: int
    token: SecretStr


class WsLoginResponse(WsResponse):
    pass


class ListDevicesRequest(Request):
    pass


class ListDevicesResponse(Response):
    class Properties(BaseModel):
        displayName: str
        deviceHasBeenConfigured: bool
        ignoreUpdateVersion: str | None = None

    class Device(BaseModel):
        owner: str | None = None
        device: str | None = None
        role: str | None = None
        properties: ListDevicesResponse.Properties

    data: list[Device]


class GetDeviceRequest(Request):
    request: str = "get"
    device: str


class User(BaseModel):
    role: str
    email: str


class GetDeviceResponse(Response):
    class Module(BaseModel):
        firmware_version: str
        local_ip: str
        ssid: str
        mac_address: str

    class Esh(BaseModel):
        brand: str
        esh_version: str
        class_: int = Field(alias="class")  # keyword in Python
        device_id: str
        model: str

    class Data(BaseModel):
        class Profile(BaseModel):
            module: GetDeviceResponse.Module  # forward reference
            esh: GetDeviceResponse.Esh  # forward reference

            class Config:
                exclude = ["cert"]

        users: list[User]
        status: dict[str, int]
        fields: list[str]
        profile: Profile
        # calendar - excluded
        device: str
        connected: int
        device_state: str

        # Not doing it this way right now.
        # def get_fan_percent(self):
        #     return self.status[field_mapping_['FAN_PERCENT']]
        #
        # def get_fan_power(self):
        #     return self.status[field_mapping_['FAN_POWER']] == 1
        #
        # def get_fan_mode(self):
        #     return fan_mode_[self.status[field_mapping_['FAN_MODE']]]
        #
        # def get_fan_direction(self):
        #     return fan_direction_[self.status[field_mapping_['FAN_DIRECTION']]]
        #
        # def get_light_percent(self):
        #     return self.status[field_mapping_['LIGHT_PERCENT']]
        #
        # def get_light_power(self):
        #     return self.status[field_mapping_['LIGHT_POWER']]
        #
        # def get_home_away(self):
        #     return self.status[field_mapping_['HOME_AWAY']] == 1

        # class Config:
        #     exclude = ['calendar']

    data: Data


# Best guess; only have one event type now
class Event(BaseModel):
    event: str


# Best guess; This is the only concrete event observed
class DeviceChangeEvent(Event):
    class Data(BaseModel):
        class Changes(BaseModel):
            status: dict[str, int]

        changes: Changes
        device: str

    data: Data
