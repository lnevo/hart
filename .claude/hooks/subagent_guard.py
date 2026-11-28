#!/usr/bin/env python3
"""Block subagent shell commands that publish, touch hosts, or act on the railroad.

Runs as a PreToolUse hook from .claude/agents/*.md, so the main session is not
affected. Matches programs by name in each command the line runs, as shell_parse.py
finds them (behind `$(...)`, backticks, a shell's -c text, find -exec and wrappers
such as timeout, sudo, env, xargs or if), so searching for these names still works.
This is a guardrail against mistakes, not a security boundary.

`ssh` is allowed when it only reads. The remote command may hold only plain
characters (REMOTE_TEXT: no quotes, `=`, `$`, `&`, backslash, redirect or
grouping), so it reads the same in a POSIX shell, cmd and PowerShell. Each part
must be a bare program name from READ_ONLY, or one from READ_ONLY_SUB with its
subcommand first. scp and rsync stay blocked.

`make ready` (tools/agent/ready.py) is how a subagent commits, pushes and opens its PR. It passes only with the
variables in READY_VARS (or, called directly, the options in READY_OPTIONS) and no assignments in front. The hook
reads the command line only, so the git and gh calls ready.py makes as its children are not checked here; ready.py
refuses the main checkout, other branches than agent/claude/*, pushes to another name, force and any gh call
but `pr view` and `pr create`.

Any error inside the guard blocks the command (exit 2).
"""
import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:        # loaded by path from the tests
    sys.path.insert(0, HERE)
import shell_parse  # noqa: E402
from shell_parse import SimpleCommand, base  # noqa: E402

BLOCKED_PROGRAMS = {
    "deploy_hartrailroad.sh", "sync_hart_package.sh", "redeploy_commit.sh", "flash_nano.py",
    "ship_pi.sh", "ship_win.sh", "ship_mac.sh", "gate.sh",
    "serial_to_mqtt.py", "mosquitto_pub", "scp", "rsync", "pull_ops.sh",
    "pull_roster.sh", "land.py",   # tools/agent/land.py merges a PR: the coordinator's, never a subagent's
    "triage.py",                   # tools/agent/triage.py starts Claude processes: the coordinator's too
}
BLOCKED_PREFIXES = ("run_serial_mqtt", "pi_")  # pi_*.sh in tools/hosts act on the Pi
BLOCKED_MAKE = ("deploy-layout", "deploy-all", "deploy-site", "redeploy", "ops-pull", "roster-pull", "sts-pull",
                "mqtt-clean", "land", "triage")
BLOCKED_GIT = {"commit", "push", "pull", "merge", "rebase", "reset", "stash", "switch", "checkout", "restore",
               "clean", "cherry-pick", "revert", "am", "apply", "rm", "mv", "add", "fetch"}
GIT_WRITING = {"branch": {"-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move", "--copy", "-f", "--force"},
               "worktree": {"add", "remove", "move", "prune"}, "tag": {"-d", "--delete", "-a", "-s", "-f"},
               "submodule": {"update", "add", "deinit", "sync"}}
GH_WRITING = {"merge", "create", "close", "edit", "comment", "delete", "review", "reopen", "ready", "lock",
              "unlock", "rerun", "cancel", "run", "upload", "transfer", "archive", "fork", "sync"}
# make ready (tools/agent/ready.py): the one way a subagent commits, pushes and opens a PR. The guard sees only this
# command line; the git and gh calls the script makes are child processes it never sees, so ready.py holds their rules.
READY_SCRIPT = "tools/agent/ready.py"
READY_VARS = {"FILES", "MSG", "TITLE", "BODY", "BODY_FILE", "BRANCH"}
# make expands $(...) and ${...} (a $(shell ...) among them) in a command-line value before ready.py starts, where
# this hook never sees it; the Makefile reads the values with $(value V), and a value holding one is refused here too.
MAKE_EXPANSION = re.compile(r"\$[({]|`|\n")
READY_OPTIONS = {"--files", "--msg", "--title", "--body", "--body-file", "--branch", "-h", "--help"}
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
SHELLS = shell_parse.SHELLS
INTERPRETER = re.compile(r"(ba|z|da|k)?sh|fish|python[\d.]*|node|perl|ruby")
# Local redirects that only send output to a descriptor or nowhere; removed outside quotes.
HARMLESS_REDIRECT = re.compile(r"(?<=\s)\d?>&\d(?=\s|$|[;|&])|(?<=\s)\d?>\s*/dev/null(?=\s|$|[;|&])")
FOLLOW = re.compile(r"-[A-Za-z0-9]*[fF][A-Za-z0-9]*|--follow.*|--retry")

