"""Traced stamps: record what a step's Python processes really read, and skip the step while all of that is unchanged.

Shared by tools/schematic/panel_stamps.py (the make panels steps) and tools/audit/check_stamps.py (the tools/check.sh
jobs), like a compiler's depfile. Two halves:

Capture. A runner sets HART_TRACE_LOG=<file> and puts tools/audit/trace_hook on PYTHONPATH; its sitecustomize calls
install() in every Python process that starts with that environment (the step and its Python children). The hook
appends one line per event to the log ("<pid>\\t<kind>\\t<data>"):

    s  a process started: ppid, the spawn token it inherited, start time (ns), argv[0]
    r  a file opened for reading (an import's .pyc counts as its source)      w  a file written, renamed or removed
    m  a file probed (opened or stat'ed) and not there                         p  a file or folder stat'ed and there
    d  a folder listed (listdir, scandir, glob)                                x  a subprocess spawned: token, cwd, argv
    b  written by the runner, not the hook: one Python process it starts and expects to see a "s" line from

Paths are relative to the repo root (HART_TRACE_ROOT) or absolute for files outside it. A spawn hands its child a
token (HART_TRACE_SPAWN); a child whose "s" line carries it, as the spawner's child or its exec, was traced. Any other
spawn ran a program the hook cannot see (git, bash, Chrome, a Python child with the hook dropped): see untraced().

Record and compare. read_set() turns a log into the files read (content), the misses (still absent), the folders
listed (their names) and the paths stat'ed (still there, same type), leaving out .cache/ (shared caches keyed on
content), __pycache__, .git internals and the schematic plugin (stamped by its commit). A stamp is JSON holding a key
(the caller's digest of command, code, interpreter, plugin, environment) and that read set with its hashes;
mismatch() is None only when the key and every entry match. The safety rules: no stamp means run; a log with no
process start, or fewer Python processes than the runner started (problem()), means run and record nothing; a
spawn the hook did not see into (a Python child that dropped the hook counts) is listed by untraced(), and the
callers either refuse to record (make panels) or add their wide declarations (check.sh); a file, folder or absence
the job saw that changed after the job started (changed_since) records nothing.
"""
from __future__ import annotations

import os
import sys

LOG_ENV, ROOT_ENV, TOKEN_ENV = "HART_TRACE_LOG", "HART_TRACE_ROOT", "HART_TRACE_SPAWN"
VERSION = 1
LITTER_NAMES = {"__pycache__", ".DS_Store"}

# ---------------------------------------------------------------- capture (runs inside every traced process)

_state: dict = {}


def install() -> bool:
    """Start tracing this process into HART_TRACE_LOG; False (and nothing done) when it is not set."""
    log, root = os.environ.get(LOG_ENV), os.environ.get(ROOT_ENV)
    if not log or not root or _state:
        return False
    import threading
    import time
    fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    now = time.time_ns()
    _state.update(fd=fd, root=os.path.normpath(root) + os.sep, pid=os.getpid(), n=0, lock=threading.Lock(),
                  last_popen=None, prefix=getattr(sys, "pycache_prefix", None), busy=threading.local(), born=now)
    argv = list(getattr(sys, "orig_argv", None) or sys.argv or [""])
    _write("s", f"{os.getppid()}\t{os.environ.get(TOKEN_ENV, '')}\t{now}\t{_words(argv)}")
    os.register_at_fork(after_in_child=_after_fork)
    _patch_stat()
    sys.addaudithook(_hook)
    return True


def _after_fork() -> None:
    # a forked child (no exec) keeps the hook; its lines carry its own pid, attributed by its "s" line
    import time
    _state["pid"], _state["born"], _state["n"] = os.getpid(), time.time_ns(), 0
    _write("s", f"{os.getppid()}\tfork\t0\tfork")


def _words(argv) -> str:
    """argv as tab-separated words (tabs and newlines inside a word made spaces)."""
    try:
        words = [os.fsdecode(a) for a in (argv if isinstance(argv, (list, tuple)) else [argv])]
    except Exception:  # noqa: BLE001
        words = [repr(argv)]
    return "\t".join(w.replace("\t", " ").replace("\n", " ") for w in words)


