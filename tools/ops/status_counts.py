#!/usr/bin/env python3
"""Build wiki/STATUS.md from its entry files in wiki/status/, with the Counts line from tables.xml and traininfo.

    python3 tools/ops/status_counts.py              (make status) write wiki/STATUS.md (gitignored, ADR-038)
    python3 tools/ops/status_counts.py --out FILE   write the page to FILE instead
    python3 tools/ops/status_counts.py --check      build the page in memory and write nothing; exit 1 on an entry
                                                    over MAX_WORDS words, a stray file, a missing or repeated
                                                    `order:` line, a doubled entry, or wiki/STATUS.md tracked by
                                                    git again (check.sh)

Each entry is one file, wiki/status/<section>/<slug>.md, holding the bullet's text without its "- ". Its Markdown
links are relative to the entry file, so they work on GitHub; the build rebases them to wiki/. The sections are
SECTIONS, in page order. Every entry opens with an `order: N` line, and each section lists its entries by N, so
entries on one topic stay together (steps of 10 leave room for a new entry between two others).
The Counts line is computed when the page is built: it stands where the Current state file whose text is
COUNTS_TOKEN (current/counts.md) puts it, between the counts markers. The page head and the section intros are
PAGE_HEAD and SECTIONS below. The session-start hook and `make wt` build the page, so readers by path find it in every checkout.
"""
from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import files, parked, paths, tables as hl_tables  # noqa: E402

ROOT = paths.REPO_ROOT
TABLES = paths.TABLES_XML
TRAININFO = paths.LAYOUT_DIR / "dispatcher/traininfo"
STATUS = ROOT / "wiki/STATUS.md"
FOLDER = ROOT / "wiki/status"
START, END = "<!-- counts:start -->", "<!-- counts:end -->"
MAX_WORDS = 60          # ADR-038: the detail goes to the linked page or ADR
ORDER = re.compile(r"order:\s*(-?\d+)\s*$")
PAGE_HEAD = ("# Live status\n\n"
             "One or two lines per fact, with the owner and date and a link to the detail. PR numbers, how each fact "
             "came about and the full earlier wording are in [`STATUS_LOG.md`](STATUS_LOG.md) (the 2026-11-21 and "
             "2026-11-25 \"Full text\" entries hold the last long versions).\n")
# (folder, heading, intro paragraph); page order
SECTIONS = (
    ("now", "Now", ""),
    ("current", "Current state", ""),
    ("owed", "Owed", "In order; the first two are the main track (owner, 2026-11-21)."),
    ("in-progress", "In progress", ""),
    ("future", "Future goals", ""),
)
COUNTS_SECTION = "current"
COUNTS_TOKEN = "<!-- counts: the Counts line is computed here when the page is built -->"
# a Markdown link target: its path may hold one level of balanced parentheses, and a "title" may follow it
LINK = re.compile(r'(\]\()((?:[^()\s]|\([^()\s]*\))+)((?:\s+"[^"]*")?\))')


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


def rebase(text: str, src: str, dst: str) -> str:
    """`text` with each relative Markdown link written from folder `src` rewritten to lead to the same file from folder
    `dst` (both repo-relative). Web addresses, mailto:, absolute paths and anchors in the same page stay as they are."""
    def one(m: re.Match[str]) -> str:
        target = m.group(2)
        if "://" in target or target.startswith(("#", "/", "mailto:")):
            return m.group(0)
        path, hash_, anchor = target.partition("#")
        new = posixpath.relpath(posixpath.normpath(posixpath.join(src, path)), dst)
        if path.endswith("/") and not new.endswith("/"):
            new += "/"
        return f"{m.group(1)}{new}{hash_}{anchor}{m.group(3)}"
    return LINK.sub(one, text)


def words(text: str) -> int:
    """The words of an entry: whitespace-separated tokens, a nested list's "-" markers left out."""
    return sum(1 for tok in text.split() if tok != "-")


class Entry:
    def __init__(self, section: str, path: Path, text: str, order: int):
        self.section, self.path, self.text, self.order = section, path, text, order


