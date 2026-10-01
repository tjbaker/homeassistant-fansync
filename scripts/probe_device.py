#!/usr/bin/env python3
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

"""Measure how a FanSync fan responds to raw `set` payloads.

Fans disagree about the same payload (see "Device Protocol Rules" in AGENTS.md),
so a change to what the integration writes has to be measured, not assumed. This
runs a fixed matrix against one fan. Each case starts from a verified state,
sends one payload, records the acknowledgements and pushes, reads the state
back, and asks you what the fan is physically doing. It prints a Markdown table
to paste into an issue.

It WILL switch the fan on and off and change its speed and direction for several
minutes, then restore the state it found. Nothing else should control the fan
meanwhile: stop Home Assistant (`make docker-down`) and leave the app alone.

The light has its own group of cases (L1 to L7), run only when asked for. They
switch the light, sweep its brightness and color temperature, and leave the fan
motor alone.

    venv/bin/python scripts/probe_device.py            # fan matrix
    venv/bin/python scripts/probe_device.py --lights   # light matrix
    venv/bin/python scripts/probe_device.py --list     # show the cases, no network
    venv/bin/python scripts/probe_device.py --cases 1,5,L3 --out probe-report.md

Credentials come from FANSYNC_EMAIL / FANSYNC_PASSWORD, else from the dev
container's config entry, else from a prompt. They are never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import websockets

LOGIN_URL = os.environ.get("FANSYNC_LOGIN_URL", "https://fanimation.apps.exosite.io/api:1/session")
WS_URL = os.environ.get("FANSYNC_WS_URL", "wss://fanimation.apps.exosite.io/api:1/phone")
POWER, PRESET, SPEED, DIRECTION = "H00", "H01", "H02", "H06"
LIGHT, BRIGHTNESS, COLOR = "H0B", "H0C", "H04"
SHOWN = {"fan": (POWER, PRESET, SPEED, DIRECTION), "light": (LIGHT, BRIGHTNESS, COLOR)}
SWEEP = (19, 20, 34, 35, 49, 50, 64, 65, 79, 80, 99, 100)
BRIGHTNESS_SWEEP = (1, 10, 25, 50, 75, 100)
# Every preset a known fixture holds, plus 6500 as a value none is known to hold.
COLOR_SWEEP = (2700, 3000, 3500, 4000, 5000, 6500)


@dataclass(frozen=True)
class Case:
    """One row group of the matrix. `payloads` may reference BASE and FLIP placeholders."""

    label: str  # "1".."10" for the fan, "L1".. for the light
    title: str
    start: str  # "running", "off", "light on" or "light off"
    payloads: tuple[dict[str, int | str], ...]
    ask: str  # a key of QUESTIONS, or "none"
    repeat: int = 1
    reset_between: bool = True
    why: str = ""

    @property
    def group(self) -> str:
        return "light" if self.label.startswith("L") else "fan"


CASES: tuple[Case, ...] = (
    Case("1", "bare off", "running", ({POWER: 0},), "power", 3, why="applied? reported?"),
    Case("2", "bare on", "off", ({POWER: 1},), "power", 3, why="applied? reported?"),
    Case("3", "off + speed", "running", ({POWER: 0, SPEED: "BASE"},), "power"),
    Case("4", "on + speed", "off", ({POWER: 1, SPEED: "BASE"},), "power"),
    Case(
        "5",
        "speed while off",
        "off",
        ({SPEED: "BASE"},),
        "power",
        3,
        why="does a speed write start the fan?",
    ),
    Case(
        "6",
        "three registers, 100",
        "running",
        ({POWER: 1, SPEED: 100, PRESET: 0},),
        "speed",
        3,
        why="applied but unreported?",
    ),
    Case("7", "three registers, 99", "running", ({POWER: 1, SPEED: 99, PRESET: 0},), "speed"),
    Case(
        "8",
        "direction alone",
        "running",
        ({DIRECTION: "FLIP"}, {DIRECTION: "FLIP"}),
        "direction",
        reset_between=False,
        why="reported without a speed?",
    ),
    Case(
        "9",
        "preset alone",
        "running",
        ({PRESET: 1}, {PRESET: 0}),
        "none",
        reset_between=False,
        why="reported without a speed?",
    ),
    Case(
        "10",
        "speed rounding",
        "running",
        tuple({SPEED: n} for n in SWEEP),
        "none",
        reset_between=False,
        why="which values does the fan hold?",
    ),
    Case("L1", "light: bare off", "light on", ({LIGHT: 0},), "light", 3, why="applied? reported?"),
    Case("L2", "light: bare on", "light off", ({LIGHT: 1},), "light", 3, why="applied? reported?"),
    Case(
        "L3",
        "light: brightness while off",
        "light off",
        ({BRIGHTNESS: 50},),
        "light",
        why="does a brightness write turn the light on?",
    ),
    Case(
        "L4",
        "light: color while off",
        "light off",
        ({COLOR: 4000},),
        "light",
        why="does a color write turn the light on?",
    ),
    Case(
        "L5",
        "light: three registers",
        "light on",
        ({LIGHT: 1, BRIGHTNESS: 60, COLOR: 4000},),
        "light",
        3,
        why="reported?",
    ),
    Case(
        "L6",
        "light: brightness sweep",
        "light on",
        tuple({BRIGHTNESS: n} for n in BRIGHTNESS_SWEEP),
        "brightness",
        reset_between=False,
        why="which values does the light hold?",
    ),
    Case(
        "L7",
        "light: color sweep",
        "light on",
        tuple({COLOR: n} for n in COLOR_SWEEP),
        "color",
        reset_between=False,
        why="which color temperatures exist?",
    ),
)


@dataclass
class Outcome:
    acks: list[str] = field(default_factory=list)
    pushes: list[tuple[float, dict[str, Any]]] = field(default_factory=list)
    after: dict[str, Any] = field(default_factory=dict)


@dataclass
class Row:
    case: Case
    step: str
    start: str
    payload: dict[str, int]
    outcome: Outcome
    observed: str


class Session:
    """One WebSocket session against the FanSync cloud, strictly sequential."""

    def __init__(self, ws: Any, device: str) -> None:
        self._ws = ws
        self._device = device
        self._next_id = 10
        # Last value this script wrote per register. The cloud's state cannot stand in
        # for it: that is exactly what goes stale when a write is not reported.
        self.written: dict[str, int] = {}
        # Findings that do not fit a table row, such as a report contradicting the fan.
        self.notes: list[str] = []

    async def _recv(self, timeout: float) -> dict[str, Any] | None:
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=max(0.05, timeout))
        except TimeoutError:
            return None
        frame = json.loads(raw)
        return frame if isinstance(frame, dict) else None

    @staticmethod
    def _push_status(frame: dict[str, Any]) -> dict[str, Any] | None:
        data = frame.get("data")
        if not isinstance(data, dict) or "id" in frame:
            return None
        changes = data.get("changes")
        status = changes.get("status") if isinstance(changes, dict) else data.get("status")
        return status if isinstance(status, dict) else None

    async def request(self, request: str, **extra: Any) -> dict[str, Any]:
        """Send a request and return its first response, discarding anything else."""
        request_id = self._next_id
        self._next_id += 1
        await self._ws.send(json.dumps({"id": request_id, "request": request, **extra}))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            frame = await self._recv(deadline - time.monotonic())
            if frame is not None and frame.get("id") == request_id:
                return frame
        raise TimeoutError(f"no response to {request}")

    async def get(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (status, profile) as the cloud currently holds them."""
        data = (await self.request("get", device=self._device)).get("data")
        data = data if isinstance(data, dict) else {}
        status, profile = data.get("status"), data.get("profile")
        return (
            status if isinstance(status, dict) else {},
            profile if isinstance(profile, dict) else {},
        )

    async def set_and_listen(self, payload: dict[str, int], listen: float) -> Outcome:
        """Send one `set`, record every ack and push for `listen` seconds, then read back."""
        outcome = Outcome()
        request_id = self._next_id
        self._next_id += 1
        self.written.update(payload)
        await self._ws.send(
            json.dumps(
                {"id": request_id, "request": "set", "device": self._device, "data": payload}
            )
        )
        start = time.monotonic()
        while (remaining := listen - (time.monotonic() - start)) > 0:
            frame = await self._recv(remaining)
            if frame is None:
                break
            if frame.get("id") == request_id:
                outcome.acks.append(str(frame.get("status", "?")))
            elif (status := self._push_status(frame)) is not None:
                outcome.pushes.append((time.monotonic() - start, status))
        outcome.after = (await self.get())[0]
        return outcome