def _write(kind: str, data: str) -> None:
    try:
        os.write(_state["fd"], f"{_state['pid']}\t{kind}\t{data}\n".encode("utf-8", "surrogateescape"))
    except OSError:
        pass


def _path(path, dir_fd=None) -> str | None:
    """The absolute normalised path of an event's path argument, or None (a file descriptor, a path relative to a
    directory fd, bytes that will not decode)."""
    if dir_fd is not None or isinstance(path, int):
        return None
    try:
        p = os.fsdecode(path) if isinstance(path, (str, bytes, os.PathLike)) else None
    except Exception:  # noqa: BLE001 - an odd argument is no path
        return None
    if not p:
        return None
    return os.path.normpath(os.path.join(os.getcwd(), p)) if not os.path.isabs(p) else os.path.normpath(p)


def _source_of_pyc(p: str) -> str:
    """An import's cached .pyc stands for its source: dir/__pycache__/m.cpython-313.pyc -> dir/m.py (and the same
    under PYTHONPYCACHEPREFIX, where the cached copy sits below the prefix at the source's own folder)."""
    if not p.endswith(".pyc"):
        return p
    folder, name = os.path.split(p)
    stem = name.split(".", 1)[0]
    if os.path.basename(folder) == "__pycache__":
        return os.path.join(os.path.dirname(folder), stem + ".py")
    prefix = _state.get("prefix")
    if prefix and p.startswith(os.path.normpath(prefix) + os.sep):
        return os.path.join(folder[len(os.path.normpath(prefix)):] or os.sep, stem + ".py")
    return p


def _hook(event: str, args: tuple) -> None:
    if event not in _EVENTS:
        return
    busy = _state["busy"]
    if getattr(busy, "on", False):
        return
    busy.on = True
    try:
        _EVENTS[event](args)
    except Exception:  # noqa: BLE001 - tracing must never break the traced program
        pass
    finally:
        busy.on = False


def _on_open(args) -> None:
    path, mode, flags = args
    p = _path(path)
    if p is None:
        return
    if isinstance(mode, str):
        writes, reads = any(c in mode for c in "wax+"), "r" in mode      # "w+" truncates: nothing of it is read
    else:
        flags = flags if isinstance(flags, int) else 0
        acc = flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)
        writes = acc != os.O_RDONLY or bool(flags & (os.O_CREAT | os.O_TRUNC))
        reads = acc == os.O_RDONLY or (acc == os.O_RDWR and not flags & os.O_TRUNC)
    if writes:
        _write("w", p)
    if reads:
        p = _source_of_pyc(p)
        if os.path.isdir(p):
            _write_listing(p)       # a folder opened by os.open (os.walk with fd, shutil) is a listing
        elif os.path.exists(p):
            _write("r", p)
            real = os.path.realpath(p)
            if real != p:
                _write("r", real)   # a link (a .cache view linking back to the data folder) reads its target
        else:
            _write("m", p)


def _on_list(args) -> None:
    p = _path(args[0] if args and args[0] is not None else ".")
    if p is not None:
        _write_listing(p)


def _write_listing(p: str) -> None:
    """A listing with the hash of the names the folder held when it was listed (the same as listing() at compare
    time), so a name added or removed while the job still runs is told from the job's own view."""
    _write("d", f"{p}\t{listing(p) or kind_of(p)}")


def _on_glob(args) -> None:
    # "glob.glob/2" (pathname, recursive, root_dir, dir_fd); the plain "glob.glob" event of the same call is ignored
    pattern, root_dir = args[0], (args[2] if len(args) > 2 else None)
    if isinstance(pattern, (str, bytes)):
        pattern = os.fsdecode(pattern)
        head = pattern.split("*", 1)[0].split("?", 1)[0].split("[", 1)[0]
        folder = os.path.dirname(head) or "."
        p = _path(os.path.join(os.fsdecode(root_dir), folder) if root_dir else folder)
        if p is not None:
            _write_listing(p)


