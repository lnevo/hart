#!/usr/bin/env python3
"""Fail when a .py, .js or .sh file crosses its line limit, or a listed file grows past its cap.

LIMITS gives each kind its limit: .py and .js 800 lines, .sh 500. A file at or under its limit passes; the limit is
its only rule. A file at 90 percent of its limit or more (WARN_SHARE, warn_at: 720 lines for .py and .js, 450 for .sh)
with no row gets a WARNING line, which does not fail the check, so the guard speaks before the crossing. The warning
is advisory: it shows when the py-sizes job runs, not when its stamp lets check.sh skip it.

Every tracked file of those kinds outside EXCLUDED (and outside any node_modules folder) that is over its limit has a
row in SIZES (path, lines). The row is a cap with headroom: the file fails only when it grows past
row + floor(row * HEADROOM), so a fix that adds a few lines (a named error, an input check) passes. A file over its
limit with no row fails. A row is never lowered: a file that shrank keeps its row, so it can grow back for a fix. A
row whose file is gone or has fallen to its limit or below passes with one note, and `--update` drops it.

    python3 tools/audit/check_py_sizes.py            check (exit 1 on a problem, 2 when it cannot run)
    python3 tools/audit/check_py_sizes.py --update   drop the rows of files that are gone or at or under their
                                                     limit; it never lowers, raises or adds a row
    python3 tools/audit/check_py_sizes.py --update --accept PATH [--accept PATH ...]
                                                     also take PATH's current size as its row: growth, or a new
                                                     file over its limit, accepted by name, so the diff of SIZES
                                                     shows it

Lines are newlines, as `wc -l` counts them, plus a last line with no newline. Untracked files that git does not
ignore are measured too, so a new file over its limit fails before it is staged.
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
# The line limit of each kind of file the check covers, by suffix. Shell is lower: check.sh grew from 47 to 526 lines
# in 14 days, and at 800 no shell file in the repo would have a row (tools/audit size sweep, 2026-11-25).
LIMITS = {".py": 800, ".js": 800, ".sh": 500}
# What it reads, as git globs (then in_scope); the step's quiet_inputs in tools/pipeline/checks.toml are these
# (tools/audit/tests/test_manifest_scans.py)
SCAN_GLOBS = tuple(f"**/*{suffix}" for suffix in LIMITS)
# Code this repo does not grow: vendored or submodule code, the archive (the third-party STRR speed-match scripts
# are there) and parked features (docs/parked/UNPARK.md). The same set ruff.toml leaves out. No vendored or minified
# .js is tracked outside them (2026-11-25: the longest .js lines are hand-written data in www/exam/run.js).
EXCLUDED = ("archive/", "external/", "reference/", "tools/cats/src-repo/", "jmri/layouts/hart/parked/")
HEADER = ("path", "lines")
WARN_SHARE = 0.9        # the share of its limit at which a file with no row gets a WARNING
HEADROOM = 0.10         # the share of its row a listed file may grow by before it fails


class SizeError(Exception):
    """The check cannot run: git failed, or SIZES is not a valid list."""


class Problem(NamedTuple):  # a NamedTuple, not a dataclass: tests load this file by path
    path: str
    text: str


def limit_of(path: str) -> int | None:
    """The line limit of `path`'s kind, or None for a kind the check does not cover."""
    return LIMITS.get(Path(path).suffix)


def line_limit(path: str) -> int:
    """The line limit of a path whose kind the check covers; SizeError for any other kind."""
    limit = limit_of(path)
    if limit is None:
        raise SizeError(f"{path}: not a {kinds()} file this check covers")
    return limit


def warn_at(limit: int) -> int:
    """The line count from which a file under `limit` with no row is warned about (720 of 800, 450 of 500)."""
    return int(limit * WARN_SHARE)


def allowed_size(row: int) -> int:
    """The most lines a listed file may have: its row plus HEADROOM of it, rounded down (900 gives 990)."""
    return row + int(row * HEADROOM)


def in_scope(path: str) -> bool:
    """A kind LIMITS covers, outside EXCLUDED and outside node_modules (an npm install's untracked vendor code, which
    .gitignore does not leave out)."""
    return (limit_of(path) is not None and not path.startswith(EXCLUDED)
            and "node_modules" not in path.split("/")[:-1])


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
    """Lines of every in-scope file git lists (tracked, or new and not ignored) that exists on disk."""
    root = root or ROOT
    return {p: count_lines(root / p) for p in tracked(root) if (root / p).is_file()}


