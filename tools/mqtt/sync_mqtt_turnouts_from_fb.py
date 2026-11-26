#!/usr/bin/env python3
"""Publish MQTT turnout retain from JMRI FB N/R sensors (field SoR).

TWOSENSOR convention in tables.xml:
  FB R active → THROWN
  FB N active → CLOSED

Digicon SELECTEDREPORT follows track/turnout/{addr}. This updates broker
retain from sensors only — it does not command turnout motors.

Skips Switch 13/7/11/9 (DCC 116–119 — yard / engine-house, not FB-driven Digicon SoR).
Exits 1 when JMRI cannot be reached or any publish fails.

    python3 tools/mqtt/sync_mqtt_turnouts_from_fb.py
    python3 tools/mqtt/sync_mqtt_turnouts_from_fb.py --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.error
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib.hosts import jmri_json_url, mqtt_broker  # noqa: E402

import turnout_feedback as tf  # noqa: E402  (sibling module; the script's folder is on sys.path)

JMRI_JSON = jmri_json_url()
MQTT_HOST = mqtt_broker()


class SyncCounts(NamedTuple):
    synced: int
    unchanged: int
    no_clear_fb: int
    failed: int


def _mqtt_pub(addr: int, msg: str) -> bool:
    """Retain msg on turnout addr; True when mosquitto_pub exits 0."""
    proc = subprocess.run(
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
    return proc.returncode == 0


def sync(
    table: Sequence[Mapping[str, object]],
    retain: Callable[[int], str | None],
    publish: Callable[[int, str], bool],
    dry_run: bool,
) -> SyncCounts:
    """Set each FB-driven turnout's retain to its feedback state; print one line per turnout with a clear state."""
    n_ok = n_skip = n_chg = n_fail = 0

    def _name(item: Mapping[str, object]) -> str:
        data = item.get("data")
        return str(data.get("name", "")) if isinstance(data, dict) else ""

    for item in sorted(table, key=_name):
        d = item.get("data", item)
        if not isinstance(d, Mapping):
            raise ValueError(f"JMRI turnout row is not an object: {item!r}")
        name = str(d.get("name") or "")
        addr = tf.m2t_address(name)
        if addr is None:
            continue
        uname = str(d.get("userName") or name)
        if tf.switch_number(uname) in tf.SKIP_FB:
            continue
        fb = tf.fb_state(d)
        if fb is None:
            n_skip += 1
            continue
        prev = retain(addr)
        if prev == fb:
            print(f"ok  {name:10} {uname:16} FB→{fb} MQTT={prev}")
            n_ok += 1
            continue
        if dry_run:
            print(f"dry {name:10} {uname:16} FB→{fb} MQTT={prev!r} → would set {fb}")
        elif publish(addr, fb):
            print(f"set {name:10} {uname:16} FB→{fb} MQTT={prev!r} → {fb}")
        else:
            print(f"FAIL {name:10} {uname:16} FB→{fb} MQTT={prev!r}: publish failed", file=sys.stderr)
            n_fail += 1
            continue
        n_chg += 1
    return SyncCounts(n_chg, n_ok, n_skip, n_fail)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        table = tf.get_json(f"{JMRI_JSON}/turnout", timeout=15)
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"JMRI unreachable: {e}", file=sys.stderr)
        return 1

    counts = sync(table, lambda addr: tf.mqtt_retain(MQTT_HOST, addr), _mqtt_pub, args.dry_run)
    print(f"synced={counts.synced} unchanged={counts.unchanged} no_clear_fb={counts.no_clear_fb} failed={counts.failed}")
    return 1 if counts.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
