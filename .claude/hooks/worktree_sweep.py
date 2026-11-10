#!/usr/bin/env python3
"""Remove agent worktrees whose PR is merged: at session start and after `gh pr merge`.

Calls tools/agent/worktrees.py sweep, keeping the worktree the session is in. A merge done
on GitHub is caught at the next session start. Never blocks: any failure exits 0 quietly.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MERGE = re.compile(r"(^|[;&|\n]\s*)gh\s+pr\s+merge\b")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    event = data.get("hook_event_name", "")
    if event == "PostToolUse" and not MERGE.search(data.get("tool_input", {}).get("command", "")):
        return 0
    cwd = data.get("cwd") or os.getcwd()
    project = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    script = Path(project) / "tools" / "agent" / "worktrees.py"
    if not script.exists():
        return 0
    try:
        done = subprocess.run([sys.executable, str(script), "sweep", "--keep", cwd],
                              capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.SubprocessError):
        return 0
    lines = [l for l in done.stdout.splitlines() if l.startswith(("removed", "kept"))]
    if lines and event in ("PostToolUse", "SessionStart"):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": "Worktree sweep:\n" + "\n".join(lines),
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
