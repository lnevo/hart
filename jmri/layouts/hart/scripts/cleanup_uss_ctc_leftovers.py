#!/usr/bin/env python3
"""Rename USS CTC internals to live Switch N and drop unreferenced leftovers.

IS*: systemNames stay frozen. userNames were still CTC 100/101/… after convert.
Orphan UniqueIDs 13/15/19 and unused 14/16/20 siblings (except LOCKTOGGLE on
the packed board), OpenLCB leftover sensors, and unused MTT aliases go away.
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

# Unreferenced after the 20-col pack. LOCKTOGGLE on 14/16/20 stays (panel Local).
DELETE_SYSTEM_NAMES = frozenset(
    {
        "MS01.01.02.00.00.FF.00.EA;01.01.02.00.00.FF.00.EB",
        "MS01.01.02.00.00.FF.00.EC;01.01.02.00.00.FF.00.ED",
        "MTT100",
        "MTT111",
        "MTT113",
        "MTT114",
        "MTT115",
        "IS13:LEVER",
        "IS13:SWNI",
        "IS13:SWRI",
        "IS15:LEVER",
        "IS15:SWNI",
        "IS15:SWRI",
        "IS19:LEVER",
        "IS19:SWNI",
        "IS19:SWRI",
        "IS14:CALLON",
        "IS14:CB",
        "IS14:LDGK",
        "IS14:LDGL",
        "IS14:NGK",
        "IS14:NGL",
        "IS14:RDGK",
        "IS14:RDGL",
        "IS14:UNLOCKEDINDICATOR",
        "IS16:CALLON",
        "IS16:CB",
        "IS16:LDGK",
        "IS16:LDGL",
        "IS16:NGK",
        "IS16:NGL",
        "IS16:RDGK",
        "IS16:RDGL",
        "IS16:UNLOCKEDINDICATOR",
        "IS20:CALLON",
        "IS20:CB",
        "IS20:LDGK",
        "IS20:LDGL",
        "IS20:NGK",
        "IS20:NGL",
        "IS20:RDGK",
        "IS20:RDGL",
        "IS20:UNLOCKEDINDICATOR",
    }
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
        if system_name_of(match.group(0)) in DELETE_SYSTEM_NAMES:
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
