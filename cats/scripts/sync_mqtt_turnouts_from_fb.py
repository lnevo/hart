#!/usr/bin/env python3
"""Publish MQTT turnout retain from JMRI FB N/R sensors (field SoR).

TWOSENSOR convention in hart_prod:
  FB R active → THROWN
  FB N active → CLOSED

Digicon SELECTEDREPORT follows track/turnout/{addr}. This updates broker
retain from sensors only — it does not command turnout motors.

Skips switches 116–119 (yard — not FB-driven Digicon SoR).

    python3 cats/scripts/sync_mqtt_turnouts_from_fb.py
    python3 cats/scripts/sync_mqtt_turnouts_from_fb.py --dry-run
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

# Yard ladder — Digicon not FB-SoR for these.
SKIP_SWITCH = {116, 117, 118, 119}

def _get(url: str):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)


def _fb_state(d: dict) -> str | None:
    n_on = r_on = False
    for s in d.get("sensor") or []:
        if s is None or not isinstance(s, dict):
            continue
        data = s.get("data")
        sd = data if isinstance(data, dict) else s
        if sd is None or not isinstance(sd, dict):
            continue
        if sd.get("state") != 4:  # ACTIVE
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        table = _get(f"{JMRI_JSON}/turnout")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"JMRI unreachable: {e}", file=sys.stderr)
        return 1

    n_ok = n_skip = n_chg = 0
    for item in sorted(table, key=lambda x: x.get("data", {}).get("name", "")):
        d = item.get("data", item)
        name = d.get("name") or ""
        if not name.startswith("M2T"):
            continue
        try:
            addr = int(name[3:])
        except ValueError:
            continue
        uname = d.get("userName") or name
        parts = uname.split()
        if len(parts) >= 2 and parts[0] == "Switch" and parts[1].isdigit():
            if int(parts[1]) in SKIP_SWITCH:
                continue
        fb = _fb_state(d)
        if fb is None:
            n_skip += 1
            continue
        prev = _mqtt_retain(addr)
        if prev == fb:
            print(f"ok  {name:10} {uname:16} FB→{fb} MQTT={prev}")
            n_ok += 1
            continue
        if args.dry_run:
            print(f"dry {name:10} {uname:16} FB→{fb} MQTT={prev!r} → would set {fb}")
        else:
            _mqtt_pub(addr, fb)
            print(f"set {name:10} {uname:16} FB→{fb} MQTT={prev!r} → {fb}")
        n_chg += 1

    print(f"synced={n_chg} unchanged={n_ok} no_clear_fb={n_skip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
