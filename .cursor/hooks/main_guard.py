#!/usr/bin/env python3
"""Cursor beforeShellExecution hook: the same rules as the Claude Code guard.

Loads `.claude/hooks/main_guard.py`, which holds the rules (no commit or push on main,
no force-push, no admin merge, ask before a track/cmd publish), runs it in this
process on the command text, and turns its answer into Cursor's reply: exit 2
becomes deny, an "ask" becomes ask, anything else allows. One rule set, two tools.
Like the Claude guard, it only reads the command; it never runs it.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / ".claude/hooks/main_guard.py"


def load_guard():
    spec = importlib.util.spec_from_file_location("hart_main_guard", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decide(data: dict) -> dict:
    """Cursor's input ({command, cwd, workspace_roots}) in, Cursor's reply out."""
    cwd = data.get("cwd") or os.getcwd()
    project = os.environ.get("CURSOR_PROJECT_DIR") or (data.get("workspace_roots") or [str(ROOT)])[0]
    payload = json.dumps({"tool_input": {"command": data.get("command", "")}, "cwd": cwd})
    out, err = io.StringIO(), io.StringIO()
    saved_stdin, saved_env = sys.stdin, os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = project
    try:
        sys.stdin = io.StringIO(payload)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = load_guard().main()
    finally:
        sys.stdin = saved_stdin
        if saved_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = saved_env
    if code == 2:
        why = err.getvalue().strip() or "Blocked by the repo guard (AGENTS.md)."
        return {"permission": "deny", "user_message": why, "agent_message": why}
    try:
        answer = json.loads(out.getvalue() or "{}").get("hookSpecificOutput", {})
    except json.JSONDecodeError:
        answer = {}
    if answer.get("permissionDecision") == "ask":
        why = answer.get("permissionDecisionReason", "")
        return {"permission": "ask", "user_message": why, "agent_message": why}
    return {"permission": "allow"}


def main() -> int:
    print(json.dumps(decide(json.load(sys.stdin))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
