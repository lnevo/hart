"""File helpers several tools wrote for themselves: an atomic write and the checkout's tracked files.

    files.write_atomic(path, text_or_bytes)     # readers see the old file or the new one, never half
    files.tracked_files(root, ":(glob)**/*.py")  # git ls-files; GitError when git cannot list them
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

SUBMODULE_MODE = "160000"


class GitError(RuntimeError):
    """git could not list the tracked files; the message says where and why."""


def write_atomic(target: Path | str, data: bytes | str, encoding: str = "utf-8") -> None:
    """Replace the file the path names through a temporary file in its folder and os.replace, so a reader or a
    stopped run sees the old file or the new one, never a cut-off one. Text is written in `encoding`. The new file
    keeps the old one's mode (0644 for a new file). A symlink stays a symlink (its target is written); a hard-linked
    file is rewritten in place, so every link sees the new bytes. The folder must exist."""
    if isinstance(data, str):
        data = data.encode(encoding)
    target = Path(os.path.realpath(target))
    try:
        hard_linked = target.stat().st_nlink > 1
    except OSError:
        hard_linked = False
    if hard_linked:
        with open(target, "r+b") as handle:
            handle.write(data)
            handle.truncate()
        return
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        try:
            os.chmod(tmp, target.stat().st_mode & 0o7777)
        except OSError:
            os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def tracked_files(root: Path | str, *pathspecs: str, submodules: bool = True, timeout: float = 60) -> list[str]:
    """The paths git tracks in the checkout at `root`, in git's order, relative to it (git ls-files -z, limited
    to `pathspecs` when given). submodules=False leaves out submodule entries (their contents are never listed).
    No fallback to walking the folder, which would also find untracked and ignored files: GitError when git cannot
    run, fails or times out."""
    args = ["git", "-C", str(root), "ls-files", "-z"] + ([] if submodules else ["-s"]) + ["--", *pathspecs]
    try:
        done = subprocess.run(args, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as err:
        raise GitError(f"git ls-files could not run in {root}: {err}") from None
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip() or f"exit {done.returncode}"
        raise GitError(f"git ls-files failed in {root}: {detail}")
    entries = [e for e in done.stdout.decode("utf-8").split("\0") if e]
    if submodules:
        return entries
    out = []
    for entry in entries:
        meta, path = entry.split("\t", 1)
        if meta.split()[0] != SUBMODULE_MODE:
            out.append(path)
    return out
