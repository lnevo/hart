#!/usr/bin/env python3
"""Clear MQTT junk that must never be on this broker.

1) track/cmd/sensor/#     — sensors are status-only (never commanded)
2) bare "{addr}" topics   — ACTIVE|INACTIVE at broker root (bug from
   MqttSensor.setKnownState with an empty JMRI send-topic template)

Does not touch track/sensor/{addr} or track/turnout/{addr} status retain.

    MQTT_HOST=minipc-e5h6x.local python3 cats/scripts/clear_mqtt_cmd_sensor_retain.py
"""

from __future__ import annotations

import os
import subprocess
import sys

MQTT_HOST = os.environ.get("MQTT_HOST", "minipc-e5h6x.local")


def _sub(topic: str, wait: str = "1") -> list[tuple[str, str]]:
    try:
        out = subprocess.check_output(
            ["mosquitto_sub", "-h", MQTT_HOST, "-t", topic, "-v", "-W", wait],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        out = e.output or ""
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or " " not in line:
            continue
        if line.lower().startswith("timed out"):
            continue
        t, p = line.split(" ", 1)
        rows.append((t, p.strip()))
    return rows


def _clear(topic: str) -> None:
    subprocess.run(
        ["mosquitto_pub", "-h", MQTT_HOST, "-t", topic, "-n", "-r"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    cleared: list[str] = []

    for t, _p in _sub("track/cmd/sensor/#"):
        if t.startswith("track/cmd/sensor/"):
            _clear(t)
            cleared.append(t)

    # Bare numeric root topics with sensor payloads (layout bug artifacts).
    for t, p in _sub("+"):
        if t.isdigit() and p.upper() in ("ACTIVE", "INACTIVE"):
            _clear(t)
            cleared.append(t)

    # Discard sink if someone setKnownState with the disabled send template.
    for t, _p in _sub("_discard/cmd/sensor/#"):
        if t.startswith("_discard/cmd/sensor/"):
            _clear(t)
            cleared.append(t)

    left_cmd = [t for t, _ in _sub("track/cmd/sensor/#") if t.startswith("track/cmd/sensor/")]
    left_root = [
        t
        for t, p in _sub("+")
        if t.isdigit() and p.upper() in ("ACTIVE", "INACTIVE")
    ]
    left_discard = [
        t for t, _ in _sub("_discard/cmd/sensor/#") if t.startswith("_discard/cmd/sensor/")
    ]
    print(
        "cleared=%d remaining_cmd=%d remaining_root_numeric=%d remaining_discard=%d host=%s"
        % (len(cleared), len(left_cmd), len(left_root), len(left_discard), MQTT_HOST)
    )
    return 0 if not left_cmd and not left_root and not left_discard else 1


if __name__ == "__main__":
    sys.exit(main())
