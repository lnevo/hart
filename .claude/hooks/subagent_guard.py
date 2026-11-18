#!/usr/bin/env python3
"""Block subagent shell commands that publish, touch hosts, or act on the railroad.

Runs as a PreToolUse hook from .claude/agents/*.md, so the main session is not
affected. Matches where a command starts, so searching for these names still works.
This is a guardrail against mistakes, not a security boundary.

`ssh` is allowed when it only reads: options, a host, then a remote command made of
read-only programs (READ_ONLY), with no redirect, substitution, tunnel or interactive
shell. scp and rsync stay blocked.
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
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")

# Programs a subagent may run on a layout host. Each only reads.
READ_ONLY = {
    "cat", "head", "tail", "ls", "grep", "egrep", "fgrep", "zgrep", "stat", "file", "wc",
    "sha256sum", "shasum", "md5sum", "cmp", "diff", "ps", "pgrep", "uptime", "df", "du",
    "date", "hostname", "uname", "whoami", "id", "free", "ss", "journalctl", "find",
    "readlink", "realpath", "test", "true", "echo", "sort", "uniq", "cut", "sed",
}
# Programs that stay read-only only with these subcommands.
READ_ONLY_SUB = {
    "systemctl": {"status", "is-active", "is-enabled", "list-units", "show"},
    "docker": {"ps", "logs", "inspect", "images"},
    "git": {"status", "log", "show", "diff", "rev-parse", "branch"},
}
# Options that make a read-only program write or run something.
WRITING_OPTIONS = {
    "find": ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"),
    "sed": ("-i", "--in-place"),
    "sort": ("-o", "--output"),
    "journalctl": ("--vacuum", "--rotate", "--flush"),
}
SSH_VALUE_OPTIONS = set("bcEeFIiJlmOopQSw")
SSH_REFUSED_OPTIONS = set("DLRNfWt")  # tunnels, background and forced terminals


def commands(text: str) -> list[list[str]] | None:
    """Split a shell line into commands (lists of words), honouring quotes; None if it cannot be parsed."""
    lexer = shlex.shlex(text, posix=True, punctuation_chars=SEPARATORS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
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
    """Skip leading VAR=value words; return (program name, its arguments)."""
    i = 0
    while i < len(words) and ASSIGNMENT.fullmatch(words[i]):
        i += 1
    if i == len(words):
        return "", []
    return words[i].rsplit("/", 1)[-1], words[i + 1:]


def remote_command(args: list[str]) -> tuple[str, str]:
    """From ssh's arguments, return (remote command, problem)."""
    args = list(args)
    while args and args[0].startswith("-"):
        opt = args.pop(0)
        for i, letter in enumerate(opt[1:]):
            if letter in SSH_REFUSED_OPTIONS:
                return "", f"option -{letter}"
            if letter in SSH_VALUE_OPTIONS:
                if i == len(opt) - 2:  # the value is the next word
                    if not args:
                        return "", "missing option value"
                    args.pop(0)
                break
    if len(args) < 2:
        return "", "no remote command"
    return " ".join(args[1:]), ""


def read_only_problem(remote: str) -> str:
    """'' when every command in the remote line only reads, else what is wrong."""
    if re.search(r"[<>`]|\$\(|\b(tee|xargs|sudo|awk|perl|python3?|sh|bash)\b", remote):
        return "redirect, substitution or a program that can write"
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
            continue
        if program not in READ_ONLY:
            return program
        for opt in WRITING_OPTIONS.get(program, ()):
            if any(w == opt or w.startswith(opt) for w in args):
                return f"{program} {opt}"
    return ""


def problem(command: str, depth: int = 0) -> str:
    """'' when a subagent may run `command`, else the message saying why not."""
    parsed = commands(command)
    if parsed is None:  # unbalanced quotes: fall back to a plain split and refuse any ssh
        parsed = [part.split() for part in re.split(r"&&|\|\||[;|\n]", command)]
    for words in parsed:
        program, args = program_of(words)
        if program in ("sh", "bash", "zsh") and "-c" in args and depth < 3:
            inner = args[args.index("-c") + 1:args.index("-c") + 2]
            found = problem(inner[0], depth + 1) if inner else ""
            if found:
                return found
            continue
        if program == "ssh":
            remote, wrong = remote_command(args)
            wrong = wrong or read_only_problem(remote)
            if wrong:
                return f"ssh is for read-only commands only ({wrong}): {shlex.join(words)}"
            continue
        line = shlex.join(words)
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
