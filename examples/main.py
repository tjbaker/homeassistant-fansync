#!./venv/bin/python
# SPDX-License-Identifier: GPL-2.0-only

import json
import os

from credentials import EMAIL, PASSWORD

from fansync.devices.device_factory import DeviceFactory
from fansync.models import Credentials, GetDeviceResponse

# client = httpx.Client(http2=True)
#
# # Login
# r = client.post('https://fanimation.apps.exosite.io/api:1/session', json=LOGIN_JSON)
# print(r)
# print(r.json())
#

# Doesn't work
# r = client.get('https://fanimation.apps.exosite.io/api:1/')
# print(r)
# print(r.json())
#

# https://fanimation.apps.exosite.io/api:1/fw/list/[]  OPTIONS  ?   GET ?

# https://fanimation.apps.exosite.io/api:1/fw/list/[%22OdynCustom-FDR1L2%22]  GET ?  OPTIONS?    Auth not required?

# Get status of the session
# r = client.get('https://fanimation.apps.exosite.io/api:1/session')
# print(r)
# print(r.json())

CREDENTIALS_FILE = ".fansync-credentials"


def _load_cached_credentials() -> Credentials | None:
    print("Trying to load cached credential token...", end="")
    _id = None
    _token = None
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE) as cred_file:
            try:
                json_data = json.loads(cred_file.read())
                _id = int(json_data["id"])
                _token = json_data["token"]
            except json.JSONDecodeError:
                print("Cached credentials file invalid")
                return None

    if _id and _token:
        print("success!")
        return Credentials(id=_id, token=_token)

    print("failed")
    return None


def _save_cached_credentials(creds: Credentials):
    with open(CREDENTIALS_FILE, "w") as creds_file:
        creds_file.write(json.dumps(creds.model_dump()))


# try:

# creds = _load_cached_credentials()
#
# h = HttpApi()
#
# h.options_session()
# credentials: Credentials = h.post_session(EMAIL, PASSWORD)
# h.get_session(credentials)
#
# # credentials: Credentials = Credentials(id=10, token="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOjI3MTA2LCJpc3MiOiJodHRwOi8vc3BoaW54LXVzbTo0MDcwL2FwaS92MS91c2VyL2xvZ2luIiwiaWF0IjoxNjkxOTYwMzgyLCJleHAiOjE2OTQ1NTIzODIsIm5iZiI6MTY5MTk2MDM4MiwianRpIjoiejVvNXhzU2NkODFMOFRFNSJ9.MOb2wAr4AVKUUEIe3kgdJpZE_rqEljOCCznHoEigBu8")
#
# if not credentials:
#     raise AuthFailed()
#
# ws = fansync.Websocket(credentials.token)
# ws.connect()
#
# try:
#     ws.login()
#     ws.provision_token()
# except Exception as e:
#     print(e)
#     ws.close()
#
#
# def run(self):
#     devices: ListDevicesResponse = self.list_devices()
#     for device in devices.data:
#         d: GetDeviceResponse = self.get_device(device)
#         self._devices[d.data.device] = Device(self, device.properties.displayName, d)
#
#

# listDeviceResponse = f.ws_list_devices()
# for i in range(100):
#     time.sleep(0.5)
#     for device in listDeviceResponse.data:
#         f.ws_get_device(device)

# time.sleep(100.0)
# finally:
#     pass
# f.close()

with open("samples/http/info-model.json") as infoModel:
    df: DeviceFactory = DeviceFactory(json.loads(infoModel.read()))

with open("samples/websocket/get_response.json") as getResponse:
    gdr: GetDeviceResponse = GetDeviceResponse(**json.loads(getResponse.read()))
    df.get_device(gdr)
