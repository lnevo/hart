#!/usr/bin/env python3
"""Remove agent worktrees whose PR is merged: at session start and after `gh pr merge`.

Calls tools/agent/worktrees.py sweep, keeping the session's working and project directories. A merge done
on GitHub is caught at the next session start. The sweep also covers the worktrees of the checked-out submodules
(agent/* branches only). The sweep runs under TIMEOUT (keep it below the hook's own 60 s in
.claude/settings.json); no removal starts and no submodule is looked at after BUDGET, which leaves each removal TIMEOUT - BUDGET seconds, so a long
backlog waits for the next sweep, or `make wt-sweep`, instead of being cut off mid-delete. At session start it
also sets the pipeline map's git merge drivers (tools/ops/merge_pipeline_map.py --install, silent once set; a
failure is shown in the session context). Never blocks: any failure exits 0.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TIMEOUT = 45  # seconds for the whole sweep
BUDGET = TIMEOUT - 25  # no removal starts after this many seconds of removing
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
        done = subprocess.run([sys.executable, str(script), "sweep", "--keep", cwd, "--keep", project, "--budget", str(BUDGET)],
                              capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return 0
    lines = [l for l in done.stdout.splitlines() if l.startswith(("removed", "kept", "left"))]
    context = ["Worktree sweep:", *lines] if lines else []
    if event == "SessionStart":
        context += merge_drivers(project)
    if context and event in ("PostToolUse", "SessionStart"):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": "\n".join(context),
        }}))
    return 0


def merge_drivers(project: str) -> list[str]:
    """Set the repo's git merge drivers (tools/ops/merge_pipeline_map.py --install; git config is shared by every
    worktree, so a no-op once set). Return the lines to show: what it changed, or why it failed; none when set."""
    script = Path(project) / "tools" / "ops" / "merge_pipeline_map.py"
    if not script.exists():  # a checkout from before the driver: nothing to set
        return []
    try:
        done = subprocess.run([sys.executable, str(script), "--install", "--repo", project],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as err:
        return [f"Merge drivers not set ({err}); run python3 tools/ops/merge_pipeline_map.py --install"]
    if done.returncode != 0:
        return [f"Merge drivers not set: {done.stderr.strip()}; run python3 tools/ops/merge_pipeline_map.py --install"]
    return ["Merge drivers:", *done.stdout.splitlines()] if done.stdout.strip() else []


if __name__ == "__main__":
    sys.exit(main())
