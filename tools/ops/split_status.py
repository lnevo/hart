#!/usr/bin/env python3
"""Split a one-file wiki/STATUS.md into one file per entry under wiki/status/ (ADR-038), and check the result.

    python3 tools/ops/split_status.py --canonical [--from FILE]   rewrite FILE (default wiki/STATUS.md) in the page
                                                                  order the build gives: each unordered section's
                                                                  entries by file name, the Counts lines at the end of
                                                                  Current state, one blank line between blocks
    python3 tools/ops/split_status.py [--from FILE | --from-git REF]
                                                                  write wiki/status/<section>/<slug>.md for every entry
                                                                  (replacing the section folders' entries) and
                                                                  wiki/status/README.md, then build the page in memory
                                                                  (status_counts.py) and compare it with FILE byte for
                                                                  byte apart from the Counts line; exit 1 if it differs

Re-runnable: a branch that waits for the migration takes the latest main's wiki/STATUS.md (--from-git origin/main),
cuts any entry over 60 words by hand, runs --canonical on it, commits that, then runs the split. Owed entries get
`order:` lines 10, 20, 30 in the file's order. The page head and the section headings and intros must match
status_counts.PAGE_HEAD and SECTIONS; a change there stops the split, so it is carried over by hand.
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
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

ROOT = sc.ROOT
SLUG_WORDS = 6
README = """# Live status, one file per entry

The status page is built from this folder ([ADR-038](../decisions/ADR-038-one-file-per-status-entry.md)).
`make status` (`python3 tools/ops/status_counts.py`) writes `wiki/STATUS.md`, which is gitignored; the session-start
hook and `make wt` build it, so it is there to read in every checkout. `check.sh` and CI build it in memory
(`status_counts.py --check`).

## Sections

| Folder | Heading | What goes there |
|---|---|---|
| [`now/`](now/) | Now | What is active, waits on the owner or is blocked, in a few lines |
| [`current/`](current/) | Current state | How the railroad, its data and its tooling are today; the Counts line is added at build time |
| [`owed/`](owed/) | Owed | Work owed, in order: each file opens with an `order: N` line, lowest first |
| [`in-progress/`](in-progress/) | In progress | Work under way that is not owed |
| [`future/`](future/) | Future goals | Goals with no date |

## An entry

- One file, `<section>/<slug>.md`, named from its bold lead or first words, holding the bullet's text without
  its `- `. The page lists an unordered section's entries by file name.
- At most 60 words (owner, 2026-11-25): the fact, the owner and date, and a link to the detail. The check fails a
  longer one; move the detail to the linked page or ADR.
- Links are relative to the entry file (`../../decisions/ADR-038-one-file-per-status-entry.md`), so they work here
  on GitHub; the build rewrites them for `wiki/STATUS.md`.
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


def parse(text: str) -> tuple[str, dict[str, list[str]], list[str]]:
    """The page head, each section's entries (bullet text without "- ", links still relative to wiki/, nested lines
    kept), and the Counts block lines. Raises SplitError when the head or a heading or intro is not the builder's."""
    by_heading = {h: (name, intro) for name, h, intro, _o in sc.SECTIONS}
    head, _, body = text.partition("\n## ")
    if head != sc.PAGE_HEAD:
        raise SplitError("the page head differs from status_counts.PAGE_HEAD; carry the change over by hand:\n"
                         + "".join(difflib.unified_diff(sc.PAGE_HEAD.splitlines(True), head.splitlines(True))))
    entries: dict[str, list[str]] = {}
    counts_block: list[str] = []
    for chunk in ("## " + body).split("\n## "):
        heading, _, rest = chunk.removeprefix("## ").partition("\n")
        if heading not in by_heading:
            raise SplitError(f"unknown section heading: ## {heading}")
        name, intro = by_heading[heading]
        items, prose, in_counts = [], [], False
        for line in rest.split("\n"):
            if line == sc.START:
                in_counts = True
                counts_block.append(line)
            elif line == sc.END:
                in_counts = False
                counts_block.append(line)
            elif in_counts:
                counts_block.append(line)
            elif line.startswith("- "):
                items.append(line[2:])
            elif line.startswith("  ") and items:
                items[-1] += "\n" + line
            elif line.strip():
                prose.append(line)
        if " ".join(prose) != intro:
            raise SplitError(f"## {heading}: the text before its entries is {' '.join(prose)!r}, not the builder's "
                             f"intro {intro!r}; carry the change over by hand")
        entries[name] = items
    return head, entries, counts_block


