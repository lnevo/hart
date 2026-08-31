#!/usr/bin/env python3
"""Build consolidation wiring crosswalk: signal_wiring packed → live IH beans.

Reads live signal_wiring.csv + deploy tables.xml + public_name_map.csv (read-only).
Writes consolidation/sor/wiring/packed_id_crosswalk.csv only.
"""
from __future__ import annotations

import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consolidation" / "scripts" / "lib"))

from consolidation_paths import hart_runtime_root, path_lcos_bridge, path_public_name_map, path_signal_wiring, path_tables_xml

HART_ROOT = hart_runtime_root()
WIRING = path_signal_wiring()
TABLES = path_tables_xml()
MAP = path_public_name_map()
OUT = ROOT / "consolidation/sor/wiring/packed_id_crosswalk.csv"

# Known stale packed IDs (node*100+uid or pre-rename helix) → live IH from deploy tables.
# Keyed by (mast_user_name, head_role_hint) where hint is T|B|single for multi-head masts.
MANUAL: dict[tuple[str, str], str] = {
    ("Mast 24RA", "T"): "1232",
    ("Mast 24RA", "B"): "1233",
    ("Mast 24L", "T"): "1234",
    ("Mast 24L", "B"): "1235",
    ("Mast 24RB", "single"): "1236",
    ("Mast 40LB", "T"): "132",
    ("Mast 40LB", "B"): "133",
    ("Mast 2036", "single"): "134",
    ("Mast 2035", "single"): "141",
    ("Mast 40LA", "single"): "142",
    ("Mast 34L", "T"): "1237",
    ("Mast 34L", "B"): "1238",
    ("Mast 32R", "single"): "1239",
    ("Mast 34R", "T"): "1240",
    ("Mast 34R", "B"): "1241",
}


def head_role_hint(user_name: str) -> str:
    u = user_name.upper()
    if " T " in f" {u} " or u.endswith(" T G"):
        return "T"
    if " B " in f" {u} " or u.endswith(" B G"):
        return "B"
    return "single"


def ih_from_tables(tree: ET.ElementTree) -> dict[str, str]:
    out: dict[str, str] = {}
    for head in tree.getroot().iter("signalhead"):
        sn = (head.findtext("systemName") or head.get("systemName") or "").strip()
        un = (head.findtext("userName") or "").strip()
        m = re.match(r"IH(\d+)", sn)
        if m and un:
            out[un] = m.group(1)
    return out


def packed_ids_from_wiring() -> dict[str, tuple[str, str, str]]:
    """packed -> (mast, user_name, wiring_ih column)."""
    by_packed: dict[str, tuple[str, str, str]] = {}
    with WIRING.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            packed = (row.get("packed") or "").strip()
            if not packed.isdigit():
                continue
            mast = (row.get("mast_user_name") or "").strip()
            user = (row.get("user_name") or "").strip()
            ih_col = (row.get("system_name") or "").strip()
            by_packed.setdefault(packed, (mast, user, ih_col))
    return by_packed


def main() -> int:
    if not WIRING.is_file() or not TABLES.is_file():
        print("missing wiring or tables", file=sys.stderr)
        return 1

    tree = ET.parse(TABLES)
    bean_ih = {
        int(v)
        for v in ih_from_tables(tree).values()
    }
    wiring = packed_ids_from_wiring()

    rows: list[dict[str, str]] = []
    for packed in sorted(wiring, key=int):
        mast, user, ih_col = wiring[packed]
        hint = head_role_hint(user)
        live = MANUAL.get((mast, hint), "")
        wiring_int = int(packed)
        status = "ok"
        if wiring_int in bean_ih and live and str(wiring_int) != live:
            status = "collision"
        elif wiring_int not in bean_ih and not live:
            status = "unmapped"
        elif wiring_int in bean_ih:
            live = str(wiring_int)
            status = "direct"
        elif live:
            status = "remap"

        rows.append(
            {
                "wiring_packed": packed,
                "wiring_system_name": ih_col,
                "wiring_mast": mast,
                "wiring_head_sample": user,
                "live_ih": live,
                "status": status,
                "notes": "",
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "wiring_packed",
        "wiring_system_name",
        "wiring_mast",
        "wiring_head_sample",
        "live_ih",
        "status",
        "notes",
    ]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    remap = [r for r in rows if r["status"] == "remap"]
    collision = [r for r in rows if r["status"] == "collision"]
    print(f"wrote {len(rows)} rows -> {OUT.relative_to(ROOT)}")
    print(f"remap: {len(remap)}  collision: {len(collision)}  direct: {sum(1 for r in rows if r['status']=='direct')}")
    if collision:
        print("WARN: packed ID matches a bean IH but maps to a different live head — see audits/wiring-crosswalk-gap.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
