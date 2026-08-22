#!/usr/bin/env python3
"""Add Layout Editor TurnoutIcons for yard-ladder IT:HART:YL:* triggers.

Same internal turnouts Digicon buttons use — click THROWN fires IO:AUTO:020x routes.

Target is tables.xml (Layout Editor lives in preference:tables.xml), not hart_prod.

Place triangles on the same Y as the S-1–5 Dispatcher stations
(those sit *above* each rail, where the old "Track N" labels were). Do not
use BlockContentsIcon "Yard Track N" — those sit in the gap *below* the rail
and shift every row down.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # repo root (…/hart)
# Working source (tables/tables.xml is read-only snapshot)
DEFAULT_PANEL = ROOT / "tables/new_tables.xml"
SYNC_COPIES = [
    ROOT / "jmri/layouts/hart/output/tables.xml",
]
MARKER = "hart-yard-ladder-le"

# Horizontal offset from the S-1–5 station cluster (x=943).
# Left X comes from the live L1 placement in Pi tables2.xml (x=921).
ICON_SIZE = 16
RIGHT_DX = 77
LEFT_DX = -22
SOUTH_YARD_STATION_ANCHORS = {
    "1": (943, 293),
    "2": (943, 344),
    "3": (943, 391),
    "4": (943, 438),
    "5": (943, 480),
}

# One equilateral pair, pointing east. West buttons use the same files at 180°.
# Idle grey, lined warm white. Install copies them to preference:hart/icons/.
ICON_SCALE = "1.0"
PREF = "preference:hart/icons"
IDLE_URL = f"{PREF}/triangle_idle.png"
ACTIVE_URL = f"{PREF}/triangle_active.png"
FACE_URLS = {
    "closed": IDLE_URL,
    "thrown": ACTIVE_URL,
    "unknown": IDLE_URL,
    "inconsistent": IDLE_URL,
}
# JMRI NamedIcon degrees. Keep <rotation> at 0 so we do not double-spin.
SIDE_DEGREES = {"L": "180", "R": "0"}
ICON_FILES = (
    "triangle_idle.png",
    "triangle_active.png",
)
STALE_ICON_FILES = (
    "triangle_left_idle.png",
    "triangle_left_active.png",
    "triangle_right_idle.png",
    "triangle_right_active.png",
)


def install_preference_icons() -> list[Path]:
    """Copy triangle PNGs into JMRI user-files / profile hart/icons dirs."""
    src = ROOT / "cats/resources/buttons"
    missing = [n for n in ICON_FILES if not (src / n).is_file()]
    if missing:
        raise SystemExit(f"Missing yard-ladder triangles: {missing}")

    dests: list[Path] = []
    candidates = [
        Path.home() / "JMRI_UserFiles",
        Path.home() / "Library/Preferences/JMRI",
        Path.home() / ".jmri",
    ]
    for base in candidates:
        if not base.is_dir():
            continue
        if base.name == "JMRI_UserFiles":
            dests.append(base / "hart/icons")
            continue
        dests.extend(p / "hart/icons" for p in base.glob("*.jmri") if p.is_dir())

    written: list[Path] = []
    for dest in dests:
        dest.mkdir(parents=True, exist_ok=True)
        for name in ICON_FILES:
            target = dest / name
            target.write_bytes((src / name).read_bytes())
            written.append(target)
        for name in STALE_ICON_FILES:
            stale = dest / name
            if stale.exists():
                stale.unlink()
    return written


def _icon_el(tag: str, url: str, degrees: str) -> ET.Element:
    el = ET.Element(tag, {"url": url, "degrees": degrees, "scale": ICON_SCALE})
    ET.SubElement(el, "rotation").text = "0"
    return el


def _side_for(sysname: str) -> str:
    return "L" if ":YL:L" in sysname else "R"


def _xy_for(sysname: str) -> tuple[int, int]:
    n = sysname.rsplit(":", 1)[-1][-1]
    ax, ay = SOUTH_YARD_STATION_ANCHORS[n]
    dx = LEFT_DX if _side_for(sysname) == "L" else RIGHT_DX
    return ax + dx, ay


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
    degrees = SIDE_DEGREES[_side_for(sysname)]
    for tag, url in FACE_URLS.items():
        icons.append(_icon_el(tag, url, degrees))
    ET.SubElement(ti, "iconmaps")
    return ti


def restyle_existing(le: ET.Element) -> int:
    """Swap artwork, rotation, and x so left/right stay symmetric."""
    changed = 0
    for el in le.findall("turnouticon"):
        to = el.get("turnout") or ""
        if not to.startswith("IT:HART:YL:"):
            continue
        x, y = _xy_for(to)
        if el.get("x") != str(x) or el.get("y") != str(y):
            el.set("x", str(x))
            el.set("y", str(y))
            changed += 1
        degrees = SIDE_DEGREES[_side_for(to)]
        icons = el.find("icons")
        if icons is None:
            continue
        for child in icons:
            url = FACE_URLS.get(child.tag)
            if url is None:
                continue
            if (
                child.get("url") != url
                or child.get("scale") != ICON_SCALE
                or child.get("degrees") != degrees
            ):
                child.set("url", url)
                child.set("scale", ICON_SCALE)
                child.set("degrees", degrees)
                changed += 1
    return changed


def strip_previous(le: ET.Element) -> None:
    for el in list(le):
        if el.tag != "turnouticon":
            continue
        to = el.get("turnout") or ""
        tip = (el.findtext("tooltip") or "")
        if to.startswith("IT:HART:YL:") or MARKER in tip:
            le.remove(el)


def track_text_labels(le: ET.Element) -> dict[str, tuple[int, int]]:
    """Map '1'..'5' -> (x, y) for the South Yard body.

    Prefer live "Track N" labels near x≈940 if they are still on the panel;
    otherwise use the Dispatcher station anchors that replaced them.
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
        center = [p for p in pts if 800 <= p[0] <= 1100]
        if center:
            out[n] = center[0]
        elif pts:
            out[n] = sorted(pts, key=lambda p: abs(p[0] - 943))[0]
        else:
            out[n] = SOUTH_YARD_STATION_ANCHORS[n]
    return out