def _on_write(args) -> None:
    for a in args[:2]:
        p = _path(a)
        if p is not None:
            _write("w", p)


def _on_remove(args) -> None:
    p = _path(args[0])
    if p is not None:
        _write("w", p)


def _spawn(argv, cwd, env) -> None:
    """Note a spawn and hand the child its token: in the env mapping it is given, or in os.environ (inherited)."""
    with _state["lock"]:
        _state["n"] += 1
        # pid, the process's start time and a count: unique even across an exec (same pid) or a reused pid
        token = f"{_state['pid']}:{_state['born']}:{_state['n']}"
    target = env if isinstance(env, dict) else (os.environ if env is None else None)
    if target is not None:
        try:
            target[TOKEN_ENV] = token
        except Exception:  # noqa: BLE001
            pass
    here = _path(cwd) if cwd is not None else os.getcwd()
    _write("x", f"{token}\t{here or ''}\t{_words(argv)}")


def _on_popen(args) -> None:
    executable, argv, cwd, env = args
    words = list(argv) if isinstance(argv, (list, tuple)) else [argv]
    _state["last_popen"] = words
    _spawn(words, cwd, env)


def _on_posix_spawn(args) -> None:
    path, argv, env = args[:3]
    if _state.get("last_popen") is not None and list(argv) == _state["last_popen"]:
        _state["last_popen"] = None     # subprocess's own posix_spawn of the Popen just noted
        return
    _spawn(list(argv), None, env)


def _on_system(args) -> None:
    _spawn(["sh", "-c", os.fsdecode(args[0])], None, None)


def _on_exec(args) -> None:
    path, argv, env = args[:3]
    _spawn(list(argv), None, env)


def _on_spawn(args) -> None:
    mode, path, argv, env = args[:4]
    _spawn(list(argv), None, env)


_EVENTS = {
    "open": _on_open, "os.listdir": _on_list, "os.scandir": _on_list, "glob.glob/2": _on_glob,
    "os.rename": _on_write, "os.replace": _on_write, "os.remove": _on_remove, "os.rmdir": _on_remove,
    "shutil.rmtree": _on_remove, "subprocess.Popen": _on_popen, "os.posix_spawn": _on_posix_spawn,
    "os.system": _on_system, "os.exec": _on_exec, "os.spawn": _on_spawn,
}


def _patch_stat() -> None:
    """os.stat and os.lstat note a probe: a miss for an absent path, a presence for one that is there. The import
    system keeps its own reference to the C functions, so module lookups along sys.path are not noted (the folder
    listings it takes are)."""
    real_stat, real_lstat = os.stat, os.lstat

    def wrap(real):
        def probe(path, *args, dir_fd=None, follow_symlinks=True):
            try:
                st = real(path, *args, dir_fd=dir_fd, follow_symlinks=follow_symlinks) if real is real_stat \
                    else real(path, *args, dir_fd=dir_fd)
            except FileNotFoundError:
                _note_probe(path, dir_fd, None)
                raise
            except NotADirectoryError:
                _note_probe(path, dir_fd, None)
                raise
            _note_probe(path, dir_fd, st)
            return st
        probe.__wrapped__ = real
        probe.__name__ = real.__name__
        probe.__doc__ = real.__doc__
        return probe
    os.stat, os.lstat = wrap(real_stat), wrap(real_lstat)


def _note_probe(path, dir_fd, st) -> None:
    busy = _state["busy"]
    if getattr(busy, "on", False):
        return
    busy.on = True
    try:
        p = _path(path, dir_fd)
        if p is not None:
            if st is None:
                _write("m", p)
            else:
                import stat as _st
                _write("p", f"{'d' if _st.S_ISDIR(st.st_mode) else f'f:{st.st_size}'}\t{p}")
    except Exception:  # noqa: BLE001
        pass
    finally:
        busy.on = False


# ---------------------------------------------------------------- reading a log


