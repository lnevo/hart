#!/usr/bin/env python3
"""Fail if static MQTT head allow-lists reappear in live publisher/bridge/build."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consolidation" / "scripts" / "lib"))

from consolidation_paths import hart_runtime_root, path_lcos_bridge

HART_ROOT = hart_runtime_root()
LCOS = path_lcos_bridge()

TARGETS_STRICT = [
    HART_ROOT / "jmri/scripts/mqtt_signalhead_publisher.py",
    LCOS / "serial_to_mqtt.py",
    LCOS / "lcos_mqtt_bridge.cpp",
]

TARGETS_GUARD_OK = [
    HART_ROOT / "cats/scripts/build_hart_signal_heads.py",
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
            print(f"SKIP missing: {path.relative_to(HART_ROOT) if path.is_relative_to(HART_ROOT) else path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in FORBIDDEN:
            if needle in text:
                rel = path.relative_to(HART_ROOT) if path.is_relative_to(HART_ROOT) else path
                print(f"FAIL {rel}: contains {needle!r}")
                failed = True
        if path in TARGETS_STRICT and "\nHEAD_NAMES =" in text:
            rel = path.relative_to(HART_ROOT) if path.is_relative_to(HART_ROOT) else path
            print(f"FAIL {rel}: contains HEAD_NAMES assignment")
            failed = True
    if failed:
        return 1
    print("OK: no static MQTT head allow-lists in publisher/bridge/build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
