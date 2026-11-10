#!/usr/bin/env python3
"""Stop or question the shell commands AGENTS.md rules out, in every session.

Blocks a commit on main, a push to main, any force-push from this repo and an
admin merge, which would skip the required check. Asks first for a track/cmd
publish. Other merges through gh pass: the owner lets agents merge a PR once its
required check is green, and GitHub refuses it otherwise. Submodules keep their own rules, so
pushes from external/ pass.

Two more rules. While PanelPro, DecoderPro, DispatcherPro or CATS runs on this machine it
blocks the commands that write the JMRI tables or deploy (make tables-pull, ops-pull,
deploy-layout and deploy-all, pull_tables.sh, sync_hart_package.sh and the table-writing
scripts in TABLE_WRITERS); make panelpro-test and --check/--dry-run runs pass. And it
blocks a git commit, gh pr create/edit or gh issue create whose command text, or -F /
--body-file file, holds the railroad's private name (checked by hash, never spelled out).
HART_GUARD_JMRI_RUNNING=1 or 0 overrides the process check, for tests.

This is a guardrail against mistakes, not a security boundary: it reads the command text,
so a script that publishes is not seen.
"""
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys

SPLIT = re.compile(r"&&|\|\||[;|\n]")
PUBLISH = re.compile(r"\bmosquitto_pub\b.*track/cmd|track/cmd.*\bmosquitto_pub\b", re.S)
MERGE = re.compile(r"^\s*gh\s+pr\s+merge\b")
PROCESS = r"java .*(cats\.apps\.Crandic|apps\.PanelPro\.PanelPro|apps\.DecoderPro|apps\.DispatcherPro)"
PUBLISHING = re.compile(r"^\s*(gh\s+pr\s+(create|edit)|gh\s+issue\s+create)\b")
GIT_COMMIT = re.compile(r"^\s*git\s+(-\S+\s+)*commit\b")  # for a part shlex cannot split
FILE_FLAGS =("-F", "--file", "--body-file")

# make targets and scripts that write tables.xml, ~/JMRI_UserFiles or the hosts' copies.
MAKE_TARGETS = {"tables-pull", "ops-pull", "deploy-layout", "deploy-all"}  # not deploy-site
WRITERS = {"pull_tables.sh", "pull_ops.sh", "sync_hart_package.sh"}
TABLE_WRITERS = {
    "add_digicon_le_signal_icons.py", "add_yard_ladder_le_icons.py", "annotate_mqtt_sensors_and_dispatcher.py",
    "apply_blocks_to_panel.py", "apply_le_cleanup.py", "apply_le_sml_facing.py", "apply_nx_layer.py",
    "apply_sml_cats_pairs.py", "apply_yard_throat_blocks.py", "disable_digicon_sml_in_tables.py",
    "fix_traininfo_detection.py", "gen_ctc_track_plan.py", "patch_ctc_locking.py",
    "polish_hart_layout_editor.py", "reconcile_dispatcher_stations.py", "refresh_bean_comments.py",
    "retarget_dispatcher_traininfo_transits.py",
}
APPLY_ONLY = {  # dry-run unless given --apply
    "apply_public_names.py", "apply_public_names_tree.py", "cleanup_uss_ctc_leftovers.py", "uss_switch_only_columns.py",
}
SAFE_FLAGS = {"--check", "--dry-run", "-n", "--help", "-h"}
BRANCHED = re.compile(r"^\s*git\s+(checkout\s+(-q\s+)?-[bB]|switch\s+(-q\s+)?-[cC])\s+\S+")


