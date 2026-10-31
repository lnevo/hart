#!/usr/bin/env python3
"""Fail if agent instructions point at a repo path that does not exist.

Covers the files agents load first, so a move or retirement cannot leave them
stale. Checks relative Markdown links and backticked paths under a known root.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = ("AGENTS.md", "*/AGENTS.md", ".cursor/*", ".claude/*", "wiki/home.md",
            "wiki/AGENTS_GIT.md", "docs/AI_CONTEXT.md")
EXCLUDED = ("external/",)
ROOTS = ("jmri", "cats", "docs", "www", "ops", "tools", "wiki", "archive", ".cursor", ".claude")
LINK = re.compile(r"\]\(([^)#\s]+)")
CODE = re.compile(r"`([^`\s]+)`")


def agent_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z", *PATTERNS], cwd=ROOT, text=True)
    return [p for p in out.split("\0") if p and not p.startswith(EXCLUDED)]


def is_ignored(token: str) -> bool:
    """Gitignored data is absent from a clean clone, so a missing path is fine."""
    return subprocess.run(["git", "check-ignore", "-q", token], cwd=ROOT).returncode == 0


def is_repo_path(token: str) -> bool:
    return "/" in token and token.split("/")[0] in ROOTS and not re.search(r"[<>*{}$|]", token)


def problems_in(rel: str) -> list[str]:
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    found = []
    for target in LINK.findall(text):
        if "://" not in target and not target.startswith("mailto:"):
            if not (path.parent / target).exists():
                found.append(f"{rel}: broken link {target}")
    for token in CODE.findall(text):
        token = token.rstrip("/")
        if is_repo_path(token) and not (ROOT / token).exists() and not is_ignored(token):
            found.append(f"{rel}: missing path {token}")
    return found


def main() -> int:
    problems = [p for rel in agent_files() for p in problems_in(rel)]
    for line in problems:
        print(f"FAIL {line}")
    if not problems:
        print("OK: agent instructions point at real paths")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
