#!/usr/bin/env python3
"""Stop or question the shell commands AGENTS.md rules out, in every session.

Blocks a commit on main, a push to main, any force-push from this repo and an
admin merge, which would skip the required check. Asks first for a track/cmd
publish. Other merges through gh pass: agents may merge a PR once its required
check is green, and GitHub refuses it otherwise. Submodules keep their own rules, so
pushes from external/ pass.

It also blocks a commit, tag, PR, issue, comment, review or release whose text or body
file holds the railroad's private name (checked by fingerprint, never spelled out); if that
check cannot load, publishing is blocked. A running PanelPro or CATS on this machine blocks
nothing: the Mac is expendable, and what matters lives on the Pi (AGENTS.md).

While the operating flag is set (tools/hosts/operating.sh: the owner is running trains, or a
speed-matching run is on the layout) it blocks what reaches the layout hosts (host_control): a deploy
to the Pi or Windows, quitting or starting PanelPro on the Pi, an STS update there, an ssh command to
either host that touches JMRI, PanelPro, CATS, java, STS's docker, a shell, a kill or a reboot, an ssh
shell on either host with no remote command, and, under the owner's flag, a new speed-matching job.
Windows stays guarded because it runs the LCOS bridge; the Mac stays open. Every command the line runs
counts, as shell_parse.py finds them: behind `$(...)`, backticks, xargs, find -exec, a shell's -c text
and wrappers such as env, timeout or sudo. An ssh target the text does not show (xargs' `{}`, a
variable) counts as a layout host. A line shell_parse.py cannot split that names a layout host is
blocked. HART_GUARD_OPERATING=1 or 0 overrides the flag file, for tests.

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
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:        # loaded by path from the Cursor hook, edit_guard.py and the tests
    sys.path.insert(0, HERE)
import shell_parse  # noqa: E402
from shell_parse import SimpleCommand  # noqa: E402

SPLIT = shell_parse.ROUGH_SPLIT
PUBLISH = re.compile(r"\bmosquitto_pub\b.*track/cmd|track/cmd.*\bmosquitto_pub\b", re.S)
MERGE = re.compile(r"^\s*gh\s+pr\s+merge\b")
BRANCHED = re.compile(r"^\s*git\s+(checkout\s+(-q\s+)?-[bB]|switch\s+(-q\s+)?-[cC])\s+\S+")
# Commands that publish text: commits, tags, PRs, issues, comments, reviews and releases.
PUBLISHING = re.compile(
    r"^\s*(gh\s+(pr|issue)\s+(create|edit|comment|review)|gh\s+release\s+(create|edit)"
    r"|git\s+(-\S+\s+)*(commit|tag)|git\s+(-\S+\s+)*notes\s+(add|append|edit))\b")
FILE_FLAGS = ("-F", "--file", "--body-file", "--notes-file")
# The operating flag file (tools/hosts/operating.sh) and what it rules out (host_control).
OPERATING_FLAG = os.environ.get("HART_OPERATING_FLAG") or os.path.expanduser("~/.hart_operating")
HOST_SCRIPTS = {"pi_quit_panelpro.sh", "pi_start_panelpro.sh", "pi_sts_update.sh"}
HOST_FLAGS = ("--pi", "--win", "--all")          # sync_hart_package.sh and redeploy_commit.sh: a layout host
# The deploy steps in tools/hosts/deploy/: the entry point's own steps. The ship steps for a host always reach one;
# the gate does with a host flag (it asks the hosts over ssh); the Mac step and staging never do.
DEPLOY_ENTRY = ("sync_hart_package.sh", "redeploy_commit.sh")
DEPLOY_SHIP_HOST = ("ship_pi.sh", "ship_win.sh")
SSH_VALUE_OPTS = {"-b", "-c", "-D", "-E", "-e", "-F", "-I", "-i", "-J", "-L", "-l", "-m", "-O", "-o", "-p", "-Q",
                  "-R", "-S", "-W", "-w"}     # ssh options that take the next word as their value
HOST_TARGETS = {"deploy-layout", "deploy-all"}    # make targets that deploy to the hosts (redeploy: by HOSTS)
REMOTE_TOUCH = re.compile(r"PanelPro|JMRI|\bcats\b|\bjava\b|\bdocker\b|\breboot\b|\bshutdown\b|\bsystemctl\b|"
                          r"\bkill(all)?\b|\bpkill\b|jmri_cmd|speedrun|\btaskkill\b|Stop-Process|Restart-Computer|"
                          r"Stop-Computer|serial_to_mqtt|\bpython|(?<![.\w-])(ba|z|da|k)?sh\b|\bpowershell|"
                          r"\bpwsh\b|\bcmd(\.exe)?\s+/[ck]\b", re.I)     # Windows runs the LCOS bridge
UNSHOWN = re.compile(r"[$`{}*?\[]")                # an ssh target the text does not spell out
HOST_KEYS = ("HART_PI_SSH", "HART_WIN_SSH", "HART_PI_WEB_HOST", "HART_MQTT_BROKER")
ENV_FILES = [os.path.join(HERE, "..", "..", "tools", "env", n) for n in ("defaults.env", "hart.env")]
NAME_CHECK = os.path.join(HERE, "..", "..", "ops", "hart-ops", "card_pipeline", "private_name.py")


@dataclass(frozen=True)
class OperatingFlag:
    """The operating flag file's fields (tools/hosts/operating.sh writes them as key=value lines)."""
    by: str = "?"
    since: str = ""
    reason: str = ""