REMOTE_TEXT = re.compile(r"[A-Za-z0-9_./~:,@+* \t;|-]+")
# Programs a subagent may run on a layout host. None of them can write a file or run another program.
READ_ONLY = {
    "cat", "head", "tail", "ls", "grep", "egrep", "fgrep", "stat", "wc", "cut",
    "sha256sum", "shasum", "md5sum", "cmp", "ps", "pgrep", "uptime", "df", "du", "free",
    "uname", "whoami", "id", "readlink", "realpath", "test", "true", "echo", "journalctl", "find",
    "type", "dir", "Get-Content", "Get-ChildItem", "Get-FileHash", "Get-Process",
}
# Programs that stay read-only only when one of these subcommands is their first argument.
READ_ONLY_SUB = {
    "systemctl": {"status", "is-active", "is-enabled", "list-units", "show"},
    "docker": {"ps", "logs", "inspect", "images"},
    "git": {"log", "show", "rev-parse"},  # not status: it can rewrite the index
}
# Options that make an allowed program write or run something (matched as a prefix).
WRITING_OPTIONS = {
    "find": ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fls"),
    "journalctl": ("--vacuum", "--rotate", "--flush", "--setup-keys", "--update-catalog"),
    "git": ("--output", "--ext-diff", "--textconv", "--exec-path"),
}
# ssh options: flags without a value, options with a value, and the -o keys allowed.
SSH_FLAGS = set("46qTnCv")
SSH_VALUE_OPTIONS = {"-p", "-l"}
SSH_O_KEYS = {"connecttimeout", "batchmode", "connectionattempts", "serveraliveinterval",
              "serveralivecountmax", "port", "user", "loglevel", "stricthostkeychecking"}


def git_subcommand(args: list[str]) -> str:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GIT_VALUE_OPTIONS else 1
    return args[i] if i < len(args) else ""


def blocked_name(word: str) -> bool:
    name = base(word)
    return name in BLOCKED_PROGRAMS or name.startswith(BLOCKED_PREFIXES)


def ready_call(program: str, args: list[str]) -> bool | None:
    """For `make ready ...` or `python3 tools/agent/ready.py ...`: True when allowed, False when it adds anything
    beyond READY_VARS or READY_OPTIONS (another target, a make flag, an option ready.py lacks). None for any other
    command."""
    if program == "make" and "ready" in args:
        rest = [a for a in args if a != "ready"]
        return args.count("ready") == 1 and all(a.split("=", 1)[0] in READY_VARS and "=" in a
                                                and not MAKE_EXPANSION.search(a.split("=", 1)[1]) for a in rest)
    if INTERPRETER.fullmatch(program) and program not in SHELLS and args[:1] and \
            os.path.normpath(args[0]) == READY_SCRIPT:
        return all(a.split("=", 1)[0] in READY_OPTIONS for a in args[1:] if a.startswith("-"))
    return None


def blocked_local(program: str, args: list[str]) -> bool:
    if blocked_name(program):
        return True
    if INTERPRETER.fullmatch(program) and any(blocked_name(a) for a in args):
        return True
    if program == "make" and any(a.startswith(BLOCKED_MAKE) for a in args):
        return True
    if program == "gh":
        if args[:1] == ["api"]:
            return any(a in ("-X", "--method", "-f", "-F", "--field", "--raw-field", "--input")
                       or a.startswith(("-X", "--method=")) for a in args)
        return any(a in GH_WRITING for a in args[:3])
    if program != "git":
        return False
    sub = git_subcommand(args)
    rest = args[args.index(sub) + 1:] if sub in args else []
    return sub in BLOCKED_GIT or bool(set(rest) & GIT_WRITING.get(sub, set()))


