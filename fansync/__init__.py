# SPDX-License-Identifier: GPL-2.0-only


import json

import httpx
from pydantic import SecretStr

from fansync.exceptions import AuthFailed
from fansync.models import Credentials, LoginResponse, Response
from fansync.websocket import Websocket, WebsocketAuthException


class HttpApi:
    API_URL = "https://fanimation.apps.exosite.io"

    MAX_AUTH_RETRIES = 3

    def __init__(self):
        self._id = 1
        self._status = {}
        self._session = httpx.Client()

        # TODO Move this.  Shouldn't be here.
        # self._device_factory: DeviceFactory = HttpApi._get_device_factory()

    # @staticmethod
    # # TODO We should be able to heavily cache this
    # # TODO Move this
    # def _get_device_factory() -> DeviceFactory:
    #     # GET https://fanimation.apps.exosite.io/api:1/info-model
    #     result: requests.Response = requests.get(FanSync.API_URL + '/api:1/info-model', headers=FanSync._get_headers())
    #
    #     return DeviceFactory(result.json())

    @staticmethod
    def _get_headers(token: SecretStr | None = None):
        headers = {"Content-Type": "application/json", "charset": "utf-8"}

        if token:
            headers["Authorization"] = f"Bearer {token.get_secret_value()}"

        return headers

    def get_session(self, params: Credentials):
        headers = HttpApi._get_headers(params.token)

        url = f"{self.API_URL}/api:1/session"
        print(f"GET {url} ", end="", flush=True)
        result = self._session.get(url, headers=headers)

        if result.status_code != 200:
            raise AuthFailed(f"Token validation return {result.json()}")

        print(f"{result.status_code}")

        response = Response(**json.loads(result.text))
        print(f"{response}")

        return "valid" == response.status

    def post_session(self, email: str, password: str) -> Credentials | None:
        url = f"{self.API_URL}/api:1/session"
        print(f"POST {url} ", end="", flush=True)
        result = self._session.post(
            url, headers=HttpApi._get_headers(), json={"email": email, "password": password}
        )

        print(f"{result.status_code}")

        if result.status_code != 200:
            msg = f"Failed to login, {result.reason}({result.status_code})"
            raise AuthFailed(msg)

        login_response = LoginResponse(**json.loads(result.text))
        return Credentials(id=login_response.id, token=login_response.token)

    # def _get_network_credentials(self, email: str, password: str) -> Optional[Credentials]:
    #     print("GET'ing network credentials")
    #     r = requests.get(self.API_URL + '/api:1/session',
    #                      json=HttpCredentials(email=email, password=password).model_dump_json())
    #
    #     if r.status_code != 200:
    #         msg = f"Failed to login, {r.reason}({r.status_code})"
    #         raise AuthFailed(msg)
    #
    #     ret = r.json()
    #     _id = int(ret["id"])
    #     _token = ret["token"]
    #
    #     print(f"Got login data: {ret}")
    #
    #     return Credentials(id=_id, token=_token)

    def options_session(self):
        options_headers = {
            "access-control-request-method": "GET",
            "access-control-request-headers": "authorization,content-type",
            "origin": "http://localhost",
            "referer": "http://localhost",
        }

        url = f"{self.API_URL}/api:1/session"
        print(f"OPTIONS {url} ", end="", flush=True)
        result = self._session.options(url, headers=options_headers)
        print(f"{result.text}({result.status_code})")
        if result.status_code != 200 or result.text != "OK":
            raise AuthFailed("Failed to set login OPTIONS")

    # def _authenticate(self):
    #     self._optionsSession()
    #     self._getSession()  # Got 403 Forbidden
    #
    #
    #
    # def _optionsSession(self):
    #     pass

    def open(self, email, password):
        # Try and load token from disk. If we can, use it. If we can't then get it from HTTP
        creds = HttpApi._load_cached_credentials()
        # if creds:

        # We do this if we are doing a "cold" auth, not a "warm" auth
        # is_valid = self._get_session_token_is_valid(creds)
        # print(f"Token is{'' if is_valid else ' not'} valid")
        # else:

        if not creds:
            self.options_session()  # Preflight the authentication
            creds = self.post_session(email, password)

        # Our authentication loop
        for i in range(0, HttpApi.MAX_AUTH_RETRIES):
            if not creds:
                raise ValueError("Could not get credentials")

            # Create and login our websocket
            try:
                self._websocket = Websocket(creds.token)
                break

            # Uh-oh, login failed.  Let's regroup here.
            except WebsocketAuthException:
                # Well, websocket couldn't auth.  Try and get a new token?
                creds = self.post_session(email, password)

            if i >= (HttpApi.MAX_AUTH_RETRIES - 1):
                raise AuthFailed()

        # Save the credentials we finally got
        HttpApi._save_cached_credentials(creds)
