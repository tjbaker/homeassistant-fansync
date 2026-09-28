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

import logging
from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def _cloud_flagged_devices(client: Any, device_ids: Iterable[str], flag: str) -> set[str]:
    """Return device_ids whose cloud metadata has ``properties.<flag>`` set to true.

    Only an explicit ``True`` counts. The official app writes these per-device
    hints when the owner configures the fan there; absence proves nothing, so a
    missing or false flag never changes behavior. Tolerant of clients without
    metadata support (returns an empty set on any error).
    """
    flagged: set[str] = set()
    for device_id in device_ids:
        try:
            meta = client.device_metadata(device_id)
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        props = meta.get("properties")
        if isinstance(props, dict) and props.get(flag) is True:
            flagged.add(device_id)
    return flagged


def cloud_lightless_devices(client: Any, device_ids: Iterable[str]) -> set[str]:
    """Return device_ids the Fanimation cloud marks as having no light kit.

    The official app sets ``properties.hideLightDimmer`` to true on devices whose
    owner told it no light kit is installed (issue #199). Observed across five
    devices: true only ever appears on lightless fans, while light-equipped fans
    report false or omit the key — but so do lightless fans whose owner never
    told the app. So true is trusted as "no light"; absence proves nothing, and
    the manual per-device option remains for the untagged case.
    """
    return _cloud_flagged_devices(client, device_ids, "hideLightDimmer")


def cloud_no_direction_devices(client: Any, device_ids: Iterable[str]) -> set[str]:
    """Return device_ids the Fanimation cloud marks as not reversible.

    The official app sets ``properties.hideFanDirection`` to true on devices
    whose owner told it the fan cannot change direction (issue #228: a universal
    receiver on a third-party fan accepts the reverse command, but the motor
    never reverses). The fan entity drops its direction feature for these so a
    control that cannot work is not offered.
    """
    return _cloud_flagged_devices(client, device_ids, "hideFanDirection")


def create_device_info(client: Any, device_id: str) -> DeviceInfo:
    """Build DeviceInfo from the client's device profile for a device."""
    device_id = device_id or "unknown"
    brand = "Fanimation"
    model = "FanSync"
    name = "FanSync"
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

    # Prefer the user's display name from the account (e.g. "Living Room Fan")
    # so multi-fan households get distinct, meaningful device names instead of
    # every device showing as "FanSync".
    try:
        meta = client.device_metadata(device_id)
        if isinstance(meta, dict):
            props = meta.get("properties")
            if isinstance(props, dict):
                display = props.get("displayName")
                if isinstance(display, str) and display.strip():
                    name = display.strip()
    except Exception:
        # Best-effort; fall back to the generic name
        pass

    info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        manufacturer=brand,
        model=model,
        name=name,
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


def confirm_after_initial_delay(
    *,
    confirmed_by_push: bool,
    coordinator_data: dict[str, dict[str, object]] | None,
    device_id: str,
    predicate: Callable[[dict], bool],
    logger: logging.Logger,
) -> tuple[dict[str, object], bool, bool]:
    """Check for push confirmation after the initial delay.

    Returns (status, confirmed_by_push, ok).
    """
    if not confirmed_by_push:
        return {}, confirmed_by_push, False

    data = coordinator_data or {}
    status = data.get(device_id, {}) if isinstance(data, dict) else {}
    if predicate(status):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "optimism early confirm d=%s via push update",
                device_id,
            )
        return status, confirmed_by_push, True

    return status, False, False
