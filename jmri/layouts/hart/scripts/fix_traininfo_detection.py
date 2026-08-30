#!/usr/bin/env python3
"""Force HEAD_AND_TAIL train detection in Dispatcher traininfo files.

JMRI's Dispatcher System (jython/DispatcherSystem) hardcodes
TrainInfo.setResistanceWheels(True) — i.e. "Entire Train" detection —
every time it regenerates traininfo files in Stage 1. Our rolling stock
only has resistance wheelsets on the head and tail, so rerun this script
after any Dispatcher System Stage 1 run:

    python3 fix_traininfo_detection.py [traininfo_dir]

Default dir: /home/pi/JMRI_UserFiles/dispatcher/traininfo (Pi) or the
repo copy if run from the repo.
"""
import re
import sys
from pathlib import Path

DEFAULT_DIRS = [
    Path("/home/pi/JMRI_UserFiles/dispatcher/traininfo"),
    Path(__file__).resolve().parents[1] / "dispatcher" / "traininfo",
]


def fix_dir(d: Path) -> int:
    n = 0
    for f in sorted(d.glob("*.xml")):
        txt = f.read_text(encoding="utf-8")
        new = re.sub(
            r'traindetection="(?:TRAINDETECTION_)?(?:WHOLETRAIN|HEADONLY)"',
            'traindetection="TRAINDETECTION_HEADANDTAIL"',
            txt,
        )
        if new != txt:
            f.write_text(new, encoding="utf-8")
            print(f"fixed {f.name}")
            n += 1
    return n


def main() -> None:
    if len(sys.argv) > 1:
        dirs = [Path(sys.argv[1])]
    else:
        dirs = [d for d in DEFAULT_DIRS if d.is_dir()]
        if not dirs:
            raise SystemExit("no traininfo dir found; pass one explicitly")
    total = 0
    for d in dirs:
        print(f"scanning {d}")
        total += fix_dir(d)
    print(f"{total} file(s) updated")


if __name__ == "__main__":
    main()
