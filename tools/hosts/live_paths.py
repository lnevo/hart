#!/usr/bin/env python3
"""The repo paths the layout deploy ships (live_paths.txt), and which commits touch them.

    live_paths.py check                  every listed path exists in this checkout (the deploy runs this)
    live_paths.py changed COMMIT [REV]   prints "ahead N" (commits from COMMIT to REV, default HEAD, that touch a
                                         shipped path) and "behind N" (the same for REV to COMMIT), each followed
                                         by the shipped paths changed, indented, one per line

Errors are one line on stderr and exit 2. Reads git only.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import parked  # noqa: E402

LIST = Path(__file__).resolve().with_name("live_paths.txt")
ROOT = Path(__file__).resolve().parents[2]
JYTHON_DIR = "jmri/layouts/hart/scripts/"


class LivePathsError(Exception):
    """A clear, user-facing failure (bad list, bad repo, bad commit)."""


def _under(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder + "/")


def read_list(list_file: Path = LIST) -> list[str]:
    """The listed paths, validated: plain repo-relative paths, no duplicates, at least one."""
    try:
        text = list_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise LivePathsError(f"cannot read the live path list {list_file}: {exc.strerror}") from exc
    found: list[str] = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("/") or ".." in line.split("/") or line.endswith("/") or any(c in line for c in "*?[]\\:"):
            raise LivePathsError(f"{list_file.name} line {n}: {line!r} is not a plain repo-relative path")
        if line in found:
            raise LivePathsError(f"{list_file.name} line {n}: {line!r} is listed twice")
        found.append(line)
    if not found:
        raise LivePathsError(f"{list_file.name} lists no paths")
    return found


def shipped(list_file: Path = LIST) -> list[str]:
    """The listed paths minus those of a parked feature (what the deploy skips)."""
    skip_dirs = parked.shipped_dirs()
    skip_files = [JYTHON_DIR + name for name in parked.shipped_jython()]
    return [p for p in read_list(list_file)
            if not any(_under(p, d) for d in skip_dirs) and p not in skip_files]


def check(root: Path = ROOT, list_file: Path = LIST) -> list[str]:
    """Every listed path (parked ones too) must exist in the checkout, so a rename without a list edit stops here."""
    paths = read_list(list_file)
    missing = [p for p in paths if not (root / p).exists()]
    if missing:
        raise LivePathsError("listed in live_paths.txt but missing from the checkout: " + ", ".join(missing))
    return paths


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise LivePathsError(f"git {args[0]} failed: {done.stderr.strip() or 'exit ' + str(done.returncode)}")
    return done.stdout


def _live_range(root: Path, base: str, tip: str, pathspec: list[str]) -> tuple[int, list[str]]:
    """(commits in base..tip touching the pathspec, shipped paths changed between their merge base and tip)."""
    count = int(_git(root, "rev-list", "--count", f"{base}..{tip}", *pathspec).strip())
    names = sorted(set(_git(root, "diff", "--name-only", f"{base}...{tip}", *pathspec).splitlines()))
    if names and count == 0:
        raise LivePathsError("the diff names shipped paths but no commit touches them")
    return count, names


def changed(commit: str, rev: str = "HEAD", root: Path = ROOT, list_file: Path = LIST) -> dict:
    """What a deploy of rev would change on a host that has commit.

    ahead: (commits in commit..rev that touch a shipped path, those paths). behind: the same for rev..commit, the
    live changes the host has that rev lacks and a deploy of rev would roll back. A count above zero with no paths
    means the changes cancel out."""
    for ref in (commit, rev):
        if not ref or ref.startswith("-"):
            raise LivePathsError(f"not a commit name: {ref!r}")
        if subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{ref}^{{commit}}"],
                          capture_output=True).returncode != 0:
            raise LivePathsError(f"{ref} is not a commit in this checkout (fetch, or it was never pushed)")
    pathspec = ["--", *shipped(list_file)]
    return {"ahead": _live_range(root, commit, rev, pathspec), "behind": _live_range(root, rev, commit, pathspec)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    ch = sub.add_parser("changed")
    ch.add_argument("commit")
    ch.add_argument("rev", nargs="?", default="HEAD")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "check":
            check()
        else:
            result = changed(args.commit, args.rev)
            for key in ("ahead", "behind"):
                count, names = result[key]
                print(f"{key} {count}")
                for name in names:
                    print(f"  {name}")
    except LivePathsError as exc:
        print(f"live_paths: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
