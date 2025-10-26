# SPDX-License-Identifier: GPL-2.0-only
# Copyright 2025 Trevor Baker, all rights reserved.

"""Client construction and SSL verification behavior tests.

Verifies that the HTTP client is instantiated with the expected verify flag
when the integration is configured with verify_ssl=True.
"""
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.fansync.client import FanSyncClient


async def test_client_ssl_flag(hass: HomeAssistant):
    """Ensure FanSyncClient builds HTTPX client with verify=True when configured."""
    with patch("custom_components.fansync.client.httpx.Client") as mock_cls:
        mock_http = object()
        mock_cls.return_value = mock_http
        c = FanSyncClient(hass, "e", "p", verify_ssl=True)
        async def _fake_connect():
            def inner():
                # ensure we instantiate with verify=True
                pass
            return await hass.async_add_executor_job(inner)
        # call normal connect to exercise code path
        with patch("fansync.HttpApi.post_session") as post, patch("custom_components.fansync.client.Websocket") as ws_cls:
            post.return_value = type("C", (), {"token": "t"})()
            ws = ws_cls.return_value
            ws.connect.return_value = None
            ws.login.return_value = None
            ws.list_devices.return_value = type("D", (), {"data": [type("X", (), {"device": "id"})()]})()
            await c.async_connect()
        mock_cls.assert_called_with(verify=True)
