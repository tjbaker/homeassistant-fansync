# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from homeassistant.core import HomeAssistant

from fansync import HttpApi  # type: ignore[attr-defined]
from fansync.websocket import Websocket  # type: ignore[attr-defined]


class FanSyncClient:
    def __init__(self, hass: HomeAssistant, email: str, password: str, verify_ssl: bool = True):
        self.hass = hass
        self.email = email
        self.password = password
        self.verify_ssl = verify_ssl
        self._http = None
        self._ws = None
        self._device_id: str | None = None
        self._status_callback: Callable[[dict[str, Any]], None] | None = None

    async def async_connect(self):
        def _connect():
            http = HttpApi()
            http._session = httpx.Client(verify=self.verify_ssl)
            creds = http.post_session(self.email, self.password)
            ws = Websocket(creds.token, verify_ssl=self.verify_ssl)
            ws.connect()
            ws.login()
            devices = ws.list_devices()
            device_id = devices.data[0].device if devices.data else None
            self._http = http
            self._ws = ws
            self._device_id = device_id
        await self.hass.async_add_executor_job(_connect)

    async def async_disconnect(self):
        if self._ws:
            await self.hass.async_add_executor_job(self._ws.close)
            self._ws = None

    async def async_get_status(self) -> dict[str, Any]:
        def _get():
            from fansync.models import ListDevicesResponse

            d = ListDevicesResponse.Device(
                device=self._device_id,
                properties=ListDevicesResponse.Properties(
                    displayName="Fan", deviceHasBeenConfigured=True
                ),
            )
            info = self._ws.get_device(d)
            return info.data.status
        return await self.hass.async_add_executor_job(_get)

    async def async_set(self, data: dict[str, int]):
        def _set():
            self._ws.set_device(self._device_id, data)
        await self.hass.async_add_executor_job(_set)
        # After a successful set, fetch the latest status and notify listeners, if any.
        if self._status_callback is not None:
            status = await self.async_get_status()

            def _notify():
                # Ensure callback is executed in HA event loop context
                assert self._status_callback is not None
                self._status_callback(status)

            self.hass.loop.call_soon_threadsafe(_notify)

    @property
    def device_id(self) -> str | None:
        return self._device_id

    def set_status_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback invoked when fresh status is available.

        The callback will be called in the Home Assistant event loop thread.
        """
        self._status_callback = callback
