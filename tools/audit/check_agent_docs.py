#!/usr/bin/env python3
"""Fail if agent instructions point at a repo path that does not exist.

Covers the files agents load first, so a move or retirement cannot leave them
stale. Checks relative Markdown links and backticked paths under a known root.

`references()` is the one parser for what an agent doc points at; the pipeline
map (tools/ops/agent_docs_map.py) draws its "points to" links from it too.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import NamedTuple
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = ("AGENTS.md", "*/AGENTS.md", ".cursor/*", ".claude/*", "wiki/home.md",
            "wiki/AGENTS_GIT.md")
EXCLUDED = ("external/",)
ROOTS = ("jmri", "cats", "docs", "www", "ops", "tools", "wiki", "archive", ".cursor", ".claude")
# A Markdown link target: <in angle brackets> (may hold spaces) or a bare target up to a space, ")" or "#".
LINK = re.compile(r"\]\(\s*(?:<(?P<angled>[^>#]*)[^>]*>|(?P<bare>[^)#\s]+))")
CODE = re.compile(r"`([^`\s]+)`")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


class AgentDocsError(Exception):
    pass


class Ref(NamedTuple):
    """One thing a doc points at. `target` is the repo-relative path it names, `..` and `./` resolved but symlinks
    not followed (a mirror stays under its own name); None for a link that leaves the repo."""
    kind: str      # "link" (a Markdown link, read from the linking file's folder) or "code" (a backticked token)
    raw: str
    target: str | None


def _git(*args: str) -> list[str]:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as err:
        detail = getattr(err, "stderr", "") or str(err)
        raise AgentDocsError(f"git {' '.join(args)} failed in {ROOT}: {detail.strip()}") from None
    return [p for p in out.split("\0") if p]


def agent_files() -> list[str]:
    return [p for p in _git("ls-files", "-z", *PATTERNS) if not p.startswith(EXCLUDED)]


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


def main() -> int:
    try:
        problems = [p for rel in agent_files() for p in problems_in(rel)]
    except AgentDocsError as err:
        print(f"FAIL {err}")
        return 1
    for line in problems:
        print(f"FAIL {line}")
    if not problems:
        print("OK: agent instructions point at real paths")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
