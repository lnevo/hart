#!/usr/bin/env python3
"""Stop or question the shell commands AGENTS.md rules out, in every session.

Blocks a push to main and any force-push from this repo. Asks first for a merge
through gh and for a track/cmd publish. Submodules keep their own rules, so
pushes from external/ pass. This is a guardrail against mistakes, not a security
boundary: it reads the command text, so a script that publishes is not seen.
"""
import json
import os
import re
import shlex
import subprocess
import sys

SPLIT = re.compile(r"&&|\|\||[;|\n]")
PUBLISH = re.compile(r"\bmosquitto_pub\b.*track/cmd|track/cmd.*\bmosquitto_pub\b", re.S)
MERGE = re.compile(r"^\s*gh\s+pr\s+merge\b")


def git(cwd, *args):
    try:
        done = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def push_args(part):
    """Return (extra -C dir, args after push), or None when this is not a push."""
    try:
        words = shlex.split(part)
    except ValueError:
        return None
    while words and re.fullmatch(r"\w+=.*", words[0]):
        words.pop(0)
    if not words or words[0] != "git":
        return None
    i, where = 1, None
    while i < len(words) and words[i].startswith("-"):
        if words[i] == "-C" and i + 1 < len(words):
            where = words[i + 1]
            i += 2
        elif words[i] == "-c":
            i += 2
        else:
            i += 1
    if i >= len(words) or words[i] != "push":
        return None
    return where, words[i + 1:]


def push_problem(cwd, where, args, project):
    target = os.path.join(cwd, where) if where else cwd
    top = git(target, "rev-parse", "--show-toplevel")
    if top and project and os.path.realpath(top) != os.path.realpath(project):
        return None
    if any(a.startswith("--force") or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", a) for a in args):
        return "force-push"
    refs = [a for a in args if not a.startswith("-")][1:]
    if any(a.startswith("+") for a in refs):
        return "force-push"
    if any(a == "--all" or a == "--mirror" for a in args):
        return "push of every branch"
    current = git(target, "symbolic-ref", "--short", "HEAD")
    if any(r.split(":")[-1] in ("main", "refs/heads/main") for r in refs):
        return "push to main"
    if current == "main" and (not refs or any(r.split(":")[-1] == "HEAD" for r in refs)):
        return "push to main"
    return None


def main():
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")
    cwd = data.get("cwd") or os.getcwd()
    project = os.environ.get("CLAUDE_PROJECT_DIR", cwd)
    ask = []
    for part in SPLIT.split(command):
        moved = re.match(r"\s*cd\s+(\S+)\s*$", part)
        if moved:
            cwd = os.path.join(cwd, os.path.expanduser(moved.group(1).strip("\"'")))
            continue
        push = push_args(part)
        if push:
            problem = push_problem(cwd, push[0], push[1], project)
            if problem:
                print(f"Blocked: {problem}. Use an agent/ branch and a PR (AGENTS.md).", file=sys.stderr)
                return 2
        if MERGE.search(part):
            ask.append("This merges a PR. AGENTS.md leaves merges to main to the owner.")
    if PUBLISH.search(command):
        ask.append("This publishes to track/cmd, which commands field turnouts.")
    if ask:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": " ".join(ask),
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
