# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Trevor Baker, all rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#   http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import json
import logging
import ssl
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
import websocket
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class FanSyncClient:
    def __init__(
        self,
        hass: HomeAssistant,
        email: str,
        password: str,
        verify_ssl: bool = True,
        *,
        enable_push: bool = True,
    ):
        self.hass = hass
        self.email = email
        self.password = password
        self.verify_ssl = verify_ssl
        self._enable_push = enable_push
        self._http: httpx.Client | None = None
        self._ws: websocket.WebSocket | None = None
        self._token: str | None = None
        self._device_id: str | None = None
        self._device_ids: list[str] = []
        self._status_callback: Callable[[dict[str, Any]], None] | None = None
        self._running: bool = False
        self._recv_lock: threading.Lock = threading.Lock()
        self._recv_thread: threading.Thread | None = None

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
            # Build a strictly typed list of device IDs (strings only)
            _ids: list[str] = []
            for d in devices:
                if isinstance(d, dict):
                    dev = d.get("device")
                    if isinstance(dev, str) and dev:
                        _ids.append(dev)
            device_ids: list[str] = _ids
            device_id = device_ids[0] if device_ids else None

            self._http = session
            self._ws = ws
            self._token = token
            self._device_id = device_id
            self._device_ids = device_ids
            self._running = True

        await self.hass.async_add_executor_job(_connect)

        # Start background receive loop to push unsolicited updates
        if self._enable_push:

            def _recv_loop():
                while self._running:
                    ws = self._ws
                    if ws is None:
                        time.sleep(0.1)
                        continue
                    # avoid racing with explicit get/set operations
                    acquired = self._recv_lock.acquire(blocking=False)
                    if not acquired:
                        time.sleep(0.02)
                        continue
                    try:
                        try:
                            raw = ws.recv()
                        except Exception:
                            time.sleep(0.1)
                            continue
                    finally:
                        self._recv_lock.release()

                    try:
                        payload = json.loads(raw if isinstance(raw, str) else raw.decode())
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    # Ignore direct responses to our own requests except set when it includes status
                    if payload.get("response") in {"login", "lst_device", "get"}:
                        continue
                    data = payload.get("data")
                    if isinstance(data, dict) and isinstance(data.get("status"), dict):
                        pushed_status = data["status"]
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug("recv push status keys=%s", list(pushed_status.keys()))
                        if self._status_callback is not None:

                            def _notify(s: dict[str, Any] = pushed_status) -> None:
                                assert self._status_callback is not None
                                self._status_callback(s)

                            self.hass.loop.call_soon_threadsafe(_notify)

            thread = threading.Thread(target=_recv_loop, name="_recv_loop", daemon=True)
            self._recv_thread = thread
            thread.start()

    async def async_disconnect(self):
        # Signal background thread to stop first
        self._running = False
        if self._ws:
            await self.hass.async_add_executor_job(self._ws.close)
            self._ws = None
        # Join background thread if it exists
        thread = self._recv_thread
        if thread is not None and thread.is_alive():
            await self.hass.async_add_executor_job(thread.join, 1.0)
        self._recv_thread = None

    # Internal helper: ensure websocket is connected and logged in (called in executor)
    def _ensure_ws_connected(self) -> None:
        if self._ws is not None:
            return
        if self._http is None:
            raise RuntimeError("HTTP session not initialized")

        token = self._token
        if not token:
            url = "https://fanimation.apps.exosite.io/api:1/session"
            resp = self._http.post(
                url,
                headers={"Content-Type": "application/json", "charset": "utf-8"},
                json={"email": self.email, "password": self.password},
            )
            resp.raise_for_status()
            token = resp.json()["token"]
            self._token = token

        ws_opts = {} if self.verify_ssl else {"cert_reqs": ssl.CERT_NONE}
        ws = websocket.WebSocket(sslopt=ws_opts)
        ws.timeout = 10
        ws.connect("wss://fanimation.apps.exosite.io/api:1/phone")
        ws.send(json.dumps({"id": 1, "request": "login", "data": {"token": token}}))
        raw = ws.recv()
        payload = json.loads(raw if isinstance(raw, str) else raw.decode())
        if not (isinstance(payload, dict) and payload.get("status") == "ok"):
            raise RuntimeError("Websocket login failed")
        self._ws = ws

    async def async_get_status(self, device_id: str | None = None) -> dict[str, Any]:
        def _get():
            did = device_id or self._device_id
            assert did is not None
            self._ensure_ws_connected()
            assert self._ws is not None
            with self._recv_lock:
                try:
                    self._ws.send(json.dumps({"id": 3, "request": "get", "device": did}))
                except Exception:
                    # reconnect and retry once
                    self._ws = None
                    self._ensure_ws_connected()
                    assert self._ws is not None
                    self._ws.send(json.dumps({"id": 3, "request": "get", "device": did}))  # type: ignore[unreachable]
                # Bounded read to find the response
                for _ in range(5):
                    raw = self._ws.recv()
                    payload = json.loads(raw if isinstance(raw, str) else raw.decode())
                    if isinstance(payload, dict) and payload.get("response") == "get":
                        return payload["data"]["status"]
                raise RuntimeError("Get status response not received")

        return await self.hass.async_add_executor_job(_get)

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        def _set():
            did = device_id or self._device_id
            assert did is not None
            self._ensure_ws_connected()
            assert self._ws is not None
            message = {
                "id": 4,
                "request": "set",
                "device": did,
                "data": data,
            }
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("set start d=%s keys=%s", did, list(data.keys()))
            with self._recv_lock:
                try:
                    self._ws.send(json.dumps(message))
                except Exception:
                    # reconnect and retry once
                    self._ws = None
                    self._ensure_ws_connected()
                    assert self._ws is not None
                    self._ws.send(json.dumps(message))  # type: ignore[unreachable]
                # Best-effort ack read; ignore errors
                try:
                    raw = self._ws.recv()
                    try:
                        payload = json.loads(raw if isinstance(raw, str) else raw.decode())
                        if isinstance(payload, dict) and payload.get("response") == "set":
                            d = payload.get("data")
                            if isinstance(d, dict) and isinstance(d.get("status"), dict):
                                if _LOGGER.isEnabledFor(logging.DEBUG):
                                    _LOGGER.debug("set ack includes status d=%s", did)
                                return d["status"]
                    except Exception:
                        pass
                except Exception:
                    return None
            return None

        ack_status = await self.hass.async_add_executor_job(_set)
        # After a successful set, fetch latest status and notify listeners, if any.
        if self._status_callback is not None:
            if isinstance(ack_status, dict):
                status = ack_status
            else:
                status = await self.async_get_status()

            def _notify():
                assert self._status_callback is not None
                self._status_callback(status)

            self.hass.loop.call_soon_threadsafe(_notify)

    @property
    def device_id(self) -> str | None:
        return self._device_id

    @property
    def device_ids(self) -> list[str]:
        # Fallback to single device if list is empty
        if self._device_ids:
            return list(self._device_ids)
        return [d for d in [self._device_id] if d]

    def set_status_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._status_callback = callback
