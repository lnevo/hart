#!/usr/bin/env python3
"""Say whether a change needs the full checks, or only the quick docs checks (tools/ci/docs_checks.sh).

    git diff --name-only A B | changed_kind.py    print "docs" or "full" for the paths on stdin (CI)
    changed_kind.py --git [--base origin/main]     the same for this checkout's changes (tools/check.sh): print
                                                   "docs: <why>", "full: <why>" or "unknown: <why>"

"docs" only when every path is prose that the quick docs checks cover. Anything else, and an empty list, is "full".
The paths are repo-relative with "/" separators (git diff --name-only).

With --git the paths are the branch against its merge base with --base, plus uncommitted and untracked files, read
the way the portal job reads them (tools/audit/portal_inputs.changed_files). "unknown" means git could not say what
changed (no merge base: a shallow clone, no origin/main); the caller runs the full checks and prints the reason.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "audit"))
from portal_inputs import ChangedFilesError, changed_files  # noqa: E402

# Rules for agents: tools/audit/check_agent_docs.py reads these and the rest of check.sh follows from them.
AGENT_FILES = {"AGENTS.md", "CLAUDE.md"}
# Generated from the repo and compared by tests that only the full run executes.
GENERATED = ("docs/pipeline-map/",)


def is_docs(path: str) -> bool:
    path = path.strip().removeprefix("./")
    # git quotes a path with odd bytes (non-ASCII, quotes) in double quotes: not a plain name, so full
    if not path or path.startswith('"'):
        return False
    # a ".." or "." segment could step out of the folders checked below: not a plain repo path, so full
    if any(part in ("", ".", "..") for part in path.split("/")):
        return False
    if path.startswith(".claude/") or path.split("/")[-1] in AGENT_FILES:
        return False
    if path.startswith(GENERATED):
        return False
    return path.endswith(".md")


def kind(paths: list[str]) -> str:
    paths = [p for p in paths if p.strip()]
    return "docs" if paths and all(is_docs(p) for p in paths) else "full"


def describe(paths: list[str]) -> str:
    """The verdict for paths with its reason: "docs: ..." or "full: ..."."""
    paths = [p for p in paths if p.strip()]
    if not paths:
        return "full: no changed paths"
    if kind(paths) == "docs":
        return f"docs: {len(paths)} changed path{'s' if len(paths) != 1 else ''}, all Markdown docs"
    others = [p for p in paths if not is_docs(p)]
    more = f" and {len(others) - 1} more" if len(others) > 1 else ""
    return f"full: {others[0]} is not docs{more}"


def checkout_verdict(root: Path, base: str) -> str:
    try:
        paths = changed_files(root, base)
    except ChangedFilesError as e:
        return f"unknown: {e}"
    return describe(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--git", action="store_true", help="read this checkout's changes from git, not stdin")
    parser.add_argument("--base", help="with --git: the branch to diff against (default origin/main)")
    args = parser.parse_args(argv)
    if args.base is not None and not args.git:
        parser.error("--base goes with --git")
    if args.git:
        base = args.base if args.base is not None else "origin/main"
        if not base.strip() or base.startswith("-"):
            parser.error(f"--base must name a branch or commit, not {base!r}")
        print(checkout_verdict(ROOT, base))
    else:
        print(kind(sys.stdin.read().splitlines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
