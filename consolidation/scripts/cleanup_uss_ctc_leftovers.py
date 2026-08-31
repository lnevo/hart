#!/usr/bin/env python3
"""CONSOLIDATION COPY — do not run against live without promotion.

Rename USS CTC internals to live Switch N and drop unreferenced leftovers.
See consolidation/audits/tables-pipeline.md and DECISIONS_PENDING.md D5.

Original: jmri/layouts/hart/scripts/cleanup_uss_ctc_leftovers.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_bean_comments import refresh_comments

TABLES = [
    ROOT / "jmri/layouts/hart/output/tables.xml",
    ROOT / "tables/new_tables.xml",
    ROOT / "jmri/layouts/hart/output/hart_prod.xml",
]

# Unreferenced after the 20-col pack. OpenLCB leftover sensors only.
# MTT* LCC aliases of MQTT plants are required (device map DCC Switch N).
DELETE_SYSTEM_NAMES = frozenset(
    {
        "MS01.01.02.00.00.FF.00.EA;01.01.02.00.00.FF.00.EB",
        "MS01.01.02.00.00.FF.00.EC;01.01.02.00.00.FF.00.ED",
    }
)
assert not any(name.startswith("MTT") for name in DELETE_SYSTEM_NAMES), (
    "LCC MTT* aliases are required; do not list them in DELETE_SYSTEM_NAMES"
)

BEAN_RE = re.compile(
    r"    <(sensor|turnout)\b[^>]*>.*?</\1>\n",
    re.S,
)


def system_name_of(block: str) -> str:
    match = re.search(r"<systemName>(.*?)</systemName>", block, re.S)
    return match.group(1).strip() if match else ""


def delete_orphans(text: str) -> tuple[str, int]:
    removed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal removed
        sn = system_name_of(match.group(0))
        if sn.startswith("MTT"):
            return match.group(0)
        if sn in DELETE_SYSTEM_NAMES:
            removed += 1
            return ""
        return match.group(0)

    return BEAN_RE.sub(repl, text), removed


def main() -> int:
    write = "--apply" in sys.argv
    for path in TABLES:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        updated, n_refresh = refresh_comments(text)
        updated, n_delete = delete_orphans(updated)
        rel = path.relative_to(ROOT)
        print(f"{rel}: refresh={n_refresh} deleted={n_delete}")
        leftover = [name for name in DELETE_SYSTEM_NAMES if f"<systemName>{name}</systemName>" in updated]
        if leftover:
            print(f"  still present: {leftover}")
        if write:
            path.write_text(updated, encoding="utf-8")
    if not write:
        print("dry-run (pass --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
