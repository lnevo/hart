#!/usr/bin/env python3
"""Fail if static MQTT head allow-lists reappear in live publisher/bridge/build."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

HART_ROOT = paths.REPO_ROOT
LCOS = paths.lcos_bridge()

TARGETS_STRICT = [
    HART_ROOT / "jmri/scripts/signal_coordinator.py",
    LCOS / "serial_to_mqtt.py",
    LCOS / "lcos_mqtt_bridge.cpp",
]

TARGETS_GUARD_OK = [
    HART_ROOT / "jmri/layouts/hart/scripts/build_hart_signal_heads.py",
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
