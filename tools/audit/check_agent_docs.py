#!/usr/bin/env python3
"""Fail if agent instructions point at a repo path that does not exist, or a wiki table cell runs too long.

Covers the files agents load first, so a move or retirement cannot leave them
stale. Checks relative Markdown links and backticked paths under a known root.
A second rule keeps wiki/ and AGENTS.md tables readable: a table cell over MAX_CELL_WORDS words fails, naming file,
line and count (wiki/STATUS_LOG.md and wiki/archive/ hold history and are exempt). Long detail goes in a section
below the table, linked from the cell.
A third rule caps the root AGENTS.md, which every session loads whole: over MAX_ROOT_LINES lines or MAX_ROOT_WORDS
words fails. Detail goes in a skill, /done, or the AGENTS.md of the folder it applies to.
A fourth rule caps each .claude/skills/*/SKILL.md at MAX_SKILL_WORDS words, counted as the AGENTS.md cap counts them
(whitespace-separated, frontmatter included). Detail goes in a reference file the skill links to.

`references()` is the one parser for what an agent doc points at; the pipeline
map (tools/ops/agent_docs_map.py) draws its "points to" links from it too.
"""
from __future__ import annotations

import os
import posixpath
import re
import subprocess
import sys
from typing import NamedTuple
from pathlib import Path, PurePosixPath

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib.files import GitError, tracked_files  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
# The tracked files it reads, as git globs (** crosses folders, * does not): the agent docs (PATTERNS, less EXCLUDED)
# and the Markdown files the cell rule covers (CELL_GLOBS, less the exempt history). The step's quiet_inputs in
# tools/pipeline/checks.toml are these (tools/audit/tests/test_manifest_scans.py).
PATTERNS = ("**/AGENTS.md", ".cursor/**", ".claude/**", "wiki/home.md", "wiki/AGENTS_GIT.md")
EXCLUDED = ("external/",)
ROOTS = ("jmri", "cats", "docs", "www", "ops", "tools", "wiki", "archive", ".cursor", ".claude")
# A Markdown link target: <in angle brackets> (may hold spaces) or a bare target up to a space, ")" or "#".
LINK = re.compile(r"\]\(\s*(?:<(?P<angled>[^>#]*)[^>]*>|(?P<bare>[^)#\s]+))")
CODE = re.compile(r"`([^`\s]+)`")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
MAX_CELL_WORDS = 80
ROOT_DOC = "AGENTS.md"
MAX_ROOT_LINES = 70
MAX_ROOT_WORDS = 1000
SKILL_GLOB = ".claude/skills/*/SKILL.md"
MAX_SKILL_WORDS = 1500
CELL_GLOBS = ("wiki/**/*.md", "AGENTS.md")
SCAN_GLOBS = (*PATTERNS, CELL_GLOBS[0])         # CELL_GLOBS' AGENTS.md is one of PATTERNS' **/AGENTS.md
CELL_EXEMPT_FILES = ("wiki/STATUS_LOG.md",)
CELL_EXEMPT_DIRS = ("wiki/archive/",)
FENCE = re.compile(r"^\s*(?P<run>`{3,}(?=[^`]*$)|~{3,})(?P<info>.*)$")   # a backtick fence has no backtick after it
BR = re.compile(r"<br\s*/?>", re.I)
DELIMITER_ROW = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


class AgentDocsError(Exception):
    pass


class Ref(NamedTuple):
    """One thing a doc points at. `target` is the repo-relative path it names, `..` and `./` resolved but symlinks
    not followed (a mirror stays under its own name); None for a link that leaves the repo."""
    kind: str      # "link" (a Markdown link, read from the linking file's folder) or "code" (a backticked token)
    raw: str
    target: str | None


def _git(*args: str) -> list[str]:
    """A NUL-separated git listing (ls-files --others, which tracked_files does not cover); AgentDocsError on failure."""
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as err:
        detail = getattr(err, "stderr", "") or str(err)
        raise AgentDocsError(f"git {' '.join(args)} failed in {ROOT}: {detail.strip()}") from err
    return [p for p in out.split("\0") if p]


def _tracked(*pathspecs: str) -> list[str]:
    """The tracked files matching `pathspecs` (hartlib.files.tracked_files); AgentDocsError when git cannot list them."""
    try:
        return tracked_files(ROOT, *pathspecs)
    except GitError as err:
        raise AgentDocsError(str(err)) from err


def agent_files() -> list[str]:
    return [p for p in _tracked(*globs(PATTERNS)) if not p.startswith(EXCLUDED)]


def globs(patterns: tuple[str, ...]) -> list[str]:
    """Repo globs as git pathspecs with the glob magic, so * stays inside one folder as in the step manifest."""
    return [f":(glob){g}" for g in patterns]


def is_ignored(token: str) -> bool:
    """Gitignored data is absent from a clean clone, so a missing path is fine."""
    return subprocess.run(["git", "check-ignore", "-q", token], cwd=ROOT).returncode == 0


