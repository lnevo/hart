#!/usr/bin/env python3
"""Drive Princess MQTT like lcos_mqtt_mimic.py, grim Pi desktop, then restore.

Never publishes track/cmd/turnout. TWOSENSOR plants get FB N/R + turnout status.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

HOST = "minipc-e5h6x.local"
PUB = "/opt/local/bin/mosquitto_pub"
SUB = "/opt/local/bin/mosquitto_sub"
OUT = Path("/Users/lnevo/hart/cats/screenshots/mimic_qa")
PI = "pi"

# Switch 113/114/115 TWOSENSOR (sensor1=R, sensor2=N)
TO = {
    "113": {"addr": "108", "n": "167", "r": "168"},
    "114": {"addr": "109", "n": "169", "r": "170"},
    "115": {"addr": "110", "n": "171", "r": "172"},
}

HEADS = ["IH132", "IH133", "IH134", "IH137", "IH138", "IH139", "IH140", "IH141"]


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
    pub(f"track/sensor/{rec['n']}", "INACTIVE" if thrown else "ACTIVE")
    pub(f"track/sensor/{rec['r']}", "ACTIVE" if thrown else "INACTIVE")
    pub(f"track/turnout/{rec['addr']}", state)


def snap_mqtt() -> str:
    p = subprocess.run(
        [SUB, "-h", HOST, "-t", "track/sensor/#", "-t", "track/turnout/#",
         "-t", "track/signalhead/IH132", "-t", "track/signalhead/IH133",
         "-t", "track/signalhead/IH134", "-t", "track/signalhead/IH139",
         "-t", "track/signalhead/IH140", "-t", "track/signalhead/IH141",
         "-v", "-W", "2"],
        capture_output=True, text=True,
    )
    return p.stdout


def grim(name: str) -> Path:
    dest = OUT / name
    subprocess.check_call(
        [
            "ssh", "-o", "BatchMode=yes", PI,
            "XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 grim /tmp/hart_shot.png",
        ]
    )
    subprocess.check_call(["scp", "-o", "BatchMode=yes", f"{PI}:/tmp/hart_shot.png", str(dest)])
    return dest


def restore(baseline: Path) -> None:
    for line in baseline.read_text().splitlines():
        if " " not in line:
            continue
        topic, payload = line.split(" ", 1)
        if topic.startswith("track/cmd/"):
            continue
        if not (topic.startswith("track/sensor/") or topic.startswith("track/turnout/")):
            continue
        pub(topic, payload)


def main() -> None:
    baseline = OUT / "mqtt_baseline.txt"
    notes = []

    def step(tag: str, desc: str) -> None:
        time.sleep(2.5)
        path = grim(f"{tag}_desktop.png")
        mqtt = snap_mqtt()
        (OUT / f"{tag}_mqtt.txt").write_text(mqtt)
        heads = "\n".join(
            ln for ln in mqtt.splitlines() if "signalhead" in ln or "sensor/10" in ln
            or "turnout/10" in ln
        )
        notes.append(f"## {tag}\n{desc}\n{path.name}\n{heads}\n")
        print(f"saved {path.name}")

    step("01_live", "Live field retain (no mimic yet)")

    # 115 should proceed: 113 normal, 115 thrown, WME empty, Rocks empty
    set_occ("100", "INACTIVE")
    set_occ("107", "INACTIVE")
    set_to("113", "CLOSED")
    set_to("115", "THROWN")
    step("02_115_clear_route", "Rocks empty, 113 normal, 115 thrown, WME empty")

    set_occ("107", "ACTIVE")
    step("03_wme_occupied", "Same but West Main Ext occupied — 115 should Stop")

    set_occ("107", "INACTIVE")
    set_to("113", "THROWN")
    step("04_113_reverse", "113 reverse, East Lead empty — 115 dest East Lead")

    set_to("113", "CLOSED")
    set_occ("101", "ACTIVE")
    set_to("114", "THROWN")
    step("05_mckeesport_occ_114_thrown", "McKeesport occupied, 114 thrown, 113 normal")

    set_occ("101", "INACTIVE")
    step("06_mckeesport_empty_114_thrown", "McKeesport empty, 114 thrown — South dwarf / 114 home")

    print("restoring baseline MQTT retain…")
    restore(baseline)
    time.sleep(2.5)
    grim("99_restored_desktop.png")
    (OUT / "notes.md").write_text("\n".join(notes))
    print("done")


if __name__ == "__main__":
    main()
