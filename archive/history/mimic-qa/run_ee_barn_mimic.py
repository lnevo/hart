#!/usr/bin/env python3
"""Tickle 110/111/112/117 + occupancy; compare CATS-prefixed masts vs SML.

Never publishes track/cmd/turnout. TWOSENSOR plants get FB N/R + turnout status.
117 is DIRECT — turnout status only.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

HOST = "minipc-e5h6x.local"
PUB = "/opt/local/bin/mosquitto_pub"
SUB = "/opt/local/bin/mosquitto_sub"
OUT = Path("/Users/lnevo/hart/cats/screenshots/mimic_qa")
PI = "pi"

MASTS = [
    "West Yard West East Main Ext",
    "West Yard East OS 117b",
    "West Yard West OS 117",
    "East End West Main West",
    "East End East OS 111a",
    "East End West Yard Track 1",
    "East End East Lead",
    "East End South OS 110",
    "East End South OS 112",
    "Plane East East Main Ext",
    "Brick East Main West",
    "Princess West OS 113a",
    "Princess West OS 113b",
]

# MQTT addr, N FB, R FB. None FB = DIRECT.
TO = {
    "110": {"addr": "1211", "n": "1273", "r": "1274"},
    "111": {"addr": "1212", "n": "1275", "r": "1276"},
    "112": {"addr": "1213", "n": "1277", "r": "1278"},
    "117": {"addr": "1308", "n": None, "r": None},
}


def pub(topic: str, payload: str) -> None:
    subprocess.check_call(
        [PUB, "-h", HOST, "-r", "-t", topic, "-m", payload],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def set_occ(addr: str, state: str) -> None:
    pub(f"track/sensor/{addr}", state)


def set_to(sw: str, state: str) -> None:
    rec = TO[sw]
    thrown = state == "THROWN"
    if rec["n"] and rec["r"]:
        pub(f"track/sensor/{rec['n']}", "INACTIVE" if thrown else "ACTIVE")
        pub(f"track/sensor/{rec['r']}", "ACTIVE" if thrown else "INACTIVE")
    pub(f"track/turnout/{rec['addr']}", state)


RESTORE_TOPICS = [
    "track/turnout/1211",
    "track/turnout/1212",
    "track/turnout/1213",
    "track/turnout/1308",
    "track/sensor/1273",
    "track/sensor/1274",
    "track/sensor/1275",
    "track/sensor/1276",
    "track/sensor/1277",
    "track/sensor/1278",
    "track/sensor/202",
    "track/sensor/106",
    "track/sensor/200",
    "track/sensor/107",
    "track/sensor/406",
    "track/sensor/1206",
]


REST = {
    "track/turnout/1211": "CLOSED",
    "track/turnout/1212": "CLOSED",
    "track/turnout/1213": "THROWN",
    "track/turnout/1308": "CLOSED",
    "track/sensor/1273": "ACTIVE",
    "track/sensor/1274": "INACTIVE",
    "track/sensor/1275": "ACTIVE",
    "track/sensor/1276": "INACTIVE",
    "track/sensor/1277": "INACTIVE",
    "track/sensor/1278": "ACTIVE",
    "track/sensor/202": "INACTIVE",
    "track/sensor/106": "INACTIVE",
    "track/sensor/200": "INACTIVE",
    "track/sensor/107": "INACTIVE",
    "track/sensor/406": "INACTIVE",
    "track/sensor/1206": "INACTIVE",
}


def restore(_baseline: Path | None = None) -> None:
    for topic, payload in REST.items():
        pub(topic, payload)


def jmri_snapshot() -> dict:
    remote = r"""
import json, urllib.request
want = set(%s)
with urllib.request.urlopen("http://127.0.0.1:12080/json/signalMast", timeout=8) as r:
    data = json.load(r)
out = {}
for m in data:
    d = m["data"]
    un = d.get("userName") or ""
    if un in want or (un.startswith("CATS ") and un[5:] in want):
        out[un] = d.get("aspect")
with urllib.request.urlopen("http://127.0.0.1:12080/json/turnout", timeout=8) as r:
    tos = json.load(r)
tstat = {}
for m in tos:
    d = m["data"]
    un = d.get("userName") or ""
    if un in ("Switch 110", "Switch 111", "Switch 112", "Switch 117"):
        st = d.get("state")
        tstat[un] = {2: "CLOSED", 4: "THROWN", 1: "UNKNOWN", 8: "INCONSISTENT"}.get(st, str(st))
