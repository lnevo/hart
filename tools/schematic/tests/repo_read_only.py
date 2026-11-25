"""For the data checks that run the real builders over the repo's committed files: while repo_read_only() is on, any
write, new folder, rename or delete under the repo fails the test instead of changing a file. Paths outside the repo
(temporary folders) are untouched, and so is the shared build cache (hartlib.paths.cache_dir, <main checkout>/.cache/hart,
gitignored): builders keep their caches there."""
from __future__ import annotations

import builtins
import contextlib
import io
import os
import unittest.mock
from pathlib import Path

from hartlib import paths

REPO = Path(paths.REPO_ROOT).resolve()
CACHE = paths.cache_dir("x", REPO).parent.resolve()   # the shared cache root; writes there are the builders' caches


def in_repo(target, follow: bool = True) -> bool:
    """Whether `target` is in the repo (and not the shared cache). `follow` False judges a symbolic link by where it
    stands, not where it points: rename, replace and unlink act on the link itself (layer_files.view swaps a cache
    link that points into the checkout)."""
    try:
        p = Path(os.fspath(target))
    except TypeError:                                  # a file descriptor, not a path
        return False
    p = p.resolve() if follow else p.absolute().parent.resolve() / p.name
    return p.is_relative_to(REPO) and not p.is_relative_to(CACHE)


def _refuse(what: str, target):
    raise AssertionError(f"a data check tried to {what} {target} inside the repo; data checks only read it")


def _guard_open(real):
    def guarded(file, mode="r", *args, **kwargs):
        if set(mode) & set("wax+") and in_repo(file):
            _refuse(f"open (mode {mode!r})", file)
        return real(file, mode, *args, **kwargs)
    return guarded


def _guard_first(real, what):
    def guarded(first, *args, **kwargs):
        follow = what not in ("rename", "replace", "unlink", "remove")      # these act on a link, not its target
        if in_repo(first, follow) or (what in ("rename", "replace") and args and in_repo(args[0], follow)):
            _refuse(what, first)
        return real(first, *args, **kwargs)
    return guarded


@contextlib.contextmanager
def repo_read_only():
    with contextlib.ExitStack() as stack:
        real_open = builtins.open                      # io.open is the same function; pathlib calls it as io.open
        for owner in (builtins, io):
            stack.enter_context(unittest.mock.patch.object(owner, "open", _guard_open(real_open)))
        stack.enter_context(unittest.mock.patch.object(Path, "open", _guard_open(Path.open)))
        for owner, names in ((Path, ("mkdir", "unlink", "rmdir", "rename", "replace", "touch")),
                             (os, ("rename", "replace", "remove", "unlink", "mkdir", "makedirs"))):
            for name in names:
                stack.enter_context(unittest.mock.patch.object(owner, name, _guard_first(getattr(owner, name), name)))
        yield


class RepoReadOnly:
    """Mix in before unittest.TestCase: the whole class runs under repo_read_only()."""

    @classmethod
    def setUpClass(cls):
        cls.enterClassContext(repo_read_only())
        super().setUpClass()
