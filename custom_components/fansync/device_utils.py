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

from typing import Any

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def create_device_info(client: Any, device_id: str) -> DeviceInfo:
    """Build DeviceInfo from the client's device profile for a device."""
    device_id = device_id or "unknown"
    brand = "Fanimation"
    model = "FanSync"
    sw: str | None = None
    mac: str | None = None

    try:
        prof = client.device_profile(device_id)
        if isinstance(prof, dict):
            esh = prof.get("esh")
            if isinstance(esh, dict):
                model = esh.get("model", model)
                brand = esh.get("brand", brand)
            module = prof.get("module")
            if isinstance(module, dict):
                fv = module.get("firmware_version")
                if isinstance(fv, str) and fv:
                    sw = fv
                m = module.get("mac_address")
                if isinstance(m, str) and m:
                    mac = m.lower()
    except Exception:
        # Best-effort device info; ignore profile errors
        pass

    info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        manufacturer=brand,
        model=model,
        name="FanSync",
        sw_version=sw,
        serial_number=device_id,
    )
    if mac:
        info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}
    return info


def module_attrs(client: Any, device_id: str) -> dict[str, object] | None:
    """Return selected module attributes (local_ip, mac_address) for a device."""
    try:
        prof = client.device_profile(device_id)
    except Exception:
        prof = {}
    module = prof.get("module") if isinstance(prof, dict) else None
    attrs: dict[str, object] = {}
    if isinstance(module, dict):
        ip = module.get("local_ip")
        mac = module.get("mac_address")
        if isinstance(ip, str) and ip:
            attrs["local_ip"] = ip
        if isinstance(mac, str) and mac:
            attrs["mac_address"] = mac.lower()
    return attrs or None
