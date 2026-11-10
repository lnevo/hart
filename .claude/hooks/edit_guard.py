#!/usr/bin/env python3
"""Block Edit/Write in the main checkout: agents edit in their own worktree (AGENTS.md).

The main checkout stays on main for pulls and deploys; another session's half-done edit
there ends up in someone else's commit. Gitignored files (local settings, mirrors) pass,
and so does anything outside a repo that uses agent worktrees. Uses main_guard's test.
"""
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_guard():
    spec = importlib.util.spec_from_file_location("hart_main_guard_for_edits", os.path.join(HERE, "main_guard.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lexical_top(path):
    """The checkout holding `path` as written, without following symlinks: a worktree's
    mirror links (media/, ops/car-cards/) belong to the worktree, not to the main checkout."""
    folder = os.path.dirname(path)
    while folder and folder != os.path.dirname(folder):
        if os.path.lexists(os.path.join(folder, ".git")):
            return folder
        folder = os.path.dirname(folder)
    return None


def main():
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path:
        return 0
    path = os.path.normpath(os.path.join(data.get("cwd") or os.getcwd(), os.path.expanduser(path)))
    top = lexical_top(path)
    if not top or not os.path.isdir(os.path.join(top, ".git")):
        return 0  # outside a repo, or in a worktree (whose .git is a file)
    guard = load_guard()
    if not guard.main_checkout(top):
        return 0
    rel = os.path.relpath(path, top)
    ignored = subprocess.run(["git", "-C", top, "check-ignore", "-q", "--no-index", rel],
                             capture_output=True).returncode == 0
    if ignored:
        return 0
    print(f"Blocked: {path} is in the main checkout, which stays on main. Edit in your own worktree: "
          f"{guard.NEW_WORKTREE}, then work on the same path under .claude/worktrees/<topic>/ (AGENTS.md).",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
