#!/usr/bin/env python3
"""Add Layout Editor TurnoutIcons for yard-ladder IT:HART:YL:* triggers.

Same internal turnouts Digicon buttons use — click THROWN fires IO:AUTO:020x routes.

Target is tables.xml (Layout Editor lives in preference:tables.xml), not hart_prod.

Place lamps on the same Y as the center-yard positionablelabels
"Track 1"…"Track 5" (those sit *above* each rail). Do not use BlockContentsIcon
"Yard Track N" — those sit in the gap *below* the rail and shift every row down.
"""

from __future__ import annotations

import argparse
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # repo root (…/hart)
# Working source (tables/tables.xml is read-only snapshot)
DEFAULT_PANEL = ROOT / "tables/new_tables.xml"
SYNC_COPIES = [
    ROOT / "jmri/layouts/hart/output/tables.xml",
]
MARKER = "hart-yard-ladder-le"

# Horizontal offset from "Track N" label (center-yard labels ≈ x=943)
LEFT_DX = -43
RIGHT_DX = 77

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


def track_text_labels(le: ET.Element) -> dict[str, tuple[int, int]]:
    """Map '1'..'5' -> (x, y) from center-yard positionablelabel "Track N".

    Prefer labels near x≈940 (south yard body). Edge labels at x≈100/1650 are ignored.
    """
    candidates: dict[str, list[tuple[int, int]]] = {n: [] for n in "12345"}
    for el in le:
        if el.tag != "positionablelabel":
            continue
        text = (el.get("text") or "").strip()
        if not text.startswith("Track "):
            continue
        n = text.replace("Track ", "").strip()
        if n not in candidates:
            continue
        x = int(float(el.get("x") or "0"))
        y = int(float(el.get("y") or "0"))
        candidates[n].append((x, y))

    out: dict[str, tuple[int, int]] = {}
    for n, pts in candidates.items():
        if not pts:
            continue
        # Center-yard labels (~943); fall back to closest to 943
        center = [p for p in pts if 800 <= p[0] <= 1100]
        pick = center[0] if center else sorted(pts, key=lambda p: abs(p[0] - 943))[0]
        out[n] = pick
    return out


def apply(panel: Path) -> None:
    tree = ET.parse(panel)
    root = tree.getroot()
    le = root.find("LayoutEditor")
    if le is None:
        raise SystemExit(f"No LayoutEditor in {panel}")

    strip_previous(le)
    labels = track_text_labels(le)
    if len(labels) < 5:
        raise SystemExit(
            f"Expected positionablelabel Track 1–5 in {panel}, found {sorted(labels)}"
        )

    # Insert near the Track N labels
    anchor = None
    for el in le:
        if el.tag == "positionablelabel" and (el.get("text") or "").startswith("Track "):
            anchor = el

    extras: list[ET.Element] = []
    for n in ("1", "2", "3", "4", "5"):
        lx, ly = labels[n]
        extras.append(
            _turnouticon(
                f"IT:HART:YL:L{n}", f"Yard ladder L S-{n}", lx + LEFT_DX, ly
            )
        )
        extras.append(
            _turnouticon(
                f"IT:HART:YL:R{n}", f"Yard ladder R S-{n}", lx + RIGHT_DX, ly
            )
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
    for n in ("1", "2", "3", "4", "5"):
        lx, ly = labels[n]
        print(
            f"  S-{n}: Track {n} label=({lx},{ly}) "
            f"L=({lx + LEFT_DX},{ly}) R=({lx + RIGHT_DX},{ly})"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    ap.add_argument(
        "--no-sync",
        action="store_true",
        help="Do not copy result to jmri/layouts/hart/output/tables.xml",
    )
    args = ap.parse_args()
    panel = args.panel.resolve()
    apply(panel)
    if not args.no_sync and panel == DEFAULT_PANEL.resolve():
        for dest in SYNC_COPIES:
            shutil.copy2(panel, dest)
            print(f"Synced → {dest}")


if __name__ == "__main__":
    main()