def file_names(name: str, items: list[str]) -> list[str]:
    names = [slug(t) + ".md" for t in items]
    doubles = sorted({n for n in names if names.count(n) > 1})
    if doubles:
        raise SplitError(f"{name}: two entries would share a file name: {', '.join(doubles)}")
    return names


def canonical(text: str) -> str:
    """The page with its entries in the order the build gives them, the Counts block at the end of Current state."""
    _head, entries, counts_block = parse(text)
    out = [sc.PAGE_HEAD]
    for name, heading, intro, ordered in sc.SECTIONS:
        items = entries.get(name, [])
        if not ordered:
            items = [t for _n, t in sorted(zip(file_names(name, items), items))]
        bullets = ["- " + t for t in items]
        if name == sc.COUNTS_SECTION:
            bullets += counts_block
        block = [f"## {heading}\n"] + ([intro + "\n"] if intro else []) + (["\n".join(bullets) + "\n"] if bullets
                                                                          else [])
        out.append("\n".join(block))
    return "\n".join(out)


def split(text: str, folder: Path) -> int:
    """Write the entry files and README; return how many entries."""
    _head, entries, _counts = parse(text)
    n = 0
    folder.mkdir(parents=True, exist_ok=True)
    for name, _heading, _intro, ordered in sc.SECTIONS:
        d = folder / name
        d.mkdir(exist_ok=True)
        for old in d.glob("*.md"):
            old.unlink()
        items = entries.get(name, [])
        for i, (fname, item) in enumerate(zip(file_names(name, items), items)):
            body = sc.rebase(item, "wiki", f"wiki/status/{name}") + "\n"
            if ordered:
                body = f"order: {(i + 1) * 10}\n" + body
            (d / fname).write_text(body, encoding="utf-8")
            n += 1
    (folder / "README.md").write_text(README, encoding="utf-8")
    return n


def without_counts(text: str) -> str:
    return re.sub(r"^- \*\*Counts:\*\*.*$", "- **Counts:** (computed)", text, flags=re.M)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--from", dest="source", type=Path, default=sc.STATUS, help="the one-file page (wiki/STATUS.md)")
    src.add_argument("--from-git", metavar="REF", help="read wiki/STATUS.md as it is at REF")
    ap.add_argument("--canonical", action="store_true", help="rewrite the page in build order; split nothing")
    ap.add_argument("--folder", type=Path, default=sc.FOLDER, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.from_git:
        text = subprocess.run(["git", "-C", str(ROOT), "show", f"{args.from_git}:wiki/STATUS.md"], check=True,
                              capture_output=True, text=True).stdout
    else:
        text = args.source.read_text(encoding="utf-8")
    try:
        if args.canonical:
            if args.from_git:
                raise SplitError("--canonical rewrites a file: use --from")
            new = canonical(text)
            args.source.write_text(new, encoding="utf-8")
            print("already in build order" if new == text else f"rewrote {args.source} in build order")
            return 0
        n = split(text, args.folder)
    except SplitError as err:
        print(f"split_status: {err}")
        return 1
    entries, problems = sc.read_entries(args.folder)
    built = sc.page(entries, sc.line(sc.counts()))
    print(f"wrote {n} entries and README.md under {args.folder}")
    if without_counts(built) == without_counts(text):
        print("built page matches the one-file page byte for byte, apart from the Counts line")
    else:
        print("built page differs from the one-file page (run --canonical on it first if only the order differs):")
        sys.stdout.writelines(difflib.unified_diff(without_counts(text).splitlines(True),
                                                   without_counts(built).splitlines(True), "one file", "built"))
        return 1
    if problems:
        print("problems the check will fail on:\n" + "\n".join(f"  {p}" for p in problems))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
