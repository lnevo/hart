#!/usr/bin/env python3
"""Split a one-file wiki/STATUS.md into one file per entry under wiki/status/ (ADR-038), and check the result.

    python3 tools/ops/split_status.py [--from FILE | --from-git REF]
        write wiki/status/<section>/<slug>.md for every entry (replacing the section folders' entries), each opening
        with an `order:` line (10, 20, 30 in the page's order, so a section keeps its topic grouping), current/counts.md
        where the Counts lines stand, and wiki/status/README.md; then build the page in memory (status_counts.py) and
        compare it with FILE byte for byte apart from the Counts line; exit 1 if it differs
    python3 tools/ops/split_status.py --tidy [--from FILE]
        rewrite FILE with one blank line between blocks and none between entries, the only layout the build writes;
        no entry moves

Re-runnable: when main's wiki/STATUS.md changes before the migration lands, take it (--from-git origin/main or the
file itself), cut any entry over 60 words by hand, run --tidy if the split reports blank lines between entries, and
run the split again. The page head and the section headings and intros must match status_counts.PAGE_HEAD and
SECTIONS; a change there stops the split, so it is carried over by hand.
"""
from __future__ import annotations

import argparse
import difflib
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("status_counts", HERE / "status_counts.py")
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load {HERE / 'status_counts.py'}")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

ROOT = sc.ROOT
SLUG_WORDS = 6
STEP = 10
COUNTS_FILE = "counts.md"
README = """# Live status, one file per entry

The status page is built from this folder ([ADR-038](../decisions/ADR-038-one-file-per-status-entry.md)).
`make status` (`python3 tools/ops/status_counts.py`) writes `wiki/STATUS.md`, which is gitignored; the session-start
hook and `make wt` build it, so it is there to read in every checkout. `check.sh` and CI build it in memory
(`status_counts.py --check`).

## Sections

| Folder | Heading | What goes there |
|---|---|---|
| [`now/`](now/) | Now | What is active, waits on the owner or is blocked, in a few lines |
| [`current/`](current/) | Current state | How the railroad, its data and its tooling are today, grouped by topic |
| [`owed/`](owed/) | Owed | Work owed, in the order it is to be done |
| [`in-progress/`](in-progress/) | In progress | Work under way that is not owed |
| [`future/`](future/) | Future goals | Goals with no date |

## An entry

- One file, `<section>/<slug>.md`, named from its bold lead or opening words. Its first line is `order: N`, its
  place in the section: the page lists each section by N, so entries on one topic stay together.
  The numbers go in steps of 10; a new entry takes a free number between its neighbours'. Two entries in one
  section with the same number fail the check.
- Below that line, the bullet's text without its `- `. At most 60 words: the fact, the owner
  and date, and a link to the detail. The check fails a longer one; move the detail to the linked page or ADR.
- Links are relative to the entry file (`../../decisions/ADR-038-one-file-per-status-entry.md`), so they work here
  on GitHub; the build rewrites them for `wiki/STATUS.md`.
- `current/counts.md` holds no entry: it marks where the Counts line goes, which the build computes from
  `tables.xml` and traininfo.
- When an entry is removed or replaced, its old text goes to [`STATUS_LOG.md`](../STATUS_LOG.md) as before.
- A branch from before the split that edits `wiki/STATUS.md` gets a modify/delete conflict when it merges `main`:
  move the edit into the entry file and run `git rm wiki/STATUS.md`.
"""


class SplitError(Exception):
    pass


def slug(text: str) -> str:
    """A file name stem from an entry: up to SLUG_WORDS words of its bold lead, or of its opening phrase, without
    links, parentheses or code marks."""
    m = re.match(r"\*\*(.+?)\*\*", text)
    lead = m.group(1) if m else re.split(r"[:(.;]", text, maxsplit=1)[0]   # no bold lead: its opening phrase
    lead = lead.replace("'", "")
    lead = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", lead)
    while True:
        cut = re.sub(r"\([^()]*\)", "", lead)
        if cut == lead:
            break
        lead = cut
    tokens = re.findall(r"[a-z0-9]+", lead.lower())
    if not tokens:
        raise SplitError(f"no words to name the entry {text[:60]!r}")
    return "-".join(tokens[:SLUG_WORDS])


