#!/usr/bin/env python3
"""The repo paths the layout deploy ships (live_paths.txt), and which commits touch them.

    live_paths.py check                  every listed path exists in this checkout (the deploy runs this)
    live_paths.py changed COMMIT [REV]   prints the number of commits from COMMIT to REV (default HEAD) that
                                         touch a shipped path, then those paths, one per line

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


def changed(commit: str, rev: str = "HEAD", root: Path = ROOT, list_file: Path = LIST) -> tuple[int, list[str]]:
    """(commits in commit..rev that touch a shipped path, the shipped paths they changed, sorted)."""
    for ref in (commit, rev):
        if not ref or ref.startswith("-"):
            raise LivePathsError(f"not a commit name: {ref!r}")
        if subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{ref}^{{commit}}"],
                          capture_output=True).returncode != 0:
            raise LivePathsError(f"{ref} is not a commit in this checkout (fetch, or it was never pushed)")
    pathspec = ["--", *shipped(list_file)]
    count = int(_git(root, "rev-list", "--count", f"{commit}..{rev}", *pathspec).strip())
    names = sorted(set(_git(root, "diff", "--name-only", f"{commit}..{rev}", *pathspec).splitlines()))
    if names and count == 0:
        raise LivePathsError("the diff names shipped paths but no commit touches them")
    return count, names


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
            count, names = changed(args.commit, args.rev)
            print(count)
            for name in names:
                print(name)
    except LivePathsError as exc:
        print(f"live_paths: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
