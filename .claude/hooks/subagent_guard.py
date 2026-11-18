#!/usr/bin/env python3
"""Block subagent shell commands that publish, touch hosts, or act on the railroad.

Runs as a PreToolUse hook from .claude/agents/*.md, so the main session is not
affected. Matches where a command starts, so searching for these names still works.
This is a guardrail against mistakes, not a security boundary.

`ssh` is allowed when it only reads: a few harmless options, a host, then a remote
command made only of programs that cannot write (READ_ONLY), with no redirect,
substitution, grouping or script block. The same check suits a POSIX shell (the Pi)
and PowerShell or cmd (Windows). scp and rsync stay blocked.
"""
import json
import re
import shlex
import sys

BLOCKED = re.compile(
    r"^\s*(\S+=\S*\s+)*(sudo\s+)?((ba|z)?sh\s+|python3?\s+|\S*python3?\s+)?(\S*/)?("
    r"deploy_hartrailroad\.sh|sync_hart_package\.sh|flash_nano\.py|serial_to_mqtt\.py|run_serial_mqtt"
    r"|mosquitto_pub|scp|rsync|make\s+deploy\S*"
    r"|git\s+(-C\s+\S+\s+)?(commit|push|merge|rebase|reset|stash|switch|checkout|restore|clean)"
    r")\b"
)
SEPARATORS = ";&|\n"
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.S)
SHELLS = {"sh", "bash", "zsh"}

# Programs a subagent may run on a layout host. None of them can write a file or run another program.
READ_ONLY = {
    "cat", "head", "tail", "ls", "grep", "egrep", "fgrep", "zgrep", "stat", "wc", "cut",
    "sha256sum", "shasum", "md5sum", "cmp", "ps", "pgrep", "uptime", "df", "du", "free",
    "uname", "whoami", "id", "readlink", "realpath", "test", "true", "echo", "journalctl", "find",
    "type", "dir", "Get-Content", "Get-ChildItem", "Get-FileHash", "Get-Process",
}
# Programs that stay read-only only with these subcommands.
READ_ONLY_SUB = {
    "systemctl": {"status", "is-active", "is-enabled", "list-units", "show"},
    "docker": {"ps", "logs", "inspect", "images"},
    "git": {"status", "log", "show", "rev-parse"},
}
# Options that make an allowed program write or run something (matched as a prefix).
WRITING_OPTIONS = {
    "find": ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fls"),
    "journalctl": ("--vacuum", "--rotate", "--flush", "--setup-keys", "--update-catalog"),
    "git": ("--output", "--ext-diff", "--textconv", "-c", "--exec-path", "--git-dir", "--work-tree"),
    "docker": ("-H", "--host", "--config", "--context"),
}
# Anything that redirects, substitutes, groups or opens a script block, in a POSIX shell,
# cmd or PowerShell.
UNSAFE_TEXT = re.compile(r"[<>`(){}$%^]")
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


def program_of(words: list[str]) -> tuple[str, list[str]]:
    """Skip leading VAR=value words; return (program name without its folder, its arguments)."""
    i = 0
    while i < len(words) and ASSIGNMENT.fullmatch(words[i]):
        i += 1
    if i == len(words):
        return "", []
    return re.split(r"[/\\]", words[i])[-1], words[i + 1:]


def remote_command(args: list[str]) -> tuple[str, str]:
    """From ssh's arguments, return (remote command, problem)."""
    args = list(args)
    while args and args[0].startswith("-"):
        opt = args.pop(0)
        if opt in SSH_VALUE_OPTIONS or opt == "-o":
            if not args:
                return "", f"{opt} needs a value"
            value = args.pop(0)
            if opt == "-o" and value.split("=", 1)[0].split()[0].lower() not in SSH_O_KEYS:
                return "", f"-o {value.split('=', 1)[0]}"
        elif opt[:2] in SSH_VALUE_OPTIONS:  # -p2222
            continue
        elif not set(opt[1:]) <= SSH_FLAGS:
            return "", f"option {opt}"
    if len(args) < 2:
        return "", "no remote command"
    return " ".join(args[1:]), ""


def read_only_problem(remote: str) -> str:
    """'' when every command in the remote line only reads, else what is wrong."""
    if UNSAFE_TEXT.search(remote):
        return "redirect, substitution, grouping or variable"
    parsed = commands(remote)
    if parsed is None:
        return "cannot parse the remote command"
    for words in parsed:
        program, args = program_of(words)
        if not program:
            continue
        if program in READ_ONLY_SUB:
            rest = args[2:] if program == "git" and args[:1] == ["-C"] else args
            sub = next((w for w in rest if not w.startswith("-")), "")
            if sub not in READ_ONLY_SUB[program]:
                return f"{program} {sub}".strip()
        elif program not in READ_ONLY:
            return program
        for opt in WRITING_OPTIONS.get(program, ()):
            if any(w == opt or w.startswith(opt) for w in args):
                return f"{program} {opt}"
    return ""


def shell_command(args: list[str]) -> str | None:
    """The command a shell runs from -c (also in combined flags such as -lc), or None."""
    for i, arg in enumerate(args):
        if arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]:
            rest = [a for a in args[i + 1:] if not a.startswith("-")]
            return rest[0] if rest else ""
    return None


def problem(command: str, depth: int = 0) -> str:
    """'' when a subagent may run `command`, else the message saying why not."""
    parsed = commands(command)
    if parsed is None:  # unbalanced quotes: fall back to a plain split and refuse any ssh
        parsed = [part.split() for part in re.split(r"&&|\|\||[;|&\n]", command)]
    for words in parsed:
        program, args = program_of(words)
        if not program:
            continue
        if program in SHELLS:
            inner = shell_command(args)
            if inner is not None:
                if depth >= 3:
                    return "nested shells"
                found = problem(inner, depth + 1)
                if found:
                    return found
                continue
        if program == "ssh":
            remote, wrong = remote_command(args)
            wrong = wrong or read_only_problem(remote)
            if wrong:
                return f"ssh is for read-only commands only ({wrong}): {shlex.join(words)}"
            continue
        # Match on the program and its arguments, without assignments and with a script's folder dropped.
        first = re.split(r"[/\\]", args[0])[-1] if args and program in SHELLS | {"python", "python3"} else None
        line = " ".join([program] + ([first] + args[1:] if first is not None else args))
        if BLOCKED.search(line):
            return line
    return ""


def main() -> int:
    command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    found = problem(command)
    if found:
        print(f"Blocked for subagents: {found}. Report it to the main session instead.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