class Trace:
    """A parsed HART_TRACE_LOG."""

    def __init__(self) -> None:
        self.reads: set[str] = set()
        self.writes: set[str] = set()
        self.misses: set[str] = set()
        self.present: dict[str, str] = {}
        self.listed: set[str] = set()
        self.listed_as: dict[str, str] = {}                     # folder -> its names' hash when first listed
        self.starts: list[tuple[int, int, str, int]] = []      # pid, ppid, token, time ns
        self.start_argv: list[list[str]] = []                   # the argv of each start, in the same order
        self.spawns: list[tuple[int, str, str, list[str]]] = []  # pid, token, cwd, argv
        self.expected_roots = 0

    @property
    def started_ns(self) -> int | None:
        times = [t for *_, t in self.starts if t]
        return min(times) if times else None


def parse(log: str | os.PathLike) -> Trace:
    t = Trace()
    try:
        with open(log, encoding="utf-8", errors="surrogateescape") as f:
            text = f.read()
    except OSError:
        return t
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        pid_s, kind, rest = parts[0], parts[1], parts[2:]
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        if kind == "b":
            t.expected_roots += 1
        elif kind == "s" and len(rest) >= 3:
            try:
                t.starts.append((pid, int(rest[0]), rest[1], int(rest[2])))
                t.start_argv.append(rest[3:])
            except ValueError:
                pass
        elif kind == "x" and len(rest) >= 2:
            t.spawns.append((pid, rest[0], rest[1], rest[2:]))
        elif kind == "d" and len(rest) == 2:
            t.listed.add(rest[0])
            t.listed_as.setdefault(rest[0], rest[1])
        elif kind == "p" and len(rest) == 2:
            t.present.setdefault(rest[1], rest[0])
        elif rest:
            {"r": t.reads, "w": t.writes, "m": t.misses, "d": t.listed}.get(kind, set()).add(rest[0])
    return t


PYTHON_NAME = __import__("re").compile(r"python[0-9.]*$|Python$")


def traced_spawns(t: Trace) -> set[str]:
    """The tokens of the spawns whose child loaded the hook: a "s" line carrying the token, from the spawner's child
    (fork and exec) or from the spawner itself (exec), whose own argv ends with the spawn's arguments. So a Python
    started by a shell's -c string (its other commands unseen), or one that inherited a stale token, matches nothing;
    a bare interpreter spawn (no arguments) matches only when it was a Python."""
    by_token = {s[1]: (s[0], s[3]) for s in t.spawns}
    done = set()
    for (pid, ppid, token, _t), child in zip(t.starts, t.start_argv):
        spawner, argv = by_token.get(token, (None, None))
        if spawner is None or spawner not in (pid, ppid):
            continue
        args = argv[1:]
        if args and child[-len(args):] == args or not args and PYTHON_NAME.search(program(argv)):
            done.add(token)
    return done


def problem(t: Trace) -> str | None:
    """Why the log is no trace to record, or None: no process loaded the hook, or fewer than the runner started."""
    if not t.starts:
        return "the trace hook did not load (no process start in the log)"
    tokens = {s[1] for s in t.spawns}
    roots = [s for s in t.starts if s[2] not in tokens and s[2] != "fork"]
    if len(roots) < t.expected_roots:
        return f"the trace hook loaded in {len(roots)} of the {t.expected_roots} Python processes started"
    return None


# git subcommands that only read (refs, index, objects, the working tree): a recorded one is run again at compare
# time and its output compared (git_replay), so what it read is covered whatever it was
GIT_READ = {"rev-parse", "merge-base", "symbolic-ref", "rev-list", "log", "show", "cat-file", "ls-tree", "describe",
            "for-each-ref", "show-ref", "ls-files", "version", "--version", "name-rev", "diff", "check-ignore"}
GIT_READ_IF = {"config": {"--get", "--list", "-l", "--get-all", "--get-regexp"}, "worktree": {"list"}}
ROOT_MARK = "{root}"