@dataclass(frozen=True)
class LayoutEnv:
    """The layout hosts' names (host part only, lower case) and the HART_ values they came from."""
    hosts: frozenset[str]
    values: Mapping[str, str]


def git(cwd: str, *args: str) -> str:
    """git's output in `cwd`, or "" when git fails or cannot start."""
    try:
        done = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def operating() -> OperatingFlag | None:
    """The operating flag when it is set, else None. A flag file that cannot be read counts as set."""
    forced = os.environ.get("HART_GUARD_OPERATING")
    if forced in ("0", "1"):
        return OperatingFlag(by="test") if forced == "1" else None
    try:
        with open(OPERATING_FLAG, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return None
    except OSError:
        return OperatingFlag(reason="the flag file cannot be read")
    fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    return OperatingFlag(by=fields.get("by", "?"), since=fields.get("since", ""), reason=fields.get("reason", ""))


def layout_env() -> LayoutEnv:
    """The ssh names of the Pi and Windows, the Pi's web name and the broker address (tools/env: environment,
    then hart.env, then defaults.env). Read once per hook call."""
    values: dict[str, str] = {}
    for path in ENV_FILES:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"\s*(HART_\w+)=(.*)", line)
                    if m:
                        values[m.group(1)] = m.group(2).strip().strip("\"'")
        except OSError:
            continue
    values.update({k: v for k, v in os.environ.items() if k.startswith("HART_")})
    names = {values.get(k, "") for k in HOST_KEYS}
    return LayoutEnv(frozenset(n.split("@")[-1].lower() for n in names if n), values)


def names_host(text: str, hosts: frozenset[str]) -> bool:
    """True when a layout host's name stands in `text` as a word of its own."""
    return any(re.search(r"(?<![\w.-])" + re.escape(h) + r"(?![\w-]|\.\w)", text, re.I) for h in hosts)


def speedmatch_sends(args: Sequence[str]) -> bool:
    """speedmatch.py's words after the script: True when they send to the Pi (drop JOB, pom ... --send)."""
    if args[:1] == ["drop"]:
        return len(args) > 1 and args[1] not in ("--fetch", "--kill", "-h", "--help")
    # any prefix of --send counts (an argparse abbreviation), though speedmatch.py turns abbreviations off
    return args[:1] == ["pom"] and any(len(a) > 2 and "--send".startswith(a) for a in args[1:])


