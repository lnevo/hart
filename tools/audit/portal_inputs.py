#!/usr/bin/env python3
"""Exit 0 when this checkout changes something the public site build reads, 3 when it does not.

    python3 tools/audit/portal_inputs.py            # compares with origin/main
    python3 tools/audit/portal_inputs.py --list     # also prints the changed site inputs

tools/check.sh skips the portal build check (www/scripts/check_portal_build.py) only when this
exits 3; any other exit (a crash included) runs it. A tables-only or CATS-only change then does not
rebuild the whole site. The deploy (www/scripts/deploy_hartrailroad.sh) always runs the portal
check, with its count comparison.

Changed means: committed since the merge base with origin/main, staged, unstaged or untracked,
with renames listed under both paths. A submodule checked out at another commit than the one
recorded is not a change; a commit that moves a submodule is.
The site inputs are SITE_PREFIXES (www/, the folders prepare_github_pages.py copies from through
MIRROR_PREFIXES, and the folders the www/scripts modules import from: ops/hart-ops/card_pipeline,
tools/hartlib/src) plus every source named in www/scripts/published-files.json. The tables page
the build writes reads tables.xml, which check.sh checks on its own (tables-browser), so a
tables-only change does not rebuild the site.

When no merge base can be found (no origin/main, a shallow clone) this exits 0: run the check.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path("www/scripts/published-files.json")
SITE_PREFIXES = ("www/", "ops/", "docs/", "external/", "media/", "tools/hartlib/src/")
NO_CHANGE = 3


def _git(root: Path, *args: str) -> list[str] | None:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if done.returncode != 0:
        return None
    return [line for line in done.stdout.splitlines() if line]


def changed_files(root: Path, base: str = "origin/main") -> list[str] | None:
    """Paths changed against the merge base with `base`, including uncommitted and untracked; None if unknown."""
    merge_base = _git(root, "merge-base", base, "HEAD")
    if not merge_base:
        return None
    committed = _git(root, "diff", "--name-only", "--no-renames", merge_base[0], "HEAD")
    working = _git(root, "diff", "--name-only", "--no-renames", "--ignore-submodules=all", "HEAD")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard")
    if committed is None or working is None or untracked is None:
        return None
    return sorted(set(committed) | set(working) | set(untracked))


def manifest_sources(root: Path) -> set[str]:
    path = root / MANIFEST
    if not path.is_file():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).values())


def site_inputs(paths: list[str], sources: set[str]) -> list[str]:
    return [p for p in paths if p.startswith(SITE_PREFIXES) or p in sources]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    paths = changed_files(ROOT, args.base)
    if paths is None:
        print(f"no merge base with {args.base}; treating the site as changed")
        return 0
    hits = site_inputs(paths, manifest_sources(ROOT))
    if args.list:
        print("\n".join(hits))
    if not hits:
        print(f"{len(paths)} changed files against {args.base}, none a site input")
    return 0 if hits else NO_CHANGE


if __name__ == "__main__":
    sys.exit(main())
