"""Traced stamps: record what a step's Python processes really read, and skip the step while all of that is unchanged.

Shared by tools/schematic/panel_stamps.py (the make panels steps) and tools/audit/check_stamps.py (the tools/check.sh
jobs), like a compiler's depfile. Two halves:

Capture. A runner sets HART_TRACE_LOG=<file> and puts tools/audit/trace_hook on PYTHONPATH; its sitecustomize calls
install() in every Python process that starts with that environment (the step and its Python children). The hook
appends one line per event to the log ("<pid>\\t<kind>\\t<data>"):

    s  a process started: ppid, the spawn token it inherited, start time (ns), argv[0]
    r  a file opened for reading (an import's .pyc counts as its source)      w  a file written, renamed or removed
    c  a file opened for reading as code: imported, run as the main script or by runpy, or shown in a traceback.
       The stamps hash it like an "r" read; the declaration audit takes only the "r" lines (a file read both ways
       has both, so its data read is still audited)
    m  a file probed (opened or stat'ed) and not there                         p  a file or folder stat'ed and there
    d  a folder listed (listdir, scandir, glob)                                x  a subprocess spawned: token, cwd, argv
    h  a shutil.which lookup on the starting PATH: the name, what it found      k  a unittest skip: the test's id, reason
    b  written by the runner, not the hook: one Python process it starts and expects to see a "s" line from
    t  written by the runner: the time (ns) it started a program the hook cannot see, so a log with no "s" line
       still says since when a file the job read must be unchanged (changed_since)

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

LOG_ENV, ROOT_ENV, TOKEN_ENV, PATH_ENV = "HART_TRACE_LOG", "HART_TRACE_ROOT", "HART_TRACE_SPAWN", "HART_TRACE_PATH"

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
    _patch_which()
    if _runs_unittest(argv):
        _patch_skips()
    sys.addaudithook(_hook)
    return True


def _runs_unittest(argv: list[str]) -> bool:
    """Whether the process was started as `python ... -m unittest ...`."""
    return any(a == "-m" and argv[i + 1:i + 2] == ["unittest"] for i, a in enumerate(argv))


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
            code = _opened_as_code()
            real = os.path.realpath(p)
            for q in (p, real) if real != p else (p,):    # a link (a .cache view of the data) reads its target too
                _write("c" if code else "r", q)
        else:
            _write("m", p)


# The frames that open a file as code, by file name: the frozen importlib module, or its source file in an
# interpreter built without the frozen copy.
_IMPORTLIB = ("<frozen importlib._bootstrap_external>", os.path.join("importlib", "_bootstrap_external.py"))


def _opened_as_code(frame=None) -> bool:
    """Whether the open being traced loads code, by the first frame above the hook (`frame`, for tests): none at all
    (the interpreter opening the main script), zipimport (asking whether the script is a zip of code), importlib's
    get_data called by its get_code (an import: the source or its .pyc), runpy reading a script it runs, or
    tokenize.open called by linecache (the source of a frame in a traceback or a warning). Every other open reads the
    file as data: pkgutil.get_data and importlib.resources included."""
    f = frame if frame is not None else sys._getframe(1)
    while frame is None and f is not None and f.f_code.co_filename == __file__:
        f = f.f_back
    if f is None:
        return True
    name, file, up = f.f_code.co_name, f.f_code.co_filename, f.f_back
    if file.endswith(_IMPORTLIB) and name == "get_data":
        return up is not None and up.f_code.co_filename.endswith(_IMPORTLIB) and up.f_code.co_name == "get_code"
    if name == "_get_code_from_file" and (file == "<frozen runpy>" or os.path.basename(file) == "runpy.py"):
        return True
    if file == "<frozen zipimport>" or os.path.basename(file) == "zipimport.py":
        return True         # the import system asks whether a script or a sys.path entry is a zip of code
    return (name == "open" and os.path.basename(file) == "tokenize.py" and up is not None
            and os.path.basename(up.f_code.co_filename) == "linecache.py")


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


def _patch_which() -> None:
    """shutil.which notes a lookup on the PATH the job started with ("h": the name, and what it found or nothing),
    so a test that skips when a tool is missing (pwsh, flock) runs again once the tool is there. The job's first
    traced process hands its PATH to its children (HART_TRACE_PATH); a lookup on another PATH (a child started with a
    test's stub folder on it), or with an explicit path or mode, is no input of the job and is not noted."""
    import shutil
    real, start_path = shutil.which, os.environ.setdefault(PATH_ENV, os.environ.get("PATH", ""))

    def which(cmd, mode=os.F_OK | os.X_OK, path=None):
        found = real(cmd, mode, path)
        try:
            if path is None and mode == os.F_OK | os.X_OK and isinstance(cmd, str) \
                    and os.environ.get("PATH", "") == start_path:
                _write("h", _words([cmd, found or ""]))
        except Exception:  # noqa: BLE001 - tracing must never break the traced program
            pass
        return found
    which.__wrapped__ = real
    which.__doc__ = real.__doc__
    shutil.which = which


def _patch_skips() -> None:
    """In a `python -m unittest` process, every skip ("k": the test's id and the reason; a skipped class reports each
    of its tests, a skipped class or module fixture reports itself once, as unittest does). tools/audit/check_stamps.py
    puts them in the stamp's key, so a job whose tests skipped may record a stamp that says which and why."""
    import unittest.result
    real = unittest.result.TestResult.addSkip

    def add_skip(self, test, reason):
        try:
            _write("k", _words([test.id(), str(reason)]))
        except Exception:  # noqa: BLE001
            pass
        return real(self, test, reason)
    unittest.result.TestResult.addSkip = add_skip


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


HOOK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trace_hook")
# This file, its parts and the hook that loads it, from the repo root. Each is in the stamps' key (check_stamps
# ALWAYS, panel_stamps CODE) and in tools/ci/stamp_gate.MACHINERY, so editing a part reruns what editing this does.
PARTS = ("traced_read",)
HOOK_FILES = ("tools/audit/traced.py", *(f"tools/audit/{p}.py" for p in PARTS),
              "tools/audit/trace_hook/sitecustomize.py")


def _import_part(stem: str) -> None:
    """Import a part of this file as the module `stem`, from this file's folder.

    The hook and panel_stamps load traced.py by path, with nothing of the repo on sys.path, so the folder is put on
    sys.path for this one import and taken off again: a traced process sees no change to its sys.path. A part
    already imported from another folder is refused, so a copy of traced.py never runs with another copy's part.
    """
    import importlib
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, f"{stem}.py")
    if not os.path.isfile(path):
        raise ImportError(f"traced: its part {path} is missing")
    mod = sys.modules.get(stem)
    if mod is None:
        sys.path.insert(0, here)
        try:
            mod = importlib.import_module(stem)
        finally:
            sys.path.remove(here)
    got = os.path.dirname(os.path.abspath(getattr(mod, "__file__", None) or ""))
    if os.path.normcase(os.path.realpath(got)) != os.path.normcase(os.path.realpath(here)):
        raise ImportError(f"traced: its part {stem} was imported from {got}, not from {here}")


_import_part("traced_read")     # the one part in PARTS; the capture half calls its listing() and kind_of()
# The read half's names are traced's own: callers use traced.parse, traced.read_set and the rest.
from traced_read import (  # noqa: E402,F401
    GIT_READ, GIT_READ_IF, LITTER_NAMES, PYTHON_NAME, ROOT_MARK, RUNNER_PID, VERSION, _ROOT_FORMS, Trace, _abs,
    _root_forms, _skip_prefixes, changed_since, git_replay, git_reads_only, git_subcommand, hash_entries, keep,
    kind_of, listing, load, make_stamp, mismatch, parse, problem, program, read_set, save, sha_file, snapshot,
    traced_spawns, untraced,
)