def git_subcommand(argv: list[str]) -> tuple[str | None, str | None, int]:
    """git's subcommand, its -C folder and the subcommand's index in argv (None, None, len when there is none)."""
    i, where = 1, None
    while i < len(argv):
        a = argv[i]
        if a == "-C" and i + 1 < len(argv):
            where = argv[i + 1]
            i += 2
        elif a in ("-c", "--git-dir", "--work-tree", "--namespace") and i + 1 < len(argv):
            i += 2
        elif a.startswith("-") and a != "--version":
            i += 1
        else:
            return a, where, i
    return None, where, i


def git_reads_only(argv: list[str]) -> bool:
    sub, _, i = git_subcommand(argv)
    if sub in GIT_READ:
        return True
    return sub in GIT_READ_IF and bool(GIT_READ_IF[sub] & set(argv[i + 1:]))


def program(argv: list[str]) -> str:
    return os.path.basename(argv[0]) if argv else ""


def untraced(t: Trace, root: str, also_inside: tuple[str, ...] = ()) -> tuple[list[str], list[list[str]]]:
    """The programs the hook could not see that may have read the checkout (sorted, one entry per program), and the
    read-only git commands (cwd first, then argv, the root written as {root}) to replay at compare time. A spawn is
    left out when its child loaded the hook, or when it ran outside the checkout: its folder (cwd, git -C) is outside
    `root` and every `also_inside` folder (the main checkout of a worktree) and no argument names one of them (a
    test's git in a scratch repo). A Python child that did not load the hook counts as a program."""
    done = traced_spawns(t)
    homes = [f for p in (root, *also_inside) if p for f in _root_forms(p)]
    progs, gits = set(), []

    def inside(p: str) -> bool:
        return any(p == h or p.startswith(h + os.sep) for h in homes)

    for _pid, token, cwd, argv in t.spawns:
        if token in done:
            continue
        name = program(argv)
        where = cwd
        if name == "git":
            c = git_subcommand(argv)[1]
            if c:
                where = os.path.normpath(os.path.join(cwd, c))
        if not inside(where) and not any(h in a for a in argv for h in homes):
            continue
        if name == "git":
            if git_reads_only(argv):
                cmd = [cwd, *argv]
                for r in _root_forms(root):
                    cmd = [a.replace(r, ROOT_MARK, 1) if (a == r or a.startswith(r + os.sep)) else a for a in cmd]
                if cmd not in gits:
                    gits.append(cmd)
                continue
            progs.add(f"git {git_subcommand(argv)[0] or ''}".strip())
            continue
        progs.add(name)
    return sorted(progs), gits


def git_replay(cmds: list[list[str]], root: str) -> list[str]:
    """sha256 of each recorded git command's exit code and output, run now in this checkout."""
    import hashlib
    import subprocess
    out = []
    for cmd in cmds:
        cmd = [a.replace(ROOT_MARK, os.path.normpath(root), 1) for a in cmd]
        cwd, argv = cmd[0], cmd[1:]
        try:
            done = subprocess.run(argv, cwd=cwd if os.path.isdir(cwd) else None, capture_output=True, timeout=60)
            out.append(hashlib.sha256(f"{done.returncode}\0".encode() + done.stdout).hexdigest())
        except (OSError, subprocess.SubprocessError) as exc:
            out.append(f"unavailable:{type(exc).__name__}")
    return out


# ---------------------------------------------------------------- the read set


def _skip_prefixes(root: str) -> tuple[str, ...]:
    import tempfile
    out = {"/dev/", "/proc/", "/sys/", "/System/", "/usr/", "/Library/", "/opt/", "/etc/", "/private/etc/",
           "/bin/", "/sbin/", "/Applications/", "/private/var/", "/var/", "/tmp/", "/private/tmp/",
           os.path.expanduser("~/Library/")}
    for p in (tempfile.gettempdir(), sys.prefix, sys.base_prefix, sys.exec_prefix):
        if p:
            out.add(os.path.normpath(p) + os.sep)
            out.add(os.path.realpath(p) + os.sep)
    return tuple(sorted(out))


