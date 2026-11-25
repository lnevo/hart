#!/usr/bin/env python3
"""Keep the Counts line in wiki/STATUS.md in step with tables.xml and traininfo.

The line sits between <!-- counts:start --> and <!-- counts:end -->. A plain run
rewrites it; --check exits 1 when it is stale.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import parked, paths, tables as hl_tables  # noqa: E402

ROOT = paths.REPO_ROOT
TABLES = paths.TABLES_XML
TRAININFO = paths.LAYOUT_DIR / "dispatcher/traininfo"
STATUS = ROOT / "wiki/STATUS.md"
START, END = "<!-- counts:start -->", "<!-- counts:end -->"


def counts(tables: Path = TABLES, traininfo: Path = TRAININFO) -> dict:
    root = hl_tables.read(tables)
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
        "parked": parked.parked_in(root),       # the parked features these tables leave out (hartlib.parked)
    }


def line(c: dict) -> str:
    left_out = c.get("parked", ())
    graph = ("sections and transits parked" if "dispatcher" in left_out
             else f"{c['sections']:,} sections, {c['transits']:,} transits")
    nx = "NX pairs parked" if "nx" in left_out else f"{c['nx']:,} NX pairs"
    trains = (f"{c['traininfo']:,} traininfo files kept in the repo" if "dispatcher" in left_out
              else f"{c['traininfo']:,} traininfo files")
    uss = ", USS CTC machine parked" if "uss" in left_out else ""
    return (f"- **Counts:** {c['masts']:,} masts ({c['real']:,} real, {c['virtual']:,} virtual), "
            f"{graph}, {nx}, {c['sml']:,} SML sources with {c['dest']:,} destinations, {trains}{uss}.")


def rewrite(text: str, new: str) -> str:
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError(f"STATUS.md needs exactly one {START} and one {END}")
    a, b = text.index(START) + len(START), text.index(END)
    if b < a:
        raise ValueError(f"{END} comes before {START} in STATUS.md")
    return text[:a] + "\n" + new + "\n" + text[b:]


OPENING_WORDS = 8  # an entry with no bold lead is known by its first words; 8 flagged only real doubles in 331 versions


def opening(line_: str) -> str | None:
    """The first OPENING_WORDS words of a bullet with no bold lead, lower case; None for a bullet shorter than that."""
    words = re.findall(r"\w+", line_[2:].lower())
    return " ".join(words[:OPENING_WORDS]) if len(words) >= OPENING_WORDS else None


def duplicates(text: str) -> list[str]:
    """Entries a union merge (.gitattributes: wiki/STATUS.md merge=union) can leave twice: a bullet line repeated, two
    bullets with the same bold lead ("- **Lead:**"), or two bullets with no bold lead that open with the same words
    (two versions of one entry edited on both sides; 2026-11-25 a Future goals entry was left twice that way)."""
    seen_line, seen_lead, seen_open, out = set(), {}, set(), []
    for line_ in text.splitlines():
        if not line_.startswith("- "):
            continue
        if line_ in seen_line:
            out.append(f"repeated line: {line_[:90]}")
            continue
        seen_line.add(line_)
        m = re.match(r"- \*\*([^*]+)\*\*", line_)
        if m:
            lead = m.group(1)
            if lead in seen_lead:
                out.append(f"two entries for: {lead}")
            seen_lead[lead] = True
        elif (start := opening(line_)) is not None:
            if start in seen_open:
                out.append(f"two entries opening: {start}")
            seen_open.add(start)
    return out


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
    if not args.check:
        paths.exit_if_overridden(Path(__file__).name)
    dup = duplicates(text)
    if dup:
        print("wiki/STATUS.md has duplicated entries (a union merge keeps both sides); keep one of each:")
        print("\n".join(f"  {d}" for d in dup))
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
