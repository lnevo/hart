#!/usr/bin/env python3
"""Deep read-only inventory of Desktop/HART class-C operational subtrees.

Writes:
  sor/desktop/hart_subtree_inventory.csv
  audits/desktop-subtree-inventory.md

Does not modify Desktop files.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = Path.home() / "Desktop/HART"
OUT_CSV = ROOT / "consolidation/sor/desktop/hart_subtree_inventory.csv"
OUT_MD = ROOT / "consolidation/audits/desktop-subtree-inventory.md"

SUBTREES: dict[str, str] = {
    "Car Cards": "hart-ops (pipelines 12–15)",
    "Industries": "hart-ops (pipeline 16)",
    "Wiring Documentation": "docs/wiring bench mirror (D4)",
    "DJ Trains": "review — model collection, not layout SoR",
}

# Car Cards: inventory top two levels only (avoid 30k row walk in audit md)
CARDS_TOP_LEVELS = 2


def dir_stats(path: Path, max_depth: int | None = None, _depth: int = 0) -> tuple[int, int]:
    files, total = 0, 0
    if not path.is_dir():
        return 0, 0
    for entry in path.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.is_file():
            try:
                total += entry.stat().st_size
                files += 1
            except OSError:
                pass
        elif entry.is_dir() and (max_depth is None or _depth < max_depth):
            f, s = dir_stats(entry, max_depth, _depth + 1)
            files += f
            total += s
    return files, total


def walk_subtree(base: Path, rel_prefix: str = "") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not base.is_dir():
        return rows

    max_depth = CARDS_TOP_LEVELS if base.name == "Car Cards" else 3
    for root, dirs, files in os.walk(base):
        depth = Path(root).relative_to(base).parts
        if len(depth) > max_depth:
            dirs.clear()
            continue
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        rel = str(Path(rel_prefix) / Path(root).relative_to(base)) if root != str(base) else rel_prefix or "."
        if rel == ".":
            fc, sz = dir_stats(base, max_depth)
            rows.append(
                {
                    "subtree": base.name,
                    "path": ".",
                    "kind": "dir",
                    "depth": "0",
                    "file_count": str(fc),
                    "size_bytes": str(sz),
                    "consolidation_target": SUBTREES.get(base.name, "review"),
                    "notes": "subtree root",
                }
            )
            continue
        p = Path(root)
        if not files and not dirs:
            continue
        fc = len([f for f in files if not f.startswith(".")])
        sz = sum((p / f).stat().st_size for f in files if not f.startswith(".") and (p / f).is_file())
        rows.append(
            {
                "subtree": base.name,
                "path": rel,
                "kind": "dir",
                "depth": str(len(depth)),
                "file_count": str(fc),
                "size_bytes": str(sz),
                "consolidation_target": SUBTREES.get(base.name, "review"),
                "notes": "",
            }
        )
    return rows


def main() -> int:
    if not DESKTOP.is_dir():
        print(f"MISSING {DESKTOP}")
        return 2

    all_rows: list[dict[str, str]] = []
    for name, target in SUBTREES.items():
        base = DESKTOP / name
        if not base.is_dir():
            all_rows.append(
                {
                    "subtree": name,
                    "path": ".",
                    "kind": "missing",
                    "depth": "",
                    "file_count": "0",
                    "size_bytes": "0",
                    "consolidation_target": target,
                    "notes": "subtree not found on Desktop",
                }
            )
            continue
        all_rows.extend(walk_subtree(base))

    fields = ["subtree", "path", "kind", "depth", "file_count", "size_bytes", "consolidation_target", "notes"]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(all_rows)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# Audit — Desktop/HART class-C subtree inventory",
        "",
        f"**Date:** {ts}",
        f"**CSV:** [`sor/desktop/hart_subtree_inventory.csv`](../sor/desktop/hart_subtree_inventory.csv)",
        "",
        "Read-only scan. Standalone consolidation copies live in `consolidation/external/hart-ops` (not Desktop).",
        "",
        "## Subtrees",
        "",
        "| Subtree | Consolidation target |",
        "|---------|---------------------|",
    ]
    for name, target in SUBTREES.items():
        lines.append(f"| `{name}/` | {target} |")

    lines.extend(["", "## Summary by subtree", ""])
    by_sub: dict[str, list[dict]] = {}
    for r in all_rows:
        by_sub.setdefault(r["subtree"], []).append(r)
    for name in SUBTREES:
        roots = [r for r in by_sub.get(name, []) if r["path"] == "."]
        if roots:
            r = roots[0]
            mb = int(r["size_bytes"]) / (1024 * 1024) if r["size_bytes"].isdigit() else 0
            lines.append(f"- **{name}** — {r['file_count']} files (depth-limited scan), ~{mb:.1f} MB at root aggregate")

    lines.extend(["", "## Top-level folders (see CSV for detail)", ""])
    for name in SUBTREES:
        items = [r for r in by_sub.get(name, []) if r["path"] != "." and r["depth"] == "1"]
        if not items:
            continue
        lines.append(f"### {name}")
        lines.append("")
        for r in sorted(items, key=lambda x: x["path"])[:30]:
            mb = int(r["size_bytes"]) / (1024 * 1024) if r["size_bytes"].isdigit() else 0
            lines.append(f"- `{r['path']}/` — {r['file_count']} files, {mb:.1f} MB")
        if len(items) > 30:
            lines.append(f"- … {len(items) - 30} more in CSV")
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(all_rows)} rows → {OUT_CSV.name}")
    print(f"Wrote {OUT_MD.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