def git(cwd, *args):
    try:
        done = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def jmri_running():
    """True when PanelPro, DecoderPro, DispatcherPro or CATS runs for this user."""
    forced = os.environ.get("HART_GUARD_JMRI_RUNNING")
    if forced in ("0", "1"):
        return forced == "1"
    try:
        done = subprocess.run(["pgrep", "-u", str(os.getuid()), "-f", PROCESS], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def contains_private_name(text):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../ops/hart-ops/card_pipeline/private_name.py")
    try:
        spec = importlib.util.spec_from_file_location("hart_private_name", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, AttributeError):
        return False
    return module.contains_private_name(text)


def table_writer(part):
    """Name the table-writing or deploying command in `part`, or None."""
    try:
        words = shlex.split(part)
    except ValueError:
        return None
    while words and re.fullmatch(r"\w+=.*", words[0]):
        words.pop(0)
    if not words:
        return None
    if os.path.basename(words[0]) == "make":
        hit = [w for w in words[1:] if w in MAKE_TARGETS]
        return f"make {hit[0]}" if hit else None
    if os.path.basename(words[0]) in ("python3", "python", "bash", "sh") and len(words) > 1:
        words = words[1:]
    name = os.path.basename(words[0])
    args = set(words[1:])
    if args & SAFE_FLAGS:
        return None
    if name in WRITERS or name in TABLE_WRITERS or (name in APPLY_ONLY and "--apply" in args):
        return name
    return None


def private_name_problem(part, command, cwd):
    """The commit/PR/issue text, or a -F / --body-file file, holding the private name."""
    call = git_call(part)
    if not (PUBLISHING.search(part) or (call and call[1] == "commit") or GIT_COMMIT.search(part)):
        return None
    if contains_private_name(command):
        return "the private name in a commit, PR or issue text"
    try:
        words = shlex.split(part)
    except ValueError:
        return None
    for flag, value in zip(words, words[1:]):
        if flag in FILE_FLAGS and value != "-":
            try:
                with open(os.path.join(cwd, os.path.expanduser(value)), encoding="utf-8", errors="ignore") as f:
                    if contains_private_name(f.read()):
                        return f"the private name in {value}"
            except OSError:
                pass
    return None


def git_call(part):
    """Return (extra -C dir, subcommand, args after it), or None for anything but git."""
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
    if i >= len(words):
        return None
    return where, words[i], words[i + 1:]


def in_project(target, project):
    top = git(target, "rev-parse", "--show-toplevel")
    return not (top and project and os.path.realpath(top) != os.path.realpath(project))


def on_main(target, branched):
    return not branched and git(target, "symbolic-ref", "--short", "HEAD") == "main"


def push_problem(target, args, branched):
    if any(a.startswith("--force") or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", a) for a in args):
        return "force-push"
    refs = [a for a in args if not a.startswith("-")][1:]
    if any(a.startswith("+") for a in refs):
        return "force-push"
    if any(a == "--all" or a == "--mirror" for a in args):
        return "push of every branch"
    if any(r.split(":")[-1] in ("main", "refs/heads/main") for r in refs):
        return "push to main"
    if on_main(target, branched) and (not refs or any(r.split(":")[-1] == "HEAD" for r in refs)):
        return "push to main"
    return None


def main():
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")
    cwd = data.get("cwd") or os.getcwd()
    project = os.environ.get("CLAUDE_PROJECT_DIR", cwd)
    ask = []
    branched = False  # an earlier step in this command left main
    for part in SPLIT.split(command):
        moved = re.match(r"\s*cd\s+(\S+)\s*$", part)
        if moved:
            cwd = os.path.join(cwd, os.path.expanduser(moved.group(1).strip("\"'")))
            continue
        if BRANCHED.search(part):
            branched = True
        call = git_call(part)
        if call and call[1] in ("push", "commit"):
            target = os.path.join(cwd, call[0]) if call[0] else cwd
            problem = None
            if in_project(target, project):
                if call[1] == "push":
                    problem = push_problem(target, call[2], branched)
                elif on_main(target, branched):
                    problem = "commit on main"
            if problem:
                print(f"Blocked: {problem}. Use an agent/ branch and a PR (AGENTS.md).", file=sys.stderr)
                return 2
        found = private_name_problem(part, command, cwd)
        if found:
            print(f"Blocked: {found}. The repo is public; see AGENTS.md. Reword it.", file=sys.stderr)
            return 2
        writer = table_writer(part)
        if writer and jmri_running():
            print(f"Blocked: {writer} writes the JMRI tables or deploys, and PanelPro or CATS is open. "
                  "Quit it first (AGENTS.md).", file=sys.stderr)
            return 2
        if MERGE.search(part) and re.search(r"(^|\s)--admin\b", part):
            print("Blocked: an admin merge skips the required check. That override is the owner's.", file=sys.stderr)
            return 2
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
