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

import asyncio
import json
import logging
import ssl
import time
from collections.abc import Callable
from typing import Any

import httpx
import websockets
import websockets.asyncio.client
from homeassistant.core import HomeAssistant
from websockets.protocol import State

from .const import (
    DEFAULT_WS_TIMEOUT_SECS,
    SLOW_CONNECTION_WARNING_MS,
    SLOW_RESPONSE_WARNING_MS,
    WS_FALLBACK_TIMEOUT_SEC,
    WS_LOGIN_RETRY_ATTEMPTS,
    WS_LOGIN_RETRY_BACKOFF_SEC,
    WS_REQUEST_ID_LIST_DEVICES,
    WS_REQUEST_ID_LOGIN,
)
from .metrics import ConnectionMetrics

_LOGGER = logging.getLogger(__name__)


class FanSyncClient:
    """Async WebSocket client for FanSync API.

    Uses websockets library for native async WebSocket support.
    All operations run in the Home Assistant event loop without threading.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        email: str,
        password: str,
        verify_ssl: bool = True,
        *,
        enable_push: bool = True,
        http_timeout_s: int | float | None = None,
        ws_timeout_s: int | float | None = None,
    ):
        self.hass = hass
        self.email = email
        self.password = password
        self.verify_ssl = verify_ssl
        self._enable_push = enable_push
        self._http_timeout_s = http_timeout_s
        self._ws_timeout_s = ws_timeout_s
        self._ssl_context: ssl.SSLContext | None = None
        self._http: httpx.Client | None = None
        # Using ClientConnection (concrete type) instead of ClientProtocol (abstract).
        # websockets.connect() returns ClientConnection, and mypy needs the concrete type.
        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._token: str | None = None
        self._device_id: str | None = None
        self._device_ids: list[str] = []
        self._device_meta: dict[str, dict[str, Any]] = {}
        self._device_profile: dict[str, dict[str, Any]] = {}
        self._status_callback: Callable[[dict[str, Any]], None] | None = None
        self._running: bool = False
        self._recv_task: asyncio.Task | None = None
        # Message routing: map request ID to Future for async_get_status/async_set
        self._pending_requests: dict[int, asyncio.Future] = {}
        # Start at 3 to avoid collision with hardcoded LOGIN(1) and LIST_DEVICES(2)
        self._next_request_id: int = 3
        self._request_id_lock = asyncio.Lock()
        self.metrics = ConnectionMetrics()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context for WebSocket connections.

        This is synchronous and performs blocking I/O internally
        (ssl.create_default_context loads certificates and verify paths),
        so it must be called via hass.async_add_executor_job.
        """
        ssl_context = ssl.create_default_context()
        if not self.verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context

    async def async_connect(self):
        """Connect to FanSync cloud API and authenticate."""
        t0 = time.monotonic()

        # HTTP authentication
        timeout = None
        if self._http_timeout_s is not None:
            timeout_value = float(self._http_timeout_s)
            timeout = httpx.Timeout(
                connect=timeout_value,
                read=timeout_value,
                write=timeout_value,
                pool=timeout_value,
            )
        self._http = httpx.Client(verify=self.verify_ssl, timeout=timeout)

        url = "https://fanimation.apps.exosite.io/api:1/session"
        resp = self._http.post(
            url,
            headers={"Content-Type": "application/json", "charset": "utf-8"},
            json={"email": self.email, "password": self.password},
        )
        resp.raise_for_status()
        token = resp.json()["token"]
        self._token = token

        if _LOGGER.isEnabledFor(logging.DEBUG):
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            _LOGGER.debug("http login ms=%d verify_ssl=%s", elapsed_ms, self.verify_ssl)

        # WebSocket connection with retries
        t1 = time.monotonic()
        ws_timeout = (
            float(self._ws_timeout_s) if self._ws_timeout_s is not None else WS_FALLBACK_TIMEOUT_SEC
        )

        # Create SSL context in executor to avoid blocking event loop (cached after first call)
        if self._ssl_context is None:
            self._ssl_context = await self.hass.async_add_executor_job(self._create_ssl_context)

        ws = None
        for attempt_idx in range(WS_LOGIN_RETRY_ATTEMPTS):
            try:
                ws = await asyncio.wait_for(
                    websockets.connect(
                        "wss://fanimation.apps.exosite.io/api:1/phone",
                        ssl=self._ssl_context,
                    ),
                    timeout=ws_timeout,
                )
                # Type narrowing for mypy: websockets.connect() never returns None,
                # it raises an exception on failure. This assert is purely for type checking
                # and cannot fail at runtime (if it does, there's a bug in websockets library).
                assert ws is not None
                # Login
                await asyncio.wait_for(
                    ws.send(
                        json.dumps(
                            {
                                "id": WS_REQUEST_ID_LOGIN,
                                "request": "login",
                                "data": {"token": token},
                            }
                        )
                    ),
                    timeout=ws_timeout,
                )
                raw = await asyncio.wait_for(ws.recv(), timeout=ws_timeout)
                payload = json.loads(raw)
                if not (isinstance(payload, dict) and payload.get("status") == "ok"):
                    raise RuntimeError("WebSocket login failed")
                break
            except Exception as exc:
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug(
                        "ws initial connect/login failed (%s), attempt %d/%d",
                        type(exc).__name__,
                        attempt_idx + 1,
                        WS_LOGIN_RETRY_ATTEMPTS,
                    )
                if ws:
                    try:
                        await ws.close()
                    except Exception as cleanup_exc:
                        # Ignore errors during cleanup after failed connection attempt
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug(
                                "ws.close() cleanup failed (%s): %s",
                                type(cleanup_exc).__name__,
                                cleanup_exc,
                            )
                    ws = None
                # Retry for transient errors
                transient = isinstance(exc, TimeoutError | asyncio.TimeoutError | OSError)
                if transient and (attempt_idx + 1 < WS_LOGIN_RETRY_ATTEMPTS):
                    await asyncio.sleep(WS_LOGIN_RETRY_BACKOFF_SEC)
                else:
                    raise

        if ws is None:
            _LOGGER.error(
                "WebSocket connection failed after %d attempts. "
                "Check network connectivity and Fanimation cloud service status.",
                WS_LOGIN_RETRY_ATTEMPTS,
            )
            raise RuntimeError("WebSocket connection failed after retry attempts")

        self._ws = ws
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("ws connect+login ms=%d", int((time.monotonic() - t1) * 1000))

        # List devices
        try:
            await asyncio.wait_for(
                ws.send(json.dumps({"id": WS_REQUEST_ID_LIST_DEVICES, "request": "lst_device"})),
                timeout=ws_timeout,
            )
            raw = await asyncio.wait_for(ws.recv(), timeout=ws_timeout)
            payload = json.loads(raw)
            devices = payload.get("data") or []
        except Exception as exc:
            _LOGGER.error("Failed to fetch device list: %s", type(exc).__name__)
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("Device list error details: %s", exc)
            raise

        # Build device list
        _ids: list[str] = []
        meta: dict[str, dict[str, Any]] = {}
        for d in devices:
            if isinstance(d, dict):
                dev = d.get("device")
                if isinstance(dev, str) and dev:
                    _ids.append(dev)
                    meta[dev] = d
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug(
                            "device metadata cached: device_id=%s owner=%s",
                            dev,
                            d.get("owner", "unknown"),
                        )

        self._device_ids = _ids
        self._device_id = _ids[0] if _ids else None
        self._device_meta = meta
        self._running = True
        self.metrics.is_connected = True

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("discovered device_ids=%s", self._device_ids)

        # Log total connection time
        total_connect_ms = (time.monotonic() - t0) * 1000
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("total connection time: %.0f ms", total_connect_ms)
        if total_connect_ms > SLOW_CONNECTION_WARNING_MS:
            _LOGGER.info(
                "FanSync cloud connection took %.1f seconds. "
                "Slow connection may affect integration performance",
                total_connect_ms / 1000,
            )

        # Start background receive loop (required for message routing)
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def async_disconnect(self):
        """Disconnect from FanSync cloud API."""
        self._running = False
        self.metrics.is_connected = False

        # Cancel receive task
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                # CancelledError is raised by self._recv_task.cancel() above.
                # This is the expected completion path during graceful shutdown.
                pass
            self._recv_task = None

        # Close WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception as exc:
                # Ignore errors during WebSocket close; log for diagnostics
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("WebSocket close failed: %s: %s", type(exc).__name__, exc)
            self._ws = None

        # Close HTTP client
        if self._http:
            try:
                self._http.close()
            except Exception as exc:
                # Ignore errors closing HTTP client; log for diagnostics
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("HTTP client close failed: %s: %s", type(exc).__name__, exc)
            self._http = None

    async def _recv_loop(self):
        """Background task to receive push updates from WebSocket."""
        timeout_errors = 0
        backoff_sec = 0.5
        max_backoff_sec = 5.0

        while self._running:
            ws = self._ws
            if ws is None:
                await asyncio.sleep(0.1)
                continue

            try:
                ws_timeout = (
                    float(self._ws_timeout_s)
                    if self._ws_timeout_s is not None
                    else WS_FALLBACK_TIMEOUT_SEC
                )
                raw = await asyncio.wait_for(ws.recv(), timeout=ws_timeout)
                timeout_errors = 0
                backoff_sec = 0.5

                # Process message
                try:
                    payload = json.loads(raw)
                except Exception as parse_err:
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug(
                            "recv: invalid JSON, skipping (error=%s, raw=%s...)",
                            type(parse_err).__name__,
                            raw[:100] if isinstance(raw, str) else str(raw)[:100],
                        )
                    continue

                if not isinstance(payload, dict):
                    continue

                # Route responses to pending requests (async_get_status, async_set)
                request_id = payload.get("id")
                if request_id is not None and request_id in self._pending_requests:
                    future = self._pending_requests.pop(request_id)
                    if not future.done():
                        future.set_result(payload)
                    continue

                # Process push updates (responses without request ID and with status data)
                data = payload.get("data")
                if isinstance(data, dict) and isinstance(data.get("status"), dict):
                    pushed_status = data["status"]
                    self.metrics.record_push_update()
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug("recv push status keys=%s", list(pushed_status.keys()))
                    if self._status_callback is not None:
                        # Use call_soon_threadsafe even though we're in the event loop to ensure
                        # the callback is invoked in a thread-safe manner. This is Home Assistant
                        # best practice for callbacks that may interact with coordinator state.
                        self.hass.loop.call_soon_threadsafe(self._status_callback, pushed_status)

            except TimeoutError:
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("recv error=TimeoutError")
                timeout_errors += 1
                if timeout_errors >= 3:
                    # Reconnect after consecutive timeouts
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug(
                            "triggering reconnect after %d consecutive errors",
                            timeout_errors,
                        )
                    try:
                        await self._ensure_ws_connected()
                        timeout_errors = 0
                        backoff_sec = 0.5
                        self.metrics.record_reconnect()
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug("reconnect successful, backoff reset")
                    except Exception as reconnect_err:
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug(
                                "reconnect failed: %s, backoff=%.1fs",
                                type(reconnect_err).__name__,
                                backoff_sec,
                            )
                        await asyncio.sleep(backoff_sec)
                        backoff_sec = min(max_backoff_sec, backoff_sec * 2)
                else:
                    # Brief sleep before retry
                    await asyncio.sleep(0.1)

            except Exception as err:
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("recv error=%s", type(err).__name__)
                # Connection closed, trigger reconnect
                try:
                    await self._ensure_ws_connected()
                    timeout_errors = 0
                    backoff_sec = 0.5
                    self.metrics.record_reconnect()
                except Exception:
                    await asyncio.sleep(backoff_sec)
                    backoff_sec = min(max_backoff_sec, backoff_sec * 2)

        # Loop exited (client disconnected)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("_recv_loop exited (client disconnected)")

    async def _ensure_ws_connected(self) -> None:
        """Ensure WebSocket is connected and authenticated."""
        # If WebSocket is already connected and open, nothing to do
        if self._ws is not None and self._ws.state == State.OPEN:
            return

        # Close old WebSocket if it exists
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception as exc:
                # Ignore errors closing old WebSocket during reconnect
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Error closing old WebSocket: %s: %s", type(exc).__name__, exc)

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("_ensure_ws_connected: reconnecting websocket")

        # Refresh token if needed
        if not self._token and self._http:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("_ensure_ws_connected: refreshing auth token")
            url = "https://fanimation.apps.exosite.io/api:1/session"
            resp = self._http.post(
                url,
                headers={"Content-Type": "application/json", "charset": "utf-8"},
                json={"email": self.email, "password": self.password},
            )
            resp.raise_for_status()
            self._token = resp.json()["token"]

        # Reconnect WebSocket
        ws_timeout = (
            float(self._ws_timeout_s) if self._ws_timeout_s is not None else WS_FALLBACK_TIMEOUT_SEC
        )

        # Create SSL context in executor to avoid blocking event loop (cached after first call)
        if self._ssl_context is None:
            self._ssl_context = await self.hass.async_add_executor_job(self._create_ssl_context)

        ws = await asyncio.wait_for(
            websockets.connect(
                "wss://fanimation.apps.exosite.io/api:1/phone",
                ssl=self._ssl_context,
            ),
            timeout=ws_timeout,
        )

        # Login
        await asyncio.wait_for(
            ws.send(
                json.dumps(
                    {
                        "id": WS_REQUEST_ID_LOGIN,
                        "request": "login",
                        "data": {"token": self._token},
                    }
                )
            ),
            timeout=ws_timeout,
        )
        raw = await asyncio.wait_for(ws.recv(), timeout=ws_timeout)
        payload = json.loads(raw)
        if not (isinstance(payload, dict) and payload.get("status") == "ok"):
            raise RuntimeError("WebSocket login failed")

        self._ws = ws
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("_ensure_ws_connected: websocket reconnected successfully")

    async def async_get_status(self, device_id: str | None = None) -> dict[str, Any]:
        """Get current status of a device."""
        t0 = time.monotonic()
        did = device_id or self._device_id
        if not did:
            raise RuntimeError("No device ID available")

        await self._ensure_ws_connected()
        ws = self._ws
        if ws is None:
            raise RuntimeError("WebSocket not connected")

        ws_timeout = (
            float(self._ws_timeout_s) if self._ws_timeout_s is not None else WS_FALLBACK_TIMEOUT_SEC
        )

        # Allocate a unique request ID
        async with self._request_id_lock:
            request_id = self._next_request_id
            self._next_request_id += 1

        # Register a Future for this request
        future: asyncio.Future[dict[str, Any]] = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            # Send get request
            await asyncio.wait_for(
                ws.send(
                    json.dumps(
                        {
                            "id": request_id,
                            "request": "get",
                            "device": did,
                        }
                    )
                ),
                timeout=ws_timeout,
            )

            # Wait for _recv_loop to fulfill the Future
            payload = await asyncio.wait_for(future, timeout=ws_timeout)

            # Cache device profile if present
            try:
                data_obj = payload.get("data")
                if isinstance(data_obj, dict):
                    prof = data_obj.get("profile")
                    if isinstance(prof, dict):
                        self._device_profile[did] = prof
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug(
                                "profile cached for %s: keys=%s",
                                did,
                                list(prof.keys()),
                            )
            except Exception as exc:
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("profile cache failed for %s: %s", did, exc)

            latency_ms = (time.monotonic() - t0) * 1000
            self.metrics.record_command(success=True, latency_ms=latency_ms)
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("get rtt ms=%.0f device=%s", latency_ms, did)

            # Warn about slow responses
            if latency_ms > SLOW_RESPONSE_WARNING_MS:
                _LOGGER.warning(
                    "Slow response from FanSync cloud: %.1f seconds for device %s. "
                    "This indicates high latency in Fanimation's cloud service. "
                    "Commands still work but status updates may be delayed. "
                    "If timeouts persist, increase WebSocket timeout in Options, "
                    "though cloud delays may remain",
                    latency_ms / 1000,
                    did,
                )

            return payload["data"]["status"]

        except TimeoutError as exc:
            self.metrics.record_command(success=False)
            raise TimeoutError(f"WebSocket recv timed out: {exc}") from exc
        except Exception:
            self.metrics.record_command(success=False)
            raise
        finally:
            # Clean up pending request if not already removed
            self._pending_requests.pop(request_id, None)

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None):
        """Set device parameters."""
        t_total = time.monotonic()
        did = device_id or self._device_id
        if not did:
            raise RuntimeError("No device ID available")

        await self._ensure_ws_connected()
        ws = self._ws
        if ws is None:
            raise RuntimeError("WebSocket not connected")

        ws_timeout = (
            float(self._ws_timeout_s) if self._ws_timeout_s is not None else WS_FALLBACK_TIMEOUT_SEC
        )

        # Allocate a unique request ID
        async with self._request_id_lock:
            request_id = self._next_request_id
            self._next_request_id += 1

        # Register a Future for this request
        future: asyncio.Future[dict[str, Any]] = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("set start d=%s keys=%s", did, list(data.keys()))

            # Send set request
            await asyncio.wait_for(
                ws.send(
                    json.dumps(
                        {
                            "id": request_id,
                            "request": "set",
                            "device": did,
                            "data": data,
                        }
                    )
                ),
                timeout=ws_timeout,
            )

            # Wait for acknowledgment from _recv_loop
            payload = await asyncio.wait_for(future, timeout=ws_timeout)

            latency_ms = (time.monotonic() - t_total) * 1000
            self.metrics.record_command(success=True, latency_ms=latency_ms)

            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("set total rtt ms=%.0f device=%s", latency_ms, did)

            # Warn about slow responses
            if latency_ms > SLOW_RESPONSE_WARNING_MS:
                _LOGGER.warning(
                    "Slow response from FanSync cloud: %.1f seconds for device %s. "
                    "This indicates high latency in Fanimation's cloud service. "
                    "Commands still work but status updates may be delayed. "
                    "If timeouts persist, increase WebSocket timeout in Options, "
                    "though cloud delays may remain",
                    latency_ms / 1000,
                    did,
                )

            # Check if the acknowledgment contains updated status and trigger callback
            ack_data = payload.get("data")
            if isinstance(ack_data, dict) and isinstance(ack_data.get("status"), dict):
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("set ack with status keys=%s", list(ack_data["status"].keys()))
                # Trigger status callback with the acknowledged status
                if self._status_callback is not None:
                    self.hass.loop.call_soon_threadsafe(self._status_callback, ack_data["status"])

        except Exception:
            self.metrics.record_command(success=False)
            raise
        finally:
            # Clean up pending request if not already removed
            self._pending_requests.pop(request_id, None)

    def apply_timeouts(
        self,
        http_timeout_s: int | float | None = None,
        ws_timeout_s: int | float | None = None,
    ) -> None:
        """Apply timeout changes at runtime.

        This method is synchronous and intended to be called via
        hass.async_add_executor_job() from the event loop. It uses
        synchronous httpx.Client.close() which is safe in this context.
        """
        if http_timeout_s is not None:
            self._http_timeout_s = http_timeout_s
            if self._http is not None:
                try:
                    # Using synchronous close() for httpx.Client (not AsyncClient).
                    # In production, apply_timeouts() is called via hass.async_add_executor_job()
                    # from __init__.py, so it runs in a thread pool where blocking is safe.
                    # httpx.Client.close() is also non-blocking (just releases resources).
                    self._http.close()
                except Exception as exc:
                    # Ignore errors closing previous HTTP client; log for diagnostics
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug(
                            "Error closing previous HTTP client: %s: %s", type(exc).__name__, exc
                        )
                timeout_value = float(http_timeout_s)
                timeout = httpx.Timeout(
                    connect=timeout_value,
                    read=timeout_value,
                    write=timeout_value,
                    pool=timeout_value,
                )
                self._http = httpx.Client(verify=self.verify_ssl, timeout=timeout)
        if ws_timeout_s is not None:
            self._ws_timeout_s = ws_timeout_s

    @property
    def device_id(self) -> str | None:
        return self._device_id

    @property
    def device_ids(self) -> list[str]:
        if self._device_ids:
            return list(self._device_ids)
        return [d for d in [self._device_id] if d]

    def device_metadata(self, device_id: str) -> dict[str, Any]:
        return dict(self._device_meta.get(device_id, {}))

    def device_profile(self, device_id: str) -> dict[str, Any]:
        return dict(self._device_profile.get(device_id, {}))

    def set_status_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._status_callback = callback

    def ws_timeout_seconds(self) -> int:
        """Expose effective WebSocket timeout for coordinators."""
        try:
            if self._ws_timeout_s is not None:
                return int(self._ws_timeout_s)
        except (TypeError, ValueError, AttributeError):
            pass
        return int(DEFAULT_WS_TIMEOUT_SECS)
