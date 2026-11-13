#!/usr/bin/env python3
"""Keep the Counts line in wiki/STATUS.md in step with tables.xml and traininfo.

The line sits between <!-- counts:start --> and <!-- counts:end -->. A plain run
rewrites it; --check exits 1 when it is stale.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402

ROOT = paths.REPO_ROOT
TABLES = paths.TABLES_XML
TRAININFO = paths.LAYOUT_DIR / "dispatcher/traininfo"
STATUS = ROOT / "wiki/STATUS.md"
START, END = "<!-- counts:start -->", "<!-- counts:end -->"


def counts(tables_path: Path = TABLES, traininfo: Path = TRAININFO) -> dict:
    root = tables.read(tables_path)
    sml = root.findall("signalmastlogics/signalmastlogic")
    real = len(root.findall("signalmasts/signalmast"))
    virtual = len(root.findall("signalmasts/virtualsignalmast"))
    return {
        "masts": real + virtual, "real": real, "virtual": virtual,
        "sections": len(root.findall("sections/section")),
        "transits": len(root.findall("transits/transit")),
        "nx": len(root.findall("entryexitpairs/*/source/destination")),
        "sml": len(sml),
        "dest": sum(len(s.findall("destinationMast")) for s in sml),
        # Only the XML files Dispatcher writes; Finder's .DS_Store and the like stay out.
        "traininfo": sum(1 for p in traininfo.glob("*.xml") if p.is_file()),
    }


def line(c: dict) -> str:
    return (f"- **Counts:** {c['masts']:,} masts ({c['real']:,} real, {c['virtual']:,} virtual), "
            f"{c['sections']:,} sections, {c['transits']:,} transits, {c['nx']:,} NX pairs, "
            f"{c['sml']:,} SML sources with {c['dest']:,} destinations, "
            f"{c['traininfo']:,} traininfo files.")


def rewrite(text: str, new: str) -> str:
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError(f"STATUS.md needs exactly one {START} and one {END}")
    a, b = text.index(START) + len(START), text.index(END)
    if b < a:
        raise ValueError(f"{END} comes before {START} in STATUS.md")
    return text[:a] + "\n" + new + "\n" + text[b:]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="exit 1 if the line is stale; write nothing")
    args = ap.parse_args(argv)
    text = STATUS.read_text(encoding="utf-8")
    try:
        new = rewrite(text, line(counts()))
    except ValueError as exc:
        print(exc)
        return 1
    if args.check:
        if new != text:
            print("wiki/STATUS.md Counts line is stale; run python3 tools/ops/status_counts.py")
            return 1
        print("STATUS counts ok")
        return 0
    if new == text:
        print("STATUS counts already current")
        return 0
    STATUS.write_text(new, encoding="utf-8")
    print("STATUS counts updated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
