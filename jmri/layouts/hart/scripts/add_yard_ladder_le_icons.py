#!/usr/bin/env python3
"""Add Layout Editor TurnoutIcons for yard-ladder IT:HART:YL:* triggers.

Same internal turnouts Digicon buttons use — click THROWN fires IO:AUTO:020x routes.
Icons sit beside the Yard Track 1–5 BlockContentsIcon labels on hart_prod.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # repo root (…/hart)
PANEL = ROOT / "jmri/layouts/hart/output/hart_prod.xml"
MARKER = "hart-yard-ladder-le"

# Digicon S-n row ≈ Yard Track n label Y on LE
TRACKS = [
    ("1", 323),
    ("2", 374),
    ("3", 421),
    ("4", 468),
    ("5", 510),
]
LABEL_X = 948
LEFT_X = LABEL_X - 48
RIGHT_X = LABEL_X + 72

# Match Digicon: CLOSED/idle = red, THROWN/active = white
CLOSED_URL = "program:resources/icons/USSpanels/Lamps/lamp-r.gif"
THROWN_URL = "program:resources/icons/USSpanels/Lamps/lamp-w.gif"
UNK_URL = "program:resources/icons/USSpanels/Lamps/lamp-dr.gif"


def _icon_el(tag: str, url: str) -> ET.Element:
    el = ET.Element(tag, {"url": url, "degrees": "0", "scale": "1.0"})
    ET.SubElement(el, "rotation").text = "0"
    return el


def _turnouticon(sysname: str, uname: str, x: int, y: int) -> ET.Element:
    ti = ET.Element(
        "turnouticon",
        {
            "turnout": sysname,
            "x": str(x),
            "y": str(y),
            "level": "10",
            "forcecontroloff": "false",
            "hidden": "no",
            "positionable": "true",
            "showtooltip": "true",
            "editable": "false",
            "tristate": "false",
            "momentary": "false",
            "directControl": "false",
            "class": "jmri.jmrit.display.configurexml.TurnoutIconXml",
        },
    )
    tip = ET.SubElement(ti, "tooltip")
    tip.text = f"{uname} [{MARKER}]"
    icons = ET.SubElement(ti, "icons")
    icons.append(_icon_el("closed", CLOSED_URL))
    icons.append(_icon_el("thrown", THROWN_URL))
    icons.append(_icon_el("unknown", UNK_URL))
    icons.append(_icon_el("inconsistent", UNK_URL))
    ET.SubElement(ti, "iconmaps")
    return ti


def strip_previous(le: ET.Element) -> None:
    for el in list(le):
        if el.tag != "turnouticon":
            continue
        to = el.get("turnout") or ""
        tip = (el.findtext("tooltip") or "")
        if to.startswith("IT:HART:YL:") or MARKER in tip:
            le.remove(el)


def apply(panel: Path) -> None:
    tree = ET.parse(panel)
    root = tree.getroot()
    le = root.find("LayoutEditor")
    if le is None:
        raise SystemExit(f"No LayoutEditor in {panel}")

    strip_previous(le)

    # Insert after Yard Track BlockContentsIcons
    anchor = None
    for el in le:
        if el.tag == "BlockContentsIcon" and (el.get("blockcontents") or "").startswith(
            "Yard Track"
        ):
            anchor = el

    extras: list[ET.Element] = []
    for n, y in TRACKS:
        extras.append(
            _turnouticon(f"IT:HART:YL:L{n}", f"Yard ladder L S-{n}", LEFT_X, y)
        )
        extras.append(
            _turnouticon(f"IT:HART:YL:R{n}", f"Yard ladder R S-{n}", RIGHT_X, y)
        )

    if anchor is None:
        for el in extras:
            le.append(el)
    else:
        idx = list(le).index(anchor) + 1
        for i, el in enumerate(extras):
            le.insert(idx + i, el)

    tree.write(panel, encoding="UTF-8", xml_declaration=True)
    print(f"Wrote {len(extras)} yard-ladder TurnoutIcons → {panel}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, default=PANEL)
    args = ap.parse_args()
    apply(args.panel.resolve())


if __name__ == "__main__":
    main()
