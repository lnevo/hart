"""The last hand-drawn tables.xml, read from git, for the Layout Editor build after the cut-over (Phase 5): it is the
template the build starts from (build_layout_le.template_tables), whose "HART Railroad" panel the build replaces and
whose tables it adds the main and upper objects to. No copy of the old file is kept in the tree: it is read from the
commit before the cut-over.

    path = hand_drawn.tables_path()            # a temporary file, once per process
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


def skip_unless_available() -> Path:
    """For tests: the hand-drawn tables' path; unittest.SkipTest naming why it is missing."""
    import unittest
    try:
        return tables_path()
    except ValueError as exc:
        raise unittest.SkipTest(f"needs the last hand-drawn files from git: {exc}") from None
