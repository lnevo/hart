#!/usr/bin/env python3
"""Fail when a Python file over LIMIT lines grows (owner, 2026-11-25; wiki/projects/cleanup-streamline-handoff.md, D).

Every tracked .py file outside EXCLUDED that is over LIMIT lines has a row in SIZES (path, lines): the size it may not
pass. The check fails when such a file grows past its row, when a file crosses LIMIT with no row, and when a file
shrank, fell to LIMIT or below, or is gone, so the list is tightened in the same change (a ratchet).

    python3 tools/audit/check_py_sizes.py            check (exit 1 on a problem, 2 when it cannot run)
    python3 tools/audit/check_py_sizes.py --update   rewrite SIZES for files that shrank, fell under LIMIT or went
                                                     away; it never raises a size or adds a file
    python3 tools/audit/check_py_sizes.py --update --accept PATH [--accept PATH ...]
                                                     also take PATH's current size: growth, or a new file over LIMIT,
                                                     accepted by name, so the diff of SIZES shows it

Lines are newlines, as `wc -l` counts them, plus a last line with no newline. Untracked .py files that git does not
ignore are measured too, so a new file over LIMIT fails before it is staged.
"""
from __future__ import annotations

import argparse
import csv
import io
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
SIZES = ROOT / "tools/audit/py_sizes.csv"
LIMIT = 800
# What it reads, as git globs (then in_scope); the step's quiet_inputs in tools/pipeline/checks.toml are these
# (tools/audit/tests/test_manifest_scans.py)
SCAN_GLOBS = ("**/*.py",)
# Code this repo does not grow: vendored or submodule code, the archive, parked features (docs/parked/UNPARK.md)
# and the third-party STRR speed-match scripts. The same set ruff.toml leaves out.
EXCLUDED = ("archive/", "external/", "reference/", "tools/cats/src-repo/", "jmri/layouts/hart/parked/")
EXCLUDED_NAMES = ("docs/jmri/speedmatching/STRR_",)
HEADER = ("path", "lines")


class SizeError(Exception):
    """The check cannot run: git failed, or SIZES is not a valid list."""


class Problem(NamedTuple):  # a NamedTuple, not a dataclass: tests load this file by path
    path: str
    text: str


def in_scope(path: str) -> bool:
    return path.endswith(".py") and not path.startswith(EXCLUDED) and not path.startswith(EXCLUDED_NAMES)


def tracked(root: Path | None = None) -> list[str]:
    root = root or ROOT
    try:
        done = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--",
                               *(f":(glob){g}" for g in SCAN_GLOBS)],
                              cwd=root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise SizeError(f"git ls-files could not run: {e}") from e
    if done.returncode != 0:
        raise SizeError(f"git ls-files failed: {done.stderr.strip() or f'exit {done.returncode}'}")
    return sorted({p for p in done.stdout.split("\0") if p and in_scope(p)})


