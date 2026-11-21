#!/usr/bin/env python3
"""pipeline_map_coverage.py

Fail when the repo runs a script, or keeps a generated output, that docs/pipeline-map/pipeline_map.json does not know,
so the map agents query (tools/ops/pipeline_query.py) cannot fall behind without a check saying so.

    python3 tools/ops/pipeline_map_coverage.py          exit 1 and name each file the map lacks
    python3 tools/ops/pipeline_map_coverage.py --list   also print every file the scan found and what covers it

What must be in the map:

- Scripts: every tracked .py, .sh or .js file the pipeline's entry files (ENTRY_FILES: tools/check.sh, the Makefile,
  `make panels`, the layout deploy with its steps, the website deploy) name by path, or as
  `PYTHONPATH=<dir> python3 -m <module>`. A path is read from the repo root, then from the entry file's folder and the
  folder above it (deploy_hartrailroad.sh's $ROOT is www/). A path behind any other shell variable ($dest/x.py,
  $PI_DROP/...) or a prefix (preference:jython/x.py) is a copy destination or a host path, not a call, and is not
  read; one inside a submodule belongs to that repo, and a module whose top package is not in <dir> (unittest) is
  not a repo script. Any other path that names no tracked file fails: it is a call to a file that is gone.
  Full-line comments are not read.
- Outputs: every tracked file under OUTPUT_ROOTS, and every repo path an entry file gives to `--out`.

A file is known when a node's path is the file or a folder above it, except a top-level folder (a `www` box stands
for the site, not for each script in it). ALLOWED lists the deliberate exceptions, each with its reason; an entry the
scan no longer finds, or one that is also a node, fails so the list cannot go stale.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
BUILD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BUILD)
ME = "tools/ops/pipeline_map_coverage.py"

# The files that run the pipeline: what they call is the pipeline. A folder means every .sh file directly in it.
ENTRY_FILES = (
    "tools/check.sh",
    "Makefile",
    "tools/schematic/build_panels.sh",       # make panels
    "tools/hosts/sync_hart_package.sh",      # the layout deploy
    "tools/hosts/deploy",                    # its steps (gate, stage, ship_*)
    "www/scripts/deploy_hartrailroad.sh",    # the website deploy
)
# Folders of generated files; a hand-kept file in one is in ALLOWED with its reason.
OUTPUT_ROOTS = (
    "jmri/layouts/hart/output",
    "cats/panels",
)
# Deliberate exceptions: path (a file, or a folder for every file under it) -> why the map leaves it out.
ALLOWED = {
    # check.sh and make plumbing: they schedule, stamp or route jobs and read or write no pipeline file
    "tools/agent/worktrees.py": "makes and sweeps agent worktrees (make wt); no pipeline file",
    "tools/audit/check_stamps.py": "check.sh job stamps in .cache; no pipeline file",
    "tools/audit/test_classes.py": "lists test classes so check.sh can split a test file into jobs",
    "tools/audit/portal_inputs.py": "decides whether check.sh runs the portal build; reads git, writes nothing",
    "tools/schematic/panel_stamps.py": "make panels' step stamps in .cache; no pipeline file",
    "tools/hosts/win_run.sh": "runs a command on the Windows box (make remote); no pipeline file",
    "tools/env/load_env.sh": "loads .env.local host settings for the deploy steps",
    "tools/ops/screenshot.py": "screenshots any page for a check by eye (make shot); writes only scratch images",
    "tools/hosts/deploy_status.sh": "prints the commit each host last got; reads the hosts, writes nothing",
    "tools/hosts/pi_quit_panelpro.sh": "stops PanelPro on the Pi around a deploy; no file in or out",
    "tools/hosts/pi_start_panelpro.sh": "starts PanelPro on the Pi after a deploy; no file in or out",
    # the layout deploy's own parts, drawn as one box: tools/hosts/sync_hart_package.sh
    "tools/hosts/deploy": "the steps of sync_hart_package.sh, which the map draws as one box",
    "tools/hosts/profile_tables_guard.sh": "guard functions sourced by the deploy and the PanelPro wrappers; part of "
                                           "the sync_hart_package.sh box",
    # drawn inside another node's box
    "jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py": "parked Dispatcher traininfo repair; the "
                                                                "run_dispatcher_stage1.py box names it",
    # hand-kept files in an output folder
    "cats/panels/HART_chubb_magnet.xml": "hand-drawn legacy CATS panel; no builder writes it",
    "cats/panels/reference_ArmstrongMagnet.xml": "CATS sample panel kept for reference (cats/README.md)",
}

# A path with at least one folder and a script extension, not inside a longer word, path or prefix (preference:);
# an optional shell variable in front ($ROOT/, ${STEPS}/) is captured so a repo path can be told from a host one.
PATH_RE = re.compile(r"(?<![\w./${}:-])(?:\$\{?(?P<var>\w+)\}?/)?(?P<path>(?:\./)?(?:[\w.-]+/)+[\w.-]+\.(?:py|sh|js))"
                     r"(?![\w.-])")
MODULE_RE = re.compile(r"PYTHONPATH=(?P<dir>[\w./-]+)\s+python3?\s+-m\s+(?P<mod>[\w.]+)")
OUT_RE = re.compile(r"--out[ =](?P<path>[\w./-]+)")


class CoverageError(Exception):
    pass


def _git_files(*args: str) -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z", *args], cwd=ROOT, text=True)
    return [f for f in out.split("\0") if f]


def _submodules() -> tuple[str, ...]:
    return tuple(line.split("\t", 1)[1] for line in _git_files("-s") if line.startswith("160000 "))


def entry_files(files: frozenset[str], entries: Iterable[str] = ENTRY_FILES) -> list[str]:
    """The entry files as tracked files, each folder as the .sh files directly in it."""
    found = []
    for entry in entries:
        if entry in files:
            found.append(entry)
            continue
        inside = sorted(f for f in files if PurePosixPath(f).parent == PurePosixPath(entry) and f.endswith(".sh"))
        if not inside:
            raise CoverageError(f"ENTRY_FILES in {ME} names {entry}, which is no tracked file or folder of .sh files; "
                                f"fix or remove it")
        found.extend(inside)
    return found


def _code_lines(text: str, makefile: bool) -> list[str]:
    """The file's lines without its full-line comments (and, in a Makefile, the `## help` text after a target)."""
    return [line.split("##", 1)[0] if makefile else line
            for line in text.splitlines() if not line.lstrip().startswith("#")]