def find_layout_editor(root: ET.Element) -> ET.Element | None:
    named = [
        le
        for le in root.findall("LayoutEditor")
        if le.get("name") in {"HART Railroad", "My Layout", "HART"}
    ]
    if named:
        return named[0]
    return root.find("LayoutEditor")


def apply(panel: Path) -> None:
    tree = ET.parse(panel)
    root = tree.getroot()
    le = find_layout_editor(root)
    if le is None:
        raise SystemExit(f"No LayoutEditor in {panel}")

    existing = [
        el
        for el in le.findall("turnouticon")
        if (el.get("turnout") or "").startswith("IT:HART:YL:")
    ]
    if existing:
        changed = restyle_existing(le)
        tree.write(panel, encoding="UTF-8", xml_declaration=True)
        print(f"Restyled {changed} yard-ladder icon faces → {panel}")
        return

    strip_previous(le)
    labels = track_text_labels(le)
    if len(labels) < 5:
        raise SystemExit(
            f"Expected S-1–5 anchors in {panel}, found {sorted(labels)}"
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
        help="Do not also restyle jmri/layouts/hart/output/tables.xml",
    )
    args = ap.parse_args()
    installed = install_preference_icons()
    if installed:
        roots = sorted({p.parent for p in installed})
        print(f"Installed {len(ICON_FILES)} triangles → {len(roots)} preference dirs")
    panel = args.panel.resolve()
    apply(panel)
    if not args.no_sync and panel == DEFAULT_PANEL.resolve():
        for dest in SYNC_COPIES:
            apply(dest)


if __name__ == "__main__":
    main()