def read_entries(folder: Path = FOLDER) -> tuple[list[Entry], list[str]]:
    """Every entry file, in page order, and the problems found reading them."""
    entries, problems = [], []
    known = {s[0] for s in SECTIONS}
    if not folder.is_dir():
        return [], [f"{folder} is missing"]
    for p in sorted(folder.iterdir()):
        if p.name.startswith(".") or p.name == "README.md":
            continue
        if not (p.is_dir() and p.name in known):
            problems.append(f"wiki/status/{p.name}: not a section ({', '.join(s[0] for s in SECTIONS)})")
    for name, _heading, _intro in SECTIONS:
        found = []
        d = folder / name
        for p in sorted(d.iterdir()) if d.is_dir() else ():
            rel = f"wiki/status/{name}/{p.name}"
            if p.name.startswith("."):
                continue
            if p.is_dir() or p.suffix != ".md" or p.name == "README.md":
                problems.append(f"{rel}: not an entry (a section holds <slug>.md files only)")
                continue
            body = p.read_text(encoding="utf-8")
            first, _, rest = body.partition("\n")
            m = ORDER.fullmatch(first)
            if not m:
                problems.append(f"{rel}: an entry opens with an `order: N` line (its place in the section)")
                continue
            order, text = int(m.group(1)), rest.strip("\n")
            if not text.strip():
                problems.append(f"{rel}: empty entry")
                continue
            if text == COUNTS_TOKEN:
                if name != COUNTS_SECTION:
                    problems.append(f"{rel}: the Counts line stands in {COUNTS_SECTION}/ only")
                else:
                    found.append(Entry(name, p, text, order))
                continue
            if "\n\n" in text:
                problems.append(f"{rel}: a blank line inside an entry would break the list")
            if text.startswith("- "):
                problems.append(f"{rel}: the file holds the bullet's text; the build adds the \"- \"")
            n = words(text)
            if n > MAX_WORDS:
                problems.append(f"{rel}: {n} words, over {MAX_WORDS}; move the detail to the linked page or ADR")
            found.append(Entry(name, p, text, order))
        found.sort(key=lambda e: (e.order, e.path.name))
        for x, y in zip(found, found[1:]):
            if x.order == y.order:
                problems.append(f"wiki/status/{name}/: {x.path.name} and {y.path.name} have the same order: "
                                f"{x.order}; give one a number between its neighbours'")
        if name == COUNTS_SECTION and sum(e.text == COUNTS_TOKEN for e in found) != 1:
            problems.append(f"wiki/status/{name}/: needs one file whose text is {COUNTS_TOKEN} (where the Counts "
                            f"line goes), not {sum(e.text == COUNTS_TOKEN for e in found)}")
        entries += found
    return entries, problems


def page(entries: list[Entry], counts_line: str) -> str:
    """The page: PAGE_HEAD, then each section's heading, intro and bullets, with the Counts line where its file is."""
    out = [PAGE_HEAD]
    for name, heading, intro in SECTIONS:
        block = [f"## {heading}\n"]
        if intro:
            block.append(intro + "\n")
        bullets = ["\n".join((START, counts_line, END)) if e.text == COUNTS_TOKEN
                   else "- " + rebase(e.text, f"wiki/status/{name}", "wiki") for e in entries if e.section == name]
        if bullets:
            block.append("\n".join(bullets) + "\n")
        out.append("\n".join(block))
    return "\n".join(out)


OPENING_WORDS = 8  # an entry with no bold lead is known by its first words; 8 flagged only real doubles in 331 versions


def opening(line_: str) -> str | None:
    """The first OPENING_WORDS words of a bullet with no bold lead, lower case; None for a bullet shorter than that."""
    words_ = re.findall(r"\w+", line_[2:].lower())
    return " ".join(words_[:OPENING_WORDS]) if len(words_) >= OPENING_WORDS else None


def duplicates(text: str) -> list[str]:
    """Entries the page holds twice: a bullet line repeated, two bullets with the same bold lead ("- **Lead:**"), or two
    bullets with no bold lead that open with the same words (two files for one entry; before ADR-038 a union merge of
    the one committed file left such doubles, 2026-11-25 a Future goals entry)."""
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


def tracked_page(root: Path = ROOT) -> bool:
    """True when git tracks wiki/STATUS.md again (a branch from before ADR-038 that kept its side of the
    modify/delete conflict)."""
    done = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", "wiki/STATUS.md"],
                          capture_output=True, text=True)
    return done.returncode == 0


def build(folder: Path = FOLDER, tables: Path = TABLES, traininfo: Path = TRAININFO) -> tuple[str, list[str], int]:
    """The page, every problem with its sources, and the number of entries."""
    entries, problems = read_entries(folder)
    text = page(entries, line(counts(tables, traininfo)))
    problems += [f"the built page has {d}" for d in duplicates(text)]
    return text, problems, sum(e.text != COUNTS_TOKEN for e in entries)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="build in memory, write nothing; exit 1 on a problem")
    ap.add_argument("--out", type=Path, help="write the page here instead of wiki/STATUS.md")
    ap.add_argument("--quiet", action="store_true", help="print only problems (the session-start hook)")
    args = ap.parse_args(argv)
    if not args.check:
        paths.exit_if_overridden(Path(__file__).name)
    text, problems, n = build()
    if tracked_page():
        problems.append("wiki/STATUS.md is tracked again: it is built (ADR-038); move its edit into the entry file "
                        "under wiki/status/ and run git rm --cached wiki/STATUS.md")
    if not args.check:
        out = args.out or STATUS
        if not out.exists() or out.read_text(encoding="utf-8") != text:
            files.write_atomic(out, text, follow_links=False)  # a stopped build leaves the old page or the new one
        if not args.quiet:
            print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out} "
                  f"from wiki/status/ ({n} entries and the Counts line)")
    if problems:
        print("wiki/status/ has problems:")
        print("\n".join(f"  {p}" for p in problems))
        return 1
    if args.check:
        print("STATUS entries ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
