# SPDX-License-Identifier: GPL-2.0-only

"""Shared pytest fixtures for the FanSync custom component tests.

Provides a mocked client and automatic enabling of custom integrations so the
tests can exercise setup and service calls without external network access.
"""

import pathlib
import sys
from unittest.mock import patch

import pytest

# Ensure project root is on sys.path for direct module imports in tests
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def mock_client():
    class _Mock:
        def __init__(self):
            self.status = {"H00": 1, "H02": 41, "H06": 0, "H01": 0, "H0B": 0, "H0C": 0}
            self.device_id = "test-device"
            self.device_ids = [self.device_id]

        async def async_connect(self):
            return None

        async def async_disconnect(self):
            return None

        async def async_get_status(self, device_id: str | None = None):
            # Default tests expect a flat status dict
            if device_id is None or device_id == self.device_id:
                return self.status
            return {}

        async def async_set(self, data, *, device_id: str | None = None):
            self.status.update(data)

    return _Mock()


@pytest.fixture
def patch_client(mock_client):
    instance = mock_client
    # Patch where the class is referenced in platform modules to avoid real network calls
    with (
        patch("custom_components.fansync.fan.FanSyncClient", return_value=instance),
        patch("custom_components.fansync.light.FanSyncClient", return_value=instance),
        patch("custom_components.fansync.FanSyncClient", return_value=instance),
    ):
        yield instance
