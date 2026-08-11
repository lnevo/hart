#!/usr/bin/env python3
"""Build HART_Master_ABS_hold.xml — ABS-RO Digicon (signals listen-only).

Derived from HART_Master_ABS.xml:

1. HOLD_ONLY=true on every ASPECTMAP — Digicon paints aspects from JMRI/MQTT;
   CATS does not drive Clear/Approach/Stop (authoritative Digicon / field does).
2. Keep ROUTECOMMAND — plant clicks still throw turnouts on the layout.
3. Keep yard-ladder BUTTONs — same ladder routes as CTC/ABS.
4. Keep DISCIPLINE=ABS, geometry, occupancy, SELECTEDREPORT feedback.

Use as a second screen / spectator for signals while still lining turnouts.
Only one Digicon should be the signal authority (CATS or CATS ABS).
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "cats/panels/sheets/HART_Master_ABS.xml"
DST = ROOT / "cats/panels/sheets/HART_Master_ABS_hold.xml"


def transform(root: ET.Element) -> None:
    n_maps = 0
    for am in root.iter("ASPECTMAP"):
        am.set("HOLD_ONLY", "true")
        n_maps += 1

    btns = sum(1 for _ in root.iter("BUTTON"))
    rc = sum(1 for _ in root.iter("ROUTECOMMAND"))
    print(f"ASPECTMAP HOLD_ONLY set on {n_maps} maps")
    print(f"kept ROUTECOMMAND={rc} BUTTON={btns} (turnout control on)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--dst", type=Path, default=DST)
    args = ap.parse_args()
    if not args.src.is_file():
        raise SystemExit(f"Missing source panel: {args.src}")

    tree = ET.parse(args.src)
    root = tree.getroot()
    transform(root)
    args.dst.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.dst, encoding="UTF-8", xml_declaration=True)
    print(f"Wrote {args.dst}")


if __name__ == "__main__":
    main()
