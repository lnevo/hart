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
recorded is not a change; a commit or a staged change that moves a submodule is.
The site inputs are SITE_PREFIXES (www/, the folders prepare_github_pages.py copies from through
MIRROR_PREFIXES, and the folders the www/scripts modules import from: ops/hart-ops/card_pipeline,
tools/hartlib/src), the tools outside them it loads to write a page (SITE_TOOLS: the pipeline map, the
layout renderer the layout index loads and the wiring model's inventory sheets, ADR-036) plus every source
named in www/scripts/published-files.json. The tables page and the built JSON read tables.xml, the device master,
stations.csv, the CATS desk and the wiring model, which check.sh checks on its own (tables-browser, layout-index,
layout-index-cats, wiring-json build the same files in memory), so a data-only change does not rebuild the site.

When no merge base can be found (no origin/main, a shallow clone), or git fails, this says why and exits 0:
run the check. tools/ci/changed_kind.py --git reads the changed paths the same way (check.sh's docs-only path).
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
# Tools outside SITE_PREFIXES that the build loads to write a page it publishes (prepare_github_pages.BUILT_PAGES)
SITE_TOOLS = ("tools/ops/build_pipeline_map.py", "tools/ops/pipeline_map_page.html", "tools/ops/pipeline_map_layout.js",
              "tools/ops/pipeline_map_helpers.js", "tools/ops/pipeline_map_view.js", "tools/ops/pipeline_map_view_frame.js",
              "tools/ops/pipeline_map_facets.js", "tools/ops/pipeline_map_view_lanes.js",
              "tools/ops/pipeline_map_view_rail.js", "tools/ops/pipeline_map_view_nav.js",
              "tools/ops/pipeline_map_view_input.js",
              "tools/ops/pipeline_map_eff.py", "tools/ops/agent_docs_map.py",
              "tools/wiring/write_inventory.py")
# The schematic PNG's renderer: render_le_layout.py and the parts it imports from beside it (render_le_layout.SOURCES)
RENDERER = "jmri/layouts/hart/scripts/render_le_"
NO_CHANGE = 3


class ChangedFilesError(Exception):
    """git could not say what this checkout changes; the message says why."""


class GitCouldNotRun(ChangedFilesError):
    """git did not run or did not finish (missing, timed out): not an answer about the branch."""


def git_lines(root: Path, *args: str) -> list[str]:
    """`git -C root ARGS`'s non-empty output lines; GitCouldNotRun when git does not run, ChangedFilesError when it
    exits non-zero (the message names the command and git's last error line)."""
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as e:
        raise GitCouldNotRun(f"git {args[0]} could not run: {e}") from e
    if done.returncode != 0:
        detail = done.stderr.strip().splitlines()[-1] if done.stderr.strip() else f"exit {done.returncode}"
        raise ChangedFilesError(f"git {' '.join(args)} failed: {detail}")
    return [line for line in done.stdout.splitlines() if line]


def changed_files(root: Path, base: str = "origin/main") -> list[str]:
    """Paths changed against the merge base with `base`, including uncommitted and untracked.

    Raises ChangedFilesError when git cannot say (no merge base with `base`: a shallow clone, no such branch)."""
    try:
        merge_base = git_lines(root, "merge-base", base, "HEAD")
    except GitCouldNotRun:
        raise
    except ChangedFilesError as e:
        raise ChangedFilesError(f"no merge base with {base} (a shallow clone, or no {base}): {e}") from e
    if len(merge_base) != 1:
        raise ChangedFilesError(f"no merge base with {base}: git merge-base printed {merge_base!r}")
    committed = git_lines(root, "diff", "--name-only", "--no-renames", merge_base[0], "HEAD")
    working = git_lines(root, "diff", "--name-only", "--no-renames", "--ignore-submodules=all", "HEAD")
    # a staged submodule move is a change of the branch (the working diff above leaves every submodule out)
    staged = git_lines(root, "diff", "--cached", "--name-only", "--no-renames", "--ignore-submodules=dirty", "HEAD")
    untracked = git_lines(root, "ls-files", "--others", "--exclude-standard")
    return sorted(set(committed) | set(working) | set(staged) | set(untracked))


def manifest_sources(root: Path) -> set[str]:
    path = root / MANIFEST
    if not path.is_file():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).values())


def site_inputs(paths: list[str], sources: set[str]) -> list[str]:
    return [p for p in paths if p.startswith(SITE_PREFIXES) or p in SITE_TOOLS or p in sources
            or (p.startswith(RENDERER) and p.endswith(".py"))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    try:
        paths = changed_files(ROOT, args.base)
    except ChangedFilesError as e:
        print(f"{e}; treating the site as changed")
        return 0
    hits = site_inputs(paths, manifest_sources(ROOT))
    if args.list:
        print("\n".join(hits))
    if not hits:
        print(f"{len(paths)} changed files against {args.base}, none a site input")
    return 0 if hits else NO_CHANGE


if __name__ == "__main__":
    sys.exit(main())
