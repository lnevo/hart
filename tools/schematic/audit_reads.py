#!/usr/bin/env python3
"""Run a script as __main__ under a Python audit hook and print the repo files it opens: "R path" for a read, "W path" for a write, "M path" for a read of a missing file, "D path" for a folder listed or
globbed, sorted.

    audit_reads.py SCRIPT [ARG ...]

Used by tests/test_panel_stamps.py to pin each make panels step's declared inputs (panel_stamps.STEPS): a file a step
reads that its declaration does not cover would let a stale output be skipped. Reads by a subprocess of the script
are not seen (the test names those steps; their declarations are coarse). The script's own exit code is ignored; its
output goes to stderr so stdout holds only the list.
With the pycache redirected (PYTHONPYCACHEPREFIX, empty), imports are read from source and show up as reads.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402
ROOT = paths.REPO_ROOT
READ: set[str] = set()
WRITTEN: set[str] = set()
MISSED: set[str] = set()      # opened for reading and not there
LISTED: set[str] = set()      # folders listed or globbed


def rel_of(path) -> str | None:
    if not isinstance(path, (str, os.PathLike)):
        return None
    try:
        return Path(os.path.abspath(os.fspath(path))).relative_to(ROOT).as_posix()
    except (ValueError, OSError):
        return None


def hook(event: str, args: tuple) -> None:
    if event == "open":
        rel = rel_of(args[0])
        mode = args[1] if isinstance(args[1], str) else "r"
        if rel is None:
            return
        if any(c in mode for c in "wxa"):
            WRITTEN.add(rel)
        elif "+" in mode:
            WRITTEN.add(rel)
            READ.add(rel)
        elif (ROOT / rel).is_file():
            READ.add(rel)
        elif not (ROOT / rel).exists():
            MISSED.add(rel)
    elif event in ("os.listdir", "os.scandir"):
        rel = rel_of(args[0] if args and args[0] is not None else ".")
        if rel is not None:
            LISTED.add(rel)
    elif event == "glob.glob":
        base = args[2] if len(args) > 2 and args[2] else None
        pattern = args[0]
        if isinstance(pattern, str):
            folder = rel_of(os.path.dirname(pattern) if base is None else os.path.join(base, os.path.dirname(pattern)))
            if folder is not None:
                LISTED.add(folder)
    elif event in ("os.rename", "os.replace"):
        for p in args[:2]:
            rel = rel_of(p)
            if rel:
                WRITTEN.add(rel)
    elif event == "os.remove":
        rel = rel_of(args[0])
        if rel:
            WRITTEN.add(rel)


def main() -> int:
    script, argv = Path(sys.argv[1]).resolve(), sys.argv[2:]
    sys.argv = [str(script), *argv]
    sys.path.insert(0, str(script.parent))
    sys.stdout = sys.stderr
    sys.addaudithook(hook)
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit:
        pass
    except BaseException as exc:  # noqa: BLE001 - the reads so far still count
        print(f"audit_reads: {script.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    lines = ([f"R {p}" for p in sorted(READ)] + [f"W {p}" for p in sorted(WRITTEN)]
             + [f"M {p}" for p in sorted(MISSED)] + [f"D {p}" for p in sorted(LISTED)])
    sys.__stdout__.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
