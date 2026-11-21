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
- Outputs: every tracked file under OUTPUT_ROOTS, folders only builders write, and every repo path an entry file gives
  to `--out`.

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

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
BUILD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BUILD)

# The files that run the pipeline: what they call is the pipeline. A folder means every .sh file in it.
ENTRY_FILES = (
    "tools/check.sh",
    "Makefile",
    "tools/schematic/build_panels.sh",       # make panels
    "tools/hosts/sync_hart_package.sh",      # the layout deploy
    "tools/hosts/deploy",                    # its steps (gate, stage, ship_*)
    "www/scripts/deploy_hartrailroad.sh",    # the website deploy
)
# Folders whose every tracked file a builder writes.
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
    # the layout deploy's own steps, drawn as one box: tools/hosts/sync_hart_package.sh
    "tools/hosts/deploy": "the steps of sync_hart_package.sh, which the map draws as one box",
    # outputs folders that hold a file no builder writes
    "cats/panels/HART_chubb_magnet.xml": "hand-drawn legacy CATS panel; no builder writes it",
    "cats/panels/reference_ArmstrongMagnet.xml": "CATS sample panel kept for reference (cats/README.md)",
}

SCRIPT_EXT = (".py", ".sh", ".js")
# A path with at least one folder and a script extension, not inside a longer word or path; an optional shell variable
# in front ($ROOT/, ${STEPS}/) is captured so the caller can tell a repo path from a host one.
PATH_RE = re.compile(r"(?<![\w./${}:-])(?:\$\{?(?P<var>\w+)\}?/)?(?P<path>(?:\./)?(?:[\w.-]+/)+[\w.-]+\.(?:py|sh|js))(?![\w.-])")
MODULE_RE = re.compile(r"PYTHONPATH=(?P<dir>[\w./-]+)\s+python3?\s+-m\s+(?P<mod>[\w.]+)")
OUT_RE = re.compile(r"--out[ =](?P<path>[\w./-]+)")


class CoverageError(Exception):
    pass


def _tracked_files() -> frozenset[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT, text=True)
    return frozenset(filter(None, out.split("\0")))


def _submodules() -> tuple[str, ...]:
    out = subprocess.check_output(["git", "ls-files", "-s", "-z"], cwd=ROOT, text=True)
    return tuple(line.split("\t", 1)[1] for line in filter(None, out.split("\0")) if line.startswith("160000 "))


def entry_files(files: frozenset[str]) -> list[str]:
    found = []
    for entry in ENTRY_FILES:
        if entry in files:
            found.append(entry)
            continue
        inside = sorted(f for f in files if f.startswith(entry + "/") and f.endswith(".sh") and "/" not in f[len(entry) + 1:])
        if not inside:
            raise CoverageError(f"ENTRY_FILES in {Path(__file__).name} names {entry}, which is no tracked file or "
                                f"folder of .sh files; fix or remove it")
        found.extend(inside)
    return found


def _code_lines(text: str, makefile: bool) -> str:
    """The file without its full-line comments (and, in a Makefile, the `## help` text after a target)."""
    keep = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        keep.append(line.split("##", 1)[0] if makefile else line)
    return "\n".join(keep)


