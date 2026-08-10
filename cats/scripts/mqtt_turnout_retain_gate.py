#!/usr/bin/env python3
"""Stock-CATS safe MQTT turnout retain gate.

Stock CATS NPEs in PtsVitalLogic.setSelectedTrack when SELECTEDREPORT fires
before lock processors exist. That uncaught exception kills RREventManager
and freezes occupancy + turnout control for the session.

Workaround (no cats.jar patch):
  1. Snapshot panel turnout retain
  2. Clear retain so load has nothing to apply early
  3. After Digicon vital logic is up, restore retain (or sync from FB)

    python3 cats/scripts/mqtt_turnout_retain_gate.py snapshot-clear --panel PATH
    python3 cats/scripts/mqtt_turnout_retain_gate.py restore --snapshot PATH
    python3 cats/scripts/mqtt_turnout_retain_gate.py addrs --panel PATH
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

MQTT_HOST = os.environ.get("MQTT_HOST", "minipc-e5h6x.local")


def panel_turnout_addrs(panel: str) -> list[int]:
    root = ET.parse(panel).getroot()
    addrs: set[int] = set()
    for el in root.iter("SELECTEDREPORT"):
        for ios in el.findall("IOSPEC"):
            if ios.get("JMRIPREFIX") != "M2T":
                continue
            a = ios.get("DECADDR")
            if a and a.isdigit():
                addrs.add(int(a))
    for el in root.iter("ROUTECOMMAND"):
        for ios in el.findall("IOSPEC"):
            if ios.get("JMRIPREFIX") != "M2T":
                continue
            a = ios.get("DECADDR")
            if a and a.isdigit():
                addrs.add(int(a))
    return sorted(addrs)


def mqtt_get(addr: int) -> str | None:
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


def mqtt_clear(addr: int) -> None:
    # Null retained payload clears the topic.
    subprocess.run(
        [
            "mosquitto_pub",
            "-h",
            MQTT_HOST,
            "-t",
            f"track/turnout/{addr}",
            "-n",
            "-r",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def mqtt_set(addr: int, msg: str) -> None:
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def cmd_addrs(args: argparse.Namespace) -> int:
    addrs = panel_turnout_addrs(args.panel)
    print(" ".join(str(a) for a in addrs))
    return 0


def cmd_snapshot_clear(args: argparse.Namespace) -> int:
    addrs = panel_turnout_addrs(args.panel)
    snap: dict[str, str] = {}
    for a in addrs:
        v = mqtt_get(a)
        if v in ("CLOSED", "THROWN"):
            snap[str(a)] = v
    os.makedirs(os.path.dirname(args.snapshot) or ".", exist_ok=True)
    with open(args.snapshot, "w", encoding="utf-8") as f:
        json.dump({"host": MQTT_HOST, "panel": args.panel, "retain": snap}, f, indent=2)
        f.write("\n")
    for a in addrs:
        mqtt_clear(a)
    print(
        f"turnout retain gate: snapshotted {len(snap)}/{len(addrs)} "
        f"→ cleared {len(addrs)} topics ({args.snapshot})"
    )
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    with open(args.snapshot, encoding="utf-8") as f:
        data = json.load(f)
    retain = data.get("retain") or {}
    n = 0
    for a_s, msg in retain.items():
        if msg not in ("CLOSED", "THROWN"):
            continue
        mqtt_set(int(a_s), msg)
        n += 1
    print(f"turnout retain gate: restored {n} topics from {args.snapshot}")
    return 0


def cmd_wait_restore(args: argparse.Namespace) -> int:
    delay = max(0, int(args.delay))
    print(f"turnout retain gate: waiting {delay}s before restore…")
    time.sleep(delay)
    if args.sync_from_fb:
        script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "sync_mqtt_turnouts_from_fb.py"
        )
        print("turnout retain gate: sync_mqtt_turnouts_from_fb.py")
        return subprocess.call([sys.executable, script])
    return cmd_restore(args)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_addrs = sub.add_parser("addrs", help="Print panel M2T turnout addrs")
    p_addrs.add_argument("--panel", required=True)
    p_addrs.set_defaults(func=cmd_addrs)

    p_sc = sub.add_parser("snapshot-clear", help="Snapshot then clear panel turnout retain")
    p_sc.add_argument("--panel", required=True)
    p_sc.add_argument("--snapshot", required=True)
    p_sc.set_defaults(func=cmd_snapshot_clear)

    p_r = sub.add_parser("restore", help="Restore retain from snapshot JSON")
    p_r.add_argument("--snapshot", required=True)
    p_r.set_defaults(func=cmd_restore)

    p_w = sub.add_parser("wait-restore", help="Sleep then restore (or FB sync)")
    p_w.add_argument("--snapshot", required=True)
    p_w.add_argument("--delay", type=int, default=50)
    p_w.add_argument(
        "--sync-from-fb",
        action="store_true",
        help="After delay, run sync_mqtt_turnouts_from_fb instead of snapshot",
    )
    p_w.set_defaults(func=cmd_wait_restore)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