_ROOT_FORMS: dict[str, tuple[str, ...]] = {}


def _root_forms(root: str) -> tuple[str, ...]:
    if root not in _ROOT_FORMS:
        _ROOT_FORMS[root] = tuple(dict.fromkeys((os.path.normpath(root), os.path.realpath(root))))
    return _ROOT_FORMS[root]


def keep(path: str, root: str, skip: tuple[str, ...]) -> str | None:
    """The stamp's name for a traced path (relative to `root`, or absolute outside it), or None for one a stamp
    leaves out: any .cache folder (shared caches keyed on content), __pycache__ and Finder litter, .git internals,
    the schematic plugin (its commit is in the key), the system and the interpreter, temp folders."""
    p = os.path.normpath(path)
    rel = None
    for r in _root_forms(root):         # the root as given and its real path (a process's cwd is the real one)
        if p == r:
            rel = "."
        elif p.startswith(r + os.sep):
            rel = p[len(r) + 1:]
        if rel is not None:
            break
    parts = (rel or p).split(os.sep)
    if ".cache" in parts or LITTER_NAMES & set(parts) or "site-packages" in parts or ".git" in parts[:-1] \
            or (".git" in parts and parts[-1] != ".git"):
        return None
    if rel is not None:
        if rel == "external/model-railroad-skills" or rel.startswith("external/model-railroad-skills/"):
            return None
        return rel
    if p.startswith(skip) or p + os.sep in skip:
        return None
    real = os.path.realpath(p)          # a link to the interpreter (uv's cpython-3.13-<platform> folder)
    if real != p and (real.startswith(skip) or real + os.sep in skip):
        return None
    return p