def kinds() -> str:
    return ", ".join(LIMITS)


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
            raise SizeError(f"{path.name} row {n}: {name} is not a {kinds()} file this check covers")
        limit = line_limit(name)
        if lines <= limit:
            raise SizeError(f"{path.name} row {n}: {name} at {lines} lines is not over {limit}; take the row out")
        sizes[name] = lines
    return sizes


def problems(now: dict[str, int], sizes: dict[str, int]) -> list[Problem]:
    out = []
    for path, lines in sorted(now.items()):
        limit = line_limit(path)
        if lines <= limit:
            continue
        row = sizes.get(path)
        if row is None:
            out.append(Problem(path, f"{lines} lines, over {limit} with no row in {SIZES.name}: split it, or accept "
                                     f"it by name (--update --accept {path})"))
        elif lines > allowed_size(row):
            out.append(Problem(path, f"grew from {row} to {lines} lines, past the {allowed_size(row)} its row "
                                     f"allows ({int(HEADROOM * 100)} percent headroom): split it, or accept it by "
                                     f"name (--update --accept {path})"))
    return out


def slack(now: dict[str, int], sizes: dict[str, int]) -> list[str]:
    """The listed files whose row --update would drop: gone, or at or under their limit. Not a failure."""
    return sorted(path for path in sizes if path not in now or now[path] <= line_limit(path))


def warnings(now: dict[str, int], sizes: dict[str, int]) -> list[Problem]:
    """The files at WARN_SHARE of their limit or more, not over it, with no row: they fail on the line that crosses."""
    out = []
    for path, lines in sorted(now.items()):
        limit = line_limit(path)
        if warn_at(limit) <= lines <= limit and path not in sizes:
            out.append(Problem(path, f"{lines} lines, at {lines * 100 // limit} percent of its {limit}-line limit; "
                                     f"over {limit} it fails without a row: split it first"))
    return out


def updated(now: dict[str, int], sizes: dict[str, int], accept: set[str]) -> dict[str, int]:
    """The new list: rows dropped where files fell to their limit or below or went away, other rows kept as they are
    (a shrink never lowers one); rows raised or added only for paths in `accept`. A path in `accept` that does not need it is an error, so a typo is not ignored."""
    for path in sorted(accept):
        if path not in now:
            raise SizeError(f"--accept {path}: no {kinds()} file this check covers has that path")
        if now[path] <= line_limit(path):
            raise SizeError(f"--accept {path}: it is {now[path]} lines, not over {line_limit(path)}")
        if path in sizes and now[path] <= sizes[path]:
            raise SizeError(f"--accept {path}: it did not grow ({now[path]} lines, row {sizes[path]})")
    new = {}
    for path, lines in now.items():
        if lines <= line_limit(path):
            continue
        if path in accept:
            new[path] = lines
        elif path in sizes:
            new[path] = sizes[path]
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


def limits_text() -> str:
    return ", ".join(f"{suffix} {limit}" for suffix, limit in LIMITS.items())


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="drop the rows of files gone or at or under their limit; never lowers a row, "
                         "and raises or adds one only with --accept")
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
                print(f"check_py_sizes: {SIZES.name} already current ({len(new)} files over their limit)")
            else:
                write_sizes(new)
                print(f"check_py_sizes: wrote {SIZES.name} ({len(new)} files over their limit)")
            sizes = new
        left = problems(now, sizes)
    except SizeError as e:
        print(f"check_py_sizes: {e}", file=sys.stderr)
        return 2
    for w in warnings(now, sizes):
        print(f"check_py_sizes: WARNING: {w.path}: {w.text}")
    below = slack(now, sizes)
    if below:
        print(f"check_py_sizes: {len(below)} listed file(s) gone or at or under their limit; `--update` drops "
              f"their rows")
    if left:
        print(f"check_py_sizes: {len(left)} problem(s) with files over their line limit ({limits_text()}):")
        for p in left:
            print(f"  {p.path}: {p.text}")
        return 1
    print(f"check_py_sizes: no file over its line limit ({limits_text()}) grew past its cap "
          f"({len(sizes)} listed)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
