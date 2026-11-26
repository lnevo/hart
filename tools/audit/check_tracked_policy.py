#!/usr/bin/env python3
"""Fail if git tracks something that should stay out of it.

A move can carry a file past a path-based ignore rule, so this checks both the
ignore rules and the forbidden names themselves, wherever the file now sits.
"""
from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib.files import GitError, tracked_files  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ("CATS_Signals.doc", ".env", ".env.*", "*.pem", "credentials*.json", "*.log", "~$*")
FORBIDDEN_DIRS = ("media/", "ops/car-cards/", "docs/wiring/bench/", "tools/cats/src-repo/")
ALLOWED = (".env.example",)
SYMLINK_MODE = "120000"


def _ls_files(root: Path, *args: str) -> list[str]:
    """NUL-separated `git ls-files -z <args>` entries; for the ignored and staged-mode listings tracked_files
    does not give. GitError with git's stderr when git cannot run or fails."""
    cmd = ["git", "-C", str(root), "ls-files", "-z", *args]
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as err:
        raise GitError(f"git ls-files {' '.join(args)} could not run in {root}: {err}") from err
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip() or f"exit {done.returncode}"
        raise GitError(f"git ls-files {' '.join(args)} failed in {root}: {detail}")
    return [e for e in os.fsdecode(done.stdout).split("\0") if e]


def problems(root: Path) -> list[str]:
    """Every tracked path under `root` that breaks the policy, as 'kind: path' lines."""
    found = [f"tracked but ignored: {p}" for p in _ls_files(root, "-ci", "--exclude-standard")]
    for entry in _ls_files(root, "-s"):
        meta, path = entry.split("\t", 1)
        if meta.split()[0] == SYMLINK_MODE:
            found.append(f"tracked symlink: {path}")
    for path in tracked_files(root):
        name = Path(path).name
        if name not in ALLOWED and any(fnmatch.fnmatch(name, g) for g in FORBIDDEN):
            found.append(f"forbidden file: {path}")
        if (path + "/").startswith(FORBIDDEN_DIRS):
            found.append(f"belongs outside git: {path}")
    return found


def main(root: Path = ROOT) -> int:
    try:
        found = problems(root)
    except GitError as err:
        print(f"FAIL {err}")
        return 1
    for line in found:
        print(f"FAIL {line}")
    if not found:
        print("OK: nothing tracked that should not be")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
