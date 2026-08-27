#!/usr/bin/env python3
"""Apply public_name_map.csv string replaces to a list of text files.

Skips the map itself, baselines, ADR-005, STATUS history, and contract tests
that still mention current names. Default is dry-run; pass --apply to write.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_public_names import apply_renames_to_text, load_rename_map

SKIP_SUFFIXES = {".png", ".gif", ".jpg", ".jpeg", ".pyc"}
SKIP_PARTS = {
    "data/baselines",
    "data/public_name_map.csv",
    "wiki/STATUS.md",
    "wiki/decisions/ADR-002-naming-contract.md",
    "wiki/decisions/ADR-005-public-equipment-names.md",
    "scripts/apply_public_names.py",
    "scripts/apply_public_names_tree.py",
    "scripts/refresh_bean_comments.py",
    "scripts/sync_public_name_map.py",
    "scripts/reconcile_dispatcher_stations.py",
    "scripts/audit_panel_contracts.py",
    "scripts/panelpro_smoke_test.py",
    "scripts/tests/",
    "ctc/history",
    "mqtt_turnout_retain_snapshot.json",
    "cats/panels/checkpoints",
    "cats/panels/sheets/checkpoints",
    "tables/tables.xml",
    "tables/checkpoints",
    "linear4/",
    "linear5/",
    "linear6/",
}


def should_skip(path: Path) -> bool:
    rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    return any(part in rel for part in SKIP_PARTS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    renames = load_rename_map(ROOT / "jmri/layouts/hart/data/public_name_map.csv")
    merged: Counter[tuple[str, str]] = Counter()
    files = 0
    for raw in args.paths:
        path = raw if raw.is_absolute() else ROOT / raw
        if path.is_dir():
            candidates = [p for p in path.rglob("*") if p.is_file()]
        else:
            candidates = [path]
        for target in candidates:
            if should_skip(target) or not target.is_file():
                continue
            try:
                text = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            updated, counts = apply_renames_to_text(text, renames)
            if not counts:
                continue
            files += 1
            merged.update(counts)
            if args.apply:
                target.write_text(updated, encoding="utf-8")
            print(f"{target.relative_to(ROOT)}: {sum(counts.values())}")
    print(f"{'APPLIED' if args.apply else 'DRY-RUN'} files={files} replacements={sum(merged.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