HOSTS_PI = re.compile(r"(^|\s|=)(" + "|".join(re.escape(f) for f in HOST_FLAGS) + r")\b")


def deploy_problem(head: str, args: list[str], assigned: Mapping[str, str]) -> str | None:
    """A deploy to the Pi or Windows, a Pi PanelPro or STS script, or make mqtt-clean, or None."""
    if head in DEPLOY_ENTRY and any(a == f or a.startswith(f + "=") for a in args for f in HOST_FLAGS):
        return "a deploy to the Pi or Windows"
    if head in DEPLOY_SHIP_HOST:
        return "a deploy to the Pi or Windows"
    if head == "gate.sh" and any(a in ("--pi", "--win") for a in args):
        return "a deploy to the Pi or Windows"
    if head == "make":
        hosts = " ".join([a for a in args if a.startswith("HOSTS=")] + [assigned.get("HOSTS", "")])
        if HOST_TARGETS & set(args) or ("redeploy" in args and HOSTS_PI.search(hosts)):
            return "a deploy to the Pi or Windows"
        if "mqtt-clean" in args:
            return "make mqtt-clean, which writes to the layout broker on the Pi"
    if head in HOST_SCRIPTS:
        return f"{head}, which acts on the Pi"
    return None


def speedmatch_call(head: str, args: list[str], assigned: Mapping[str, str]) -> tuple[str, list[str]]:
    """(program, its words) with `python3 [opts] [-m] speedmatch...` and `make speedmatch ARGS=...` read as
    speedmatch.py, which runs drop_job.sh itself; any other command comes back as it is."""
    if re.fullmatch(r"python[\d.]*", head):
        while args and args[0].startswith("-") and args[0] not in ("-c", "-m", "-"):
            # -W and -X take the next word as their value unless it is joined (-Wignore)
            args = args[2:] if args[0] in ("-W", "-X") else args[1:]
        if args[:1] == ["-m"]:
            args = args[1:]         # python3 -m speedmatch ...: the module stands for the script
        head, args = (os.path.basename(args[0]), args[1:]) if args and args[0] not in ("-c", "-") else (head, [])
        head = "speedmatch.py" if head == "speedmatch" else head
    if head == "make" and "speedmatch" in args:
        make_args = [a[len("ARGS="):] for a in args if a.startswith("ARGS=")] or [assigned.get("ARGS", "")]
        try:
            return "speedmatch.py", shlex.split(make_args[-1])
        except ValueError:
            return "speedmatch.py", make_args[-1].split()
    return head, args


def assignments(words: Sequence[str]) -> dict[str, str]:
    """The VAR=value words among `words`, as {VAR: value}."""
    return {name: value for name, _, value in (w.partition("=") for w in words if shell_parse.ASSIGNMENT.fullmatch(w))}


def expand_vars(word: str, values: Mapping[str, str]) -> str:
    """`word` with $NAME and ${NAME} replaced where `values` knows NAME; unknown ones stay as written."""
    return re.sub(r"\$\{?(\w+)\}?", lambda m: values.get(m.group(1), m.group(0)), word)


def ssh_problem(cmd: SimpleCommand, args: list[str], values: Mapping[str, str], env: LayoutEnv,
                line: str) -> str | None:
    """An ssh command to a layout host that touches the layout software or opens a shell there, or None.
    A target the text does not show counts as a layout host; xargs may add remote words from its input,
    so then the whole line counts as the remote command."""
    i, target = 0, ""
    while i < len(args):
        if args[i] in SSH_VALUE_OPTS:
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            target = args[i]
            break
    host = re.sub(r"^ssh://|:\d+$", "", expand_vars(target, values)).split("@")[-1].lower()
    unshown = (cmd.from_input and (not target or "{}" in target)) or bool(UNSHOWN.search(host))
    if not (unshown or host in env.hosts):
        return None
    where = target or "a host from xargs' input"
    remote = " ".join(args[i + 1:]) if target else ""
    if not remote and not cmd.from_input:
        return f"an ssh shell on {where}, which runs whatever it reads"
    if REMOTE_TOUCH.search("\n".join((remote, cmd.stdin, line if cmd.from_input else ""))):
        return f"an ssh command to {where} that touches the layout software"
    return None


