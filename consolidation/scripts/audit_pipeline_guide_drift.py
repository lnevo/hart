#!/usr/bin/env python3
"""Report drift between live wiki/pipelines and consolidation/wiki/pipelines.

Read-only — does not overwrite consolidation drafts. Writes audit report only.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "wiki/pipelines"
CONSOL = ROOT / "consolidation/wiki/pipelines"
OUT = ROOT / "consolidation/audits/pipeline-guide-drift.md"
SKIP = {"lcos-bom.md"}
CONSOL_ONLY = {"mqtt-mimic.md", "tables-merge.md"}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def main() -> None:
    live_files = {p.name for p in LIVE.glob("*.md") if p.name not in SKIP and p.name != "README.md"}
    consol_files = {p.name for p in CONSOL.glob("*.md") if p.name != "README.md"}

    only_live = sorted(live_files - consol_files)
    only_consol = sorted(consol_files - live_files - CONSOL_ONLY)
    shared = sorted(live_files & consol_files)

    identical = []
    differ = []
    for name in shared:
        if file_hash(LIVE / name) == file_hash(CONSOL / name):
            identical.append(name)
        else:
            differ.append(name)

    lines = [
        "# Audit — pipeline guide drift (live vs consolidation)",
        "",
        f"**Date:** auto-generated",
        "",
        "Live [`wiki/pipelines/`](../../wiki/pipelines/) is read-only reference.",
        "Consolidation [`wiki/pipelines/`](../wiki/pipelines/) is the build target — **intentional diffs expected** (SoR headers, hart-ops paths, D12 notes).",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|------:|",
        f"| Shared guides | {len(shared)} |",
        f"| Byte-identical | {len(identical)} |",
        f"| Intentionally diverged | {len(differ)} |",
        f"| Consolidation-only | {len(only_consol) + len(CONSOL_ONLY & consol_files)} |",
        f"| Live-only (excluded) | {len(only_live)} |",
        "",
    ]

    if differ:
        lines.extend(["## Diverged (consolidation is authoritative for build)", ""])
        for name in differ:
            lines.append(f"- `{name}`")
        lines.append("")

    consol_extra = sorted(CONSOL_ONLY & consol_files | set(only_consol))
    if consol_extra:
        lines.extend(["## Consolidation-only guides", ""])
        for name in consol_extra:
            lines.append(f"- `{name}`")
        lines.append("")

    if only_live:
        lines.extend(["## Live-only (not copied)", ""])
        for name in only_live:
            lines.append(f"- `{name}`")
        lines.append("")

    if identical:
        lines.extend(["## Byte-identical (may still need SoR header review)", ""])
        for name in identical:
            lines.append(f"- `{name}`")
        lines.append("")

    lines.extend(
        [
            "## When to sync",
            "",
            "Do **not** blind-run `sync_pipeline_guides.py` — it overwrites consolidation drafts.",
            "Merge live changes manually into consolidation guides when live wiki updates.",
            "",
            "Regenerate this report:",
            "",
            "```bash",
            "python3 consolidation/scripts/audit_pipeline_guide_drift.py",
            "```",
            "",
        ]
    )

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    print(f"  diverged={len(differ)} identical={len(identical)} consol-only={len(consol_extra)}")


if __name__ == "__main__":
    main()