def is_repo_path(token: str) -> bool:
    return "/" in token and token.split("/")[0] in ROOTS and not re.search(r"[<>*{}$|]", token)


def _normal(path: str) -> str | None:
    """The repo-relative form of a path written from the repo root ("." for the root itself), or None when it climbs
    out: an absolute path or one that starts with "..". """
    norm = os.path.normpath(path)
    if PurePosixPath(norm).is_absolute() or norm.split("/")[0] == "..":
        return None
    return norm


def references(rel: str, text: str) -> list[Ref]:
    """What the doc at repo path `rel` (whose content is `text`) points at, in reading order. HTML comments are not
    read. Links to a web address, mailto: or an anchor in the same page are left out."""
    text = HTML_COMMENT.sub("", text)
    here = PurePosixPath(rel).parent
    found = []
    for m in LINK.finditer(text):
        target = (m["angled"] if m["angled"] is not None else m["bare"]).strip()
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        found.append(Ref("link", target, None if target.startswith("/") else _normal(str(here / target))))
    for token in CODE.findall(text):
        token = token.rstrip("/")
        found.append(Ref("code", token, _normal(token.removeprefix("./")) if token.removeprefix("./") else None))
    return found


def problems_in(rel: str, text: str | None = None) -> list[str]:
    """What is wrong with the paths the doc at repo path `rel` names; `text` stands in for its content in tests."""
    text = (ROOT / rel).read_text(encoding="utf-8") if text is None else text
    found = []
    for ref in references(rel, text):
        if ref.kind == "link":
            if ref.target is None:
                found.append(f"{rel}: link {ref.raw} leaves the repo")
            elif not (ROOT / ref.target).exists():
                found.append(f"{rel}: broken link {ref.raw}")
        elif ref.target is None and is_repo_path(ref.raw.removeprefix("./")):
            found.append(f"{rel}: path {ref.raw} leaves the repo")
        elif ref.target and is_repo_path(ref.target) and not (ROOT / ref.target).exists() \
                and not is_ignored(ref.target):
            found.append(f"{rel}: missing path {ref.target}")
    return found


def _code_span_end(line: str, i: int) -> int:
    """Where the backtick run at line[i] ends as code: just past the closing run of the same length, or past the
    opening run alone when nothing closes it (then the backticks are plain text)."""
    n = 1
    while i + n < len(line) and line[i + n] == "`":
        n += 1
    j = i + n
    while j < len(line):
        if line[j] != "`":
            j += 1
            continue
        m = 1
        while j + m < len(line) and line[j + m] == "`":
            m += 1
        if m == n:
            return j + m
        j += m
    return i + n


def _without_comments(line: str, in_comment: bool) -> tuple[str, bool]:
    """`line` with HTML comments cut out (code spans are not read for them), and whether one is still open."""
    out: list[str] = []
    i = 0
    while i < len(line):
        if in_comment:
            end = line.find("-->", i)
            if end < 0:
                return "".join(out), True
            i, in_comment = end + 3, False
        elif line[i] == "`":
            end = _code_span_end(line, i)
            out.append(line[i:end])
            i = end
        elif line.startswith("<!--", i):
            in_comment = True
            i += 4
        else:
            out.append(line[i])
            i += 1
    return "".join(out), in_comment


def split_cells(row: str) -> list[str]:
    """The cells of one table row. A `|` splits unless written `\\|` or inside an inline code span; the row's
    outer pipes make no empty cells."""
    cells, cur, i = [], [], 0
    while i < len(row):
        ch = row[i]
        if ch == "\\" and row[i + 1:i + 2] == "|":
            cur.append("\\|")
            i += 2
        elif ch == "`":
            end = _code_span_end(row, i)
            cur.append(row[i:end])
            i = end
        elif ch == "|":
            cells.append("".join(cur))
            cur = []
            i += 1
        else:
            cur.append(ch)
            i += 1
    cells.append("".join(cur))
    body = row.strip()
    if body.startswith("|") and cells:
        cells = cells[1:]
    if body.endswith("|") and not body.endswith("\\|") and cells:
        cells = cells[:-1]
    return cells