def host_control(cmd: SimpleCommand, flag: OperatingFlag, exported: Mapping[str, str], env: LayoutEnv,
                 line: str = "") -> str | None:
    """What this command reaches on a layout host while the operating flag `flag` is set, or None: a host
    deploy, a Pi PanelPro or STS script, an ssh command to the Pi or Windows that touches the layout software,
    or (under the owner's flag) a new speed-matching job. `line` is the whole command line."""
    if not cmd.words:
        return None
    assigned = {**exported, **cmd.assigned}
    assigned.update(assignments(cmd.words[1:]))
    head, args = shell_parse.base(cmd.words[0]), list(cmd.words[1:])
    found = deploy_problem(head, args, assigned)
    if found:
        return found
    if head == "drop_job.sh" and flag.by == "owner" and args and \
            args[0] not in ("--fetch", "--kill", "-h", "--help"):
        return "a speed-matching job during the owner's session"
    head, args = speedmatch_call(head, args, assigned)
    if head == "speedmatch.py" and flag.by == "owner" and speedmatch_sends(args):
        return "a speed-matching job during the owner's session"
    if head == "ssh":
        return ssh_problem(cmd, args, {**env.values, **assigned}, env, line)
    return None


def host_problem(command: str, flag: OperatingFlag, env: LayoutEnv) -> str | None:
    """The first command in `command` that host_control blocks, or None. A line that cannot be split is
    blocked when it names a layout host, and its rough split is checked as well."""
    try:
        commands = shell_parse.simple_commands(command)
    except shell_parse.TooDeep:
        return "a command nested too deep for the guard to read"
    except shell_parse.ParseError as err:
        if names_host(command, env.hosts):
            return f"a command the guard cannot split ({err}) that names a layout host"
        commands = shell_parse.rough_commands(command)
    exported: dict[str, str] = {}     # VAR=value and export VAR=value commands seen so far (make redeploy's HOSTS)
    for cmd in commands:
        if not cmd.words:
            exported.update(cmd.assigned)
        elif cmd.words[0] == "export":
            exported.update(assignments(cmd.words[1:]))
        found = host_control(cmd, flag, exported, env, command)
        if found:
            return found
    return None


