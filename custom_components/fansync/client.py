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
        self._device_meta: dict[str, dict[str, Any]] = {}
        self._device_profile: dict[str, dict[str, Any]] = {}
        self._status_callback: Callable[[dict[str, Any]], None] | None = None
        self._running: bool = False
        self._recv_lock: threading.Lock = threading.Lock()
        self._recv_thread: threading.Thread | None = None

    async def async_connect(self):
        def _connect():
            session = httpx.Client(verify=self.verify_ssl)
            t0 = time.monotonic()
            # Authenticate over HTTP
            url = "https://fanimation.apps.exosite.io/api:1/session"
            resp = session.post(
                url,
                headers={"Content-Type": "application/json", "charset": "utf-8"},
                json={"email": self.email, "password": self.password},
            )
            resp.raise_for_status()
            token = resp.json()["token"]
            if _LOGGER.isEnabledFor(logging.DEBUG):
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                _LOGGER.debug("http login ms=%d verify_ssl=%s", elapsed_ms, self.verify_ssl)

            # Websocket connect and login
            t1 = time.monotonic()
            ws_opts = {} if self.verify_ssl else {"cert_reqs": ssl.CERT_NONE}
            ws = websocket.WebSocket(sslopt=ws_opts)
            ws.timeout = 10
            ws.connect("wss://fanimation.apps.exosite.io/api:1/phone")
            ws.send(json.dumps({"id": 1, "request": "login", "data": {"token": token}}))
            raw = ws.recv()
            payload = json.loads(raw)
            if not (isinstance(payload, dict) and payload.get("status") == "ok"):
                raise RuntimeError("Websocket login failed")
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("ws connect+login ms=%d", int((time.monotonic() - t1) * 1000))

            # List devices
            ws.send(json.dumps({"id": 2, "request": "lst_device"}))
            raw = ws.recv()
            payload = json.loads(raw)
            devices = payload.get("data") or []
            # Build a strictly typed list of device IDs (strings only)
            _ids: list[str] = []
            meta: dict[str, dict[str, Any]] = {}
            for d in devices:
                if isinstance(d, dict):
                    dev = d.get("device")
                    if isinstance(dev, str) and dev:
                        _ids.append(dev)
                        # Keep full metadata for the device (owner, properties, etc.)
                        meta[dev] = d
            device_ids: list[str] = _ids
            device_id = device_ids[0] if device_ids else None
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("discovered device_ids=%s", device_ids)

            self._http = session
            self._ws = ws
            self._token = token
            self._device_id = device_id
            self._device_ids = device_ids
            self._device_meta = meta
            self._running = True

        await self.hass.async_add_executor_job(_connect)

        # Start background receive loop to push unsolicited updates
        if self._enable_push:

            def _recv_loop():
                timeout_errors = 0
                backoff_sec = 0.5
                max_backoff_sec = 5.0
                while self._running:
                    ws = self._ws
                    if ws is None:
                        time.sleep(0.1)
                        continue
                    # avoid racing with explicit get/set operations
                    acquired = self._recv_lock.acquire(timeout=0.2)
                    if not acquired:
                        continue
                    try:
                        try:
                            raw = ws.recv()
                            timeout_errors = 0
                        except Exception as err:
                            if _LOGGER.isEnabledFor(logging.DEBUG):
                                _LOGGER.debug("recv error=%s", type(err).__name__)
                            # Count consecutive timeouts/closed errors and reconnect after a few
                            if isinstance(
                                err,
                                websocket.WebSocketTimeoutException
                                | websocket.WebSocketConnectionClosedException,
                            ):
                                timeout_errors += 1
                                if timeout_errors >= 3:
                                    self._ws = None
                                    try:
                                        self._ensure_ws_connected()
                                        timeout_errors = 0
                                        backoff_sec = 0.5
                                    except Exception:
                                        time.sleep(backoff_sec)
                                        backoff_sec = min(max_backoff_sec, backoff_sec * 2)
                            time.sleep(0.1)
                            continue
                    finally:
                        self._recv_lock.release()

                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    # Ignore direct responses to our own requests except set when it includes status
                    if payload.get("response") in {"login", "lst_device", "get"}:
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug("ignored frame response=%s", payload.get("response"))
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
        payload = json.loads(raw)
        if not (isinstance(payload, dict) and payload.get("status") == "ok"):
            raise RuntimeError("Websocket login failed")
        self._ws = ws

    async def async_get_status(self, device_id: str | None = None) -> dict[str, Any]:
        def _get():
            t0 = time.monotonic()
            did = device_id or self._device_id
            assert did is not None
            self._ensure_ws_connected()
            assert self._ws is not None
            with self._recv_lock:
                ws: websocket.WebSocket | None = self._ws
                if ws is None:
                    raise RuntimeError("Websocket not connected")
                sent = False
                req_id = 3  # keep stable for compatibility; match responses by id when present
                try:
                    ws.send(json.dumps({"id": req_id, "request": "get", "device": did}))
                    sent = True
                except Exception:
                    sent = False
                if not sent:
                    # reconnect and retry once
                    self._ws = None
                    self._ensure_ws_connected()
                    ws2 = self._ws
                    if ws2 is None:
                        raise RuntimeError("Websocket not connected after reconnect")
                    # mypy may flag this as unreachable; it's a valid retry after reconnect
                    ws2.send(json.dumps({"id": req_id, "request": "get", "device": did}))  # type: ignore[unreachable]
                # Bounded read to find the response
                for _ in range(5):
                    raw = self._ws.recv()
                    payload = json.loads(raw)
                    if isinstance(payload, dict) and payload.get("response") == "get":
                        pid = payload.get("id")
                        if pid is not None and pid != req_id:
                            # different reply; keep waiting
                            continue
                        # Opportunistically cache device profile metadata from get() responses
                        # so we can enrich DeviceInfo/attributes without extra requests.
                        try:
                            data_obj = payload.get("data")
                            if isinstance(data_obj, dict):
                                prof = data_obj.get("profile")
                                if isinstance(prof, dict):
                                    self._device_profile[did] = prof
                        except Exception as exc:
                            if _LOGGER.isEnabledFor(logging.DEBUG):
                                _LOGGER.debug("profile cache failed for %s: %s", did, exc)
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug("get rtt ms=%d", int((time.monotonic() - t0) * 1000))
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
                ws: websocket.WebSocket | None = self._ws
                if ws is None:
                    raise RuntimeError("Websocket not connected")
                sent = False
                try:
                    ws.send(json.dumps(message))
                    sent = True
                except Exception:
                    sent = False
                if not sent:
                    # reconnect and retry once
                    self._ws = None
                    self._ensure_ws_connected()
                    ws2 = self._ws
                    if ws2 is None:
                        raise RuntimeError("Websocket not connected after reconnect")
                    # mypy may flag this as unreachable; it's a valid retry after reconnect
                    ws2.send(json.dumps(message))  # type: ignore[unreachable]
                # Best-effort ack read; ignore errors
                try:
                    raw = self._ws.recv()
                    try:
                        payload = json.loads(raw)
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

        t_total = time.monotonic()
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
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("set total rtt ms=%d", int((time.monotonic() - t_total) * 1000))

    @property
    def device_id(self) -> str | None:
        return self._device_id

    @property
    def device_ids(self) -> list[str]:
        # Fallback to single device if list is empty
        if self._device_ids:
            return list(self._device_ids)
        return [d for d in [self._device_id] if d]

    def device_metadata(self, device_id: str) -> dict[str, Any]:
        return dict(self._device_meta.get(device_id, {}))

    def device_profile(self, device_id: str) -> dict[str, Any]:
        return dict(self._device_profile.get(device_id, {}))

    def set_status_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._status_callback = callback
