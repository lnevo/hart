"""The last hand-drawn files, read from git, for what still needs them after the cut-overs to the generated panels:
the Layout Editor tables.xml (Phase 5) and the CATS desks HART_CTC.xml and HART_ABS.xml (the CATS cut-over). Used by
the Layout Editor build (template_tables), the cut-over comparisons (parity of the generated panels with the hand-drawn ones) and
the tests of one-off scripts and pixel tables that only ever applied to the hand-drawn panels. No copy of an old file
is kept in the tree: each is read from the commit before its cut-over.

    path = hand_drawn.tables_path()            # tables.xml; a temporary file, once per process
    path = hand_drawn.cats_desk_path("HART_CTC.xml")
ValueError when git or the object is not there (a shallow clone, or no git); skip_unless_available() turns that into
unittest.SkipTest for tests.
"""
from __future__ import annotations

import atexit
import functools
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import paths

COMMIT = "1e79b457"         # main just before the Layout Editor cut-over: the last tables.xml with the hand-drawn panel
REL = "jmri/layouts/hart/output/tables.xml"
CATS_COMMIT = "42192d9c"    # main just before the CATS cut-over: the last hand-wired desks (wire_digicon.py)
CATS_DESKS = ("HART_CTC.xml", "HART_ABS.xml")
CATS_REL = "cats/panels/{}"


@functools.lru_cache(maxsize=None)
def file_bytes(rel: str, commit: str) -> bytes:
    """The file `rel` (repo-relative) at `commit`, from this checkout's git. ValueError when it is not there."""
    try:
        done = subprocess.run(["git", "-C", str(paths.REPO_ROOT), "show", f"{commit}:{rel}"],
                              capture_output=True, check=False)
    except OSError as exc:
        raise ValueError(f"cannot run git for the hand-drawn {rel} ({exc})") from None
    if done.returncode != 0 or not done.stdout:
        raise ValueError(f"the hand-drawn {commit}:{rel} is not in this checkout's git "
                         f"({done.stderr.decode(errors='replace').strip() or 'empty'})")
    return done.stdout


@functools.lru_cache(maxsize=None)
def file_path(rel: str, commit: str) -> Path:
    """A read-only temporary copy of `rel` at `commit` under its own name (one per process, removed at exit).
    Callers copy it before writing. ValueError as file_bytes."""
    data = file_bytes(rel, commit)
    folder = Path(tempfile.mkdtemp(prefix="hart-hand-drawn-"))
    atexit.register(shutil.rmtree, folder, True)
    path = folder / Path(rel).name
    path.write_bytes(data)
    path.chmod(0o444)
    return path


def tables_bytes(commit: str = COMMIT) -> bytes:
    """The hand-drawn tables.xml at `commit`."""
    return file_bytes(REL, commit)


def tables_path(commit: str = COMMIT) -> Path:
    """A temporary copy of the hand-drawn tables.xml at `commit`."""
    return file_path(REL, commit)


def cats_desk_path(name: str, commit: str = CATS_COMMIT) -> Path:
    """A temporary copy of the hand-wired CATS desk `name` (HART_CTC.xml or HART_ABS.xml) at `commit`."""
    if name not in CATS_DESKS:
        raise ValueError(f"{name!r} is not a hand-wired CATS desk ({', '.join(CATS_DESKS)})")
    return file_path(CATS_REL.format(name), commit)


def skip_unless_available(desk: str | None = None):
    """For tests: the hand-drawn tables' path, or with `desk` the hand-wired CATS desk's; unittest.SkipTest naming
    why it is missing."""
    import unittest
    if desk is not None and desk not in CATS_DESKS:     # a caller's mistake: raised, never a skip
        raise ValueError(f"{desk!r} is not a hand-wired CATS desk ({', '.join(CATS_DESKS)})")
    try:
        return cats_desk_path(desk) if desk else tables_path()
    except ValueError as exc:
        raise unittest.SkipTest(f"needs the last hand-drawn files from git: {exc}") from None
