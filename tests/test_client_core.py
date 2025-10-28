# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


def _login_ok() -> str:
    return json.dumps({"status": "ok", "response": "login", "id": 1})


def _lst_device_ok(device_id: str = "id") -> str:
    return json.dumps(
        {
            "status": "ok",
            "response": "lst_device",
            "data": [{"device": device_id}],
            "id": 2,
        }
    )


def _get_ok(status: dict[str, int] | None = None) -> str:
    if status is None:
        status = {"H00": 1, "H02": 42}
    return json.dumps(
        {
            "status": "ok",
            "response": "get",
            "data": {"status": status},
            "id": 3,
        }
    )


async def test_connect_sets_device_id(hass: HomeAssistant):
    c = FanSyncClient(hass, "e@example.com", "p", verify_ssl=True, enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()
        ws = ws_cls.return_value
        ws.connect.return_value = None
        ws.recv.side_effect = [_login_ok(), _lst_device_ok("dev-123")]
        await c.async_connect()

    assert c.device_id == "dev-123"
    http_cls.assert_called_with(verify=True)


async def test_get_status_returns_mapping(hass: HomeAssistant):
    c = FanSyncClient(hass, "e", "p", verify_ssl=False, enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()
        ws = ws_cls.return_value
        ws.connect.return_value = None
        # login, list, then get
        ws.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("id"),
            _get_ok({"H00": 1, "H02": 19}),
            # background recv loop may consume an extra frame; provide a benign event
            json.dumps({"event": "noop"}),
            json.dumps({"event": "noop2"}),
        ]
        await c.async_connect()
        status = await c.async_get_status()

    assert status.get("H02") == 19


async def test_async_set_triggers_callback(hass: HomeAssistant):
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()
        ws = ws_cls.return_value
        ws.connect.return_value = None
        # login, list, set ack, get
        ws.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("id"),
            json.dumps({"status": "ok", "response": "set", "id": 4}),
            _get_ok({"H00": 1, "H02": 55}),
            json.dumps({"event": "noop"}),
            json.dumps({"event": "noop2"}),
        ]

        # Capture callback result
        seen: list[dict[str, int]] = []
        c.set_status_callback(lambda s: seen.append(s))

        await c.async_connect()
        await c.async_set({"H02": 55})
        await hass.async_block_till_done()

    assert seen and seen[-1].get("H02") == 55


async def test_async_set_uses_ack_status_when_present(hass: HomeAssistant):
    c = FanSyncClient(hass, "e", "p", verify_ssl=True, enable_push=False)
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()
        ws = ws_cls.return_value
        ws.connect.return_value = None
        # login, list, then set ACK with embedded status (no subsequent get response provided)
        ws.recv.side_effect = [
            _login_ok(),
            _lst_device_ok("id"),
            json.dumps(
                {
                    "status": "ok",
                    "response": "set",
                    "id": 4,
                    "data": {"status": {"H00": 0, "H02": 1}},
                }
            ),
        ]

        seen: list[dict[str, int]] = []
        c.set_status_callback(lambda s: seen.append(s))

        await c.async_connect()
        await c.async_set({"H00": 0})
        await hass.async_block_till_done()

    # Should have used ACK status directly without needing a separate get
    assert seen and seen[-1].get("H00") == 0 and seen[-1].get("H02") == 1


async def test_connect_ws_login_failure_raises(hass: HomeAssistant):
    c = FanSyncClient(hass, "e", "p")
    with (
        patch("custom_components.fansync.client.httpx.Client") as http_cls,
        patch("custom_components.fansync.client.websocket.WebSocket") as ws_cls,
    ):
        http_inst = http_cls.return_value
        http_inst.post.return_value = type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"token": "t"}}
        )()
        ws = ws_cls.return_value
        ws.connect.return_value = None
        ws.recv.side_effect = [json.dumps({"status": "fail", "response": "login", "id": 1})]

        with pytest.raises(RuntimeError):
            await c.async_connect()


async def test_connect_http_error_bubbles(hass: HomeAssistant):
    c = FanSyncClient(hass, "e", "p")
    with patch("custom_components.fansync.client.httpx.Client") as http_cls:
        http_inst = http_cls.return_value
        http_inst.post.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            await c.async_connect()
