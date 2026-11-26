"""Logs the repo files a Python process (and its Python children) opens or lists, for tools/audit/check_stamps.py.

tools/check.sh puts this folder on PYTHONPATH for a job only when CHECK_AUDIT names a folder; any other run never
imports it. Each line is "<kind><TAB><path relative to CHECK_AUDIT_ROOT>": r (opened for reading), d (a folder listed).
"""
import os
import sys

_log = os.environ.get("CHECK_AUDIT_LOG")
_root = os.environ.get("CHECK_AUDIT_ROOT", "")
if _log and _root:
    _fd = os.open(_log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    _prefix = _root.rstrip("/") + "/"

    def _note(kind: str, path: object) -> None:
        try:
            p = os.fsdecode(path) if isinstance(path, (str, bytes, os.PathLike)) else None
        except Exception:
            return
        if p is None:
            return
        if not os.path.isabs(p):
            # A bare name may be relative to a directory fd (shutil.rmtree, copytree): log it only when it exists
            # under the working folder too, so a temp tree's names are not taken for repo files.
            p = os.path.join(os.getcwd(), p)
        if not os.path.lexists(p):          # a probe of a file that is not there reads nothing a stamp could hold
            return
        p = os.path.normpath(p)
        if kind == "r" and os.path.isdir(p):
            kind = "d"                      # a folder opened by os.open (shutil, git-like walkers) is a listing
        if p.startswith(_prefix):
            os.write(_fd, f"{kind}\t{p[len(_prefix):]}\n".encode())

    def _hook(event: str, args: tuple[object, ...]) -> None:
        if event == "open":
            path, mode, flags = args
            if isinstance(mode, str):
                if mode.startswith(("w", "a", "x")) and "+" not in mode:
                    return
            elif isinstance(flags, int) and flags & (os.O_WRONLY | os.O_CREAT):
                return
            _note("r", path)
        elif event in ("os.listdir", "os.scandir"):
            _note("d", args[0] if args[0] is not None else ".")

    sys.addaudithook(_hook)