def cell_word_counts(rel: str, text: str) -> list[tuple[int, int, int]]:
    """(line, column, words) for every table cell in the Markdown `text` of `rel`, 1-based. Code fences and HTML
    comments are not read. A table is a header row, a delimiter row (`|---|---|`) and the rows after it up to a
    line with no pipe. An unclosed code fence or comment is an error, not a silent skip of the rest of the file."""
    lines = text.split("\n")
    clean: list[str] = []
    fence: tuple[str, int, int] | None = None   # (character, length, line it opened on)
    comment_from = 0                            # line a still-open comment began on, 0 when none
    for no, raw in enumerate(lines, 1):
        if fence:
            m = FENCE.match(raw)
            if m and m["run"][0] == fence[0] and len(m["run"]) >= fence[1] and not m["info"].strip():
                fence = None
            clean.append("")
            continue
        was_open = bool(comment_from)
        line, open_now = _without_comments(raw, bool(comment_from))
        comment_from = (comment_from or no) if open_now else 0
        m = None if was_open else FENCE.match(line)
        if m:
            fence = (m["run"][0], len(m["run"]), no)
            line = ""
        clean.append(line)
    if fence:
        raise AgentDocsError(f"{rel}:{fence[2]}: code fence never closed")
    if comment_from:
        raise AgentDocsError(f"{rel}:{comment_from}: HTML comment never closed")
    found = []
    no = 0
    while no < len(clean) - 1:
        head, delim = clean[no], clean[no + 1]
        if "|" in head and "|" in delim and DELIMITER_ROW.match(delim) and len(split_cells(head)) == len(split_cells(delim)):
            row = no
            while row < len(clean) and clean[row].strip() and "|" in clean[row]:
                if row != no + 1:
                    for col, cell in enumerate(split_cells(clean[row]), 1):
                        found.append((row + 1, col, len(BR.sub(" ", cell).split())))
                row += 1
            no = row
        else:
            no += 1
    return found


def cell_files() -> list[str]:
    """The tracked Markdown files the cell-length rule covers: all of wiki/ and AGENTS.md, minus the history."""
    # a file git still lists but the working tree no longer has (deleted, not yet staged) has nothing to read
    return [p for p in _tracked(*globs(CELL_GLOBS))
            if not is_cell_exempt(p) and (ROOT / p).exists()]


def is_cell_exempt(rel: str) -> bool:
    norm = posixpath.normpath(rel)      # repo paths use /; os.path would turn them into \ on Windows
    return norm in CELL_EXEMPT_FILES or norm.startswith(CELL_EXEMPT_DIRS)


def long_cells(rel: str, text: str | None = None) -> list[str]:
    """One message per table cell of `rel` over MAX_CELL_WORDS words; `text` stands in for its content in tests.
    A file under an exempt path has none."""
    if is_cell_exempt(rel):
        return []
    if text is None:
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as err:
            raise AgentDocsError(f"{rel}: cannot read: {err}") from err
    try:
        counted = cell_word_counts(rel, text)
    except AgentDocsError as err:     # one malformed page is a problem to list, the other files are still read
        return [str(err)]
    return [f"{rel}:{line}: table cell {col} has {words} words (limit {MAX_CELL_WORDS}); move the detail to a "
            f"section below the table and link it" for line, col, words in counted if words > MAX_CELL_WORDS]


def root_size(text: str | None = None) -> list[str]:
    """The root AGENTS.md over its line or word cap, as FAIL lines; [] when it fits."""
    if text is None:
        text = (ROOT / ROOT_DOC).read_text(encoding="utf-8")
    lines, words = len(text.splitlines()), len(text.split())
    out = []
    if lines > MAX_ROOT_LINES:
        out.append(f"{ROOT_DOC}: {lines} lines, over {MAX_ROOT_LINES}; move detail to a skill, /done or a folder AGENTS.md")
    if words > MAX_ROOT_WORDS:
        out.append(f"{ROOT_DOC}: {words} words, over {MAX_ROOT_WORDS}; move detail to a skill, /done or a folder AGENTS.md")
    return out


def skill_files() -> list[str]:
    """The tracked skill files the skill word cap covers, those still in the working tree."""
    return [p for p in _tracked(*globs((SKILL_GLOB,))) if (ROOT / p).exists()]


def skill_size(rel: str, text: str | None = None) -> list[str]:
    """The skill at repo path `rel` over MAX_SKILL_WORDS words, as one FAIL line; [] when it fits. Words are counted
    as root_size counts them, frontmatter included. `text` stands in for its content in tests."""
    if text is None:
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as err:
            raise AgentDocsError(f"{rel}: cannot read: {err}") from err
    words = len(text.split())
    if words <= MAX_SKILL_WORDS:
        return []
    return [f"{rel}: {words} words, over {MAX_SKILL_WORDS}; move detail into a reference file in the skill's folder "
            f"and link it from SKILL.md"]


def main() -> int:
    try:
        problems = [p for rel in agent_files() for p in problems_in(rel)]
        problems += [p for rel in cell_files() for p in long_cells(rel)]
        problems += root_size()
        problems += [p for rel in skill_files() for p in skill_size(rel)]
    except AgentDocsError as err:
        print(f"FAIL {err}")
        return 1
    for line in problems:
        print(f"FAIL {line}")
    if not problems:
        print("OK: agent instructions point at real paths; no wiki table cell over "
              f"{MAX_CELL_WORDS} words; {ROOT_DOC} within {MAX_ROOT_LINES} lines and {MAX_ROOT_WORDS} words; "
              f"each skill within {MAX_SKILL_WORDS} words")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
