#!/usr/bin/env python3
"""Fail if static MQTT head allow-lists reappear in live publisher/bridge/build.

The HART files are always read; a missing one fails. The two LCOS bridge files are read when the bridge is
checked out (external/lcos-bridge, or a sibling clone: hartlib.paths.lcos_bridge); a missing one then fails.
With no bridge checkout (CI clones only external/model-railroad-skills) the check says so and reads the rest."""
from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import coordinator, paths  # noqa: E402

HART_ROOT = paths.REPO_ROOT
LCOS_FILES = ("serial_to_mqtt.py", "lcos_mqtt_bridge.cpp")
BUILD = HART_ROOT / "jmri/layouts/hart/scripts/build_hart_signal_heads.py"

FORBIDDEN = (
    "MQTT_HEAD_NAMES",
    "DIGICON_PACKED_HEADS",
    "# HEAD_NAMES_BEGIN",
    "HEAD_NAMES = [",
)


def checked_out(folder: Path) -> bool:
    """True when ``folder`` holds a checkout: an empty submodule folder is not one."""
    return folder.is_dir() and any(folder.iterdir())


def problems(path: Path, strict: bool) -> list[str]:
    """What ``path`` holds that it must not; a missing file is a problem too."""
    rel = paths.rel(path, HART_ROOT)
    if not path.is_file():
        return [f"FAIL {rel}: missing, so it cannot be checked"]
    text = path.read_text(encoding="utf-8", errors="replace")
    found = [f"FAIL {rel}: contains {needle!r}" for needle in FORBIDDEN if needle in text]
    if strict and "\nHEAD_NAMES =" in text:
        found.append(f"FAIL {rel}: contains HEAD_NAMES assignment")
    return found


def run(strict: Sequence[Path], guard_ok: Sequence[Path], lcos: Path) -> int:
    """Check ``strict`` (no HEAD_NAMES assignment either) and ``guard_ok`` files, and the bridge files in ``lcos``."""
    targets = [(p, True) for p in strict] + [(p, False) for p in guard_ok]
    if checked_out(lcos):
        targets += [(lcos / name, True) for name in LCOS_FILES]
    else:
        print(f"NOT CHECKED: no LCOS bridge checkout at {paths.rel(lcos, HART_ROOT)}; "
              f"{', '.join(LCOS_FILES)} not read (git submodule update --init external/lcos-bridge)")
    found = [line for path, is_strict in targets for line in problems(path, is_strict)]
    for line in found:
        print(line)
    if found:
        return 1
    print("OK: no static MQTT head allow-lists in publisher/bridge/build")
    return 0


def main() -> int:
    try:
        files = coordinator.files()   # signal_coordinator.py and every sibling module it loads
    except coordinator.CoordinatorError as exc:
        print(f"FAIL {exc}")
        return 1
    return run(files, [BUILD], paths.lcos_bridge())


if __name__ == "__main__":
    raise SystemExit(main())