def parse(text: str) -> dict[str, list[str]]:
    """Each section's entries in page order: the bullet text without "- " (links still relative to wiki/, nested
    lines kept), and in Current state the Counts block, as one item holding its lines. Raises SplitError when the head
    or a heading or intro is not the builder's."""
    by_heading = {h: (name, intro) for name, h, intro in sc.SECTIONS}
    head, _, body = text.partition("\n## ")
    if head != sc.PAGE_HEAD:
        raise SplitError("the page head differs from status_counts.PAGE_HEAD; carry the change over by hand:\n"
                         + "".join(difflib.unified_diff(sc.PAGE_HEAD.splitlines(True), head.splitlines(True))))
    entries: dict[str, list[str]] = {}
    for chunk in ("## " + body).split("\n## "):
        heading, _, rest = chunk.removeprefix("## ").partition("\n")
        if heading not in by_heading:
            raise SplitError(f"unknown section heading: ## {heading}")
        name, intro = by_heading[heading]
        items, prose, counts = [], [], None
        for line in rest.split("\n"):
            if line == sc.START:
                counts = [line]
            elif counts is not None:
                counts.append(line)
                if line == sc.END:
                    if name != sc.COUNTS_SECTION:
                        raise SplitError(f"## {heading}: the counts markers belong in {sc.COUNTS_SECTION}")
                    items.append(sc.COUNTS_TOKEN)
                    counts = None
            elif line.startswith("- "):
                items.append(line[2:])
            elif line.startswith("  ") and items and items[-1] != sc.COUNTS_TOKEN:
                items[-1] += "\n" + line
            elif line.strip():
                prose.append(line)
        if counts is not None:
            raise SplitError(f"## {heading}: {sc.START} has no {sc.END}")
        if " ".join(prose) != intro:
            raise SplitError(f"## {heading}: the text before its entries is {' '.join(prose)!r}, not the builder's "
                             f"intro {intro!r}; carry the change over by hand")
        entries[name] = items
    if sc.COUNTS_TOKEN not in entries.get(sc.COUNTS_SECTION, []):
        raise SplitError(f"no {sc.START} ... {sc.END} block in the Current state section")
    return entries


def file_names(name: str, items: list[str]) -> list[str]:
    names = [COUNTS_FILE if t == sc.COUNTS_TOKEN else slug(t) + ".md" for t in items]
    doubles = sorted({n for n in names if names.count(n) > 1})
    if doubles:
        raise SplitError(f"{name}: two entries would share a file name: {', '.join(doubles)}")
    return names


def tidy(text: str) -> str:
    """The page with one blank line between blocks and none between the entries of a section; nothing moves."""
    out: list[str] = []
    for line in text.split("\n"):
        if line == "" and out and out[-1] == "":
            continue
        out.append(line)
    # a blank line between two entries (a bullet, a nested line or the counts block on either side) goes
    entry = re.compile(r"^(- |  |<!-- counts:)")
    keep = [l for i, l in enumerate(out)
            if not (l == "" and 0 < i < len(out) - 1 and entry.match(out[i - 1]) and entry.match(out[i + 1]))]
    return "\n".join(keep)


def split(text: str, folder: Path) -> int:
    """Write the entry files, current/counts.md and README; return how many entries (the counts file left out).
    Every section is parsed and named first, so a split that stops leaves the folders as they were."""
    entries = parse(text)
    plan = []
    for name, _heading, _intro in sc.SECTIONS:
        items = entries.get(name, [])
        for i, (fname, item) in enumerate(zip(file_names(name, items), items)):
            body = item if item == sc.COUNTS_TOKEN else sc.rebase(item, "wiki", f"wiki/status/{name}")
            plan.append((name, fname, f"order: {(i + 1) * STEP}\n{body}\n", item != sc.COUNTS_TOKEN))
    folder.mkdir(parents=True, exist_ok=True)
    for name, _heading, _intro in sc.SECTIONS:
        d = folder / name
        d.mkdir(exist_ok=True)
        for old in d.glob("*.md"):
            old.unlink()
    for name, fname, body, _entry in plan:
        (folder / name / fname).write_text(body, encoding="utf-8")
    (folder / "README.md").write_text(README, encoding="utf-8")
    return sum(entry for *_rest, entry in plan)


def without_counts(text: str) -> str:
    return re.sub(r"^- \*\*Counts:\*\*.*$", "- **Counts:** (computed)", text, flags=re.M)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--from", dest="source", type=Path, default=sc.STATUS, help="the one-file page (wiki/STATUS.md)")
    src.add_argument("--from-git", metavar="REF", help="read wiki/STATUS.md as it is at REF")
    ap.add_argument("--tidy", action="store_true", help="rewrite the page's blank lines as the build writes them")
    ap.add_argument("--folder", type=Path, default=sc.FOLDER, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.from_git:
        text = subprocess.run(["git", "-C", str(ROOT), "show", f"{args.from_git}:wiki/STATUS.md"], check=True,
                              capture_output=True, text=True).stdout
    else:
        text = args.source.read_text(encoding="utf-8")
    try:
        if args.tidy:
            if args.from_git:
                raise SplitError("--tidy rewrites a file: use --from")
            new = tidy(text)
            args.source.write_text(new, encoding="utf-8")
            print("already tidy" if new == text else f"rewrote the blank lines of {args.source}")
            return 0
        n = split(text, args.folder)
    except SplitError as err:
        print(f"split_status: {err}")
        return 1
    entries, problems = sc.read_entries(args.folder)
    built = sc.page(entries, sc.line(sc.counts()))
    print(f"wrote {n} entries, {sc.COUNTS_SECTION}/{COUNTS_FILE} and README.md under {args.folder}")
    if without_counts(built) == without_counts(text):
        same = "Counts line included" if built == text else "apart from the Counts line"
        print(f"built page matches the one-file page byte for byte, {same}")
    else:
        print("built page differs from the one-file page (--tidy first if only blank lines differ):")
        sys.stdout.writelines(difflib.unified_diff(without_counts(text).splitlines(True),
                                                   without_counts(built).splitlines(True), "one file", "built"))
        return 1
    if problems:
        print("problems the check will fail on:\n" + "\n".join(f"  {p}" for p in problems))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
