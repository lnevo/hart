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


def main():
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path:
        return 0
    path = os.path.abspath(os.path.join(data.get("cwd") or os.getcwd(), os.path.expanduser(path)))
    folder = os.path.dirname(path)
    while folder and not os.path.isdir(folder):
        folder = os.path.dirname(folder)
    guard = load_guard()
    if not folder or not guard.main_checkout(folder):
        return 0
    ignored = subprocess.run(["git", "-C", folder, "check-ignore", "-q", path], capture_output=True).returncode == 0
    if ignored:
        return 0
    print(f"Blocked: {path} is in the main checkout, which stays on main. Edit in your own worktree: "
          f"{guard.NEW_WORKTREE}, then work on the same path under .claude/worktrees/<topic>/ (AGENTS.md).",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
