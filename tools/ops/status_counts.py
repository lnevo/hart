#!/usr/bin/env python3
"""Keep the Counts line in wiki/STATUS.md in step with tables.xml and traininfo.

The line sits between <!-- counts:start --> and <!-- counts:end -->. Plain run
rewrites it; --check exits 1 when it is stale. Parsing helpers come from the
website's tables page (www/scripts/tables_page.py).
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "www/scripts"))
import tables_page  # noqa: E402

TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
TRAININFO = ROOT / "jmri/layouts/hart/dispatcher/traininfo"
STATUS = ROOT / "wiki/STATUS.md"
START, END = "<!-- counts:start -->", "<!-- counts:end -->"


def counts(tables: Path = TABLES, traininfo: Path = TRAININFO) -> dict:
    root = ET.parse(tables).getroot()
    d = tables_page._direct
    real = len(d(root, "signalmasts", "signalmast"))
    virtual = len(d(root, "signalmasts", "virtualsignalmast"))
    sml = d(root, "signalmastlogics", "signalmastlogic")
    pairs = [x for m in root.findall("entryexitpairs") for p in m for s in p.findall("source")
             for x in s.findall("destination")]
    return {
        "masts": real + virtual, "real": real, "virtual": virtual,
        "sections": len(d(root, "sections", "section")),
        "transits": len(d(root, "transits", "transit")),
        "nx": len(pairs),
        "sml": len(sml),
        "dest": sum(len(s.findall("destinationMast")) for s in sml),
        "traininfo": sum(1 for p in traininfo.iterdir() if p.is_file()),
    }


def line(c: dict) -> str:
    return (f"- **Counts:** {c['masts']} masts ({c['real']} real, {c['virtual']} virtual), "
            f"{c['sections']} sections, {c['transits']:,} transits, {c['nx']} NX pairs, "
            f"{c['sml']} SML sources with {c['dest']} destinations, {c['traininfo']:,} traininfo files.")


def rewrite(text: str, new: str) -> str:
    a, b = text.index(START) + len(START), text.index(END)
    return text[:a] + "\n" + new + "\n" + text[b:]


def main(argv: list[str]) -> int:
    text = STATUS.read_text(encoding="utf-8")
    new = rewrite(text, line(counts()))
    if "--check" in argv:
        if new != text:
            print("wiki/STATUS.md Counts line is stale; run python3 tools/ops/status_counts.py")
            return 1
        print("STATUS counts ok")
        return 0
    STATUS.write_text(new, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
