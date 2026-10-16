#!/usr/bin/env python3
"""Build HART_Master_CTC_hold.xml — CTC Digicon, signals HOLD_ONLY (JMRI SML).

Derived from HART_Master.xml:

1. HOLD_ONLY=true — CATS only Held/Unheld; SML owns Clear/Approach/Stop.
2. Keep DISCIPLINE=CTC and ROUTECOMMAND — left-click still codes routes / throws.
3. AAR/C&O-1980 aspect name bridge so Digicon paints from JMRI appearances.

Legacy aspect-driving CTC remains HART_Master.xml (rollback).
"""

from __future__ import annotations

import argparse
import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "cats/panels/HART_Master.xml"
DST = ROOT / "cats/panels/HART_Master_CTC_hold.xml"


def _load_bridge():
    path = Path(__file__).with_name("aar_aspect_bridge.py")
    spec = importlib.util.spec_from_file_location("aar_aspect_bridge", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _load_polish():
    path = Path(__file__).with_name("polish_hart_master_header.py")
    spec = importlib.util.spec_from_file_location("polish_hart_master_header", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--dst", type=Path, default=DST)
    args = ap.parse_args()
    if not args.src.is_file():
        raise SystemExit(f"Missing source panel: {args.src}")

    tree = ET.parse(args.src)
    root = tree.getroot()
    bridge = _load_bridge()
    bridge.apply_aar_bridge(root, hold_only=True)

    rc = sum(1 for _ in root.iter("ROUTECOMMAND"))
    disc = {blk.get("DISCIPLINE") for blk in root.iter("BLOCK") if blk.get("DISCIPLINE")}
    print(f"kept ROUTECOMMAND={rc} DISCIPLINE={sorted(disc)}")

    args.dst.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.dst, encoding="UTF-8", xml_declaration=True)
    print(f"Wrote {args.dst}")

    if args.dst.resolve() == DST.resolve():
        polish = _load_polish()
        meta = polish.PANELS["ctc_hold"]
        polish.polish(args.dst, meta["pub_id"], meta["mode"], rev="A", effective=None)


if __name__ == "__main__":
    main()
