#!/usr/bin/env python3
"""Static checks for CATS Designer panel XML (catch HART_Brick schema mistakes)."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

FORBIDDEN = {
    "ROUTEFEEDBACK",  # not a CATS 3 element; use SELECTEDREPORT
}


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

    if root.find("TRACKPLAN") is None:
        errs.append("missing TRACKPLAN")
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
