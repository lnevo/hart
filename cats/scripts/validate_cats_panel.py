#!/usr/bin/env python3
"""Static checks for CATS Designer panel XML (catch HART_Brick schema mistakes)."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

FORBIDDEN = {
    "ROUTEFEEDBACK",  # not a CATS 3 element; use SELECTEDREPORT
}

# Gate 1 SoR — must appear on Designer primary (cats/panels/HART.xml).
GATE1_BLOCKS = {
    "Main West",
    "OS 100 (Brick)",
    "OS 101 (Brick)",
    "Main West Brick–Plane",
    "OS 102 (Plane)",
    "East Main Ext",
}

# Gate 2 SoR — required on LE WIP (cats/panels/HART_le.xml) once built.
GATE2_BLOCKS = {
    "OS 116",
    "OS 117 (Barn)",
    "OS 117b (Barn)",
    "OS 118",
    "OS 119",
    "Main East",
}


def named_blocks(root: ET.Element) -> set[str]:
    return {b.get("NAME") for b in root.iter("BLOCK") if b.get("NAME")}


def block_track_kinds(root: ET.Element) -> dict[str, set[str]]:
    """Map named block → TRACK kinds on sections that carry that name."""
    out: dict[str, set[str]] = {}
    for s in root.iter("SECTION"):
        tracks = [(t.text or "").strip() for t in s.findall("./TRACKGROUP/TRACK")]
        names: set[str] = set()
        for e in s.findall("SEC_EDGE"):
            b = e.find("BLOCK")
            if b is not None and b.get("NAME"):
                names.add(b.get("NAME"))
        for n in names:
            out.setdefault(n, set()).update(tracks)
    return out


def check(path: Path) -> list[str]:
    errs: list[str] = []
    root = ET.parse(path).getroot()
    if root.tag != "DOCUMENT":
        errs.append(f"root is {root.tag}, expected DOCUMENT")

    for tag in FORBIDDEN:
        n = len(list(root.iter(tag)))
        if n:
            errs.append(f"forbidden element <{tag}> ×{n}")

    for sp in root.iter("SWITCHPOINTS"):
        for ri in sp.findall("ROUTEINFO"):
            # children allowed: SELECTEDREPORT, ROUTECOMMAND (and empty)
            for child in list(ri):
                if child.tag not in {"SELECTEDREPORT", "ROUTECOMMAND"}:
                    errs.append(
                        f"ROUTEINFO child <{child.tag}> not in "
                        f"{{SELECTEDREPORT, ROUTECOMMAND}}"
                    )
            # ROUTECOMMAND must not be direct child of SWITCHPOINTS
        for child in list(sp):
            if child.tag not in {"ROUTEINFO", "POINTSMSG"}:
                errs.append(f"SWITCHPOINTS child <{child.tag}> unexpected")

    # Hand-sliced extracts crashed when PtsEdge had no Block anywhere on the
    # section. Armstrong often puts SWITCHPOINTS on LEFT with ROUTEID RIGHT and
    # the BLOCK on another edge — require a BLOCK on *some* edge, not only LEFT.
    for s in root.iter("SECTION"):
        edges = list(s.findall("SEC_EDGE"))
        has_sw = any(e.find("SWITCHPOINTS") is not None for e in edges)
        if not has_sw:
            continue
        if not any(e.find("BLOCK") is not None for e in edges):
            # Ladder throat cells in Armstrong also omit BLOCK on the SW section
            # entirely — allow empty if a ROUTEINFO exists (Designer/Armstrong).
            pass

    if root.find("TRACKPLAN") is None:
        errs.append("missing TRACKPLAN")

    name = path.name
    blocks = named_blocks(root)

    if name in {"HART.xml", "HART_magnet.xml", "HART_designer_wired.xml"}:
        missing = sorted(GATE1_BLOCKS - blocks)
        if missing:
            errs.append(f"Gate1 missing named blocks: {', '.join(missing)}")
        # Designer Gate 1 places 100-102 on the Brick→Plane diagonal (slash cells).
        # LE WIP must keep 100-102 on a HORIZONTAL spine cell (continuing route).
        kinds = block_track_kinds(root).get("Main West Brick–Plane", set())
        if kinds and "HORIZONTAL" not in kinds and name.startswith("HART_le"):
            errs.append(
                "Main West Brick–Plane has no HORIZONTAL cell "
                f"(tracks={sorted(kinds)}) — continuing route must be HORIZONTAL"
            )

    if name in {"HART_le.xml", "HART_le_magnet.xml"}:
        missing1 = sorted(GATE1_BLOCKS - blocks)
        if missing1:
            errs.append(f"LE Gate1 missing named blocks: {', '.join(missing1)}")
        missing2 = sorted(GATE2_BLOCKS - blocks)
        if missing2:
            errs.append(f"LE Gate2 missing named blocks: {', '.join(missing2)}")
        kinds = block_track_kinds(root).get("Main West Brick–Plane", set())
        if "HORIZONTAL" not in kinds:
            errs.append(
                "LE Main West Brick–Plane must sit on HORIZONTAL "
                f"(tracks={sorted(kinds) or 'none'})"
            )
        # Occupancy wiring expected on MQTT LE panel
        if name == "HART_le.xml":
            wired = {
                b.get("NAME")
                for b in root.iter("BLOCK")
                if b.get("NAME") and b.find("OCCUPIEDSPEC") is not None
            }
            unwired = sorted(GATE1_BLOCKS - wired)
            if unwired:
                errs.append(f"LE MQTT missing OCCUPIEDSPEC: {', '.join(unwired)}")

    if name == "HART.xml":
        wired = {
            b.get("NAME")
            for b in root.iter("BLOCK")
            if b.get("NAME") and b.find("OCCUPIEDSPEC") is not None
        }
        unwired = sorted(GATE1_BLOCKS - wired)
        if unwired:
            errs.append(f"Gate1 MQTT missing OCCUPIEDSPEC: {', '.join(unwired)}")

    return errs


def main() -> int:
    paths = [Path(a) for a in sys.argv[1:]]
    if not paths:
        root = Path(__file__).resolve().parents[1] / "panels"
        paths = sorted(root.glob("HART*.xml"))
    failed = 0
    for p in paths:
        errs = check(p)
        if errs:
            failed += 1
            print(f"FAIL {p}")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"PASS {p}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
