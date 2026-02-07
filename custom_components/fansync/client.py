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
import base64
import json
import logging
import ssl
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import websockets
import websockets.asyncio.client
from homeassistant.core import HomeAssistant
from websockets.protocol import State

from .const import (
    DEFAULT_HTTP_TIMEOUT_SECS,
    DEFAULT_WS_TIMEOUT_SECS,
    PUSH_LOG_EVERY,
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


class FanSyncConfigError(Exception):
    """Non-retryable configuration error."""

    ...


class FanSyncClient:
    """Async WebSocket client for FanSync API.

    Uses websockets library for native async WebSocket support.
    All operations run in the Home Assistant event loop without threading.
    RuntimeError indicates transient remote failures; use FanSyncConfigError
    for deterministic misconfiguration.
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
        self._push_count: int = 0
        self._last_push_monotonic: float | None = None
        self._last_push_utc: str | None = None
        self._last_push_keys: list[str] | None = None
        self._last_push_key_count: int | None = None
        self._last_push_by_device: dict[str, dict[str, Any]] = {}
        self._last_set_by_device: dict[str, dict[str, Any]] = {}
        self._last_get_by_device: dict[str, dict[str, Any]] = {}
        self._last_request_id: int | None = None
        self._last_reconnect_utc: str | None = None
        self._last_recv_error: str | None = None
        self._last_recv_error_utc: str | None = None
        self._command_history: list[dict[str, Any]] = []
        self._command_history_max = 50
        # Message routing: map request ID to Future for async_get_status/async_set
        self._pending_requests: dict[int, asyncio.Future[dict[str, Any]]] = {}
        # Start at 3 to avoid collision with hardcoded LOGIN(1) and LIST_DEVICES(2).
        # LOGIN and LIST_DEVICES remain hardcoded for connection bootstrap before
        # the request routing system is active. Dynamic allocation is used for
        # async_get_status and async_set which rely on _pending_requests routing.
        self._next_request_id: int = 3
        self._request_id_lock = asyncio.Lock()
        self.metrics = ConnectionMetrics()
        # Diagnostics tracking
        self._last_http_login_ms: float | None = None
        self._last_ws_connect_ms: float | None = None  # WebSocket handshake only
        self._last_ws_login_ms: float | None = None  # Full connect + login time
        self._last_ws_login_wait_ms: float | None = None  # Time waiting for login response
        self._token_refresh_count: int = 0
        self._last_login_response: dict[str, Any] | None = None  # Last login response (sanitized)
        self._connection_failures: list[dict[str, Any]] = []
        self._max_failure_history = 10

    def _record_connection_failure(
        self,
        stage: str,
        error_type: str,
        elapsed_ms: float,
        attempt: int | None = None,
    ) -> None:
        """Record a connection failure for diagnostics."""
        failure_record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "stage": stage,  # "http_login", "ws_connect", "ws_login", etc.
            "error_type": error_type,
            "elapsed_ms": round(elapsed_ms, 2),
        }
        if attempt is not None:
            failure_record["attempt"] = attempt

        self._connection_failures.append(failure_record)
        # Keep only the most recent failures
        if len(self._connection_failures) > self._max_failure_history:
            self._connection_failures.pop(0)

    def _record_command_history(
        self,
        *,
        command: str,
        device_id: str,
        keys: list[str],
        request_id: int | None,
        success: bool,
        latency_ms: float | None,
        error_type: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "command": command,
            "device_id": device_id,
            "keys": keys,
            "success": success,
            "request_id": request_id,
            "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
        }
        if error_type:
            entry["error_type"] = error_type
        self._command_history.append(entry)
        if len(self._command_history) > self._command_history_max:
            self._command_history.pop(0)

    def _record_last_get(
        self,
        *,
        device_id: str,
        request_id: int | None,
        success: bool,
        latency_ms: float,
        error_type: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "request_id": request_id,
            "success": success,
            "latency_ms": round(latency_ms, 2),
        }
        if error_type:
            entry["error_type"] = error_type
        self._last_get_by_device[device_id] = entry

    def _record_last_set(
        self,
        *,
        device_id: str,
        keys: list[str],
        request_id: int | None,
        success: bool,
        latency_ms: float,
        error_type: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "keys": keys,
            "request_id": request_id,
            "success": success,
            "latency_ms": round(latency_ms, 2),
        }
        if error_type:
            entry["error_type"] = error_type
        self._last_set_by_device[device_id] = entry

    def _extract_push_status(
        self, payload: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        data = payload.get("data")
        if not isinstance(data, dict):
            return None, None

        push_device = payload.get("device")
        if not isinstance(push_device, str):
            push_device = data.get("device")
        if not isinstance(push_device, str):
            push_device = None

        status = data.get("status")
        if isinstance(status, dict):
            return status, push_device

        changes = data.get("changes")
        if isinstance(changes, dict):
            change_status = changes.get("status")
            if isinstance(change_status, dict):
                return change_status, push_device

        return None, None

    def _parse_token_metadata(self) -> dict[str, Any]:
        """Extract JWT token metadata without exposing the token itself."""
        if not self._token:
            return {}

        try:
            # JWT format: header.payload.signature
            parts = self._token.split(".")
            if len(parts) != 3:
                return {"format_valid": False}

            # Decode payload (add padding if needed for base64)
            payload = parts[1]
            padding = (4 - len(payload) % 4) % 4
            if padding:
                payload += "=" * padding

            decoded = base64.urlsafe_b64decode(payload)
            claims = json.loads(decoded)

            # Extract non-sensitive metadata
            issuer = claims.get("iss")
            metadata = {
                "format_valid": True,
                "length": len(self._token),
                "issued_at": claims.get("iat"),
                "expires_at": claims.get("exp"),
                "issuer": issuer.split("/")[-1] if issuer else None,
            }

            # Calculate expiry info if available
            if "exp" in claims:
                exp_time = claims["exp"]
                now = time.time()
                metadata["expires_in_seconds"] = int(exp_time - now)
                metadata["is_expired"] = exp_time < now

            return metadata
        except Exception as exc:
            return {
                "format_valid": False,
                "parse_error": type(exc).__name__,
            }

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

    def _create_http_client(self, timeout: httpx.Timeout | None) -> httpx.Client:
        """Create HTTP client for API authentication.

        This is synchronous and performs blocking I/O internally
        (httpx.Client creation loads SSL certificates via ssl.load_verify_locations),
        so it must be called via hass.async_add_executor_job.
        """
        return httpx.Client(verify=self.verify_ssl, timeout=timeout)

    def _http_login(self, url: str, headers: dict[str, str], json_data: dict[str, Any]) -> str:
        """Perform HTTP login request (blocking I/O).

        This performs blocking HTTP I/O and must be called via
        hass.async_add_executor_job from async code.

        Returns the authentication token.
        """
        if self._http is None:
            raise RuntimeError("HTTP client not initialized")
        resp = self._http.post(url, headers=headers, json=json_data)
        resp.raise_for_status()
        return resp.json()["token"]

    async def async_connect(self) -> None:
        """Connect to FanSync cloud API and authenticate."""
        t0 = time.monotonic()

        # HTTP authentication (run in executor to avoid blocking event loop)
        http_start = time.monotonic()
        timeout = None
        if self._http_timeout_s is not None:
            timeout_value = float(self._http_timeout_s)
            timeout = httpx.Timeout(
                connect=timeout_value,
                read=timeout_value,
                write=timeout_value,
                pool=timeout_value,
            )

        # Create HTTP client in thread pool (avoids blocking on SSL cert loading)
        self._http = await self.hass.async_add_executor_job(self._create_http_client, timeout)

        # Perform HTTP login in thread pool (blocking I/O)
        url = "https://fanimation.apps.exosite.io/api:1/session"
        headers = {"Content-Type": "application/json", "charset": "utf-8"}
        json_data = {"email": self.email, "password": self.password}

        try:
            token = await self.hass.async_add_executor_job(
                self._http_login, url, headers, json_data
            )
            self._token = token
            self._last_http_login_ms = (time.monotonic() - http_start) * 1000
        except Exception as exc:
            elapsed = (time.monotonic() - http_start) * 1000
            self._record_connection_failure("http_login", type(exc).__name__, elapsed)
            raise

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "http login ms=%.0f verify_ssl=%s",
                self._last_http_login_ms,
                self.verify_ssl,
            )

        # WebSocket connection with retries
        ws_start = time.monotonic()
        ws_timeout = (
            float(self._ws_timeout_s) if self._ws_timeout_s is not None else WS_FALLBACK_TIMEOUT_SEC
        )

        # Create SSL context in executor to avoid blocking event loop (cached after first call)
        if self._ssl_context is None:
            self._ssl_context = await self.hass.async_add_executor_job(self._create_ssl_context)

        ws = None
        last_ws_error: Exception | None = None
        for attempt_idx in range(WS_LOGIN_RETRY_ATTEMPTS):
            ws_phase = "connect"
            ws_attempt_start = time.monotonic()
            try:
                # Track WebSocket handshake timing separately
                ws_connect_start = time.monotonic()
                ws = await asyncio.wait_for(
                    websockets.connect(
                        "wss://fanimation.apps.exosite.io/api:1/phone",
                        ssl=self._ssl_context,
                        compression=None,
                    ),
                    timeout=ws_timeout,
                )
                self._last_ws_connect_ms = (time.monotonic() - ws_connect_start) * 1000

                # Type narrowing for mypy: websockets.connect() never returns None,
                # it raises an exception on failure. This assert is purely for type checking
                # and cannot fail at runtime (if it does, there's a bug in websockets library).
                assert ws is not None

                # Login - track send + response wait time
                ws_login_start = time.monotonic()
                ws_phase = "login_send"
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
                ws_phase = "login_recv"
                raw = await asyncio.wait_for(ws.recv(), timeout=ws_timeout)
                self._last_ws_login_wait_ms = (time.monotonic() - ws_login_start) * 1000

                payload = json.loads(raw)
                # Store sanitized login response for diagnostics
                self._last_login_response = {
                    "status": payload.get("status"),
                    "response": payload.get("response"),
                    "has_data": "data" in payload,
                    "timestamp": datetime.now(UTC).isoformat(),
                }

                if not (isinstance(payload, dict) and payload.get("status") == "ok"):
                    raise RuntimeError("WebSocket login failed")
                # Success!
                self._last_ws_login_ms = (time.monotonic() - ws_start) * 1000
                break
            except Exception as exc:
                last_ws_error = exc
                elapsed = (time.monotonic() - ws_attempt_start) * 1000
                self._record_connection_failure(
                    "ws_login",
                    type(exc).__name__,
                    elapsed,
                    attempt=attempt_idx + 1,
                )
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug(
                        "ws initial connect/login failed (%s), attempt %d/%d, phase=%s, "
                        "elapsed_ms=%.0f",
                        type(exc).__name__,
                        attempt_idx + 1,
                        WS_LOGIN_RETRY_ATTEMPTS,
                        ws_phase,
                        elapsed,
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
                transient = isinstance(exc, TimeoutError | OSError)
                if transient and (attempt_idx + 1 < WS_LOGIN_RETRY_ATTEMPTS):
                    await asyncio.sleep(WS_LOGIN_RETRY_BACKOFF_SEC)
                else:
                    raise

        if ws is None:
            _LOGGER.error(
                "WebSocket connection failed after %d attempts. "
                "Check network connectivity and Fanimation cloud service status. "
                "Last error: %s",
                WS_LOGIN_RETRY_ATTEMPTS,
                type(last_ws_error).__name__ if last_ws_error else "Unknown",
            )
            raise RuntimeError("WebSocket connection failed after retry attempts")

        self._ws = ws
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("ws connect+login ms=%.0f", self._last_ws_login_ms)

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
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "device discovery summary ids=%d meta=%d",
                len(self._device_ids),
                len(self._device_meta),
            )
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

        # Start background receive loop.
        # This is required for both request/response routing via the Future-based
        # message routing system and for push updates from the server.
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def async_disconnect(self) -> None:
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

    async def _recv_loop(self) -> None:
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
                    try:
                        future.set_result(payload)
                    except asyncio.InvalidStateError:
                        # Future was cancelled or already completed before set_result().
                        # This can happen if request timed out just before response arrived.
                        pass
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug(
                            "recv response id=%s keys=%s",
                            request_id,
                            list(payload.keys()) if isinstance(payload, dict) else [],
                        )
                    # Skip push update processing for request/response pairs.
                    # Status callbacks for set acks are handled in async_set to avoid duplication.
                    continue

                # Process push updates (responses without request ID and with status data)
                pushed_status, push_device = self._extract_push_status(payload)
                if pushed_status is not None:
                    if not push_device:
                        push_device = "unknown"
                    self.metrics.record_push_update()
                    self._push_count += 1
                    self._last_push_monotonic = time.monotonic()
                    self._last_push_utc = datetime.now(UTC).isoformat()
                    self._last_push_keys = sorted(list(pushed_status.keys()))
                    self._last_push_key_count = len(pushed_status)
                    self._last_push_by_device[push_device] = {
                        "utc": self._last_push_utc,
                        "key_count": self._last_push_key_count,
                        "keys": self._last_push_keys,
                    }
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug("recv push status keys=%s", list(pushed_status.keys()))
                        if self._push_count % PUSH_LOG_EVERY == 0:
                            _LOGGER.debug(
                                "push heartbeat count=%d device=%s keys=%d",
                                self._push_count,
                                push_device or self._device_id or "unknown",
                                len(pushed_status),
                            )
                    if self._status_callback is not None:
                        # Use call_soon since we are in the event loop.
                        # This avoids the overhead of thread-safe locking.
                        self.hass.loop.call_soon(self._status_callback, pushed_status)

            except TimeoutError:
                self._last_recv_error = "TimeoutError"
                self._last_recv_error_utc = datetime.now(UTC).isoformat()
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug(
                        "recv error=TimeoutError timeouts=%d backoff=%.1fs timeout_s=%.0f",
                        timeout_errors + 1,
                        backoff_sec,
                        ws_timeout,
                    )
                timeout_errors += 1
                if timeout_errors >= 3:
                    # Reconnect after consecutive timeouts
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug(
                            "triggering reconnect after %d consecutive errors backoff=%.1fs",
                            timeout_errors,
                            backoff_sec,
                        )
                    try:
                        await self._ensure_ws_connected()
                        timeout_errors = 0
                        backoff_sec = 0.5
                        self.metrics.record_reconnect()
                        self._last_reconnect_utc = datetime.now(UTC).isoformat()
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug("reconnect successful, backoff reset")
                    except Exception as reconnect_err:
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug(
                                "reconnect failed: %s, backoff=%.1fs err=%s",
                                type(reconnect_err).__name__,
                                backoff_sec,
                                reconnect_err,
                            )
                        await asyncio.sleep(backoff_sec)
                        backoff_sec = min(max_backoff_sec, backoff_sec * 2)
                else:
                    # Brief sleep before retry
                    await asyncio.sleep(0.1)

            except Exception as err:
                self._last_recv_error = type(err).__name__
                self._last_recv_error_utc = datetime.now(UTC).isoformat()
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("recv error=%s err=%s", type(err).__name__, err)
                # Connection closed, trigger reconnect
                try:
                    await self._ensure_ws_connected()
                    timeout_errors = 0
                    backoff_sec = 0.5
                    self.metrics.record_reconnect()
                    self._last_reconnect_utc = datetime.now(UTC).isoformat()
                except Exception as reconnect_err:
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug(
                            "reconnect failed after recv error: %s backoff=%.1fs err=%s",
                            type(reconnect_err).__name__,
                            backoff_sec,
                            reconnect_err,
                        )
                    await asyncio.sleep(backoff_sec)
                    backoff_sec = min(max_backoff_sec, backoff_sec * 2)

        # Loop exited (client disconnected)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("_recv_loop exited (client disconnected)")

    async def _ensure_ws_connected(self) -> None:
        """Ensure WebSocket is connected and authenticated."""
        reconnect_start = time.monotonic()
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

        # Refresh token if needed (run in executor to avoid blocking event loop)
        if not self._token and self._http:
            self._token_refresh_count += 1
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "_ensure_ws_connected: refreshing auth token (attempt %d)",
                    self._token_refresh_count,
                )
            refresh_start = time.monotonic()
            url = "https://fanimation.apps.exosite.io/api:1/session"
            headers = {"Content-Type": "application/json", "charset": "utf-8"}
            json_data = {"email": self.email, "password": self.password}
            self._token = await self.hass.async_add_executor_job(
                self._http_login, url, headers, json_data
            )
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "_ensure_ws_connected: token refresh ms=%.0f",
                    (time.monotonic() - refresh_start) * 1000,
                )

        # Reconnect WebSocket
        ws_timeout = (
            float(self._ws_timeout_s) if self._ws_timeout_s is not None else WS_FALLBACK_TIMEOUT_SEC
        )
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("_ensure_ws_connected: reconnecting websocket timeout_s=%.0f", ws_timeout)

        # Create SSL context in executor to avoid blocking event loop (cached after first call)
        if self._ssl_context is None:
            self._ssl_context = await self.hass.async_add_executor_job(self._create_ssl_context)

        ws = await asyncio.wait_for(
            websockets.connect(
                "wss://fanimation.apps.exosite.io/api:1/phone",
                ssl=self._ssl_context,
                compression=None,
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
            _LOGGER.debug(
                "_ensure_ws_connected: websocket reconnected successfully in %.0f ms",
                (time.monotonic() - reconnect_start) * 1000,
            )

    async def _send_request(
        self,
        request_type: str,
        device_id: str,
        data: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Send a request with retry logic and wait for response."""
        ws_timeout = (
            float(self._ws_timeout_s) if self._ws_timeout_s is not None else WS_FALLBACK_TIMEOUT_SEC
        )

        # Allocate a unique request ID
        async with self._request_id_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
        self._last_request_id = request_id

        # Register a Future for this request
        future: asyncio.Future[dict[str, Any]] = asyncio.Future()
        self._pending_requests[request_id] = future

        payload = {
            "id": request_id,
            "request": request_type,
            "device": device_id,
        }
        if data is not None:
            payload["data"] = data

        try:
            # Send request with retry for connection failures
            for attempt in range(2):
                try:
                    await self._ensure_ws_connected()
                    ws = self._ws
                    if ws is None:
                        raise RuntimeError("WebSocket not connected")

                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug(
                            "send request id=%d type=%s device=%s",
                            request_id,
                            request_type,
                            device_id,
                        )
                    await asyncio.wait_for(
                        ws.send(json.dumps(payload)),
                        timeout=ws_timeout,
                    )
                    break
                except (OSError, RuntimeError, TimeoutError) as err:
                    # If it's the first attempt, try to force reconnect and retry
                    if attempt == 0:
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug("send failed (%s), retrying: %s", type(err).__name__, err)
                        # Force close to trigger full reconnect in next _ensure_ws_connected call
                        if self._ws:
                            try:
                                await self._ws.close()
                            except Exception as close_err:
                                if _LOGGER.isEnabledFor(logging.DEBUG):
                                    _LOGGER.debug(
                                        "WebSocket close failed during retry (%s): %s",
                                        type(close_err).__name__,
                                        close_err,
                                    )
                            self._ws = None
                        continue
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug("send retry failed (%s): %s", type(err).__name__, err)
                    raise

            # Wait for _recv_loop to fulfill the Future
            response = await asyncio.wait_for(future, timeout=ws_timeout)
            return response, request_id

        finally:
            # Clean up pending request if not already removed
            self._pending_requests.pop(request_id, None)

    async def async_get_status(self, device_id: str | None = None) -> dict[str, Any]:
        """Get current status of a device."""
        t0 = time.monotonic()
        did = device_id or self._device_id
        if not did:
            raise RuntimeError("No device ID available")

        request_id: int | None = None
        try:
            payload, request_id = await self._send_request("get", did)

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
            self._record_command_history(
                command="get",
                device_id=did,
                keys=[],
                request_id=request_id,
                success=True,
                latency_ms=latency_ms,
            )
            self._record_last_get(
                device_id=did,
                request_id=request_id,
                success=True,
                latency_ms=latency_ms,
            )
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "get rtt ms=%.0f device=%s id=%d",
                    latency_ms,
                    did,
                    request_id,
                )

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
            self._record_command_history(
                command="get",
                device_id=did,
                keys=[],
                request_id=request_id,
                success=False,
                latency_ms=(time.monotonic() - t0) * 1000,
                error_type="TimeoutError",
            )
            self._record_last_get(
                device_id=did,
                request_id=request_id,
                success=False,
                latency_ms=(time.monotonic() - t0) * 1000,
                error_type="TimeoutError",
            )
            raise TimeoutError(f"WebSocket recv timed out: {exc}") from exc
        except Exception as exc:
            self.metrics.record_command(success=False)
            self._record_command_history(
                command="get",
                device_id=did,
                keys=[],
                request_id=request_id,
                success=False,
                latency_ms=(time.monotonic() - t0) * 1000,
                error_type=type(exc).__name__,
            )
            self._record_last_get(
                device_id=did,
                request_id=request_id,
                success=False,
                latency_ms=(time.monotonic() - t0) * 1000,
                error_type=type(exc).__name__,
            )
            raise

    async def async_set(self, data: dict[str, int], *, device_id: str | None = None) -> None:
        """Set device parameters."""
        t_total = time.monotonic()
        did = device_id or self._device_id
        if not did:
            raise RuntimeError("No device ID available")

        request_id: int | None = None
        try:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("set start d=%s keys=%s", did, list(data.keys()))

            payload, request_id = await self._send_request("set", did, data)

            latency_ms = (time.monotonic() - t_total) * 1000
            self.metrics.record_command(success=True, latency_ms=latency_ms)
            self._record_command_history(
                command="set",
                device_id=did,
                keys=sorted(list(data.keys())),
                request_id=request_id,
                success=True,
                latency_ms=latency_ms,
            )
            self._record_last_set(
                device_id=did,
                keys=sorted(list(data.keys())),
                request_id=request_id,
                success=True,
                latency_ms=latency_ms,
            )

            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "set total rtt ms=%.0f device=%s id=%d",
                    latency_ms,
                    did,
                    request_id,
                )

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
                    self.hass.loop.call_soon(self._status_callback, ack_data["status"])

        except Exception as exc:
            self.metrics.record_command(success=False)
            self._record_command_history(
                command="set",
                device_id=did,
                keys=sorted(list(data.keys())),
                request_id=request_id,
                success=False,
                latency_ms=(time.monotonic() - t_total) * 1000,
                error_type=type(exc).__name__,
            )
            latency_ms = (time.monotonic() - t_total) * 1000
            self._record_last_set(
                device_id=did,
                keys=sorted(list(data.keys())),
                request_id=request_id,
                success=False,
                latency_ms=latency_ms,
                error_type=type(exc).__name__,
            )
            raise

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
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "apply_timeouts http_s=%s ws_s=%s",
                self._http_timeout_s,
                self._ws_timeout_s,
            )

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

    def get_diagnostics_data(self) -> dict[str, Any]:
        """Get comprehensive diagnostics data for troubleshooting."""
        last_push_age_s: float | None = None
        if self._last_push_monotonic is not None:
            last_push_age_s = round(time.monotonic() - self._last_push_monotonic, 2)

        ws_state: str | None = None
        if self._ws is not None:
            try:
                ws_state = self._ws.state.name
            except AttributeError:
                ws_state = str(self._ws.state)

        recv_task_state = None
        if self._recv_task is not None:
            recv_task_state = {
                "done": self._recv_task.done(),
                "cancelled": self._recv_task.cancelled(),
            }
        pending_request_ids = sorted(self._pending_requests.keys())
        if len(pending_request_ids) > 20:
            pending_request_ids = pending_request_ids[-20:]

        return {
            # Environment info
            "environment": {
                "python_version": sys.version.split()[0],
                "websockets_version": websockets.__version__,
                "httpx_version": httpx.__version__,
            },
            # Configuration
            "configuration": {
                "verify_ssl": self.verify_ssl,
                "enable_push": self._enable_push,
                "http_timeout_s": self._http_timeout_s,
                "ws_timeout_s": self._ws_timeout_s,
                "http_timeout_effective_s": (
                    self._http_timeout_s
                    if self._http_timeout_s is not None
                    else DEFAULT_HTTP_TIMEOUT_SECS
                ),
                "ws_timeout_effective_s": self.ws_timeout_seconds(),
            },
            # Connection state
            "connection_state": {
                "is_connected": self.metrics.is_connected,
                "has_websocket": self._ws is not None,
                "has_http_client": self._http is not None,
                "device_count": len(self._device_ids),
                "ws_state": ws_state,
                "recv_task": recv_task_state,
                "pending_requests": len(self._pending_requests),
                "pending_request_ids": pending_request_ids,
                "last_request_id": self._last_request_id,
                "last_reconnect_utc": self._last_reconnect_utc,
                "last_recv_error": self._last_recv_error,
                "last_recv_error_utc": self._last_recv_error_utc,
            },
            "push": {
                "enabled": self._enable_push,
                "updates_received": self.metrics.push_updates_received,
                "last_push_age_s": last_push_age_s,
                "last_push_utc": self._last_push_utc,
                "last_push_key_count": self._last_push_key_count,
                "last_push_keys": self._last_push_keys,
                "last_push_by_device": dict(self._last_push_by_device),
            },
            "last_set_by_device": dict(self._last_set_by_device),
            "last_get_by_device": dict(self._last_get_by_device),
            "command_history": list(self._command_history),
            # Connection timing (granular breakdown)
            "connection_timing": {
                "last_http_login_ms": self._last_http_login_ms,
                "last_ws_connect_ms": self._last_ws_connect_ms,  # WebSocket handshake only
                "last_ws_login_wait_ms": self._last_ws_login_wait_ms,  # Login response wait
                "last_ws_login_ms": self._last_ws_login_ms,  # Total connect + login
                "token_refresh_count": self._token_refresh_count,
            },
            # Token metadata (no secrets)
            "token_metadata": self._parse_token_metadata(),
            # Last login response (sanitized)
            "last_login_response": self._last_login_response,
            # Recent failures
            "connection_failures": self._connection_failures,
            # Metrics
            "metrics": self.metrics.to_dict(),
        }
