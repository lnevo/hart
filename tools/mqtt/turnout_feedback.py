"""Turnout feedback reading shared by diagnose_turnout_states.py and sync_mqtt_turnouts_from_fb.py.

TWOSENSOR convention in tables.xml: FB R active means THROWN, FB N active means CLOSED.
Reads only: the JMRI JSON turnout table and one retained turnout topic. Nothing here publishes.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Mapping
from typing import Literal

import mosquitto_cli  # sibling module: tools/mqtt is on sys.path wherever this module is imported

FbState = Literal["CLOSED", "THROWN"]

# Yard / engine-house switches (DCC 116-119): Digicon is not driven by their feedback.
SKIP_FB = frozenset({13, 7, 11, 9})

_ACTIVE = 4


def get_json(url: str, timeout: float) -> list[dict[str, object]]:
    """The JMRI JSON reply at url. Raises urllib.error.URLError or TimeoutError when JMRI cannot be reached."""
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def m2t_address(name: str) -> int | None:
    """The MQTT address of an M2T turnout system name; None for any other name."""
    if not name.startswith("M2T"):
        return None
    try:
        return int(name[3:])
    except ValueError:
        return None


def switch_number(user_name: str) -> int | None:
    """N from a "Switch N" user name; None for any other name."""
    parts = user_name.split()
    if len(parts) >= 2 and parts[0] == "Switch" and parts[1].isdigit():
        return int(parts[1])
    return None


def fb_state(turnout: Mapping[str, object]) -> FbState | None:
    """The state the active FB N or FB R sensor implies; None when neither or both are active."""
    n_on = r_on = False
    sensors = turnout.get("sensor") or []
    for s in sensors if isinstance(sensors, list) else []:
        if not isinstance(s, dict):
            continue
        data = s.get("data")
        sd = data if isinstance(data, dict) else s
        if sd.get("state") != _ACTIVE:
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


def mqtt_retain(host: str, addr: int, run: mosquitto_cli.Runner = mosquitto_cli.run_command) -> str | None:
    """The retained payload of turnout addr on host; None when the topic holds none. MosquittoError when
    mosquitto_sub cannot be started or the broker cannot be read."""
    found = mosquitto_cli.subscribe(host, f"track/turnout/{addr}", wait=1, count=1, run=run)
    return (found[0].payload or None) if found else None
