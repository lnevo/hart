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
    "ship_pi.sh", "ship_win.sh", "ship_mac.sh", "gate.sh",
    "serial_to_mqtt.py", "mosquitto_pub", "scp", "rsync", "pull_ops.sh",
}
BLOCKED_PREFIXES = ("run_serial_mqtt", "pi_")  # pi_*.sh in tools/hosts act on the Pi
BLOCKED_MAKE = ("deploy-layout", "deploy-all", "deploy-site", "redeploy", "ops-pull", "sts-pull", "mqtt-clean")
BLOCKED_GIT = {"commit", "push", "pull", "merge", "rebase", "reset", "stash", "switch", "checkout", "restore",
               "clean", "cherry-pick", "revert", "am", "apply", "rm", "mv", "add", "fetch"}
GIT_WRITING = {"branch": {"-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move", "--copy", "-f", "--force"},
               "worktree": {"add", "remove", "move", "prune"}, "tag": {"-d", "--delete", "-a", "-s", "-f"},
               "submodule": {"update", "add", "deinit", "sync"}}
GH_WRITING = {"merge", "create", "close", "edit", "comment", "delete", "review", "reopen", "ready", "lock",
              "unlock", "rerun", "cancel", "run", "upload", "transfer", "archive", "fork", "sync"}
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
INTERPRETER = re.compile(r"(ba|z|da|k)?sh|fish|python[\d.]*|node|perl|ruby")
# Programs and shell keywords that run the rest of their words as a command. Their option
# values are not parsed: the first later word that looks like a program (KNOWN, a path,
# a blocked name or a quoted command line) is taken as the command.
WRAPPERS = {"sudo", "timeout", "env", "nice", "nohup", "command", "exec", "time", "xargs", "stdbuf",
            "caffeinate", "watch", "then", "do", "else", "if", "elif", "while", "until", "!", "{", "(",
            "builtin", "eval", "parallel", "uv", "uvx", "pipx", "run", "npx", "poetry", "pdm"}
KNOWN = {"git", "gh", "make", "ssh", "scp", "rsync", "grep", "rg", "find", "ls", "cat", "head", "tail",
         "sed", "awk", "wc", "sort", "echo", "test", "true", "false", "python", "python3", "bash", "sh",
         "zsh", "dash", "node", "perl", "ruby", "mosquitto_pub", "mosquitto_sub", "curl", "rm", "mv",
         "cp", "touch", "mkdir", "diff", "jq", "xmllint", "shellcheck", "pytest"}
# Local redirects that only send output to a descriptor or nowhere; removed outside quotes.
HARMLESS_REDIRECT = re.compile(r"(?<=\s)\d?>&\d(?=\s|$|[;|&])|(?<=\s)\d?>\s*/dev/null(?=\s|$|[;|&])")
SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
FOLLOW = re.compile(r"-[A-Za-z0-9]*[fF][A-Za-z0-9]*|--follow.*|--retry")
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
    "journalctl": ("--vacuum", "--rotate", "--flush", "--setup-keys", "--update-catalog"),
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
        return [w.rstrip(")}") if w not in (")", "}") else w for w in words]
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


def check_words(words: list[str], depth: int) -> str:
    """'' when one command (a list of words) is allowed, else why not."""
    words = strip_to_program(words)
    if not words:
        return ""
    program, args = base(words[0]), words[1:]
    if program in WRAPPERS:
        for i, arg in enumerate(args):
            if " " in arg.strip():  # a quoted command line (watch 'git push', eval "...")
                return problem(arg, depth + 1)
            if "/" in arg or base(arg) in KNOWN or base(arg) in WRAPPERS or blocked_name(arg):
                return check_words(args[i:], depth + 1) if depth < 8 else "nested wrappers"
        return ""
    if program == "find":
        for i, arg in enumerate(args):
            if arg in ("-exec", "-execdir", "-ok", "-okdir"):
                inner = []
                for word in args[i + 1:]:
                    if word in (";", "+", "\\;"):
                        break
                    inner.append(word)
                found = check_words(inner, depth + 1)
                if found:
                    return found
    if INTERPRETER.fullmatch(program):
        for i, arg in enumerate(args):
            if program in SHELLS and arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]:
                inner = next((a for a in args[i + 1:] if not a.startswith("-")), "")
                found = problem(inner, depth + 1)
                if found:
                    return found
                break
        if program not in SHELLS:  # inline code: refuse it if it names anything that acts
            code = " ".join(args)
            if re.search(r"\bssh\b|subprocess|os\.(system|popen|exec|spawn)|\bsystem\s*\(|\bexec\s*\(|"
                         r"git\s+(" + "|".join(sorted(BLOCKED_GIT)) + r")\b|make\s+(deploy|redeploy)|"
                         + "|".join(map(re.escape, BLOCKED_PROGRAMS)), code):
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


def problem(command: str, depth: int = 0) -> str:
    """'' when a subagent may run `command`, else the message saying why not."""
    if depth > 8:
        return "nested shells"
    for match in SUBSTITUTION.finditer(command):
        found = problem(match.group(1) if match.group(1) is not None else match.group(2), depth + 1)
        if found:
            return found
    command = strip_harmless_redirects(command)
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
