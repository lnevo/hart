#!/usr/bin/env python3
"""Block subagent shell commands that publish, touch hosts, or act on the railroad.

Runs as a PreToolUse hook from .claude/agents/*.md, so the main session is not
affected. Matches programs by name where a command starts (also behind wrappers
such as timeout, sudo, env or if), so searching for these names still works.
This is a guardrail against mistakes, not a security boundary.

`ssh` is allowed when it only reads. The remote command may hold only plain
characters (REMOTE_TEXT: no quotes, `=`, `$`, `&`, backslash, redirect or
grouping), so it reads the same in a POSIX shell, cmd and PowerShell. Each part
must be a bare program name from READ_ONLY, or one from READ_ONLY_SUB with its
subcommand first. scp and rsync stay blocked.

Any error inside the guard blocks the command (exit 2).
"""
import json
import re
import shlex
import sys

BLOCKED_PROGRAMS = {
    "deploy_hartrailroad.sh", "sync_hart_package.sh", "redeploy_commit.sh", "flash_nano.py",
    "serial_to_mqtt.py", "mosquitto_pub", "scp", "rsync", "pull_ops.sh",
}
BLOCKED_PREFIXES = ("run_serial_mqtt", "pi_")  # pi_*.sh in tools/hosts act on the Pi
BLOCKED_MAKE = ("deploy", "redeploy", "ops-pull", "sts-pull")
BLOCKED_GIT = {"commit", "push", "merge", "rebase", "reset", "stash", "switch", "checkout", "restore", "clean"}
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
INTERPRETER = re.compile(r"(ba|z|da|k)?sh|fish|python[\d.]*|uv|uvx|pipx|node|perl|ruby")
# Programs and shell keywords that run the rest of their words as a command. Their option
# values are not parsed: every later word is tried as the start of the command.
WRAPPERS = {"sudo", "timeout", "env", "nice", "nohup", "command", "exec", "time", "xargs", "stdbuf",
            "caffeinate", "watch", "then", "do", "else", "if", "elif", "while", "until", "!", "{", "(",
            "builtin", "eval", "nohup", "parallel"}
# Local redirects that only send output to a descriptor or nowhere; removed before parsing.
HARMLESS_REDIRECT = re.compile(r"\s\d?>&\d|\s\d?>\s*/dev/null")
SEPARATORS = ";&|\n"
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.S)

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
    "journalctl": ("--vacuum", "--rotate", "--flush", "--setup-keys", "--update-catalog", "-f", "--follow"),
    "tail": ("-f", "-F", "--follow", "--retry"),
    "docker": ("-f", "--follow"),
    "git": ("--output", "--ext-diff", "--textconv", "--exec-path"),
}
# ssh options: flags without a value, options with a value, and the -o keys allowed.
SSH_FLAGS = set("46qTnCv")
SSH_VALUE_OPTIONS = {"-p", "-l"}
SSH_O_KEYS = {"connecttimeout", "batchmode", "connectionattempts", "serveraliveinterval",
              "serveralivecountmax", "port", "user", "loglevel", "stricthostkeychecking"}


def commands(text: str) -> list[list[str]] | None:
    """Split a shell line into commands (lists of words), honouring quotes; None if it cannot be parsed."""
    lexer = shlex.shlex(text, posix=True, punctuation_chars=SEPARATORS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""  # bash starts a comment only at a word's start; never hide text after '#'
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    result, current = [], []
    for token in tokens:
        if token and set(token) <= set(SEPARATORS):
            if current:
                result.append(current)
            current = []
        else:
            current.append(token)
    if current:
        result.append(current)
    return result


def base(word: str) -> str:
    return re.split(r"[/\\]", word)[-1]


def strip_to_program(words: list[str]) -> list[str]:
    """Drop VAR=value words and grouping marks in front of the program."""
    words = list(words)
    while words:
        first = words[0].lstrip("({!")
        if not first or ASSIGNMENT.fullmatch(first):
            words.pop(0)
            continue
        words[0] = first
        return words
    return []


def git_subcommand(args: list[str]) -> str:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GIT_VALUE_OPTIONS else 1
    return args[i] if i < len(args) else ""


def blocked_name(word: str) -> bool:
    name = base(word)
    return name in BLOCKED_PROGRAMS or name.startswith(BLOCKED_PREFIXES)


def blocked_local(program: str, args: list[str]) -> bool:
    if blocked_name(program):
        return True
    if INTERPRETER.fullmatch(program) and any(blocked_name(a) for a in args):
        return True
    if program == "make" and any(a.startswith(BLOCKED_MAKE) for a in args):
        return True
    return program == "git" and git_subcommand(args) in BLOCKED_GIT


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
        for opt in WRITING_OPTIONS.get(program, ()):
            if any(w == opt or w.startswith(opt) for w in args):
                return f"{program} {opt}"
    return ""


def check_words(words: list[str], depth: int) -> str:
    """'' when one command (a list of words) is allowed, else why not."""
    words = strip_to_program(words)
    if not words:
        return ""
    program, args = base(words[0]), words[1:]
    if program in WRAPPERS:
        # Try every later word as the program, so option values (sudo -u pi, timeout -s KILL)
        # and quoted commands (watch 'git push') cannot hide it.
        for i in range(len(args)):
            found = check_words(args[i:], depth + 1) if depth < 6 else "nested wrappers"
            found = found or (problem(args[i], depth + 1) if " " in args[i] else "")
            if found:
                return found
        return ""
    if INTERPRETER.fullmatch(program):
        for i, arg in enumerate(args):
            if arg.startswith("-") and not arg.startswith("--") and ("c" in arg[1:] or arg in ("-e", "-m")):
                inner = next((a for a in args[i + 1:] if not a.startswith("-")), "")
                if program in SHELLS:
                    found = problem(inner, depth + 1)
                else:  # inline Python or other code: refuse it if it names anything blocked
                    found = inner if re.search(r"\bssh\b|subprocess|os\.system|"
                                               + "|".join(map(re.escape, BLOCKED_PROGRAMS)), inner) else ""
                if found:
                    return found
                break
    if program == "ssh":
        remote, wrong = remote_command(args)
        wrong = wrong or read_only_problem(remote)
        return f"ssh is for read-only commands only ({wrong}): {shlex.join(words)}" if wrong else ""
    return shlex.join(words) if blocked_local(program, args) else ""


def problem(command: str, depth: int = 0) -> str:
    """'' when a subagent may run `command`, else the message saying why not."""
    if depth > 6:
        return "nested shells"
    command = HARMLESS_REDIRECT.sub(" ", command)
    parsed = commands(command)
    if parsed is None:  # unbalanced quotes: fall back to a plain split
        parsed = [part.split() for part in re.split(r"[;&|\n]", command)]
    for words in parsed:
        found = check_words(words, depth)
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
