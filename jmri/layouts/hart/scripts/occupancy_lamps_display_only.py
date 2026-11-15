#!/usr/bin/env python3
"""Make every occupancy lamp on every panel in tables.xml display only.

    python3 jmri/layouts/hart/scripts/occupancy_lamps_display_only.py           # write tables.xml
    python3 jmri/layouts/hart/scripts/occupancy_lamps_display_only.py --check   # exit 1 if a lamp can be clicked

An occupancy lamp is a sensoricon whose sensor is a block sensor ("BS ..."). On a JMRI panel a click on a sensor
icon toggles its sensor, and JMRI publishes that to MQTT, so every host sees the block occupied. Since the
switch OS lamps were centred in the turnout circles (2026-11-13), a click that throws a turnout also hit its OS
lamp. forcecontroloff="true" makes the lamps show state only; the turnout click still works. Run with PanelPro
and CATS closed, like every table script. Owner, 2026-11-15: the workaround until lamp placement is redone
before the Dispatcher and NX setup.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

# Occupancy lamps are edited as text, so the rest of each file stays byte for byte. The frozen overlay of the
# Layout Editor cut-over (tools/schematic/build_layout_le.py) holds the same lamps as XML strings inside JSON, with
# escaped quotes; they must match the panel they were frozen from.
OVERLAY = paths.LAYOUT_DATA / "schematic" / "staging_le" / "overlay.json"


def lamp_pattern(escaped: bool = False) -> re.Pattern:
    """A sensoricon start tag naming a block sensor ("BS ..."); `escaped` for the JSON-quoted overlay."""
    q = re.escape('\\"' if escaped else '"')
    return re.compile(r'<sensoricon\b[^>]*?\bsensor=' + q + r'BS [^"\\]*' + q + r'[^>]*>')


def fix(text: str, escaped: bool = False) -> tuple[str, int]:
    """(text with every occupancy lamp display only, number of lamps changed)."""
    q = '\\"' if escaped else '"'
    on = f"forcecontroloff={q}true{q}"
    off = re.compile(re.escape(f"forcecontroloff={q}") + r"[a-z]*" + re.escape(q))
    changed = 0

    def one(m: re.Match) -> str:
        nonlocal changed
        tag = m.group(0)
        if on in tag:
            return tag
        changed += 1
        if off.search(tag):
            return off.sub(lambda _m: on, tag, count=1)
        return tag.replace("<sensoricon ", f"<sensoricon {on} ", 1)

    return lamp_pattern(escaped).sub(one, text), changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if any occupancy lamp can be clicked")
    ap.add_argument("--tables", type=Path, default=paths.TABLES_XML)
    ap.add_argument("--overlay", type=Path, default=OVERLAY, help="the cut-over's frozen overlay (skipped if absent)")
    args = ap.parse_args(argv)
    bad = 0
    for path, escaped in ((args.tables, False), (args.overlay, True)):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        new, changed = fix(text, escaped)
        total = len(lamp_pattern(escaped).findall(text))
        if args.check:
            if changed:
                print(f"{changed} of {total} occupancy lamps in {path.name} can be clicked: run "
                      f"{Path(__file__).name}", file=sys.stderr)
                bad += 1
            else:
                print(f"{path.name}: all {total} occupancy lamps are display only")
            continue
        if changed:
            path.write_text(new, encoding="utf-8")
        print(f"{path.name}: {changed} of {total} occupancy lamps made display only")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
