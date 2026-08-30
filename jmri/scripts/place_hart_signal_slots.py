#!/usr/bin/env python3
"""Place dark signal-slot labels on hart Layout Editor from signal_mast_plan.csv."""

from __future__ import annotations

import csv
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

HART = Path(__file__).resolve().parents[1] / "layouts" / "hart"
PANEL = HART / "output" / "hart_prod.xml"
PLAN = HART.parent.parent.parent / "cats" / "data" / "signal_mast_plan.csv"
PREFIX = "SIG "


def main() -> int:
    tree = ET.parse(PANEL)
    root = tree.getroot()
    le = next(root.iter("LayoutEditor"), None)
    if le is None:
        raise SystemExit("no LayoutEditor")

    # Remove prior SIG slots
    for el in list(le.findall("positionablelabel")):
        if (el.get("text") or "").startswith(PREFIX):
            le.remove(el)

    with PLAN.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Insert after last positionablelabel if possible
    anchor = None
    for el in le:
        if el.tag == "positionablelabel":
            anchor = el

    n = 0
    for row in rows:
        text = f"{PREFIX}{row['cp']} {row['direction'][0].upper()}"
        lab = ET.Element(
            "positionablelabel",
            {
                "x": str(int(float(row["panel_x"]))),
                "y": str(int(float(row["panel_y"])) - 24),
                "level": "9",
                "forcecontroloff": "false",
                "hidden": "no",
                "positionable": "true",
                "showtooltip": "true",
                "editable": "false",
                "text": text,
                "size": "10",
                "style": "0",
                "red": "80",
                "green": "80",
                "blue": "80",
                "hasBackground": "no",
                "justification": "centre",
                "class": "jmri.jmrit.display.configurexml.PositionableLabelXml",
            },
        )
        if anchor is not None:
            idx = list(le).index(anchor) + 1
            le.insert(idx, lab)
            anchor = lab
        else:
            le.append(lab)
        n += 1

    out = HART / "output" / "hart_blocked.xml"
    tree.write(out, encoding="UTF-8", xml_declaration=True)
    shutil.copy2(out, HART / "output" / "hart_prod.xml")
    shutil.copy2(out, HART / "authoritative" / "hart.xml")
    print(f"Placed {n} signal-slot labels → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
