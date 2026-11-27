#!/usr/bin/env python3
"""Diagnose Digicon turnout MQTT vs FB (read-only).

Rules (SoR):
  - Live Digicon state follows **FB** for all turnouts except Switch 13/7/11/9
    (DCC 116–119; yard / engine-house, not FB-driven Digicon SoR).
  - Digicon SEL+CMD share one polarity. No switch is inverted: closed is the straight
    (normal) leg everywhere. Switches 1 and 33 start up thrown in the field (the main
    runs through their diverging legs, STARTS_THROWN); the rest start up closed.
    Nothing here sets a state: --diagnose flags 1 or 33 when not thrown.
  - Wrong Digicon direction → fix **that one switch only** in
    `jmri/layouts/hart/data/switches.csv`, then rebuild
    the desks. Do not command MQTT/JMRI.
  - This script must not throw field points.

    python3 jmri/layouts/hart/scripts/diagnose_turnout_states.py
    python3 jmri/layouts/hart/scripts/diagnose_turnout_states.py --diagnose

Read-only. Use tools/mqtt/sync_mqtt_turnouts_from_fb.py only when Digicon must track FB.
Exits 1 when JMRI or the MQTT broker cannot be read.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
from collections.abc import Callable, Mapping
from pathlib import Path

sys.path[:0] = [str(p / sub) for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir() for sub in ("tools/hartlib/src", "tools/mqtt")][:2] \
    or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib.hosts import jmri_json_url, mqtt_broker  # noqa: E402

import mosquitto_cli  # noqa: E402
import turnout_feedback as tf  # noqa: E402

JMRI_JSON = jmri_json_url()
MQTT_HOST = mqtt_broker()

# Start up thrown: the main runs through their diverging legs. Plate numbers.
STARTS_THROWN = {1, 33}

STATE = {0: "UNKNOWN", 1: "UNKNOWN", 2: "CLOSED", 4: "THROWN", 8: "INCONSISTENT"}
FB_MODE = {
    1: "DIRECT",
    2: "EXACT",
    4: "INDIRECT/ONESENSOR?",
    8: "TWOSENSOR",
    16: "MONITORING",
    32: "mode=32 (MQTT/command drives KnownState)",
    128: "mode=128",
}


class JmriUnreachable(RuntimeError):
    """The JMRI JSON server did not answer."""


def diagnose(by_name: Mapping[str, Mapping[str, object]], retain: Callable[[int], str | None]) -> int:
    rows = []
    for name, d in by_name.items():
        addr = tf.m2t_address(name or "")
        if addr is None:
            continue
        sw = tf.switch_number(str(d.get("userName") or ""))
        if sw is not None and sw in tf.SKIP_FB:
            continue
        mqtt = retain(addr) or "(none)"
        state = d.get("state")
        jmri = STATE.get(state, str(state)) if isinstance(state, int) else str(state)
        fb = tf.fb_state(d) or "?"
        mode = d.get("feedbackMode")
        mode_s = FB_MODE.get(mode, str(mode)) if isinstance(mode, int) else str(mode)
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
        if sw in STARTS_THROWN and "THROWN" not in (jmri, fb):
            note += "not-thrown(starts-thrown) "
        if mismatch:
            note += "mqtt≠fb "
        print(f"{sw_s:>4} {name:8} {mqtt:8} {jmri:12} {fb:8} {mode_s:12}  {note}")
    print()
    print("Digicon paints MQTT retain. Live SoR = FB (except Switch 13/7/11/9).")
    print("Wrong Digicon frog → fix that one switch in data/switches.csv only — do not command points.")
    print("mqtt≠fb → Digicon disagrees with field until broker retain matches FB.")
    return 0


def read_turnouts() -> dict[str, Mapping[str, object]]:
    """The JMRI turnout table by system name. Raises JmriUnreachable when JMRI does not answer."""
    try:
        table = tf.get_json(f"{JMRI_JSON}/turnout", timeout=10)
    except (urllib.error.URLError, TimeoutError) as e:
        raise JmriUnreachable(f"JMRI unreachable at {JMRI_JSON}: {e}") from e
    by_name: dict[str, Mapping[str, object]] = {}
    for item in table:
        d = item.get("data", item)
        if isinstance(d, Mapping):
            by_name[str(d.get("name") or "")] = d
    return by_name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--diagnose",
        action="store_true",
        help="Print table (the default)",
    )
    ap.parse_args()

    try:
        by_name = read_turnouts()
    except JmriUnreachable as e:
        print(f"{e}; no table to show", file=sys.stderr)
        return 1
    try:
        return diagnose(by_name, lambda addr: tf.mqtt_retain(MQTT_HOST, addr))
    except mosquitto_cli.MosquittoError as e:
        print(f"MQTT broker {MQTT_HOST} unreadable: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