def scan(files: frozenset[str], submodules: tuple[str, ...]) -> tuple[dict[str, str], dict[str, str]]:
    """The scripts and the outputs that must be in the map, each with where it was found."""
    scripts: dict[str, str] = {}
    outputs: dict[str, str] = {}
    problems = []
    for entry in entry_files(files):
        text = _code_lines((ROOT / entry).read_text(), makefile=entry == "Makefile")
        here = PurePosixPath(entry).parent
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in PATH_RE.finditer(line):
                if m["var"] and m["var"] != "ROOT":
                    continue
                raw = m["path"].removeprefix("./")
                tries = [raw, str(here / raw), str(here.parent / raw)]
                hit = next((t for t in tries if t in files), None)
                if hit:
                    scripts.setdefault(hit, entry)
                elif not any(t == s or t.startswith(s + "/") for t in tries for s in submodules):
                    problems.append(f"{entry}: {m.group(0)} names no tracked file (tried {', '.join(dict.fromkeys(tries))}); "
                                    f"fix the path in {entry}")
            for m in MODULE_RE.finditer(line):
                base = PurePosixPath(m["dir"]) / m["mod"].replace(".", "/")
                if str(PurePosixPath(m["dir"]) / m["mod"].split(".")[0]) + ".py" not in files and not any(
                        f.startswith(f"{m['dir']}/{m['mod'].split('.')[0]}/") for f in files):
                    continue    # not a module from that folder (unittest and the like)
                hit = next((t for t in (f"{base}.py", f"{base}/__main__.py") if t in files), None)
                if not hit:
                    problems.append(f"{entry}: python3 -m {m['mod']} with PYTHONPATH={m['dir']} finds no tracked "
                                    f"{base}.py; fix the command in {entry}")
                else:
                    scripts.setdefault(hit, entry)
            for m in OUT_RE.finditer(line):
                if m["path"] in files:
                    outputs.setdefault(m["path"], f"{entry} --out")
    for root in OUTPUT_ROOTS:
        inside = sorted(f for f in files if f.startswith(root + "/"))
        if not inside:
            raise CoverageError(f"OUTPUT_ROOTS in {Path(__file__).name} names {root}, which holds no tracked file; "
                                f"fix or remove it")
        for f in inside:
            outputs.setdefault(f, f"under {root}")
    if problems:
        raise CoverageError("\n".join(problems))
    return scripts, outputs


def covering_node(path: str, node_paths: dict[str, str]) -> str | None:
    """The id of the node whose path is the file or a folder above it below the top level, or None."""
    parts = PurePosixPath(path).parts
    for k in range(len(parts), 1, -1):
        nid = node_paths.get("/".join(parts[:k]))
        if nid:
            return nid
    return None


def allowed_for(path: str) -> str | None:
    parts = PurePosixPath(path).parts
    for k in range(len(parts), 0, -1):
        key = "/".join(parts[:k])
        if key in ALLOWED:
            return key
    return None


def check(graph: Path, verbose: bool = False) -> list[str]:
    """The problems: files the map lacks and stale allowlist entries. Raises CoverageError on a broken setup."""
    data = BUILD.load(graph)
    node_paths = {n["path"].rstrip("/"): n["id"] for n in data["nodes"] if n.get("path")}
    files = _tracked_files()
    scripts, outputs = scan(files, _submodules())
    problems = []
    for key, why in ALLOWED.items():
        if not why.strip():
            problems.append(f"ALLOWED entry {key} has no reason")
    used: set[str] = set()
    for what, found in (("script", scripts), ("output", outputs)):
        for path, where in sorted(found.items()):
            nid = covering_node(path, node_paths)
            allow = allowed_for(path)
            if nid and allow:
                problems.append(f"{path} is node {nid!r} and also in ALLOWED ({allow}); drop it from ALLOWED")
            elif allow:
                used.add(allow)
            elif not nid:
                problems.append(f"{what} {path} ({where}) is not in the map: add a node for it to {graph.relative_to(ROOT)}"
                                f" with its edges, or add it to ALLOWED in tools/ops/pipeline_map_coverage.py with the reason")
            if verbose:
                print(f"{what:6} {path:60} {('node ' + nid) if nid else ('allowed: ' + str(allow))}")
    for key in sorted(set(ALLOWED) - used):
        problems.append(f"ALLOWED entry {key} matches nothing the scan finds; remove it")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--graph", type=Path, default=BUILD.GRAPH)
    ap.add_argument("--list", action="store_true", help="print every file the scan found and what covers it")
    args = ap.parse_args(argv)
    try:
        problems = check(args.graph.resolve(), args.list)
    except (BUILD.GraphError, CoverageError) as err:
        print(f"pipeline map coverage cannot run:\n{err}", file=sys.stderr)
        return 1
    if problems:
        print(f"pipeline map coverage: {len(problems)} problem(s)", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