def sha_file(p: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def listing(p: str) -> str | None:
    """sha256 of a folder's names (litter left out), or None when it is no folder."""
    import hashlib
    try:
        names = sorted(n for n in os.listdir(p) if n not in LITTER_NAMES and not n.endswith(".pyc"))
    except OSError:
        return None
    return hashlib.sha256("\0".join(names).encode("utf-8", "surrogateescape")).hexdigest()


def kind_of(p: str) -> str:
    """"d" for a folder, "f:<size>" for a file (a check may decide on the size alone), "-" when absent."""
    if os.path.isdir(p):
        return "d"
    try:
        return f"f:{os.stat(p).st_size}"
    except OSError:
        return "-"


def read_set(t: Trace, root: str) -> dict[str, list[str]]:
    """{files, missing, dirs, present}: the stamp names of what the trace read, probed absent, listed and stat'ed."""
    skip = _skip_prefixes(root)

    def names(paths):
        return {n for n in (keep(p, root, skip) for p in paths) if n is not None}
    files = names(t.reads)
    missing = names(t.misses) - files
    dirs = names(t.listed)
    present = {n for n in names(t.present) if n not in files and n not in dirs} - missing
    return {"files": sorted(files), "missing": sorted(missing), "dirs": sorted(dirs), "present": sorted(present)}


def _abs(name: str, root: str) -> str:
    return name if os.path.isabs(name) else os.path.join(root, name)


def hash_entries(rs: dict[str, list[str]], root: str, hasher=None) -> dict[str, dict[str, str]]:
    """The read set's state now: a file's sha256 (or "-" when it is gone: a temp file the job made and removed),
    a folder's listing, a missing or stat'ed path's kind."""
    hasher = hasher or sha_file
    out: dict[str, dict[str, str]] = {"files": {}, "missing": {}, "dirs": {}, "present": {}}
    for n in rs["files"]:
        p = _abs(n, root)
        out["files"][n] = hasher(p) if os.path.isfile(p) else kind_of(p)
    for n in rs["missing"]:
        out["missing"][n] = kind_of(_abs(n, root))
    for n in rs["dirs"]:
        out["dirs"][n] = listing(_abs(n, root)) or kind_of(_abs(n, root))
    for n in rs["present"]:
        out["present"][n] = kind_of(_abs(n, root))
    return out


def changed_since(t: Trace, rs: dict[str, list[str]], root: str, extra_files=()) -> list[str]:
    """The read files (and `extra_files`) the job did not write that were modified after it started: their content
    now may not be what the job read, so nothing may be recorded."""
    since = t.started_ns
    if since is None:
        return ["(no start time)"]
    skip = _skip_prefixes(root)
    written = {n for n in (keep(p, root, skip) for p in t.writes) if n is not None}
    late = []
    for n in [*rs["files"], *extra_files]:
        if n in written:
            continue
        try:
            if os.stat(_abs(n, root)).st_mtime_ns >= since:
                late.append(n)
        except OSError:
            late.append(n)              # read, not written by the job, and gone now
    holders = {os.path.dirname(w) or "." for w in written} | written
    as_listed = {n: v for n, v in ((keep(p, root, skip), v) for p, v in t.listed_as.items()) if n is not None}
    for n in rs["dirs"]:
        if n in holders:
            continue                    # the job made or removed something in it itself
        p = _abs(n, root)
        if as_listed.get(n, None) not in (None, listing(p) or kind_of(p)):
            late.append(n)              # its names now are not the ones the job listed
    seen = {n: v for n, v in ((keep(p, root, skip), v) for p, v in t.present.items()) if n is not None}
    for n in rs["missing"]:
        if n not in written and kind_of(_abs(n, root)) != "-":
            late.append(n)
    for n in rs["present"]:
        if n not in written and n not in holders and seen.get(n) not in (None, kind_of(_abs(n, root))):
            late.append(n)
    return late


def make_stamp(key: str, t: Trace, root: str, hasher=None, **meta) -> dict:
    rs = read_set(t, root)
    return {"version": VERSION, "key": key, **meta, "state": hash_entries(rs, root, hasher)}


def mismatch(stamp: dict | None, key: str, root: str, hasher=None) -> str | None:
    """None when `stamp` holds `key` and its read set is as recorded, else the first difference (for a message)."""
    if not stamp or stamp.get("version") != VERSION:
        return "no traced stamp"
    if stamp.get("key") != key:
        return "the code, command, interpreter, plugin or environment changed"
    st = stamp.get("state") or {}
    rs = {k: sorted((st.get(k) or {})) for k in ("files", "missing", "dirs", "present")}
    now = hash_entries(rs, root, hasher)
    for k, label in (("files", "read"), ("missing", "absent"), ("dirs", "listed"), ("present", "stat'ed")):
        for n, v in (st.get(k) or {}).items():
            if now[k].get(n) != v:
                return f"{label} {n} changed"
    return None


def load(path) -> dict | None:
    import json
    try:
        with open(path, encoding="utf-8") as f:
            return json.loads(f.read())
    except (OSError, ValueError):
        return None


def save(path, stamp: dict) -> None:
    import json
    os.makedirs(os.path.dirname(os.fspath(path)), exist_ok=True)
    tmp = f"{os.fspath(path)}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(stamp, f, sort_keys=True)
    os.replace(tmp, path)


def snapshot(root, *parts: str) -> str:
    """What the stamp key takes from outside the traced files and may change while a job runs (HEAD, origin/main,
    their merge base, and the callers' `parts`: the plugin state, the outside state), as one sha256. A runner takes
    it before the job and the recorder again after: a difference records nothing, since the key is worked out after
    the job and would hold the new state as if the job had seen it."""
    import hashlib
    import subprocess

    def run(*a) -> str:
        try:
            r = subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return "unavailable"
        return r.stdout.strip() if r.returncode == 0 else f"failed:{r.returncode}"
    text = "\0".join((run("rev-parse", "HEAD"), run("rev-parse", "origin/main"),
                      run("merge-base", "HEAD", "origin/main"), *parts))
    return hashlib.sha256(text.encode()).hexdigest()


HOOK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trace_hook")
HOOK_FILES = ("tools/audit/traced.py", "tools/audit/trace_hook/sitecustomize.py")
