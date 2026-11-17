"""The last hand-drawn tables.xml, read from git, for what still needs the hand-drawn "HART Railroad" panel after the
Layout Editor cut-over (Phase 5): the frozen inputs' --freeze, the cut-over comparisons, and the tests of one-off
scripts and pixel tables that only ever applied to that panel. The repo's tables.xml holds the generated panel now;
no copy of the old file is kept in the tree: it is read from the commit before the cut-over.

    path = hand_drawn.tables_path()      # a temporary file, written once per process; ValueError when git cannot
"""
from __future__ import annotations

import atexit
import functools
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import paths

COMMIT = "1e79b457"         # main just before the cut-over: the last tables.xml with the hand-drawn panel
REL = "jmri/layouts/hart/output/tables.xml"


@functools.lru_cache(maxsize=None)
def tables_bytes(commit: str = COMMIT) -> bytes:
    """The hand-drawn tables.xml at `commit`, from this checkout's git. ValueError when git or the object is not
    there (a shallow clone, or no git)."""
    try:
        done = subprocess.run(["git", "-C", str(paths.REPO_ROOT), "show", f"{commit}:{REL}"],
                              capture_output=True, check=False)
    except OSError as exc:
        raise ValueError(f"cannot run git for the hand-drawn tables ({exc})") from None
    if done.returncode != 0 or not done.stdout:
        raise ValueError(f"the hand-drawn tables {commit}:{REL} are not in this checkout's git "
                         f"({done.stderr.decode(errors='replace').strip() or 'empty'})")
    return done.stdout


@functools.lru_cache(maxsize=None)
def tables_path(commit: str = COMMIT) -> Path:
    """A temporary copy of the hand-drawn tables.xml at `commit` (one per process, removed at exit). Callers must
    not write to it; copy it first. ValueError as tables_bytes."""
    data = tables_bytes(commit)
    folder = Path(tempfile.mkdtemp(prefix="hart-hand-drawn-"))
    atexit.register(shutil.rmtree, folder, True)
    path = folder / "tables.xml"
    path.write_bytes(data)
    path.chmod(0o444)
    return path


def skip_unless_available():
    """For tests: the hand-drawn tables' path, or unittest.SkipTest naming why it is missing."""
    import unittest
    try:
        return tables_path()
    except ValueError as exc:
        raise unittest.SkipTest(f"needs the last hand-drawn tables from git: {exc}") from None
