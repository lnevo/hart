#!/usr/bin/env python3
"""Stop or question the shell commands AGENTS.md rules out, in every session.

Blocks a commit on main, a push to main, any force-push from this repo and an
admin merge, which would skip the required check. Asks first for a track/cmd
publish. Other merges through gh pass: the owner lets agents merge a PR once its
required check is green, and GitHub refuses it otherwise. Submodules keep their own rules, so
pushes from external/ pass.

Two more rules. While PanelPro, DecoderPro, DispatcherPro or CATS runs on this machine it
blocks the commands that write the JMRI tables or deploy: make tables-pull, ops-pull,
deploy-layout and deploy-all, and any repo script whose source writes tables.xml or
JMRI_UserFiles (READS_TABLES and the launch_/run_ launchers excepted). The script is read
when the command runs, and --check, --dry-run or a missing --apply only count when the
script defines that flag. And it blocks a commit, tag, PR, issue, comment, review or
release whose text or body file holds the railroad's private name (checked by fingerprint,
never spelled out); if that check cannot load, publishing is blocked.
HART_GUARD_JMRI_RUNNING=1 or 0 overrides the process check, for tests.

In the main checkout of a repo that uses agent worktrees (it holds tools/agent/worktrees.py)
it blocks any commit and any switch to a branch other than main: agents work in their own
worktree under .claude/worktrees/, so no session switches the branch under another.

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
BRANCHED = re.compile(r"^\s*git\s+(checkout\s+(-q\s+)?-[bB]|switch\s+(-q\s+)?-[cC])\s+\S+")
# Matches the main classes JMRI 5 and CATS run (DecoderPro is apps.gui3.dp3.DecoderPro3).
PROCESS = (r"java .*(cats\.apps\.Crandic|apps\.PanelPro\.PanelPro|apps\.gui3\.dp3\.DecoderPro3"
           r"|apps\.DecoderPro|apps\.DispatcherPro)")
# Commands that publish text: commits, tags, PRs, issues, comments, reviews and releases.
PUBLISHING = re.compile(
    r"^\s*(gh\s+(pr|issue)\s+(create|edit|comment|review)|gh\s+release\s+(create|edit)"
    r"|git\s+(-\S+\s+)*(commit|tag)|git\s+(-\S+\s+)*notes\s+(add|append|edit))\b")
FILE_FLAGS = ("-F", "--file", "--body-file", "--notes-file")
NAME_CHECK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "..", "ops", "hart-ops", "card_pipeline", "private_name.py")

# While JMRI or CATS is open these may not run: the make targets below, and any shell or
# Python script in the repo whose source writes tables.xml or JMRI_UserFiles. The script is
# read when the command runs, so new scripts are covered without a list to keep up.
MAKE_TARGETS = {"tables-pull", "ops-pull", "deploy-layout", "deploy-all"}  # not deploy-site
WRITERS = {"pull_tables.sh", "pull_ops.sh", "sync_hart_package.sh"}  # when the file can't be read
TOUCHES = re.compile(r"tables\.xml|JMRI_UserFiles|HART_PI_USERFILES|HART_WIN_USERFILES")
PY_WRITES = re.compile(r"\.write\(|write_text\(|write_bytes\(|shutil\.(copy|move)|os\.replace\("
                       r"|open\([^)]*['\"][wa]b?\+?['\"]")
SH_WRITES = re.compile(r"\b(rsync|cp|scp|mv|install|tee)\s|[^0-9&>]>\s*[^&\s]")
# Read the tables but write somewhere else, or run inside JMRI. A new script that touches
# the tables is blocked until it is listed here, so the list errs on the safe side.
READS_TABLES = {
    "build_wiring_crosswalk.py", "capture_public_name_baseline.py", "discover_nx.py", "discover_sml.py",
    "export_hart_devices_for_cats.py", "export_track_lengths.py", "lcos_mqtt_mimic.py", "run_dispatcher_stage1.py",
}
LAUNCHER_PREFIXES = ("launch_", "run_")  # start PanelPro or CATS themselves and check what is open
SAFE_FLAGS = ("--check", "--dry-run", "--help")  # honoured only when the script defines it
LAUNCHERS = {"env", "time", "nohup", "exec", "sudo", "command"}
SHELLS = {"bash", "sh", "zsh"}


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
    """The repo's fingerprint check. Raises when it cannot be loaded, so publishing fails closed."""
    spec = importlib.util.spec_from_file_location("hart_private_name", NAME_CHECK)
    if spec is None or spec.loader is None:
        raise ImportError(f"no name check at {NAME_CHECK}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.contains_private_name(text)


def program(words):
    """Strip env assignments, launchers and interpreter options; return (words, inline -c text)."""
    words = [w.strip("()") for w in words]
    words = [w for w in words if w]
    while words:
        head = os.path.basename(words[0])
        if re.fullmatch(r"\w+=.*", words[0]) or head in LAUNCHERS:
            words.pop(0)
        elif head == "uv" and words[1:2] == ["run"]:
            words = words[2:]
        elif re.fullmatch(r"python[\d.]*", head) or head in SHELLS:
            words.pop(0)
            while words and words[0].startswith("-"):
                flag = words.pop(0)
                if flag == "-c" and words:
                    return [], words[0]
                if flag in ("-m", "-X", "-W") and words:
                    if flag == "-m":
                        return [], ""  # a module run, not a script path
                    words.pop(0)
            return words, None
        else:
            return words, None
    return words, None


def table_writer(part, cwd="."):
    """Name the table-writing or deploying command in `part`, or None."""
    try:
        words = shlex.split(part)
    except ValueError:
        return None
    words, inline = program(words)
    if inline:
        return next((w for p in SPLIT.split(inline) if (w := table_writer(p, cwd))), None)
    if not words:
        return None
    name = os.path.basename(words[0])
    if name == "make":
        hit = [w for w in words[1:] if w in MAKE_TARGETS]
        return f"make {hit[0]}" if hit else None
    if not name.endswith((".py", ".sh")) or name.startswith(("test_",) + LAUNCHER_PREFIXES) or name in READS_TABLES:
        return None
    try:
        with open(os.path.join(cwd, os.path.expanduser(words[0])), encoding="utf-8", errors="ignore") as f:
            source = f.read()
    except OSError:
        return name if name in WRITERS else None
    writes = (SH_WRITES if name.endswith(".sh") else PY_WRITES).search(source)
    if not (TOUCHES.search(source) and writes):
        return None
    args = words[1:]
    if '"--apply"' in source or "'--apply'" in source:
        return name if "--apply" in args else None
    if any(a in SAFE_FLAGS and (f'"{a}"' in source or f"'{a}'" in source or f"{a})" in source) for a in args):
        return None
    return name


def file_values(words):
    """Values given to -F / --body-file style flags, as separate words, --flag=value or -Fvalue."""
    for i, word in enumerate(words):
        for flag in FILE_FLAGS:
            if word == flag and i + 1 < len(words):
                yield words[i + 1]
            elif flag.startswith("--") and word.startswith(flag + "="):
                yield word[len(flag) + 1:]
            elif flag == "-F" and word.startswith("-F") and len(word) > 2 and not word.startswith("--"):
                yield word[2:]


def private_name_problem(part, rest, cwd):
    """The publishing text (this part to the end, for heredocs) or a body file holding the private name."""
    call = git_call(part)
    if not (PUBLISHING.search(part) or (call and call[1] in ("commit", "tag", "notes"))):
        return None
    try:
        if contains_private_name(rest):
            return "the private name in a commit, tag, PR, issue or release text"
        words = shlex.split(part)
    except ValueError:
        words = part.split()
    except Exception as err:  # noqa: BLE001 - any failure to load the check blocks publishing
        return f"the private-name check could not load ({err})"
    for value in file_values(words):
        if value == "-":
            continue
        try:
            with open(os.path.join(cwd, os.path.expanduser(value)), encoding="utf-8", errors="ignore") as f:
                if contains_private_name(f.read()):
                    return f"the private name in {value}"
        except OSError:
            pass
        except Exception as err:  # noqa: BLE001
            return f"the private-name check could not load ({err})"
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


WORKTREE_TOOL = os.path.join("tools", "agent", "worktrees.py")
NEW_WORKTREE = "python3 tools/agent/worktrees.py new <topic> (make wt TOPIC=<topic>)"


def main_checkout(target):
    """True when `target` is in the main checkout (not a worktree) of a repo using agent worktrees."""
    git_dir = git(target, "rev-parse", "--absolute-git-dir")
    common = git(target, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not git_dir or os.path.realpath(git_dir) != os.path.realpath(common):
        return False
    top = git(target, "rev-parse", "--show-toplevel")
    return bool(top) and os.path.exists(os.path.join(top, WORKTREE_TOOL))


def switch_problem(target, sub, args):
    """A git switch/checkout that would move the main checkout off main, or None."""
    if "--" in args:
        return None  # restoring files
    names = [a for a in args if not a.startswith("-")]
    if any(a in ("-b", "-B", "-c", "-C", "--create", "--force-create", "--orphan", "--detach") for a in args):
        return "a new branch"
    if not names or names[0] == "main":
        return None
    if sub == "switch":
        return f"a switch to {names[0]}"
    ref = names[0]
    if ref == "-" or re.fullmatch(r"[0-9a-f]{7,40}", ref) or any(
            git(target, "rev-parse", "--verify", "--quiet", r) for r in (f"refs/heads/{ref}", f"refs/remotes/{ref}",
                                                                          f"refs/remotes/origin/{ref}", f"refs/tags/{ref}")):
        return f"a checkout of {ref}"
    return None  # a path


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
    pos = 0
    for part in SPLIT.split(command):
        start = command.find(part, pos)
        pos = start + len(part) if start >= 0 else pos
        rest = command[start:] if start >= 0 else part  # this part onward, so a heredoc body counts
        moved = re.match(r"\s*cd\s+(\S+)\s*$", part)
        if moved:
            cwd = os.path.join(cwd, os.path.expanduser(moved.group(1).strip("\"'")))
            continue
        if BRANCHED.search(part):
            branched = True
        call = git_call(part)
        if call and call[1] in ("commit", "switch", "checkout"):
            target = os.path.join(cwd, call[0]) if call[0] else cwd
            if main_checkout(target):
                what = "a commit" if call[1] == "commit" else switch_problem(target, call[1], call[2])
                if what:
                    print(f"Blocked: {what} in the main checkout, which stays on main. Work in your own "
                          f"worktree: {NEW_WORKTREE} (AGENTS.md).", file=sys.stderr)
                    return 2
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
        found = private_name_problem(part, rest, cwd)
        if found:
            print(f"Blocked: {found}. The repo is public; see AGENTS.md. Reword it.", file=sys.stderr)
            return 2
        writer = table_writer(part, cwd)
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
