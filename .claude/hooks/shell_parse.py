"""Split a shell command line into the simple commands it would run, for the guards in this folder.

main_guard.py and subagent_guard.py both read commands through this module, so they see the same commands.
`simple_commands` finds every command a line runs: the parts between `;`, `&&`, `||`, `|`, `&`, newlines and
subshell parentheses; the text of `$(...)`, backticks and `<(...)`, nested too; heredoc bodies; a shell's `-c`
text; `find -exec`; and the command behind a wrapper (env, nohup, time, timeout, sudo, nice, exec, command,
xargs, watch, eval and others in WRAPPERS) or a keyword (if, then, do, while, until, `!`, `{`). Each command
comes back with its program first and the VAR=value words in front of it apart.

It never runs anything and never expands variables. `#` never starts a comment, so text after it is read as
commands. A `case` pattern's `)` splits the line as a subshell's does, so the pattern word reads as a
command of its own. A line it cannot split (an unbalanced quote, `$(` or backtick) raises ParseError; `rough_commands` is
the fallback split, which ignores quotes. This is a guardrail against mistakes, not a security boundary.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

MAX_DEPTH = 8                       # nested substitutions, shells and wrappers
ROUGH_SPLIT = re.compile(r"&&|\|\||[;|\n]")
SEPARATORS = ";&|()\n"
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.S)
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{"}
CLOSERS = {"fi", "done", "esac", "}", "]]"}
LOOP_HEADS = {"for", "select", "case", "function"}      # their own part runs nothing; the body is its own part
# Wrappers that run the rest of their words as a command, and their options that take the next word as a value.
WRAPPERS: dict[str, frozenset[str]] = {
    "env": frozenset({"-u", "--unset", "-C", "--chdir"}),
    "nohup": frozenset(),
    "time": frozenset({"-f", "--format", "-o", "--output"}),
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "sudo": frozenset({"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T", "-R", "--user", "--group",
                       "--host", "--prompt", "--chdir", "--role", "--type", "--other-user", "--command-timeout",
                       "--chroot", "--close-from"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "exec": frozenset({"-a"}),
    "command": frozenset(),
    "builtin": frozenset(),
    "xargs": frozenset({"-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a", "--arg-file", "--delimiter", "--max-args",
                        "--max-procs", "--max-chars", "--max-lines", "--process-slot-var"}),
    "stdbuf": frozenset({"-i", "-o", "-e"}),
    "setsid": frozenset(),
    "ionice": frozenset({"-c", "--class", "-n", "--classdata", "-p", "--pid", "-P", "--pgid", "-u", "--uid"}),
    "doas": frozenset({"-u", "-C"}),
    "chronic": frozenset(),
    "unbuffer": frozenset(),
    "caffeinate": frozenset({"-t", "-w"}),
    "uvx": frozenset({"--with", "--from", "--python", "-p", "--index", "--index-url"}),
    "npx": frozenset({"-p", "--package"}),
}
# Wrappers whose words after the options are joined into one command line, as `sh -c` would read it.
LINE_WRAPPERS: dict[str, frozenset[str]] = {
    "watch": frozenset({"-n", "--interval"}),
    "eval": frozenset(),
    "parallel": frozenset({"-j", "--jobs", "-S", "--sshlogin", "-N", "-n", "-L", "-I", "--max-args"}),
}
# Launchers that run a command after their subcommand: uv run, poetry run, pdm run, pipx run.
RUNNERS: dict[str, frozenset[str]] = {
    "uv": frozenset({"--with", "--with-requirements", "--python", "-p", "--project", "--directory", "--package",
                     "--extra", "--group", "--env-file", "--index", "--index-url", "-w"}),
    "poetry": frozenset(), "pdm": frozenset(), "pipx": frozenset({"--spec", "--python"}),
}
FIND_EXEC = {"-exec", "-execdir", "-ok", "-okdir"}
FLOCK_VALUE = frozenset({"-w", "--timeout", "-E", "--conflict-exit-code"})
# A redirection word: its operator, then its target joined (2>/dev/null, 2>&1, <f) or in the next word (> f).
REDIRECT = re.compile(r"\d*(&>>?|>&|<&|>>|>\||<>|<<<|>|<)(.*)", re.S)


class ParseError(ValueError):
    """The line cannot be split: an unbalanced quote, `$(` or backtick."""


class TooDeep(ParseError):
    """Substitutions, shells or wrappers nest deeper than MAX_DEPTH."""


@dataclass(frozen=True)
class SimpleCommand:
    """One command a line runs. `words` starts with the program (empty for a line of assignments only);
    `assigned` holds the VAR=value words in front of it; `stdin` holds the heredoc bodies it reads;
    `from_input` is True when xargs or find adds words that the text does not show (such as `{}`)."""
    words: tuple[str, ...]
    assigned: Mapping[str, str] = field(default_factory=dict)
    stdin: str = ""
    from_input: bool = False


def base(word: str) -> str:
    """The program name of a word that may be a path."""
    return re.split(r"[/\\]", word)[-1]


@dataclass
class _Part:
    words: list[str] = field(default_factory=list)
    stdin: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Heredoc:
    delimiter: str
    strip_tabs: bool
    expands: bool          # an unquoted delimiter: `$(...)` in the body runs
    part: _Part


def _skip_single(text: str, i: int) -> int:
    end = text.find("'", i + 1)
    if end < 0:
        raise ParseError("an unbalanced single quote")
    return end + 1


def _skip_backtick(text: str, i: int) -> int:
    j = i + 1
    while j < len(text):
        if text[j] == "\\":
            j += 2
        elif text[j] == "`":
            return j + 1
        else:
            j += 1
    raise ParseError("an unbalanced backtick")


def _skip_double(text: str, i: int) -> int:
    j = i + 1
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 2
        elif c == '"':
            return j + 1
        elif text.startswith("$(", j):
            j = _match_paren(text, j + 1) + 1
        elif c == "`":
            j = _skip_backtick(text, j)
        else:
            j += 1
    raise ParseError("an unbalanced double quote")


def _heredoc_op(text: str, i: int) -> tuple[str, bool, bool, int]:
    """At `<<` (not `<<<`): (delimiter, strip tabs, body expands, index after the delimiter)."""
    j = i + 2
    strip = j < len(text) and text[j] == "-"
    j += strip
    while j < len(text) and text[j] in " \t":
        j += 1
    start = j
    while j < len(text) and not text[j].isspace() and text[j] not in ";&|()<>":
        j = _skip_single(text, j) if text[j] == "'" else _skip_double(text, j) if text[j] == '"' else j + 1
    raw = text[start:j]
    delimiter = re.sub(r"['\"\\]", "", raw)
    if not delimiter:
        raise ParseError("a heredoc with no delimiter")
    return delimiter, strip, raw == delimiter, j


def _heredoc_body(text: str, i: int, delimiter: str, strip_tabs: bool) -> tuple[str, int]:
    """The body that starts at index `i` (after a newline) and the index after its closing line. A body with
    no closing line runs to the end, as bash reads it."""
    lines: list[str] = []
    j = i
    while j < len(text):
        end = text.find("\n", j)
        end = len(text) if end < 0 else end
        line = text[j:end]
        j = end + 1
        if (line.lstrip("\t") if strip_tabs else line) == delimiter:
            return "\n".join(lines), j
        lines.append(line)
    return "\n".join(lines), len(text)


def _match_paren(text: str, i: int) -> int:
    """The index of the `)` that closes the `(` at index `i`, past quotes, substitutions and heredocs."""
    level, j, pending = 1, i + 1, []
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 2
        elif c == "'":
            j = _skip_single(text, j)
        elif c == '"':
            j = _skip_double(text, j)
        elif c == "`":
            j = _skip_backtick(text, j)
        elif text.startswith("<<", j) and not text.startswith("<<<", j):
            delimiter, strip, _expands, j = _heredoc_op(text, j)
            pending.append((delimiter, strip))
        elif c == "\n" and pending:
            j += 1
            for delimiter, strip in pending:
                _body, j = _heredoc_body(text, j, delimiter, strip)
            pending = []
        else:
            level += (c == "(") - (c == ")")
            if level == 0:
                return j
            j += 1
    raise ParseError("an unbalanced $(")


def _substitutions(text: str) -> list[str]:
    """The `$(...)` and backtick texts in a heredoc body that expands, as a double-quoted string holds them."""
    found, j = [], 0
    while j < len(text):
        if text[j] == "\\":
            j += 2
        elif text.startswith("$(", j):
            end = _match_paren(text, j + 1)
            found.append(text[j + 2:end])
            j = end + 1
        elif text[j] == "`":
            end = _skip_backtick(text, j)
            found.append(_unescape_backtick(text[j + 1:end - 1]))
            j = end
        else:
            j += 1
    return found


def _unescape_backtick(inner: str) -> str:
    return re.sub(r"\\([`\\$])", r"\1", inner)


class _Scanner:
    """One pass over a line: its parts (words and heredoc bodies) and the texts of its substitutions."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.parts: list[_Part] = [_Part()]
        self.subs: list[str] = []
        self.word: list[str] | None = None
        self.pending: list[_Heredoc] = []

    def end_word(self) -> None:
        if self.word is not None:
            self.parts[-1].words.append("".join(self.word))
            self.word = None

    def add(self, chars: str) -> None:
        if self.word is None:
            self.word = []
        self.word.append(chars)

    def substitution(self, i: int, opener: int) -> int:
        """Record the substitution whose `(` is at `opener`; the word keeps its text. Returns the index after it."""
        end = _match_paren(self.text, opener)
        self.subs.append(self.text[opener + 1:end])
        self.add(self.text[i:end + 1])
        return end + 1

    def double_quoted(self, i: int) -> int:
        j, chars = i + 1, []
        while True:
            if j >= len(self.text):
                raise ParseError("an unbalanced double quote")
            c = self.text[j]
            if c == "\\" and j + 1 < len(self.text) and self.text[j + 1] in '$`"\\\n':
                chars.append(self.text[j + 1] if self.text[j + 1] != "\n" else "")
                j += 2
            elif c == '"':
                self.add("".join(chars))
                return j + 1
            elif self.text.startswith("$(", j):
                self.add("".join(chars))
                chars = []
                j = self.substitution(j, j + 1)
            elif c == "`":
                end = _skip_backtick(self.text, j)
                self.subs.append(_unescape_backtick(self.text[j + 1:end - 1]))
                chars.append(self.text[j:end])
                j = end
            else:
                chars.append(c)
                j += 1

    def newline(self, i: int) -> int:
        self.end_word()
        self.parts.append(_Part())
        j = i + 1
        for doc in self.pending:
            body, j = _heredoc_body(self.text, j, doc.delimiter, doc.strip_tabs)
            doc.part.stdin.append(body)
            if doc.expands:
                self.subs.extend(_substitutions(body))
        self.pending = []
        return j

    def scan(self) -> tuple[list[_Part], list[str]]:
        text, i = self.text, 0
        while i < len(text):
            c = text[i]
            if c == "\\":
                if text[i + 1:i + 2] != "\n":
                    self.add(text[i + 1:i + 2])
                i += 2
            elif c == "'":
                end = _skip_single(text, i)
                self.add(text[i + 1:end - 1])
                i = end
            elif c == '"':
                i = self.double_quoted(i)
            elif c == "`":
                end = _skip_backtick(text, i)
                self.subs.append(_unescape_backtick(text[i + 1:end - 1]))
                self.add(text[i:end])
                i = end
            elif text.startswith(("$(", "<(", ">("), i):
                i = self.substitution(i, i + 1)
            elif text.startswith("<<", i) and not text.startswith("<<<", i):
                self.end_word()
                delimiter, strip, expands, i = _heredoc_op(text, i)
                self.pending.append(_Heredoc(delimiter, strip, expands, self.parts[-1]))
            elif c == "\n":
                i = self.newline(i)
            elif c == "&" and (self.word and self.word[-1].endswith((">", "<")) or text[i + 1:i + 2] == ">"):
                self.add(c)             # 2>&1, >&2 and &> redirect; they do not end a command
                i += 1
            elif c in SEPARATORS:
                self.end_word()
                self.parts.append(_Part())
                i += 1
            elif c in " \t\r":
                self.end_word()
                i += 1
            else:
                self.add(c)
                i += 1
        self.end_word()
        return [p for p in self.parts if p.words or p.stdin], self.subs


