#!/usr/bin/env python3
"""Copy read-only live SoR CSVs/XLSX into consolidation/sor/ snapshots.

Does not modify live paths. Writes manifest of what was snapshotted.
"""
from __future__ import annotations

import csv
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CON = ROOT / "consolidation"
MANIFEST = CON / "sor/snapshot_manifest.csv"

SNAPSHOTS: list[tuple[str, Path, Path]] = [
    ("names/public_name_map.csv", ROOT / "jmri/layouts/hart/data/public_name_map.csv", CON / "sor/names/public_name_map.csv"),
    ("names/block_display_names.csv", ROOT / "jmri/layouts/hart/data/block_display_names.csv", CON / "sor/names/block_display_names.csv"),
    ("signals/signal_wiring.csv", ROOT / "cats/data/signal_wiring.csv", CON / "sor/signals/signal_wiring.csv"),
    ("signals/signal_head_plan.csv", ROOT / "cats/data/signal_head_plan.csv", CON / "sor/signals/signal_head_plan.csv"),
    ("signals/signal_mast_plan.csv", ROOT / "cats/data/signal_mast_plan.csv", CON / "sor/signals/signal_mast_plan.csv"),
    ("signals/le_signal_boundaries.csv", ROOT / "cats/data/le_signal_boundaries.csv", CON / "sor/signals/le_signal_boundaries.csv"),
    ("signals/occupancy_bindings.csv", ROOT / "cats/data/occupancy_bindings.csv", CON / "sor/signals/occupancy_bindings.csv"),
    ("cats/jmri_devices.csv", ROOT / "cats/data/jmri_devices.csv", CON / "sor/cats/jmri_devices.csv"),
    ("wiring/LCOS_Layout_Inventory_v85.xlsx", ROOT / "docs/wiring/LCOS_Layout_Inventory_v85.xlsx", CON / "sor/wiring/LCOS_Layout_Inventory_v85.xlsx"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for rel, src, dst in SNAPSHOTS:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not src.is_file():
            rows.append({"rel_path": rel, "live_source": str(src.relative_to(ROOT)), "status": "MISSING", "sha256": "", "bytes": ""})
            print(f"MISSING {src}")
            continue
        shutil.copy2(src, dst)
        digest = sha256(dst)
        size = dst.stat().st_size
        rows.append(
            {
                "rel_path": rel,
                "live_source": str(src.relative_to(ROOT)),
                "status": "OK",
                "sha256": digest,
                "bytes": str(size),
            }
        )
        print(f"OK {rel} ({size} bytes)")

    with MANIFEST.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["rel_path", "live_source", "status", "sha256", "bytes"])
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {MANIFEST.relative_to(ROOT)} ({ts})")
    missing = sum(1 for r in rows if r["status"] == "MISSING")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
