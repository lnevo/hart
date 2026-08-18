#!/usr/bin/env python3
"""Keep CATS ABS Digicon lamps from writing JMRI SignalMasts.

CATS looks up SECSIGNAL text as mast userName and then setAspect/setHeld.
Prefixing the name means CATS still paints PANELSIGNAL from Digicon ABS
search (the visual reference) while Layout Editor / SML owns the JMRI masts.

Idempotent. Does not touch HART_Master.xml / CTC hold (those bind on purpose).
"""
from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "cats/panels/HART_Master_ABS.xml"
PREFIX = "CATS "


def unbind(root: ET.Element) -> int:
    n = 0
    for sig in root.iter("SECSIGNAL"):
        raw = sig.text or ""
        name = raw.strip()
        if not name or name.startswith(PREFIX):
            continue
        indent = re.match(r"^\n( *)", raw)
        pad = indent.group(1) if indent else "          "
        sig.text = f"\n{pad}{PREFIX}{name}\n{pad}"
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("panel", nargs="?", type=Path, default=DEFAULT)
    args = ap.parse_args()
    tree = ET.parse(args.panel)
    n = unbind(tree.getroot())
    tree.write(args.panel, encoding="UTF-8", xml_declaration=True)
    print(f"unbound {n} SECSIGNAL names in {args.panel}")


if __name__ == "__main__":
    main()
