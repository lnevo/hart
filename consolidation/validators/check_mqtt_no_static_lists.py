#!/usr/bin/env python3
"""Fail if static MQTT head allow-lists reappear in live publisher/bridge/build."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LCOS = ROOT.parent / "LCOS_ESP32_MQTT_Client"

TARGETS_STRICT = [
    ROOT / "jmri/scripts/mqtt_signalhead_publisher.py",
    LCOS / "serial_to_mqtt.py",
    LCOS / "lcos_mqtt_bridge.cpp",
]

# build script may mention HEAD_NAMES only in guards that reject reintroduction
TARGETS_GUARD_OK = [
    ROOT / "cats/scripts/build_hart_signal_heads.py",
]

FORBIDDEN = (
    "MQTT_HEAD_NAMES",
    "DIGICON_PACKED_HEADS",
    "# HEAD_NAMES_BEGIN",
    "HEAD_NAMES = [",
)


def main() -> int:
    failed = False
    for path in TARGETS_STRICT + TARGETS_GUARD_OK:
        if not path.is_file():
            print(f"SKIP missing: {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in FORBIDDEN:
            if needle in text:
                print(f"FAIL {path.relative_to(ROOT.parent)}: contains {needle!r}")
                failed = True
        if path in TARGETS_STRICT and "\nHEAD_NAMES =" in text:
            print(f"FAIL {path.relative_to(ROOT.parent)}: contains HEAD_NAMES assignment")
            failed = True
    if failed:
        return 1
    print("OK: no static MQTT head allow-lists in publisher/bridge/build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
