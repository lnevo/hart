#!/usr/bin/env python3
"""Fail if git tracks something that should stay out of it.

A move can carry a file past a path-based ignore rule, so this checks both the
ignore rules and the forbidden names themselves, wherever the file now sits.
"""
from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ("CATS_Signals.doc", ".env", ".env.*", "*.pem", "credentials*.json", "*.log", "~$*")
FORBIDDEN_DIRS = ("media/", "ops/car-cards/", "docs/wiring/bench/", "tools/cats/src-repo/")
ALLOWED = (".env.example",)


def git_files(*args: str) -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z", *args], cwd=ROOT, text=True)
    return [p for p in out.split("\0") if p]


def main() -> int:
    problems = [f"tracked but ignored: {p}" for p in git_files("-ci", "--exclude-standard")]
    for line in subprocess.check_output(["git", "ls-files", "-s"], cwd=ROOT, text=True).splitlines():
        if line.startswith("120000 "):
            problems.append(f"tracked symlink: {line.split(chr(9), 1)[1]}")
    for path in git_files():
        name = Path(path).name
        if name not in ALLOWED and any(fnmatch.fnmatch(name, g) for g in FORBIDDEN):
            problems.append(f"forbidden file: {path}")
        if (path + "/").startswith(FORBIDDEN_DIRS):
            problems.append(f"belongs outside git: {path}")
    for line in problems:
        print(f"FAIL {line}")
    if not problems:
        print("OK: nothing tracked that should not be")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