def _is_module_from(folder: str, module: str, files: frozenset[str]) -> bool:
    top = f"{folder}/{module.split('.')[0]}"
    return f"{top}.py" in files or any(f.startswith(top + "/") for f in files)


def scan(files: frozenset[str], submodules: tuple[str, ...], read: Callable[[str], str],
         entries: Iterable[str] = ENTRY_FILES,
         output_roots: Iterable[str] = OUTPUT_ROOTS) -> tuple[dict[str, str], dict[str, str]]:
    """The scripts and the outputs that must be in the map, each with the entry file or folder that named it.
    `read` gives an entry file's text. Raises CoverageError naming every path an entry file names that is gone."""
    scripts: dict[str, str] = {}
    outputs: dict[str, str] = {}
    problems = []
    for entry in entry_files(files, entries):
        here = PurePosixPath(entry).parent
        for line in _code_lines(read(entry), makefile=PurePosixPath(entry).name == "Makefile"):
            for m in PATH_RE.finditer(line):
                if m["var"] and m["var"] != "ROOT":
                    continue
                raw = m["path"].removeprefix("./")
                tries = list(dict.fromkeys((raw, str(here / raw), str(here.parent / raw))))
                hit = next((t for t in tries if t in files), None)
                if hit:
                    scripts.setdefault(hit, entry)
                elif not any(t == s or t.startswith(s + "/") for t in tries for s in submodules):
                    problems.append(f"{entry}: {m.group(0)} names no tracked file (tried {', '.join(tries)}); "
                                    f"fix the path in {entry}")
            for m in MODULE_RE.finditer(line):
                if not _is_module_from(m["dir"], m["mod"], files):
                    continue    # a module from elsewhere (unittest and the like)
                base = f"{m['dir']}/{m['mod'].replace('.', '/')}"
                hit = next((t for t in (f"{base}.py", f"{base}/__main__.py") if t in files), None)
                if hit:
                    scripts.setdefault(hit, entry)
                else:
                    problems.append(f"{entry}: python3 -m {m['mod']} with PYTHONPATH={m['dir']} finds no tracked "
                                    f"{base}.py; fix the command in {entry}")
            for m in OUT_RE.finditer(line):
                if m["path"] in files:
                    outputs.setdefault(m["path"], f"{entry} --out")
    for root in output_roots:
        inside = sorted(f for f in files if f.startswith(root + "/"))
        if not inside:
            raise CoverageError(f"OUTPUT_ROOTS in {ME} names {root}, which holds no tracked file; fix or remove it")
        for f in inside:
            outputs.setdefault(f, f"under {root}")
    if problems:
        raise CoverageError("\n".join(problems))
    return scripts, outputs


