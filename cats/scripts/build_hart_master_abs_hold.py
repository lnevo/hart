#!/usr/bin/env python3
"""Build HART_Master_ABS_hold.xml — ABS Digicon, signals listen-only (SML).

Derived from HART_Master_ABS.xml:

1. HOLD_ONLY=true on every ASPECTMAP — CATS does not setAspect; SML owns
   Clear/Approach/Stop. CATS Hold/Unhold follows its ABS vital logic.
2. Strip the ``CATS `` SECSIGNAL prefix so lamps bind to real JMRI masts
   and paint the aspect SML is showing (the live ABS file stays unbound).
3. Keep ROUTECOMMAND / yard-ladder BUTTONs / DISCIPLINE=ABS.

Only one Digicon should be open (CATS CTC or CATS ABS).
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "cats/panels/HART_Master_ABS.xml"
DST = ROOT / "cats/panels/HART_Master_ABS_hold.xml"


PREFIX = "CATS "


def transform(root: ET.Element) -> None:
    n_maps = 0
    for am in root.iter("ASPECTMAP"):
        am.set("HOLD_ONLY", "true")
        n_maps += 1

    n_bind = 0
    for sig in root.iter("SECSIGNAL"):
        raw = (sig.text or "")
        name = raw.strip()
        if name.startswith(PREFIX):
            sig.text = raw.replace(PREFIX, "", 1)
            n_bind += 1

    btns = sum(1 for _ in root.iter("BUTTON"))
    rc = sum(1 for _ in root.iter("ROUTECOMMAND"))
    print(f"ASPECTMAP HOLD_ONLY set on {n_maps} maps")
    print(f"re-bound {n_bind} SECSIGNAL names (stripped {PREFIX!r})")
    print(f"kept ROUTECOMMAND={rc} BUTTON={btns} (turnout control on)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--dst", type=Path, default=DST)
    ap.add_argument(
        "--no-polish",
        action="store_true",
        help="Keep Designer title row and window size (Master 4 1920×540).",
    )
    args = ap.parse_args()
    if not args.src.is_file():
        raise SystemExit(f"Missing source panel: {args.src}")

    tree = ET.parse(args.src)
    root = tree.getroot()
    transform(root)

    import importlib.util

    bridge_path = Path(__file__).with_name("aar_aspect_bridge.py")
    spec = importlib.util.spec_from_file_location("aar_aspect_bridge", bridge_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    mod.apply_aar_bridge(root, hold_only=True)

    args.dst.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.dst, encoding="UTF-8", xml_declaration=True)
    print(f"Wrote {args.dst}")

    # Re-stamp publication header (ABS-RO mode) after HOLD_ONLY transform.
    if args.dst.resolve() == DST.resolve() and not args.no_polish:
        import importlib.util

        polish_path = Path(__file__).with_name("polish_hart_master_header.py")
        spec = importlib.util.spec_from_file_location("polish_hart_master_header", polish_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        meta = mod.PANELS["abs_hold"]
        mod.polish(args.dst, meta["pub_id"], meta["mode"], rev="A", effective=None)


if __name__ == "__main__":
    main()