def _options(words: list[str], takes_value: frozenset[str]) -> list[str]:
    """`words` after a wrapper's options: a value option also drops its value; `--` ends the options."""
    while words and words[0].startswith("-") and words[0] != "-":
        opt = words.pop(0)
        if opt == "--":
            break
        if opt in takes_value and words:
            words.pop(0)
    return words


def _unwrap(words: list[str], assigned: dict[str, str], from_input: bool, stdin: str,
            depth: int, rough: bool) -> list[SimpleCommand]:
    """The commands one part runs: assignments split off, then keywords, wrappers and shells removed."""
    if depth > MAX_DEPTH:
        raise TooDeep("nested shells or wrappers")
    words = list(words)
    while words:                                     # assignments and redirections may stand before the program
        redirect = REDIRECT.fullmatch(words[0])
        if redirect:
            words = words[1:] if redirect.group(2) else words[2:]
        elif ASSIGNMENT.fullmatch(words[0]):
            name, value = words.pop(0).split("=", 1)
            assigned[name] = value
        else:
            break
    if not words:
        return [SimpleCommand((), assigned, stdin, from_input)]
    head = base(words[0])
    if head in KEYWORDS:
        return _unwrap(words[1:], assigned, from_input, stdin, depth, rough)
    if head in CLOSERS:
        return _unwrap(words[1:], assigned, from_input, stdin, depth, rough) if len(words) > 1 else []
    if head in LOOP_HEADS:
        return []
    if head in WRAPPERS:
        rest = _options(words[1:], WRAPPERS[head])
        if head == "timeout" and rest:
            rest = rest[1:]                          # the duration
        return _unwrap(rest, assigned, from_input or head == "xargs", stdin, depth + 1, rough)
    if head == "flock":
        return _flock(words[1:], assigned, from_input, stdin, depth, rough)
    if head in LINE_WRAPPERS:
        rest = _options(words[1:], LINE_WRAPPERS[head])
        rest = rest[:next((i for i, w in enumerate(rest) if w in (":::", "::::")), len(rest))]
        return _expand(" ".join(rest), depth + 1, rough, from_input or head == "parallel", assigned) if rest else []
    if head in RUNNERS and len(words) > 1:
        rest = _options(words[1:], RUNNERS[head])
        if rest[:1] == ["run"]:
            return _unwrap(_options(rest[1:], RUNNERS[head]), assigned, from_input, stdin, depth + 1, rough)
    if head in SHELLS:
        rest = words[1:]
        while rest and rest[0].startswith(("-", "+")) and rest[0] not in ("-", "--"):
            opt = rest.pop(0)
            if opt in ("-o", "+o", "-O", "+O") and rest:
                rest.pop(0)
            elif opt.startswith("-") and not opt.startswith("--") and "c" in opt[1:]:
                inline = next((w for w in rest if not w.startswith("-")), "")
                return _expand(inline, depth + 1, rough, from_input, assigned)
        rest = rest[1:] if rest[:1] == ["--"] else rest
        if rest:
            return _unwrap(rest, assigned, from_input, stdin, depth + 1, rough)
        # a shell with no script or -c text runs its heredoc body
        return [SimpleCommand((words[0],), assigned, stdin, from_input),
                *(_expand(stdin, depth + 1, rough, from_input, assigned) if stdin else [])]
    found = [SimpleCommand(tuple(words), assigned, stdin, from_input)]
    if head == "find":
        for i, word in enumerate(words):
            if word in FIND_EXEC:
                inner = words[i + 1:]
                inner = inner[:next((k for k, w in enumerate(inner) if w in (";", "+", "\\;")), len(inner))]
                found += _unwrap(inner, {}, True, "", depth + 1, rough)
    return found