def _container_credentials(container: str) -> tuple[str, str] | None:
    """Read the FanSync config entry's credentials from the dev container, if present."""
    try:
        raw = subprocess.run(
            ["docker", "exec", container, "cat", "/config/.storage/core.config_entries"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        for entry in json.loads(raw)["data"]["entries"]:
            if entry.get("domain") == "fansync":
                return entry["data"]["email"], entry["data"]["password"]
    except OSError, subprocess.CalledProcessError, KeyError, ValueError:
        return None
    return None


def _credentials(container: str) -> tuple[str, str]:
    if "FANSYNC_EMAIL" in os.environ and "FANSYNC_PASSWORD" in os.environ:
        return os.environ["FANSYNC_EMAIL"], os.environ["FANSYNC_PASSWORD"]
    if (found := _container_credentials(container)) is not None:
        print(f"Using the FanSync credentials stored in the {container} container.")
        return found
    return input("FanSync email: ").strip(), getpass.getpass("FanSync password: ")


def _token(container: str) -> str:
    if "FANSYNC_TOKEN" in os.environ:  # for testing against a local fake
        return os.environ["FANSYNC_TOKEN"]
    email, password = _credentials(container)
    response = httpx.post(LOGIN_URL, json={"email": email, "password": password}, timeout=20)
    response.raise_for_status()
    return str(response.json()["token"])


async def _ainput(prompt: str) -> str:
    """Read a line from stdin without a thread, so an interrupt at a prompt exits cleanly."""
    print(prompt, end="", flush=True)
    loop = asyncio.get_running_loop()
    done: asyncio.Future[str] = loop.create_future()

    def _readable() -> None:
        if not done.done():
            done.set_result(sys.stdin.readline())

    try:
        loop.add_reader(sys.stdin.fileno(), _readable)
    except NotImplementedError, OSError, ValueError:
        return await asyncio.to_thread(sys.stdin.readline)  # stdin is not selectable
    try:
        return await done
    finally:
        loop.remove_reader(sys.stdin.fileno())


async def _ask(question: str, enabled: bool) -> str:
    if not enabled:
        return "not observed"
    answer = (await _ainput(f"    >> {question} [y/n/?] ")).strip().lower()
    return {"y": "yes", "n": "no"}.get(answer[:1], "unsure")


def _brief(status: dict[str, Any], group: str = "fan") -> str:
    return " ".join(f"{k}={status.get(k, '-')}" for k in SHOWN[group])


def _pushed(outcome: Outcome, key: str) -> Any:
    """The value the fan itself reported for `key` in answer to a write, if it reported."""
    return outcome.pushes[-1][1].get(key) if outcome.pushes else None


async def _ensure(
    session: Session, want: str, base: int, settle: float, ask: bool
) -> tuple[str, bool]:
    """Put the fan in a known state. Return ("tag: evidence", whether it was reached).

    A start state is established by the person watching the fan. The fan's own report
    is recorded next to it but is not proof: a fan can report running while standing
    still, and telling those apart is the point of this script. The cloud's stored
    state counts for nothing, since it is stale whenever a write went unreported.
    """
    running = want == "running"
    wanted_power = 1 if running else 0
    write = {POWER: 1, SPEED: base} if running else {POWER: 0}
    outcome = await session.set_and_listen(write, settle)
    if not running and not outcome.pushes and outcome.after.get(POWER) == 1:
        # The cloud still says on: the fan applied the off silently, or not at all.
        # Off + speed makes the first kind report. Sent only in this state, because on
        # a fan that starts on any speed write it would turn the fan back on.
        speed = outcome.after.get(SPEED)
        write = {POWER: 0, SPEED: speed if isinstance(speed, int) and speed > 0 else base}
        outcome = await session.set_and_listen(write, settle)
    said = _pushed(outcome, POWER)
    doing = "spinning" if running else "stopped"
    seen = await _ask(f"Start state for this test: is the fan {doing}?", ask)
    if seen == "no":
        session.notes.append(
            f"Wanted the fan {doing}. After `{json.dumps(write)}` it reported "
            f"{'H00=' + str(said) if said is not None else 'nothing'} "
            f"(cloud: `{_brief(outcome.after)}`) but was NOT {doing}."
        )
        # Resynchronize: make the fan report off, then ask for the wanted state again.
        await session.set_and_listen({POWER: 0, SPEED: base}, settle)
        if running:
            write = {POWER: 1, SPEED: base}
            outcome = await session.set_and_listen(write, settle)
        else:
            outcome = await session.set_and_listen({POWER: 0}, settle)
        said = _pushed(outcome, POWER)
        seen = await _ask(f"After a resync (off + speed first): is the fan {doing} now?", ask)
        session.notes.append(f"After a resync the fan was {doing}: {seen}.")
    report = "fan reported it" if said == wanted_power else "no matching report from the fan"
    if seen == "yes":
        tag = want
    elif seen == "no":
        tag = f"NOT {want}"
    else:
        tag = want if said == wanted_power else f"{want} (UNVERIFIED)"
    return f"{tag}: you saw {doing}: {seen}; {report}; cloud {_brief(outcome.after)}", seen != "no"


async def _ensure_light(session: Session, want: str, settle: float, ask: bool) -> tuple[str, bool]:
    """Put the light in a known state, confirmed by the person watching it.

    "Unsure" is accepted, so a fan with light registers but no light kit can still be
    probed for what it acknowledges and reports.
    """
    on = want == "light on"
    doing = "on" if on else "off"
    write = {LIGHT: 1 if on else 0}
    outcome = await session.set_and_listen(write, settle)
    seen = await _ask(f"Start state for this test: is the light {doing}? (? if no light)", ask)
    if seen == "no":
        session.notes.append(
            f"Wanted the light {doing}. After `{json.dumps(write)}` it reported "
            f"{'H0B=' + str(_pushed(outcome, LIGHT)) if outcome.pushes else 'nothing'} "
            f"(cloud: `{_brief(outcome.after, 'light')}`) but was NOT {doing}."
        )
        # Retry with a brightness alongside, which makes some devices act and report.
        write = {LIGHT: 1, BRIGHTNESS: 100} if on else {LIGHT: 0}
        outcome = await session.set_and_listen(write, settle)
        seen = await _ask(f"After `{json.dumps(write)}`: is the light {doing} now?", ask)
        session.notes.append(f"After `{json.dumps(write)}` the light was {doing}: {seen}.")
    said = _pushed(outcome, LIGHT)
    report = "reported" if said == write[LIGHT] else "no matching report"
    tag = want if seen == "yes" else f"NOT {want}" if seen == "no" else f"{want} (UNVERIFIED)"
    evidence = f"you saw it {doing}: {seen}; {report}; cloud {_brief(outcome.after, 'light')}"
    return f"{tag}: {evidence}", seen != "no"


def _resolve(
    payload: dict[str, int | str], base: int, status: dict[str, Any], written: dict[str, int]
) -> dict[str, int]:
    resolved: dict[str, int] = {}
    for key, value in payload.items():
        if value == "BASE":
            resolved[key] = base
        elif value == "FLIP":
            current = written.get(DIRECTION, status.get(DIRECTION))
            resolved[key] = 0 if current == 1 else 1
        else:
            resolved[key] = int(value)
    return resolved


QUESTIONS = {
    "power": "Is the fan spinning now?",
    "speed": "Did the fan audibly speed up?",
    "direction": "Did the fan change direction? (give it a few seconds)",
    "light": "Is the light on now?",
    "brightness": "Did the brightness visibly change?",
    "color": "Did the color of the light visibly change?",
}


async def _run_case(
    session: Session, case: Case, args: argparse.Namespace, rows: list[Row]
) -> None:
    repeats = args.repeat or case.repeat
    many = len(case.payloads) > 1
    for run in range(1, repeats + 1):
        print(
            f"\n[{case.label}] {case.title}  (run {run}/{repeats})"
            f"  starts from: {case.start}.  {case.why}"
        )
        start, reached = "", True
        status: dict[str, Any] = {}
        for index, template in enumerate(case.payloads):
            step = f"{case.label}.{run}" + (chr(ord("a") + index) if many else "")
            if index == 0 or case.reset_between:
                if case.group == "light":
                    start, reached = await _ensure_light(session, case.start, args.settle, args.ask)
                else:
                    start, reached = await _ensure(
                        session, case.start, args.speed, args.settle, args.ask
                    )
                print(f"    start -> {start}")
                status = (await session.get())[0]
            if not reached:
                print("    SKIPPED: the start state was not reached")
                rows.append(Row(case, step, start, {}, Outcome(after=status), "skipped"))
                continue
            payload = _resolve(template, args.speed, status, session.written)
            quick = case.ask == "none" or case.group == "light"  # nothing has to spin up
            listen = min(args.listen, 6.0) if quick else args.listen
            outcome = await session.set_and_listen(payload, listen)
            times = ", ".join(f"{t:.1f}s" for t, _ in outcome.pushes)
            push = f"push at {times}" if outcome.pushes else "NO push"
            print(f"    set {json.dumps(payload)}: acks={outcome.acks} {push}")
            print(f"    cloud now: {_brief(outcome.after, case.group)}")
            observed = await _ask(QUESTIONS[case.ask], args.ask) if case.ask in QUESTIONS else "n/a"
            rows.append(Row(case, step, start, payload, outcome, observed))
            status = outcome.after


PRIVATE = ("name", "email", "owner", "mac", "ip", "ssid", "serial", "cert", "token", "key")


def _public(mapping: object) -> dict[str, Any]:
    """Keep a metadata mapping's entries, dropping anything that could identify the owner."""
    if not isinstance(mapping, dict):
        return {}
    return {k: v for k, v in mapping.items() if not any(word in str(k).lower() for word in PRIVATE)}


def _device_info(
    device: str, meta: object, profile: dict[str, Any], status: dict[str, Any], args: Any
) -> dict[str, Any]:
    """Everything the cloud says about this fan that helps interpret a probe, minus identity.

    Left out on purpose: owner email, full device id, display name, MAC, IP, certificates.
    """
    meta = meta if isinstance(meta, dict) else {}
    raw_module = profile.get("module")
    module = raw_module if isinstance(raw_module, dict) else {}
    return {
        "device": f"...{device[-4:]}",
        "esh": _public(profile.get("esh")),
        "module": _public(module),
        "fields_withheld": {
            section: sorted(k for k in source if k not in _public(source))
            for section, source in (
                ("esh", profile.get("esh")),
                ("module", module),
                ("cloud_properties", meta.get("properties")),
            )
            if isinstance(source, dict)
        },
        "profile_sections": sorted(profile),
        "cloud_properties": _public(meta.get("properties")),
        "role": meta.get("role"),
        "status_at_start": dict(sorted(status.items())),
        "probe": {"base_speed": args.speed, "listen_s": args.listen, "settle_s": args.settle},
    }


def _reported(payload: dict[str, int], outcome: Outcome) -> str:
    """Summarize what the fan itself reported for a write, from its last push."""
    if not outcome.pushes:
        return "**no**"
    last = outcome.pushes[-1][1]
    differing = [f"{k}={last.get(k, '-')}" for k, v in payload.items() if last.get(k) != v]
    return "yes" if not differing else f"yes, as `{' '.join(differing)}`"


def _report(rows: list[Row], info: dict[str, Any], notes: list[str]) -> str:
    model = info["esh"].get("model", "unknown model")
    firmware = info["module"].get("firmware_version", "unknown")
    asked = {
        "power": "spinning",
        "speed": "sped up",
        "direction": "reversed",
        "light": "light on",
        "brightness": "brightness changed",
        "color": "color changed",
    }
    lines = [
        f"## FanSync probe: {model}, firmware {firmware}",
        "",
        f"Run {datetime.now(UTC):%Y-%m-%d %H:%M} UTC with `scripts/probe_device.py`. "
        "**Reported** is judged from the fan's own pushes: `yes` when the last push carries "
        "every value sent, `yes, as ...` when it reports something else, `no` when no push "
        "arrived. **Cloud after** is a `get` once the listening window closed.",
        "",
        "| # | Case | Start | Payload | Acks | Push at | Reported | Cloud after | Fan (observed) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        out = row.outcome
        begin = row.start.split(":")[0]
        cloud = _brief(out.after, row.case.group)
        if row.observed == "skipped":
            lines.append(
                f"| {row.step} | {row.case.title} | {begin} | skipped: start state not reached "
                f"| | | | `{cloud}` | |"
            )
            continue
        push = ", ".join(f"{t:.1f} s" for t, _ in out.pushes) or "none"
        fan = "n/a" if row.observed == "n/a" else f"{asked[row.case.ask]}: {row.observed}"
        lines.append(
            f"| {row.step} | {row.case.title} | {begin} "
            f"| `{json.dumps(row.payload)}` | {', '.join(out.acks) or 'none'} | {push} "
            f"| {_reported(row.payload, out)} | `{cloud}` | {fan} |"
        )
    if notes:
        lines += [
            "",
            "**Start-state findings** (the device reported one thing and did another):",
            "",
        ]
        lines += [f"- {note}" for note in notes]
    lines += [
        "",
        "### Device",
        "",
        "As the cloud describes it. Owner, device id, display name, MAC and IP are withheld.",
        "",
        "```json",
        json.dumps(info, indent=2),
        "```",
    ]
    return "\n".join(lines) + "\n"


def _emit(
    args: argparse.Namespace, rows: list[Row], info: dict[str, Any], notes: list[str]
) -> None:
    """Print the report, complete or partial, and write it to --out if given."""
    if not rows:
        return
    report = _report(rows, info, notes)
    print("\n" + report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(report)
        print(f"Report written to {args.out}")


async def _main(args: argparse.Namespace) -> int:
    chosen = _chosen(args)
    token = _token(args.container)
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"id": 1, "request": "login", "data": {"token": token}}))
        bootstrap = Session(ws, "")
        while (frame := await bootstrap._recv(20)) is not None and frame.get("id") != 1:
            pass
        devices = (await bootstrap.request("lst_device")).get("data") or []
        ids = [d["device"] for d in devices if isinstance(d, dict) and "device" in d]
        device = args.device or (ids[0] if len(ids) == 1 else "")
        if device not in ids:
            print(f"Pick one with --device. This account has: {', '.join(ids) or 'no devices'}")
            return 2
        session = Session(ws, device)
        original, profile = await session.get()
        meta = next((d for d in devices if isinstance(d, dict) and d.get("device") == device), {})
        info = _device_info(device, meta, profile, original, args)
        model = info["esh"].get("model", "unknown model")
        firmware = info["module"].get("firmware_version", "unknown")
        print(f"Device ...{device[-4:]}: {model}, firmware {firmware}")
        print(f"Current state: {_brief(original)}  {_brief(original, 'light')}")
        if LIGHT not in original and any(c.group == "light" for c in chosen):
            print("This device reports no light registers, so the light cases are left out.")
            chosen = [c for c in chosen if c.group != "light"]
            if not chosen:
                return 2
        groups = {c.group for c in chosen}
        does = {
            "fan": "switches the fan on and off and changes its speed and direction",
            "light": "switches the light on and off and changes its brightness and color",
        }
        print(f"\nThis runs {len(chosen)} case(s) over several minutes. It")
        for group in sorted(groups):
            print(f"  - {does[group]}")
        print(
            "and then restores the state above.\n"
            "Nothing else may control the fan meanwhile. If Home Assistant is running this\n"
            "integration, stop it now: disable the integration there, or for the dev\n"
            "container run `make docker-down` in another terminal (credentials have already\n"
            "been read). Leave the app and remote alone."
        )
        if not args.yes and (await _ainput("Continue? [y/N] ")).strip().lower() != "y":
            print("Nothing was sent to the fan.")
            return 0

        rows: list[Row] = []
        try:
            for case in chosen:
                await _run_case(session, case, args, rows)
        finally:
            print("\nRestoring the original state...")
            running = original.get(POWER) == 1
            speed = original.get(SPEED)
            base = speed if isinstance(speed, int) and speed > 0 else args.speed
            # Only what this run changed, and never a write that would start a stopped fan.
            restore = {
                k: original[k]
                for k in (DIRECTION, PRESET)
                if isinstance(original.get(k), int)
                and session.written.get(k, original[k]) != original[k]
            }
            if restore:
                await session.set_and_listen(
                    {**restore, SPEED: base} if running else restore, args.settle
                )
            if any(k in session.written for k in SHOWN["fan"]):
                state, _ = await _ensure(
                    session, "running" if running else "off", base, args.settle, False
                )
                print(f"    {state}")
            if any(k in session.written for k in SHOWN["light"]):
                # Brightness and color first, power last: either may switch the light on.
                levels = {
                    k: original[k]
                    for k in (BRIGHTNESS, COLOR)
                    if isinstance(original.get(k), int)
                    and session.written.get(k, original[k]) != original[k]
                }
                if levels:
                    await session.set_and_listen(levels, 3.0)
                if isinstance(original.get(LIGHT), int):
                    after = (await session.set_and_listen({LIGHT: original[LIGHT]}, 3.0)).after
                    print(f"    light: cloud {_brief(after, 'light')}")
            _emit(args, rows, info, session.notes)
    return 0


def _chosen(args: argparse.Namespace) -> list[Case]:
    """The cases to run: those named by --cases, else one whole group."""
    if args.cases:
        return [c for c in CASES if c.label in args.cases]
    return [c for c in CASES if c.group == ("light" if args.lights else "fan")]


def _labels(text: str) -> set[str]:
    labels = {part.strip().upper() for part in text.split(",") if part.strip()}
    if unknown := labels - {c.label for c in CASES}:
        raise argparse.ArgumentTypeError(f"unknown case(s): {', '.join(sorted(unknown))}")
    return labels


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="print the cases and exit")
    parser.add_argument("--cases", type=_labels, default=set(), help="cases to run, such as 1,5,L3")
    parser.add_argument(
        "--lights", action="store_true", help="run the light cases instead of the fan cases"
    )
    parser.add_argument("--repeat", type=int, default=0, help="override every case's repeat count")
    parser.add_argument("--speed", type=int, default=50, help="base running speed (default 50)")
    parser.add_argument("--listen", type=float, default=10.0, help="seconds to listen per write")
    parser.add_argument(
        "--settle", type=float, default=8.0, help="seconds to let a start state settle"
    )
    parser.add_argument("--device", default="", help="device id, if the account has several")
    parser.add_argument("--container", default="ha-fansync-dev", help="dev container name")
    parser.add_argument("--out", default="", help="also write the Markdown report to this file")
    parser.add_argument("--yes", action="store_true", help="do not ask before starting")
    parser.add_argument(
        "--no-ask", dest="ask", action="store_false", help="do not ask what the fan is doing"
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _parse(sys.argv[1:])
    if args.list:
        for case in CASES:
            payloads = ", ".join(json.dumps(p) for p in case.payloads[:3])
            more = f" ... ({len(case.payloads)} payloads)" if len(case.payloads) > 3 else ""
            head = f"{case.label:>2}. {case.title:<27} from {case.start:<9} x{case.repeat}"
            print(f"{head}  {payloads}{more}")
        return 0
    try:
        return asyncio.run(_main(args))
    except KeyboardInterrupt:
        print("\nInterrupted. The original state was restored if the run had started.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