def _first_above(path: str, keys, top: int) -> str | None:
    """The longest of the path and the folders above it, down to `top` parts, that is in keys."""
    parts = PurePosixPath(path).parts
    for k in range(len(parts), top - 1, -1):
        key = "/".join(parts[:k])
        if key in keys:
            return key
    return None


def gaps(scripts: dict[str, str], outputs: dict[str, str], node_paths: dict[str, str], allowed: dict[str, str],
         graph_name: str, listing: list[str] | None = None) -> list[str]:
    """What the map lacks, and ALLOWED entries that are empty, stale or also a node. A file is known by the node whose
    path is the file or a folder above it below the top level (`www` stands for the site, not its scripts).
    With `listing`, appends one line per file found and what covers it."""
    problems = [f"ALLOWED entry {key} in {ME} has no reason" for key, why in allowed.items() if not why.strip()]
    used: set[str] = set()
    for what, found in (("script", scripts), ("output", outputs)):
        for path, where in sorted(found.items()):
            covered = _first_above(path, node_paths, 2)
            allow = _first_above(path, allowed, 1)
            if allow:
                used.add(allow)
            if covered and allow:
                problems.append(f"{path} is node {node_paths[covered]!r} and also in ALLOWED ({allow}); drop it from "
                                f"ALLOWED in {ME}")
            elif not covered and not allow:
                problems.append(f"{what} {path} ({where}) is not in the map: add a node for it, with its edges, to "
                                f"{graph_name}, or add it to ALLOWED in {ME} with the reason")
            if listing is not None:
                listing.append(f"{what:6} {path:64} " + (f"node {node_paths[covered]}" if covered else f"allowed: {allow}"))
    problems += [f"ALLOWED entry {key} matches nothing the scan finds; remove it from {ME}"
                 for key in sorted(set(allowed) - used)]
    return problems


def check(graph: Path, listing: list[str] | None = None) -> list[str]:
    """The problems for this checkout. Raises GraphError or CoverageError when the graph or the scan cannot be read."""
    data = BUILD.load(graph)
    node_paths = {n["path"].rstrip("/"): n["id"] for n in data["nodes"] if n.get("path")}
    scripts, outputs = scan(frozenset(_git_files()), _submodules(), lambda f: (ROOT / f).read_text())
    shown = graph.relative_to(ROOT) if graph.is_relative_to(ROOT) else graph
    return gaps(scripts, outputs, node_paths, ALLOWED, str(shown), listing)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--graph", type=Path, default=BUILD.GRAPH)
    ap.add_argument("--list", action="store_true", help="also print every file the scan found and what covers it")
    args = ap.parse_args(argv)
    listing: list[str] | None = [] if args.list else None
    try:
        problems = check(args.graph.resolve(), listing)
    except (BUILD.GraphError, CoverageError) as err:
        print(f"pipeline map coverage cannot run ({args.graph}):\n{err}", file=sys.stderr)
        return 1
    for line in listing or []:
        print(line)
    if problems:
        print(f"pipeline map coverage: {len(problems)} problem(s)", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
