#!/usr/bin/env python3
"""Make every occupancy lamp on every panel in tables.xml display only.

    python3 jmri/layouts/hart/scripts/occupancy_lamps_display_only.py --check   # exit 1 if a lamp can be clicked
    python3 jmri/layouts/hart/scripts/occupancy_lamps_display_only.py --tables OTHER.xml   # fix another file

tables.xml is generated since R9c (ADR-029): the panel build writes its lamps display only, so this script checks
it and refuses to write it (hartlib.tables_build.refuse_generated); it still fixes another tables file and the parked
staging lamps.

A lamp is a sensoricon whose sensor is a block sensor ("BS ...") or that is drawn with the circuit-* lamp images
(Stage 1's occupancy and move-in-progress lamps). The panel polish script applies the same rule on every polish,
so a Stage 1 Store, which writes its lamps clickable, is put right by the wrapper and by every deploy. On a JMRI panel a click on a sensor
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
from hartlib import paths, tables_build  # noqa: E402

# Occupancy lamps are edited as text, so the rest of each file stays byte for byte. The staging panel's lamps parked
# with the Dispatcher System (jmri/layouts/hart/parked/staging_panel_lamps.json, panel_items.json form) hold the same
# lamps as XML strings inside JSON, with escaped quotes; they must stay display only to come back that way.
OVERLAY = paths.LAYOUT_DATA.parent / "parked" / "staging_panel_lamps.json"


def lamp_pattern(escaped: bool = False) -> re.Pattern:
    """A whole sensoricon element (start tag in group 1); `escaped` for the JSON-quoted overlay."""
    return re.compile(r'(<sensoricon\b[^>]*>)(.*?</sensoricon>)?', re.S)


def is_lamp(tag: str, body: str, escaped: bool = False) -> bool:
    """A lamp that shows state: a block sensor ("BS ...") or one drawn with the circuit-* lamp images (Stage 1's
    occupancy and move-in-progress lamps). The same rule as parked/polish_hart_layout_editor._is_display_lamp."""
    q = '\\"' if escaped else '"'
    return f"sensor={q}BS " in tag or "circuit-" in (body or "")


def fix(text: str, escaped: bool = False) -> tuple[str, int]:
    """(text with every occupancy lamp display only, number of lamps changed)."""
    q = '\\"' if escaped else '"'
    on = f"forcecontroloff={q}true{q}"
    off = re.compile(re.escape(f"forcecontroloff={q}") + r"[a-z]*" + re.escape(q))
    changed = 0

    def one(m: re.Match) -> str:
        nonlocal changed
        tag, body = m.group(1), m.group(2) or ""
        if not is_lamp(tag, body, escaped) or on in tag:
            return m.group(0)
        changed += 1
        if off.search(tag):
            return off.sub(lambda _m: on, tag, count=1) + body
        return tag.replace("<sensoricon ", f"<sensoricon {on} ", 1) + body

    return lamp_pattern(escaped).sub(one, text), changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if any occupancy lamp can be clicked")
    ap.add_argument("--tables", type=Path, default=paths.TABLES_XML)
    ap.add_argument("--overlay", type=Path, default=OVERLAY, help="the parked staging lamps (skipped if absent)")
    args = ap.parse_args(argv)
    bad = 0
    if not args.tables.exists():
        print(f"no tables file at {args.tables}", file=sys.stderr)
        return 2
    for path, escaped in ((args.tables, False), (args.overlay, True)):
        if not path.exists():                      # the parked lamps are optional; the tables file is not
            continue
        text = path.read_text(encoding="utf-8")
        new, changed = fix(text, escaped)
        total = sum(1 for m in lamp_pattern(escaped).finditer(text) if is_lamp(m.group(1), m.group(2), escaped))
        if args.check:
            if changed:
                print(f"{changed} of {total} occupancy lamps in {path.name} can be clicked: run "
                      f"{Path(__file__).name}", file=sys.stderr)
                bad += 1
            else:
                print(f"{path.name}: all {total} occupancy lamps are display only")
            continue
        if changed:
            if path == args.tables:
                tables_build.refuse_generated(path, Path(__file__).name)
            path.write_text(new, encoding="utf-8")
        print(f"{path.name}: {changed} of {total} occupancy lamps made display only")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
