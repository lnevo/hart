#!/usr/bin/env python3
"""Say whether a change needs the full checks: reads changed paths on stdin, prints "docs" or "full".

"docs" only when every path is prose that the quick docs checks in .github/workflows/check.yml cover. Anything else,
and an empty list, is "full". The paths are repo-relative with "/" separators (git diff --name-only).
"""
from __future__ import annotations

import sys

# Rules for agents: tools/audit/check_agent_docs.py reads these and the rest of check.sh follows from them.
AGENT_FILES = {"AGENTS.md", "CLAUDE.md"}
# Generated from the repo and compared by tests that only the full run executes.
GENERATED = ("docs/pipeline-map/",)


def is_docs(path: str) -> bool:
    path = path.strip().removeprefix("./")
    # git quotes a path with odd bytes (non-ASCII, quotes) in double quotes: not a plain name, so full
    if not path or path.startswith('"'):
        return False
    if path.startswith(".claude/") or path.split("/")[-1] in AGENT_FILES:
        return False
    if path.startswith(GENERATED):
        return False
    return path.endswith(".md")


def kind(paths: list[str]) -> str:
    paths = [p for p in paths if p.strip()]
    return "docs" if paths and all(is_docs(p) for p in paths) else "full"


def main() -> int:
    print(kind(sys.stdin.read().splitlines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