def count_lines(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def measure(root: Path | None = None) -> dict[str, int]:
    """Lines of every in-scope .py file git lists (tracked, or new and not ignored) that exists on disk."""
    root = root or ROOT
    return {p: count_lines(root / p) for p in tracked(root) if (root / p).is_file()}


def read_sizes(path: Path | None = None) -> dict[str, int]:
    path = path or SIZES
    if not path.is_file():
        raise SizeError(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path} is missing")
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
    if not rows or tuple(rows[0]) != HEADER:
        raise SizeError(f"{path.name}: the first row must be {','.join(HEADER)}")
    sizes: dict[str, int] = {}
    for n, row in enumerate(rows[1:], start=2):
        if len(row) != 2 or not row[1].isdigit():
            raise SizeError(f"{path.name} row {n}: want path,lines with lines a whole number, got {row}")
        name, lines = row[0], int(row[1])
        if name in sizes:
            raise SizeError(f"{path.name} row {n}: {name} is listed twice")
        if not in_scope(name):
            raise SizeError(f"{path.name} row {n}: {name} is not a .py file this check covers")
        if lines <= LIMIT:
            raise SizeError(f"{path.name} row {n}: {name} at {lines} lines is not over {LIMIT}; take the row out")
        sizes[name] = lines
    return sizes


def problems(now: dict[str, int], sizes: dict[str, int]) -> list[Problem]:
    out = []
    for path, lines in sorted(now.items()):
        if lines <= LIMIT:
            continue
        allowed = sizes.get(path)
        if allowed is None:
            out.append(Problem(path, f"{lines} lines, over {LIMIT} with no row in {SIZES.name}: split it, or accept it "
                                     f"by name (--update --accept {path})"))
        elif lines > allowed:
            out.append(Problem(path, f"grew from {allowed} to {lines} lines: split it, or accept it by name "
                                     f"(--update --accept {path})"))
        elif lines < allowed:
            out.append(Problem(path, f"shrank from {allowed} to {lines} lines: run --update to tighten its row"))
    for path, allowed in sorted(sizes.items()):
        if path not in now:
            out.append(Problem(path, f"listed at {allowed} lines but gone: run --update to drop its row"))
        elif now[path] <= LIMIT:
            out.append(Problem(path, f"now {now[path]} lines, at or under {LIMIT}: run --update to drop its row"))
    return out


def updated(now: dict[str, int], sizes: dict[str, int], accept: set[str]) -> dict[str, int]:
    """The new list: rows lowered or dropped where files shrank, fell under LIMIT or went away; rows raised or added
    only for paths in `accept`. A path in `accept` that does not need it is an error, so a typo is not ignored."""
    for path in sorted(accept):
        if path not in now:
            raise SizeError(f"--accept {path}: no .py file this check covers has that path")
        if now[path] <= LIMIT:
            raise SizeError(f"--accept {path}: it is {now[path]} lines, not over {LIMIT}")
        if path in sizes and now[path] <= sizes[path]:
            raise SizeError(f"--accept {path}: it did not grow ({now[path]} lines, row {sizes[path]})")
    new = {}
    for path, lines in now.items():
        if lines <= LIMIT:
            continue
        if path in accept:
            new[path] = lines
        elif path in sizes:
            new[path] = min(lines, sizes[path])
    return new


def write_sizes(sizes: dict[str, int], path: Path | None = None) -> None:
    path = path or SIZES
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEADER)
    for name in sorted(sizes):
        w.writerow((name, sizes[name]))
    path.write_text(buf.getvalue(), encoding="utf-8")
    if read_sizes(path) != sizes:  # read back what was written
        raise SizeError(f"{path.name} did not read back as written")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="tighten the list; never raises a size unless --accept")
    ap.add_argument("--accept", action="append", default=[], metavar="PATH",
                    help="with --update: take PATH's current size (growth or a new file), by name")
    args = ap.parse_args(argv)
    if args.accept and not args.update:
        print("check_py_sizes: --accept needs --update", file=sys.stderr)
        return 2
    try:
        now = measure()
        sizes = read_sizes()
        if args.update:
            new = updated(now, sizes, set(args.accept))
            if new == sizes:
                print(f"check_py_sizes: {SIZES.name} already current ({len(new)} files over {LIMIT} lines)")
            else:
                write_sizes(new)
                print(f"check_py_sizes: wrote {SIZES.name} ({len(new)} files over {LIMIT} lines)")
            left = problems(now, new)
        else:
            left = problems(now, sizes)
    except SizeError as e:
        print(f"check_py_sizes: {e}", file=sys.stderr)
        return 2
    if left:
        print(f"check_py_sizes: {len(left)} problem(s) with Python files over {LIMIT} lines:")
        for p in left:
            print(f"  {p.path}: {p.text}")
        return 1
    print(f"check_py_sizes: no Python file over {LIMIT} lines grew ({len(sizes if not args.update else new)} listed)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