def remote_command(args: list[str]) -> tuple[str, str]:
    """From ssh's arguments, return (remote command, problem)."""
    args = list(args)
    while args and args[0].startswith("-"):
        opt = args.pop(0)
        if opt in SSH_VALUE_OPTIONS or opt == "-o":
            if not args:
                return "", f"{opt} needs a value"
            value = args.pop(0)
            key = (value.split("=", 1)[0].split() or [""])[0].lower()
            if opt == "-o" and key not in SSH_O_KEYS:
                return "", f"-o {value}"
        elif opt[:2] in SSH_VALUE_OPTIONS:  # -p2222
            continue
        elif not set(opt[1:]) <= SSH_FLAGS:
            return "", f"option {opt}"
    if len(args) < 2:
        return "", "no remote command"
    return " ".join(args[1:]), ""


def read_only_problem(remote: str) -> str:
    """'' when every command in the remote line only reads, else what is wrong."""
    if not REMOTE_TEXT.fullmatch(remote):
        return "only letters, digits, spaces and / . _ - ~ : , @ + * ; | are allowed"
    for part in re.split(r"[;|]", remote):
        words = part.split()
        if not words:
            continue
        program, args = words[0], words[1:]
        if program in READ_ONLY_SUB:
            rest = args[2:] if program == "git" and args[:1] == ["-C"] else args
            if not rest or rest[0] not in READ_ONLY_SUB[program]:
                return f"{program} {' '.join(rest[:1])}".strip()
        elif program not in READ_ONLY:
            return program
        if program in ("tail", "journalctl", "docker") and any(FOLLOW.fullmatch(w) for w in args):
            return f"{program} following output"
        for opt in WRITING_OPTIONS.get(program, ()):
            if any(w == opt or w.startswith(opt) for w in args):
                return f"{program} {opt}"
    return ""


def check_command(cmd: SimpleCommand) -> str:
    """'' when one command (shell_parse.py has removed its wrappers) is allowed, else why not."""
    if not cmd.words:
        return ""
    words = list(cmd.words)
    program, args = base(words[0]), words[1:]
    allowed = ready_call(program, args)
    if allowed is not None:
        return "" if allowed and not cmd.assigned else f"make ready takes only {sorted(READY_VARS)}: {shlex.join(words)}"
    if INTERPRETER.fullmatch(program) and program not in SHELLS:  # inline code: refuse it if it names what acts
        code = " ".join(args)
        if re.search(r"\bssh\b|subprocess|os\.(system|popen|exec|spawn)|\bsystem\s*\(|\bexec\s*\(|"
                     r"git\s+(" + "|".join(sorted(BLOCKED_GIT)) + r")\b|make\s+(deploy|redeploy)|"
                     + r"(?<![\w.-])(" + "|".join(map(re.escape, sorted(BLOCKED_PROGRAMS))) + ")", code):
            return f"{program} code that runs a blocked command"
    if program == "ssh":
        remote, wrong = remote_command(args)
        wrong = wrong or read_only_problem(remote)
        return f"ssh is for read-only commands only ({wrong}): {shlex.join(words)}" if wrong else ""
    return shlex.join(words) if blocked_local(program, args) else ""


def strip_harmless_redirects(command: str) -> str:
    """Remove 2>&1 and >/dev/null where they stand outside quotes (they are local redirects)."""
    quoted, quote = [], None
    for ch in command:
        if quote:
            quote = None if ch == quote else quote
            quoted.append(True)
        else:
            quote = ch if ch in "'\"" else None
            quoted.append(bool(quote))
    kept, last = [], 0
    for match in HARMLESS_REDIRECT.finditer(command):
        if not any(quoted[match.start():match.end()]):
            kept.append(command[last:match.start()])
            last = match.end()
    kept.append(command[last:])
    return " ".join(kept)


def problem(command: str) -> str:
    """'' when a subagent may run `command`, else the message saying why not. A line shell_parse.py cannot
    split is read with its rough split, which ignores quotes."""
    command = strip_harmless_redirects(command)
    try:
        try:
            parsed = shell_parse.simple_commands(command)
        except shell_parse.TooDeep:
            raise
        except shell_parse.ParseError:
            parsed = shell_parse.rough_commands(command)
    except shell_parse.TooDeep:
        return "nested shells"
    for cmd in parsed:
        found = check_command(cmd)
        if found:
            return found
    return ""


def main() -> int:
    try:
        command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
        found = problem(command)
    except Exception as exc:  # a broken guard must block, not wave the command through
        found = f"the guard failed ({exc!r})"
    if found:
        print(f"Blocked for subagents: {found}. Report it to the main session instead.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
