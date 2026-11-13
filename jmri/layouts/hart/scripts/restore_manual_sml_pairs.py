#!/usr/bin/env python3
"""Put back the manual Princess Signal Mast Logic pairs after a Stage 1 run.

Stage 1 deletes and re-discovers SML, and Discover misses two Princess pairs
(wiki/DISPATCHER_LAYOUT_HOOPS.md). This copies each missing pair's
<destinationMast> from a reference tables.xml (the copy taken before Stage 1)
into the panel. Pairs already present are left alone.

    restore_manual_sml_pairs.py --reference before.xml [--panel tables.xml]
    restore_manual_sml_pairs.py --check [--panel tables.xml]

Run with PanelPro closed. Writes only when something changed.
"""

from __future__ import annotations

import argparse
import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PANEL = ROOT / "jmri/layouts/hart/output/tables.xml"

# source mast, destination mast
MANUAL_PAIRS = (
    ("Mast 36RA", "Mast 40LA"),
    ("Mast 36RB", "Mast 38LA"),
)


def _logic(root: ET.Element, source: str) -> ET.Element | None:
    for sml in root.iter("signalmastlogic"):
        if (sml.findtext("sourceSignalMast") or "").strip() == source:
            return sml
    return None


def _destination(sml: ET.Element | None, dest: str) -> ET.Element | None:
    if sml is None:
        return None
    for element in sml.findall("destinationMast"):
        if (element.findtext("destinationSignalMast") or "").strip() == dest:
            return element
    return None


def missing_pairs(root: ET.Element) -> list[tuple[str, str]]:
    return [
        (source, dest)
        for source, dest in MANUAL_PAIRS
        if _destination(_logic(root, source), dest) is None
    ]


def restore(root: ET.Element, reference: ET.Element) -> list[tuple[str, str]]:
    """Copy missing pairs from reference; return the pairs added."""
    added = []
    for source, dest in missing_pairs(root):
        wanted = _destination(_logic(reference, source), dest)
        if wanted is None:
            raise ValueError(f"reference has no {source} -> {dest} pair to copy")
        sml = _logic(root, source)
        if sml is None:
            raise ValueError(
                f"{source} has no Signal Mast Logic after Stage 1; check Discover"
            )
        sml.append(copy.deepcopy(wanted))
        added.append((source, dest))
    return added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    ap.add_argument("--reference", type=Path, help="tables.xml from before Stage 1")
    ap.add_argument("--check", action="store_true", help="Report missing pairs; write nothing")
    args = ap.parse_args(argv)

    tree = ET.parse(args.panel)
    root = tree.getroot()
    if args.check:
        missing = missing_pairs(root)
        for source, dest in missing:
            print(f"missing manual pair {source} -> {dest}")
        if not missing:
            print("Manual Princess SML pairs present")
        return 1 if missing else 0
    if args.reference is None:
        ap.error("--reference is required unless --check")
    try:
        added = restore(root, ET.parse(args.reference).getroot())
    except ValueError as exc:
        print(f"{args.panel}: not changed: {exc}", file=sys.stderr)
        return 1
    if added:
        tree.write(args.panel, encoding="UTF-8", xml_declaration=True)
    for source, dest in added:
        print(f"restored {source} -> {dest}")
    print(f"{len(added)} manual pair(s) restored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