print(json.dumps({"masts": out, "turnouts": tstat}))
""" % (repr(MASTS),)
    p = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", PI, "python3", "-"],
        input=remote,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if p.returncode != 0:
        raise SystemExit(p.stderr or p.stdout)
    line = [ln for ln in p.stdout.splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


def row(snap: dict) -> str:
    lines = ["turnouts: " + ", ".join("%s=%s" % kv for kv in sorted(snap["turnouts"].items()))]
    lines.append("%-42s %-14s %s" % ("mast", "SML", "CATS"))
    for name in MASTS:
        sml = snap["masts"].get(name, "—")
        cats = snap["masts"].get("CATS " + name, "—")
        mark = "" if sml == cats else "  MISMATCH"
        lines.append("%-42s %-14s %-14s%s" % (name, sml, cats, mark))
    return "\n".join(lines)


def grim(name: str) -> None:
    dest = OUT / name
    subprocess.check_call(
        [
            "ssh", "-o", "BatchMode=yes", PI,
            "XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 grim /tmp/hart_shot.png",
        ]
    )
    subprocess.check_call(["scp", "-o", "BatchMode=yes", f"{PI}:/tmp/hart_shot.png", str(dest)])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("snapshot check...", flush=True)
    print(row(jmri_snapshot()), flush=True)
    notes = []

    def step(tag: str, desc: str, do_grim: bool = False) -> dict:
        time.sleep(2.2)
        snap = jmri_snapshot()
        blob = "## %s\n%s\n%s\n" % (tag, desc, row(snap))
        notes.append(blob)
        print(blob)
        if do_grim:
            grim(tag + "_desktop.png")
        return snap

    try:
        step("ee00_baseline", "Live retain before tickle")

        set_to("110", "THROWN")
        step("ee01_110_thrown", "110 THROWN = ladder diverge into East Lead. OS 110 should leave Stop.")

        set_to("110", "CLOSED")
        step("ee02_110_closed", "110 CLOSED. OS 110 should be Stop/red.")

        set_to("111", "THROWN")
        step("ee03_111_thrown", "111 THROWN = crossover. North 111 east/west should change.")

        set_to("111", "CLOSED")
        step("ee04_111_closed", "111 CLOSED = Main West through WME. 111a Clear / West Main West Approach on CATS.")

        set_to("112", "CLOSED")
        step("ee05_112_closed", "112 CLOSED = through OS110 / East Lead. OS 112 should Stop; East Lead dest OS 110.")

        set_to("112", "THROWN")
        step("ee06_112_thrown", "112 THROWN = Barn / Main East. East Lead dest 117b; OS 112 dest 113a.")

        set_to("117", "THROWN")
        step("ee07_117_thrown", "117 THROWN = Barn crossover. Lower west Barn D should change.")

        set_to("117", "CLOSED")
        step("ee08_117_closed", "117 CLOSED = EME through Main East. Barn D Clear on CATS.")

        set_occ("202", "ACTIVE")
        step("ee09_main_east_occ", "Main East occupied — 117b / OS 112 should Stop.")
        set_occ("202", "INACTIVE")

        set_occ("106", "ACTIVE")
        step("ee10_east_lead_occ", "East Lead occupied — East Lead / OS 112 should Stop.")
        set_occ("106", "INACTIVE")

        set_occ("200", "ACTIVE")
        step("ee11_main_west_occ", "Main West occupied — 111a should Stop.")
        set_occ("200", "INACTIVE")

        set_occ("107", "ACTIVE")
        step("ee12_wme_occ", "West Main Ext occupied — West Main West / 115 should Stop.")
        set_occ("107", "INACTIVE")

        set_occ("406", "ACTIVE")
        step("ee13_eme_occ", "East Main Ext occupied — Plane EME / Barn D should Stop.")
        set_occ("406", "INACTIVE")

        set_occ("1206", "ACTIVE")
        step("ee14_os110_occ", "OS 110 occupied.")
        set_occ("1206", "INACTIVE")

        step("ee15_rest_clear", "Occupancy restored; points at field rest.")
    finally:
        print("restoring MQTT retain…")
        restore()
        time.sleep(2.0)
        step("ee99_restored", "Restored MQTT retain")

    (OUT / "ee_barn_notes.md").write_text("\n".join(notes))
    print("wrote", OUT / "ee_barn_notes.md")


if __name__ == "__main__":
    main()
