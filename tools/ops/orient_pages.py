"""The Markdown half of tools/ops/orient.py: the Claimed line's form, and reading a project page's Status and
Claimed lines outside code fences and HTML comments (parse_page). orient.py imports it from their shared folder;
it imports nothing of the repo."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime

STATUS = re.compile(r"^Status:\s*(\S.*)$")
CLAIM = re.compile(r"^Claimed: (?P<branch>[^,\s]+), (?P<path>[^,]+?), since (?P<since>\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*$")
# Anything that looks like a Claimed line, in a list, a quote or bold, so a near miss is reported, not skipped.
CLAIM_LIKE = re.compile(r"^\s*(?:[-*+>]\s*)*(?:\*\*|__)?Claimed\s*(?::|(?:\*\*|__)\s*:)")
BRANCH = re.compile(r"^(?!/)(?!.*\.\.)(?!.*//)[A-Za-z0-9._/-]+(?<![/.])$")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
FORMAT = "Claimed: <branch>, <absolute worktree path>, since YYYY-MM-DD HH:MM"


@dataclass(frozen=True)
class Claim:
    page: str  # file name in wiki/projects/
    line: int
    branch: str
    path: str  # as written
    since: str


@dataclass
class Page:
    status: str | None  # first word of the Status line, lower case; None when the page has none
    status_line: int | None  # 1-based
    claims: list[Claim] = field(default_factory=list)
    problems: list[tuple[int, str]] = field(default_factory=list)


# ---------------------------------------------------------------- Markdown

def readable_lines(text: str):
    """Yield (line number, text) for every line outside code fences, with HTML comments cut out (a line wholly
    inside a comment yields ""). Fenced lines are not yielded, so callers judge adjacency by line number."""
    fence: str | None = None
    in_comment = False
    for no, line in enumerate(text.splitlines(), 1):
        if fence:
            m = FENCE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and \
                    not line.strip()[len(m.group(1)):].strip():
                fence = None
            continue
        if not in_comment:
            m = FENCE.match(line)
            if m:
                fence = m.group(1)
                continue
        out, rest = "", line
        while rest:
            if in_comment:
                end = rest.find("-->")
                rest, in_comment = ("", True) if end < 0 else (rest[end + 3:], False)
            else:
                start = comment_start(rest)
                if start < 0:
                    out, rest = out + rest, ""
                else:
                    out, rest, in_comment = out + rest[:start], rest[start + 4:], True
        yield no, out


CODE_SPAN = re.compile(r"(`+)(?:.*?[^`])?\1(?!`)")


def comment_start(text: str) -> int:
    """Where an HTML comment opens in text, or -1; a `<!--` inside a backtick code span does not count."""
    pos = 0
    while True:
        start = text.find("<!--", pos)
        tick = text.find("`", pos)
        if start < 0 or tick < 0 or start < tick:
            return start
        span = CODE_SPAN.match(text, tick)
        if span is None:  # an unclosed backtick run is literal text
            pos = tick + len(re.match(r"`+", text[tick:]).group(0))
        else:
            pos = span.end()


def parse_page(name: str, text: str) -> Page:
    """The page's Status and its Claimed lines, with a problem for each Claimed line that is malformed or not
    directly under the Status line, and for claims on a page that is not active."""
    lines = list(readable_lines(text))
    page = Page(None, None)
    under = set()  # line numbers directly under the Status line (the run of Claimed lines that follows it)
    for i, (no, line) in enumerate(lines):
        m = STATUS.match(line)
        if m and page.status is None:
            page.status, page.status_line = m.group(1).split()[0].lower(), no
            j = i + 1
            while j < len(lines) and lines[j][0] == lines[j - 1][0] + 1 and CLAIM_LIKE.match(lines[j][1]):
                under.add(lines[j][0])
                j += 1
    for no, line in lines:
        if not CLAIM_LIKE.match(line):
            continue
        if no not in under:
            page.problems.append((no, "Claimed line not directly under the Status line"))
            continue
        m = CLAIM.match(line)
        if not m:
            page.problems.append((no, f"malformed Claimed line; the form is: {FORMAT}"))
            continue
        problem = claim_problem(m.group("branch"), m.group("path"), m.group("since"))
        if problem:
            page.problems.append((no, problem))
            continue
        page.claims.append(Claim(name, no, m.group("branch"), m.group("path"), m.group("since")))
    if page.claims and page.status != "active":
        page.problems.append((page.status_line or 0, f"claimed, but the page's Status is {page.status or 'missing'}, "
                                                     "not active"))
    return page


def claim_problem(branch: str, path: str, since: str) -> str | None:
    """Why a parsed claim is not valid, or None."""
    if not BRANCH.match(branch):
        return f"claim names an invalid branch {branch!r}"
    if not os.path.isabs(path):
        return f"claim's worktree path {path!r} is not absolute"
    try:
        datetime.strptime(since, "%Y-%m-%d %H:%M")
    except ValueError:
        return f"claim's time {since!r} is not a real date and time"
    return None