def contains_private_name(text: str) -> bool:
    """The repo's fingerprint check. Raises when it cannot be loaded, so publishing fails closed."""
    spec = importlib.util.spec_from_file_location("hart_private_name", NAME_CHECK)
    if spec is None or spec.loader is None:
        raise ImportError(f"no name check at {NAME_CHECK}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return bool(module.contains_private_name(text))


def file_values(words: Sequence[str]) -> Iterator[str]:
    """Values given to -F / --body-file style flags, as separate words, --flag=value or -Fvalue."""
    for i, word in enumerate(words):
        for flag in FILE_FLAGS:
            if word == flag and i + 1 < len(words):
                yield words[i + 1]
            elif flag.startswith("--") and word.startswith(flag + "="):
                yield word[len(flag) + 1:]
            elif flag == "-F" and word.startswith("-F") and len(word) > 2 and not word.startswith("--"):
                yield word[2:]


def private_name_problem(part: str, rest: str, cwd: str) -> str | None:
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


def git_call(part: str) -> tuple[str | None, str, list[str]] | None:
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


def main_checkout(target: str) -> bool:
    """True when `target` is in the main checkout (not a worktree) of a repo using agent worktrees."""
    git_dir = git(target, "rev-parse", "--absolute-git-dir")
    common = git(target, "rev-parse", "--git-common-dir")  # relative to target on some gits
    if not git_dir or not common:
        return False
    common = os.path.join(target, common) if not os.path.isabs(common) else common
    if os.path.realpath(git_dir) != os.path.realpath(common):
        return False
    top = git(target, "rev-parse", "--show-toplevel")
    return bool(top) and os.path.exists(os.path.join(top, WORKTREE_TOOL))


def switch_problem(target: str, sub: str, args: Sequence[str]) -> str | None:
    """A git switch/checkout that would move the main checkout off main, or None.

    Allowed: main itself, and restoring files (after `--`, or names that are all existing
    paths). Anything else is a branch, commit or revision expression and is blocked.
    """
    if "--" in args:
        return None
    if any(a in ("-b", "-B", "-c", "-C", "--create", "--force-create", "--orphan", "--detach") for a in args):
        return "a new branch"
    names = [a for a in args if a == "-" or not a.startswith("-")]
    if not names or names == ["main"]:
        return None
    if sub == "checkout" and names[0] != "-" and all(os.path.exists(os.path.join(target, n)) for n in names):
        return None  # a path
    return f"a {sub} to {names[0]}"


def in_project(target: str, project: str) -> bool:
    """False when `target` is in a different repo from `project` (a submodule or another clone)."""
    top = git(target, "rev-parse", "--show-toplevel")
    return not (top and project and os.path.realpath(top) != os.path.realpath(project))


def on_main(target: str, branched: bool) -> bool:
    """True when `target` is on main and no earlier step of the command left it."""
    return not branched and git(target, "symbolic-ref", "--short", "HEAD") == "main"


def push_problem(target: str, args: Sequence[str], branched: bool) -> str | None:
    """A force-push, a push of every branch or a push to main, or None."""
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


def git_problem(part: str, cwd: str, project: str, branched: bool) -> str | None:
    """The message for a commit or switch in the main checkout, or a commit or push on main, or None."""
    call = git_call(part)
    if call and call[1] in ("commit", "switch", "checkout"):
        target = os.path.join(cwd, call[0]) if call[0] else cwd
        if main_checkout(target):
            what = "a commit" if call[1] == "commit" else switch_problem(target, call[1], call[2])
            if what:
                return (f"Blocked: {what} in the main checkout, which stays on main. Work in your own "
                        f"worktree: {NEW_WORKTREE} (AGENTS.md).")
    if call and call[1] in ("push", "commit"):
        target = os.path.join(cwd, call[0]) if call[0] else cwd
        problem = None
        if in_project(target, project):
            if call[1] == "push":
                problem = push_problem(target, call[2], branched)
            elif on_main(target, branched):
                problem = "commit on main"
        if problem:
            return f"Blocked: {problem}. Use an agent/ branch and a PR (AGENTS.md)."
    return None


def repo_problem(command: str, cwd: str, project: str) -> str | None:
    """The message for the first part of `command` that breaks a repo rule (git, private name, admin merge)."""
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
        found = git_problem(part, cwd, project, branched)
        if found:
            return found
        found = private_name_problem(part, rest, cwd)
        if found:
            return f"Blocked: {found}. The repo is public; see AGENTS.md. Reword it."
        if MERGE.search(part) and re.search(r"(^|\s)--admin\b", part):
            return "Blocked: an admin merge skips the required check. That override is the owner's."
    return None


def operating_message(what: str, flag: OperatingFlag) -> str:
    since = f", since {flag.since}" if flag.since else ""
    reason = f": {flag.reason}" if flag.reason else ""
    return (f"Blocked: {what} must wait: the operating flag is set (by {flag.by}{since}{reason}). The layout is "
            "in use; ask the owner, or wait for the run to end (tools/hosts/operating.sh status).")


def main() -> int:
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")
    cwd = data.get("cwd") or os.getcwd()
    project = os.environ.get("CLAUDE_PROJECT_DIR", cwd)
    found = repo_problem(command, cwd, project)
    if found:
        print(found, file=sys.stderr)
        return 2
    flag = operating()
    if flag is not None:
        what = host_problem(command, flag, layout_env())
        if what:
            print(operating_message(what, flag), file=sys.stderr)
            return 2
    if PUBLISH.search(command):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "This publishes to track/cmd, which commands field turnouts.",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