def _flock(args: list[str], assigned: dict[str, str], from_input: bool, stdin: str,
           depth: int, rough: bool) -> list[SimpleCommand]:
    """flock's command: `flock [opts] FILE CMD...`, or the text of -c/--command, which a shell runs."""
    while args and args[0].startswith("-") and args[0] != "--":
        opt = args.pop(0)
        if opt in ("-c", "--command") and args:
            return _expand(args[0], depth + 1, rough, from_input, assigned)
        if opt in FLOCK_VALUE and args:
            args.pop(0)
    args = args[1:] if args[:1] == ["--"] else args
    return _unwrap(args[1:], assigned, from_input, stdin, depth + 1, rough) if len(args) > 1 else []


def _expand(text: str, depth: int, rough: bool, from_input: bool = False,
            assigned: Mapping[str, str] | None = None) -> list[SimpleCommand]:
    """The commands in `text`; each part starts with the `assigned` words of the command that holds the text."""
    if depth > MAX_DEPTH:
        raise TooDeep("nested substitutions or shells")
    if rough:
        parts = [_Part(words=p.split()) for p in re.split(r"[;&|()\n]", text)]
        subs = [m.group(1) or m.group(2) or "" for m in re.finditer(r"\$\(([^()]*)\)|`([^`]*)`", text)]
    else:
        parts, subs = _Scanner(text).scan()
    found: list[SimpleCommand] = []
    for sub in subs:
        found += _expand(sub, depth + 1, rough)
    for part in parts:
        found += _unwrap(part.words, dict(assigned or {}), from_input, "\n".join(part.stdin), depth, rough)
    return found


def simple_commands(text: str) -> list[SimpleCommand]:
    """Every command `text` runs, substitutions first. Raises ParseError when the line cannot be split, and
    TooDeep when it nests past MAX_DEPTH."""
    return _expand(text, 0, rough=False)


def rough_commands(text: str) -> list[SimpleCommand]:
    """The fallback for a line simple_commands cannot split: separators and words split with quotes ignored,
    and only innermost substitutions read. Raises TooDeep only."""
    return _expand(text, 0, rough=True)
