#!/usr/bin/env python3
"""Diagnose Digicon turnout MQTT vs FB (read-only by default).

Rules (SoR):
  - Live Digicon state follows **FB** for all turnouts except 116–119.
  - Digicon SEL+CMD share one polarity. 112/114/115: inverted motors — Digicon
    throw frog = rest tip (Barn / McKeesport / Rocks); keep MQTT THROWN.
  - Wrong Digicon direction → flip **that one plant only** in
    `wire_hart_sheet_west_yard2.py` PLANTS. Do not command MQTT/JMRI.
  - This script must not throw field points. Default = diagnose only.

    python3 cats/scripts/seed_default_thrown_turnouts.py
    python3 cats/scripts/seed_default_thrown_turnouts.py --diagnose

Writes (MQTT retain only — never JMRI turnout commands) require --write and
are for unknown retain on 100/112/114/115 defaults only. Prefer FB→MQTT via
sync_mqtt_turnouts_from_fb.py only when Digicon must track FB for non-inverted plants.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

JMRI_JSON = os.environ.get("JMRI_JSON", "http://minipc-e5h6x.local:12080/json")
MQTT_HOST = os.environ.get("MQTT_HOST", "minipc-e5h6x.local")

# THROWN retain keeps Digicon throw-frog rest tips for inverted 112/114/115 + Brick 100.
DEFAULT_THROWN = {
    100: 408,
    112: 1213,
    114: 109,
    115: 110,
}

# Yard ladder — Digicon not driven by FB SoR for these.
SKIP_FB = {116, 117, 118, 119}

STATE = {0: "UNKNOWN", 1: "UNKNOWN", 2: "CLOSED", 4: "THROWN", 8: "INCONSISTENT"}
SENS = {2: "inactive", 4: "active"}
FB_MODE = {
    1: "DIRECT",
    2: "EXACT",
    4: "INDIRECT/ONESENSOR?",
    8: "TWOSENSOR",
    16: "MONITORING",
    32: "mode=32 (MQTT/command drives KnownState)",
    128: "mode=128",
}


def _get(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def _mqtt_retain(addr: int) -> str | None:
    try:
        out = subprocess.check_output(
            [
                "mosquitto_sub",
                "-h",
                MQTT_HOST,
                "-t",
                f"track/turnout/{addr}",
                "-C",
                "1",
                "-W",
                "1",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return out or None
    except subprocess.CalledProcessError:
        return None


def _mqtt_pub(addr: int, msg: str) -> None:
    subprocess.run(
        [
            "mosquitto_pub",
            "-h",
            MQTT_HOST,
            "-t",
            f"track/turnout/{addr}",
            "-m",
            msg,
            "-r",
        ],
        check=False,
    )


def _fb_implied(d: dict) -> str | None:
    """TWOSENSOR: FB R→THROWN, FB N→CLOSED."""
    n_on = r_on = False
    for s in d.get("sensor") or []:
        sd = s.get("data") or s
        if sd.get("state") != 4:
            continue
        un = sd.get("userName") or ""
        if "FB N" in un:
            n_on = True
        elif "FB R" in un:
            r_on = True
    if n_on and not r_on:
        return "CLOSED"
    if r_on and not n_on:
        return "THROWN"
    return None


def _switch_num_from_uname(un: str) -> int | None:
    # "Switch 114" / "Switch 100"
    parts = (un or "").split()
    if len(parts) >= 2 and parts[0] == "Switch" and parts[1].isdigit():
        return int(parts[1])
    return None


def diagnose(by_name: dict) -> int:
    rows = []
    for name, d in by_name.items():
        if not name or not name.startswith("M2T"):
            continue
        try:
            addr = int(name[3:])
        except ValueError:
            continue
        un = d.get("userName") or ""
        sw = _switch_num_from_uname(un)
        if sw is not None and sw in SKIP_FB:
            continue
        mqtt = _mqtt_retain(addr) or "(none)"
        jmri = STATE.get(d.get("state"), str(d.get("state")))
        fb = _fb_implied(d) or "?"
        mode = d.get("feedbackMode")
        mode_s = FB_MODE.get(mode, str(mode))
        mismatch = fb in ("CLOSED", "THROWN") and mqtt in ("CLOSED", "THROWN") and fb != mqtt
        rows.append((sw if sw is not None else 9999, sw, name, mqtt, jmri, fb, mode_s, mismatch))

    rows.sort()
    print(
        f"{'sw':>4} {'sys':8} {'mqtt':8} {'jmri':12} {'fb→':8} {'fbMode':12}  note"
    )
    print("-" * 90)
    for _k, sw, name, mqtt, jmri, fb, mode_s, mismatch in rows:
        sw_s = f"{sw}" if sw is not None else "?"
        note = ""
        if sw in DEFAULT_THROWN:
            note += "default-THROWN-polarity "
        if mismatch:
            note += "mqtt≠fb "
        print(f"{sw_s:>4} {name:8} {mqtt:8} {jmri:12} {fb:8} {mode_s:12}  {note}")
    print()
    print("Digicon paints MQTT retain. Live SoR = FB (except 116–119).")
    print("Wrong Digicon frog → flip that one PLANTS entry only — do not command points.")
    print("mqtt≠fb → Digicon disagrees with field until broker retain matches FB.")
    return 0


def seed_unknown_only(by_name: dict) -> int:
    """MQTT retain only when missing/unknown — never JMRI turnout commands."""
    for sw, addr in sorted(DEFAULT_THROWN.items()):
        sys_name = f"M2T{addr}"
        d = by_name.get(sys_name)
        retain = _mqtt_retain(addr)
        fb = _fb_implied(d) if d else None
        if retain in ("CLOSED", "THROWN"):
            print(f"Switch {sw} M2T{addr}: retain={retain} — leave (fb→{fb})")
            continue
        # Prefer FB if clear; else THROWN default for these four.
        msg = fb if fb in ("CLOSED", "THROWN") else "THROWN"
        _mqtt_pub(addr, msg)
        print(f"Switch {sw} M2T{addr}: no retain → MQTT {msg} only (fb→{fb}; no JMRI cmd)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--diagnose",
        action="store_true",
        help="Print table (default if no --write)",
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="Publish MQTT retain only when missing for 100/112/114/115 (no JMRI cmds)",
    )
    args = ap.parse_args()

    try:
        table = _get(f"{JMRI_JSON}/turnout")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"JMRI unreachable ({e})", file=sys.stderr)
        table = []

    by_name = {}
    for item in table:
        d = item.get("data", item)
        by_name[d.get("name")] = d

    if args.write:
        return seed_unknown_only(by_name)
    return diagnose(by_name)


if __name__ == "__main__":
    raise SystemExit(main())
