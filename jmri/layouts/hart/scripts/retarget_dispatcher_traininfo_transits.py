#!/usr/bin/env python3
"""Retarget generated TrainInfo transit names after the public-name convert.

Stage 1 wrote transit via-hints as ``via Track 7``. Tables now use
``via OS Switch 7``. Dispatcher System cannot find the old names and asks
to rebuild the graph. Do not re-run Stage 1 for this — rewrite the
bindings, then ``fix_traininfo_detection.py`` if needed.

    python3 jmri/layouts/hart/scripts/retarget_dispatcher_traininfo_transits.py
    python3 jmri/layouts/hart/scripts/retarget_dispatcher_traininfo_transits.py --check

Default dir: repo ``dispatcher/traininfo``, or the Pi UserFiles copy.
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DIRS = [
    Path("/home/pi/JMRI_UserFiles/dispatcher/traininfo"),
    Path(__file__).resolve().parents[1] / "dispatcher" / "traininfo",
]
DEFAULT_TABLES = [
    Path("/home/pi/JMRI_UserFiles/tables.xml"),
    Path("/home/pi/hart/tables.xml"),
    ROOT / "jmri" / "layouts" / "hart" / "output" / "tables.xml",
]
VIA_TRACK = re.compile(r"\bvia Track ([0-9]+[a-z]?)\b")


def live_transit_names(tables: Path) -> set[str]:
    root = ET.parse(tables).getroot()
    return {
        (el.get("userName") or "").strip()
        for el in root.findall("./transits/transit")
        if (el.get("userName") or "").strip()
    }


def rewrite_name(name: str) -> str:
    return VIA_TRACK.sub(r"via OS Switch \1", name)


def retarget_file(path: Path, live: set[str], write: bool) -> str | None:
    text = path.read_text(encoding="utf-8")
    root = ET.fromstring(text)
    info = root.find("traininfo")
    if info is None:
        raise ValueError(f"{path.name}: no traininfo element")
    old = info.get("transitname") or ""
    if old in live:
        return None
    new = rewrite_name(old)
    if new == old or new not in live:
        raise ValueError(f"{path.name}: no live transit for {old!r} -> {new!r}")
    if not write:
        return f"{path.name}: {old} -> {new}"
    updated = text.replace(f'transitname="{old}"', f'transitname="{new}"', 1)
    updated = updated.replace(f'transitid="{old}"', f'transitid="{new}"', 1)
    if updated == text:
        raise ValueError(f"{path.name}: attributes not found for rewrite")
    path.write_text(updated, encoding="utf-8")
    return f"{path.name}: {old} -> {new}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traininfo_dir", nargs="?", type=Path)
    parser.add_argument("--tables", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    tables = args.tables
    if tables is None:
        tables = next((p for p in DEFAULT_TABLES if p.is_file()), None)
    if tables is None or not tables.is_file():
        raise SystemExit("tables.xml not found; pass --tables")
    live = live_transit_names(tables)

    dirs = [args.traininfo_dir] if args.traininfo_dir else [d for d in DEFAULT_DIRS if d.is_dir()]
    if not dirs:
        raise SystemExit("no traininfo dir found; pass one explicitly")

    total = 0
    for directory in dirs:
        print(f"scanning {directory} against {tables} ({len(live)} transits)")
        for path in sorted(directory.glob("*.xml")):
            detail = retarget_file(path, live, write=not args.check)
            if detail:
                print(("would " if args.check else "") + detail)
                total += 1
    print(f"{total} file(s) {'need retarget' if args.check else 'updated'}")
    return 1 if args.check and total else 0


if __name__ == "__main__":
    raise SystemExit(main())
