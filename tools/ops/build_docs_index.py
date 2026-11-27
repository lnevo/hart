#!/usr/bin/env python3
"""build_docs_index.py

Write docs/INDEX.md: every document under docs/ grouped by folder, each Markdown file with a one-line summary.

    python3 tools/ops/build_docs_index.py            write it
    python3 tools/ops/build_docs_index.py --check    exit 1 when it lists other documents than those in docs/ (tracked or new);
                                                     Markdown files with no summary are a warning
    python3 tools/ops/build_docs_index.py --check --strict    the missing summaries fail too

Summary of a Markdown file: a `summary: ...` line in its first 10 lines, else the first plain prose line after the
first `# ` heading (a paragraph of plain prose: the lines up to the next blank line, joined). A block starting with
| ` < # ![ or a list, quote or numbered marker and a space is skipped to its next blank line, as are code fences and
HTML comments. Links keep only their text. The summary is cut at the first sentence end (. ? ! and a capital).
Images, css, js and fonts are counted per folder, not listed. No dates: a shallow clone (CI) has no history.
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
TOOLING = (".py", ".sh", ".scad", ".stl", ".3mf", ".gitignore")
ASSETS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".ico", ".css", ".js", ".woff", ".woff2", ".ttf", ".otf")
DOCS_DIR = "docs"      # the folder it lists and reads: the docs-index step's input in tools/pipeline/checks.toml
SKIP = ("docs/INDEX.md",)
MAX_SUMMARY = 160
SKIP_PREFIXES = ("|", "`", "<", "#", "![")
OVERRIDE_LINES = 10
USAGE = "build_docs_index.py [--check [--strict]]"


def doc_files() -> list[str]:
    """Files under docs/ that are documents or assets (not tooling, not the index itself).

    Tracked files plus new ones git does not ignore, less tracked files already deleted, so the index
    built before a commit matches the one CI builds after it, a new doc not yet staged included.
    """
    out = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", DOCS_DIR], cwd=ROOT, text=True
    )
    paths = sorted({p for p in out.split("\0") if p and (ROOT / p).is_file()})
    return [p for p in paths if not p.startswith(SKIP) and not p.endswith(TOOLING)]


def untracked() -> list[str]:
    """The files doc_files() lists that git does not track yet."""
    out = subprocess.check_output(["git", "ls-files", "-z", "--others", "--exclude-standard", DOCS_DIR], cwd=ROOT, text=True)
    return sorted(p for p in out.split("\0") if p and not p.startswith(SKIP) and not p.endswith(TOOLING))


def is_asset(path: str) -> bool:
    return path.lower().endswith(ASSETS)


def doc_link(path: str) -> str:
    """Link from docs/INDEX.md to a docs/ file, with every space and non-ASCII character encoded."""
    return quote(path.removeprefix("docs/"))


def area_of(path: str) -> str:
    """The folder a document is grouped under: its first folder below docs/, or 'general' for a file in docs/."""
    return path.split("/")[1] if path.count("/") > 1 else "general"


def _rel(path: str, area: str) -> str:
    """The path shown for a document: below its area folder, or the file name in 'general'."""
    return path.removeprefix(f"docs/{area}/") if area != "general" else Path(path).name


def _cap(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_SUMMARY:
        return text
    return text[: MAX_SUMMARY - 3].rsplit(" ", 1)[0].rstrip(",;:") + "..."


def _skipped(line: str) -> bool:
    """A line that starts a block that is not prose: table, list, quote, code, HTML, heading, image, rule, numbered."""
    return (line.startswith(SKIP_PREFIXES) or line in ("-", "*", ">") or line.startswith(("- ", "* ", "> "))
            or bool(re.match(r"\d+\.(\s|$)", line)) or bool(re.match(r"([-*_])\1{2,}$", line)))


def _first_sentence(paragraph: str) -> str:
    """The paragraph up to its first sentence end: . ? or ! then a space and a capital, not after e.g. i.e. vs."""
    for m in re.finditer(r"([.?!])\s+(?=[A-Z])", paragraph):
        if not re.search(r"\b(e\.g|i\.e|vs|etc)\.$", paragraph[: m.end(1)]):
            return paragraph[: m.end(1)].removesuffix(".")
    return paragraph.removesuffix(".")


def _plain_text(text: str) -> str:
    """Markdown links reduced to their text: a link written for its own folder would be dead in docs/INDEX.md."""
    return re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)


def summarize(text: str) -> str:
    """One-line summary of a Markdown text, or '' when it has none (see the module docstring for the rule)."""
    lines = [ln.strip() for ln in text.splitlines()]
    for line in lines[:OVERRIDE_LINES]:
        if line.startswith("summary:"):
            return _cap(_plain_text(line[len("summary:"):]))
    after_heading = in_fence = in_comment = in_block = False
    paragraph: list[str] = []
    for line in lines:
        if not after_heading:
            after_heading = line.startswith("# ")
        elif in_fence:
            in_fence = not line.startswith("```")
        elif in_comment:
            in_comment = "-->" not in line
        elif not line:
            if paragraph:
                break
            in_block = False
        elif in_block:
            continue
        elif line.startswith("```"):
            in_fence = True
        elif line.startswith("<!--"):
            in_comment = "-->" not in line
        elif _skipped(line):
            if paragraph:
                break
            in_block = True
        else:
            paragraph.append(line)
    return _cap(_first_sentence(_plain_text(" ".join(paragraph)))) if paragraph else ""


def read_summary(path: str) -> str:
    return summarize((ROOT / path).read_text(encoding="utf-8"))


def missing_summaries(paths: list[str]) -> list[str]:
    return [p for p in paths if p.endswith(".md") and not read_summary(p)]


def render(paths: list[str]) -> str:
    """The text of docs/INDEX.md for these tracked files (read from ROOT for their summaries)."""
    groups: dict[str, list[str]] = defaultdict(list)
    for path in sorted(paths):
        groups[area_of(path)].append(path)
    lines = ["# Document index", "",
             "Generated by `tools/ops/build_docs_index.py`. One row per Markdown document with its summary; "
             "other documents are listed at the end of each folder; images, css and scripts are only counted.", ""]
    for area in sorted(groups):
        members = groups[area]
        readme = f"docs/{area}/README.md"
        lines += [f"## {area}", ""]
        if readme in members and (intro := read_summary(readme)):
            lines += [intro, ""]
        for path in (p for p in members if p.endswith(".md")):
            rel = _rel(path, area)
            summary = read_summary(path)
            lines.append(f"- [{rel}]({doc_link(path)})" + (f": {summary}" if summary else ""))
        others = [p for p in members if not p.endswith(".md") and not is_asset(p)]
        if others:
            links = ", ".join(f"[{_rel(p, area)}]({doc_link(p)})" for p in others)
            lines.append(f"- Other files: {links}")
        if assets := sum(is_asset(p) for p in members):
            lines.append(f"- Plus {assets} image, css or script files")
        lines.append("")
    return "\n".join(lines)


def entries(text: str) -> list[tuple[str, str]]:
    """The (area, entry) pairs of an index text, in order and with repeats: the documents it links and its asset
    counts, not the summaries."""
    area, rows = "", []
    for line in text.splitlines():
        if line.startswith("## "):
            area = line[3:]
        elif line.startswith("- Plus "):
            rows.append((area, line))
        elif line.startswith("- Other files: "):
            rows.extend((area, link) for link in re.findall(r"\]\(([^)]*)\)", line))
        elif line.startswith("- ") and (m := re.match(r"- \[[^\]]*\]\(([^)]*)\)", line)):
            rows.append((area, m.group(1)))   # the row's own link only: a summary holds none, and its words are not compared
    return rows


def listed(text: str) -> set[tuple[str, str]]:
    return set(entries(text))


def prose(text: str) -> dict[str, int]:
    """Per area, how many prose lines (a folder README's summary) the index text holds."""
    area = ""
    count: dict[str, int] = {}
    for line in text.splitlines():
        if line.startswith("## "):
            area = line[3:]
        elif line.strip() and not line.startswith(("- ", "#")):
            count[area] = count.get(area, 0) + 1
    return count


def repeated(text: str) -> list[tuple[str, str]]:
    """Entries listed more than once. The index merges with git's union driver (.gitattributes), which keeps both
    sides' lines: two branches that changed one row leave it twice, and a set comparison alone would not see it."""
    seen, twice = set(), []
    for row in entries(text):
        if row in seen and row not in twice:
            twice.append(row)
        seen.add(row)
    return twice


def check(strict: bool = False) -> int:
    """0 when docs/INDEX.md lists exactly the documents in docs/, tracked or new, and the asset counts.

    Missing summaries are a warning, or a failure with strict. New files are named, since CI sees them only once committed.
    """
    paths = doc_files()
    if new := untracked():
        print("build_docs_index.py: note: the index counts these new docs/ files; commit them with docs/INDEX.md, "
              "or remove them and rebuild it:", file=sys.stderr)
        for path in new[:10]:
            print(f"  new: {path}", file=sys.stderr)
    index = ROOT / "docs/INDEX.md"
    text = index.read_text(encoding="utf-8") if index.is_file() else ""
    have, want = listed(text), listed(rendered := render(paths))
    status = 0
    if twice := repeated(text):
        status = 1
        print("build_docs_index.py: docs/INDEX.md lists an entry more than once (a union merge kept both sides); "
              "run python3 tools/ops/build_docs_index.py and commit it", file=sys.stderr)
        for area, row in twice[:10]:
            print(f"  twice: {area}: {row}", file=sys.stderr)
    extra = sorted(a for a, n in prose(text).items() if n > prose(rendered).get(a, 0))
    if extra:
        status = 1
        print("build_docs_index.py: docs/INDEX.md has more intro text than it should (a union merge kept both "
              "sides) under: " + ", ".join(a or "(top)" for a in extra) + "; run python3 tools/ops/build_docs_index.py "
              "and commit it", file=sys.stderr)
    if have != want:
        status = 1
        print("build_docs_index.py: docs/INDEX.md is out of date; run python3 tools/ops/build_docs_index.py and commit it", file=sys.stderr)
        for label, rows in (("missing", want - have), ("not in docs/", have - want)):
            for area, row in sorted(rows)[:10]:
                print(f"  {label}: {area}: {row}", file=sys.stderr)
            if len(rows) > 10:
                print(f"  ... and {len(rows) - 10} more {label}", file=sys.stderr)
    missing = missing_summaries(paths)
    if missing:
        word = "ERROR" if strict else "WARNING"
        print(f"build_docs_index.py: {word}: {len(missing)} Markdown documents have no summary "
              "(a plain prose line after the # heading, or a 'summary: ...' line in the first 10 lines):", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        if strict:
            status = 1
    if status == 0:
        print(f"docs/INDEX.md lists all {len(paths)} files ({len(missing)} Markdown documents without a summary)")
    return status


def main(argv: list[str]) -> int:
    if {"-h", "--help"} & set(argv):     # help wins over any other argument: it only prints
        print(__doc__ or USAGE)      # python -OO strips the docstring
        return 0
    if argv in (["--check"], ["--check", "--strict"]):
        return check(strict="--strict" in argv)
    if argv:            # a typo must not fall through to a rewrite
        bad = next((a for a in argv if a not in ("--check", "--strict")), None)
        if bad is None:
            print(f"build_docs_index.py: {' '.join(argv)!r} is not a valid combination; use --check, or --check --strict ({USAGE})", file=sys.stderr)
        else:
            print(f"build_docs_index.py: unknown argument {bad!r}; options are --check and --check --strict (--help for more)", file=sys.stderr)
        return 2
    paths = doc_files()
    (ROOT / "docs/INDEX.md").write_text(render(paths), encoding="utf-8")
    print(f"wrote docs/INDEX.md: {len(paths)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
