#!/usr/bin/env python3
"""Sync native HART SML into the deployment bundle without replacing CTC data.

``tables/new_tables.xml`` is the writable SML source.  The destination
``jmri/layouts/hart/output/tables.xml`` contains destination-only USS CTC data,
so whole-file copies are forbidden.  This script replaces only the
``signalmastlogics`` section and verifies that CTC/panel counts are unchanged.
"""

from __future__ import annotations

import argparse
import copy
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "tables/new_tables.xml"
DESTINATION = ROOT / "jmri/layouts/hart/output/tables.xml"


def sml_counts(root: ET.Element) -> tuple[int, int, int]:
    destinations = root.findall("./signalmastlogics/signalmastlogic/destinationMast")
    use_le = [
        (destination.findtext("useLayoutEditor") or "").strip().lower()
        for destination in destinations
    ]
    return len(destinations), use_le.count("yes"), use_le.count("no")


def protected_counts(root: ET.Element) -> tuple[int, int, int]:
    return (
        len(root.findall("ctcdata")),
        len(root.findall("paneleditor")),
        len(root.findall("LayoutEditor")),
    )


def replace_sml(source_root: ET.Element, destination_root: ET.Element) -> bool:
    source = source_root.find("signalmastlogics")
    destination = destination_root.find("signalmastlogics")
    if source is None or destination is None:
        raise ValueError("source and destination must both contain signalmastlogics")
    if sml_counts(source_root) != (36, 34, 2):
        raise ValueError(
            f"source SML contract is {sml_counts(source_root)}, expected (36, 34, 2)"
        )
    if ET.tostring(source) == ET.tostring(destination):
        return False
    children = list(destination_root)
    index = children.index(destination)
    destination_root.remove(destination)
    destination_root.insert(index, copy.deepcopy(source))
    return True


def write_atomic(tree: ET.ElementTree, destination: Path) -> None:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        tree.write(temporary, encoding="UTF-8", xml_declaration=True)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    source_tree = ET.parse(SOURCE)
    destination_tree = ET.parse(DESTINATION)
    before = protected_counts(destination_tree.getroot())
    changed = replace_sml(source_tree.getroot(), destination_tree.getroot())
    after = protected_counts(destination_tree.getroot())
    if before != after:
        raise SystemExit(f"refusing write: protected counts changed {before} -> {after}")
    if args.check:
        if changed:
            print("FAIL deployment SML differs from working source")
            return 1
        print("PASS deployment SML matches working source")
        return 0
    if changed:
        write_atomic(destination_tree, DESTINATION)
        print(f"Synced 36 native SML destinations -> {DESTINATION}")
    else:
        print("Deployment SML already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
