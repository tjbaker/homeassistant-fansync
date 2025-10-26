# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from typing import Any

import httpx
import websocket
from homeassistant.core import HomeAssistant


class FanSyncClient:
    def __init__(self, hass: HomeAssistant, email: str, password: str, verify_ssl: bool = True):
        self.hass = hass
        self.email = email
        self.password = password
        self.verify_ssl = verify_ssl
        self._http: httpx.Client | None = None
        self._ws: websocket.WebSocket | None = None
        self._device_id: str | None = None
        self._status_callback: Callable[[dict[str, Any]], None] | None = None

    async def async_connect(self):
        def _connect():
            session = httpx.Client(verify=self.verify_ssl)

            # Authenticate over HTTP
            url = "https://fanimation.apps.exosite.io/api:1/session"
            resp = session.post(
                url,
                headers={"Content-Type": "application/json", "charset": "utf-8"},
                json={"email": self.email, "password": self.password},
            )
            resp.raise_for_status()
            token = resp.json()["token"]

            # Websocket connect and login
            ws_opts = {} if self.verify_ssl else {"cert_reqs": ssl.CERT_NONE}
            ws = websocket.WebSocket(sslopt=ws_opts)
            ws.timeout = 10
            ws.connect("wss://fanimation.apps.exosite.io/api:1/phone")
            ws.send(json.dumps({"id": 1, "request": "login", "data": {"token": token}}))
            raw = ws.recv()
            payload = json.loads(raw if isinstance(raw, str) else raw.decode())
            if not (isinstance(payload, dict) and payload.get("status") == "ok"):
                raise RuntimeError("Websocket login failed")

            # List devices
            ws.send(json.dumps({"id": 2, "request": "lst_device"}))
            raw = ws.recv()
            payload = json.loads(raw if isinstance(raw, str) else raw.decode())
            devices = payload.get("data") or []
            device_id = devices[0]["device"] if devices else None

            self._http = session
            self._ws = ws
            self._device_id = device_id

        await self.hass.async_add_executor_job(_connect)

    async def async_disconnect(self):
        if self._ws:
            await self.hass.async_add_executor_job(self._ws.close)
            self._ws = None

    async def async_get_status(self) -> dict[str, Any]:
        def _get():
            assert self._ws is not None and self._device_id is not None
            self._ws.send(json.dumps({"id": 3, "request": "get", "device": self._device_id}))
            while True:
                raw = self._ws.recv()
                payload = json.loads(raw if isinstance(raw, str) else raw.decode())
                if isinstance(payload, dict) and payload.get("response") == "get":
                    return payload["data"]["status"]

        return await self.hass.async_add_executor_job(_get)

    async def async_set(self, data: dict[str, int]):
        def _set():
            assert self._ws is not None and self._device_id is not None
            message = {
                "id": 4,
                "request": "set",
                "device": self._device_id,
                "data": data,
            }
            self._ws.send(json.dumps(message))
            try:
                self._ws.recv()
            except Exception:
                pass

        await self.hass.async_add_executor_job(_set)
        # After a successful set, fetch latest status and notify listeners, if any.
        if self._status_callback is not None:
            status = await self.async_get_status()

            def _notify():
                assert self._status_callback is not None
                self._status_callback(status)

            self.hass.loop.call_soon_threadsafe(_notify)

    @property
    def device_id(self) -> str | None:
        return self._device_id

    def set_status_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._status_callback = callback
