#!/usr/bin/env python3
"""pipeline_map_coverage.py

Fail when the repo runs a script, or keeps a generated output, that docs/pipeline-map/pipeline_map.json does not know,
so the map agents query (tools/ops/pipeline_query.py) cannot fall behind without a check saying so.

    python3 tools/ops/pipeline_map_coverage.py          exit 1 and name each file the map lacks
    python3 tools/ops/pipeline_map_coverage.py --list   also print every file the scan found and what covers it

What must be in the map:

- Scripts: every tracked .py, .sh or .js file the pipeline's entry files (ENTRY_FILES: the Makefile, the layout
  deploy with its steps, the website deploy) name by path, or as
  `PYTHONPATH=<dir> python3 -m <module>`. A plain path is read from the repo root, then from the entry file's
  folder. A path behind $ROOT is read from the entry's own ROOT (deploy_hartrailroad.sh's is www/), and one behind a
  variable the file sets from ROOT or REPO (`local sm="$ROOT/.../speedmatch"`) from that folder. A path behind any
  other variable ($dest/x.py, $PI_DROP/...) or a prefix (preference:jython/x.py) is a copy destination or a host
  path, not a call, and is not read; one inside a submodule belongs to that repo, and a module whose top package is
  not in <dir> (unittest) is not a repo script. Any other path that names no file in the checkout (tracked, or new
  and not ignored) fails: it is a call to a file that is gone. Comments are not read. tools/check.sh is no entry
  file: it runs its read-only checks from the step manifest (tools/pipeline/checks.toml, ADR-037), and the map
  draws each step's script from there (its manifest lane, tools/pipeline/map_lane.py), so they are boxes by
  construction. What else check.sh runs (unit tests, its stamps and scheduling helpers) is plumbing, not pipeline.
  tools/schematic/build_panels.sh (make panels) is no entry file either: its steps are tools/pipeline/panels.toml's,
  drawn by the same lane.
- Outputs: every tracked file under OUTPUT_ROOTS, and every repo path an entry file gives to `--out`.
- Agent docs: every file, tracked or new and not ignored, that matches GLOBS in tools/ops/agent_docs_map.py (the
  .claude skills, subagents and commands, and the
  AGENTS.md files one or two folders down). The map build draws each tracked one, so ALLOWED does
  not apply to them.

A file is known when a node's path is the file or a folder above it, except a top-level folder (a `www` box stands
for the site, not for each script in it). ALLOWED lists the deliberate exceptions, each with its reason; an entry the
scan no longer finds, or one that is also a node, fails so the list cannot go stale.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
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
    "Makefile",
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
    # make plumbing: they schedule or route jobs and read or write no pipeline file (check.sh is no entry file:
    # its own plumbing is not scanned)
    "tools/agent/worktrees.py": "makes and sweeps agent worktrees (make wt); no pipeline file",
    "tools/ops/orient.py": "prints claims, worktrees in progress, deploys, PRs and what waits to be pulled in (make "
                           "orient), asking the pulls' and the gate's read-only checks; writes no pipeline file",
    "tools/hosts/win_run.sh":"runs a command on the Windows box (make remote); no pipeline file",
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
    "cats/panels/reference_ArmstrongMagnet.xml": "CATS sample panel kept for reference (cats/README.md)",
}

# A path with a script extension and at least one folder, or behind a shell variable ($ROOT/, ${sm}/, captured so a
# repo path can be told from a host one), not inside a longer word, path or prefix (preference:).
PATH_RE = re.compile(r"(?<![\w./${}:-])(?:\$\{?(?P<var>\w+)\}?/(?P<vpath>(?:[\w.-]+/)*[\w.-]+\.(?:py|sh|js))"
                     r"|(?P<path>(?:\./)?(?:[\w.-]+/)+[\w.-]+\.(?:py|sh|js)))(?![\w.-])")
MODULE_RE = re.compile(r"PYTHONPATH=[\"']?(?:\$\{?(?P<var>\w+)\}?/)?(?P<dir>[\w./-]+)(?::[^\s\"']*)?[\"']?"
                       r"\s+python3?\s+-m\s+(?P<mod>[\w.]+)")
TARGET_RE = re.compile(r"^[\w.-]+:")         # a Makefile target line, where `##` starts its help text
ROOT_ASSIGN_RE = re.compile(r'^\s*ROOT="\$\(cd "\$\(dirname "\$0"\)(?:/(?P<rel>[\w./]+))?" && pwd\)"')
VAR_ASSIGN_RE = re.compile(r'^\s*(?:local\s+|export\s+|readonly\s+)?(?P<name>[A-Za-z_]\w*)="(?P<value>.*)"\s*$')
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


def _strip_comment(line: str) -> str:
    """The line without a trailing shell comment: a # at the start or after a space, outside quotes."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


def _code_lines(text: str, makefile: bool) -> list[str]:
    """The file's logical lines (backslash continuations joined) without comments, and in a Makefile without the
    `## help` text after a target."""
    lines = []
    for line in text.replace("\\\n", " ").splitlines():
        if makefile and TARGET_RE.match(line):
            line = line.split("##", 1)[0]
        line = _strip_comment(line)
        if line.strip():
            lines.append(line)
    return lines


def _shell_vars(lines: list[str], entry: str) -> dict[str, str]:
    """The entry file's variables that name a repo folder: ROOT (its own `ROOT="$(cd "$(dirname "$0")/.." && pwd)"`,
    else the repo root, as the deploy steps get it from common.sh), REPO from `git rev-parse --show-toplevel`, and each
    `NAME="$ROOT/folder"` built on one of those. Folder paths are repo-relative; "" is the repo root."""
    here = PurePosixPath(entry).parent
    known = {"ROOT": ""}
    for line in lines:
        m = ROOT_ASSIGN_RE.search(line)
        if m:
            up = os.path.normpath(str(here / (m["rel"] or ".")))
            known["ROOT"] = "" if up == "." else up
            break
    for line in lines:
        m = VAR_ASSIGN_RE.match(line)
        if not m:
            continue
        if "rev-parse --show-toplevel" in m["value"]:
            known[m["name"]] = ""
            continue
        v = re.fullmatch(r"\$\{?(\w+)\}?(?:/([\w./-]*))?", m["value"])
        if v and v[1] in known and not (v[2] or "").endswith((".py", ".sh", ".js")):
            known.setdefault(m["name"], _join(known[v[1]], v[2] or ""))
    return known


def _join(base: str, rel: str) -> str:
    joined = os.path.normpath(f"{base}/{rel}" if base else (rel or "."))
    return "" if joined == "." else joined


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
        here = str(PurePosixPath(entry).parent)
        try:
            text = read(entry)
        except OSError as err:
            raise CoverageError(f"{entry} is in git but cannot be read ({err.strerror}); restore it or git rm it")
        lines = _code_lines(text, makefile=PurePosixPath(entry).name == "Makefile")
        known = _shell_vars(lines, entry)
        for line in lines:
            for m in PATH_RE.finditer(line):
                raw = (m["vpath"] or m["path"]).removeprefix("./")
                if m["var"]:
                    if m["var"] not in known:
                        continue    # a copy destination or a host path
                    tries = [_join(known[m["var"]], raw)]
                else:
                    tries = list(dict.fromkeys((_join("", raw), _join(here, raw))))
                hit = next((t for t in tries if t in files), None)
                if hit:
                    scripts.setdefault(hit, entry)
                elif not any(t == s or t.startswith(s + "/") for t in tries for s in submodules):
                    problems.append(f"{entry}: {m.group(0)} names no file in the checkout (tried {', '.join(tries)}); "
                                    f"fix the path in {entry}")
            for m in MODULE_RE.finditer(line):
                if m["var"] and m["var"] not in known:
                    continue
                folder = _join(known[m["var"]], m["dir"]) if m["var"] else _join("", m["dir"])
                if not _is_module_from(folder, m["mod"], files):
                    continue    # a module from elsewhere (unittest and the like)
                base = f"{folder}/{m['mod'].replace('.', '/')}"
                hit = next((t for t in (f"{base}.py", f"{base}/__main__.py") if t in files), None)
                if hit:
                    scripts.setdefault(hit, entry)
                else:
                    problems.append(f"{entry}: python3 -m {m['mod']} with PYTHONPATH={folder} finds no "
                                    f"{base}.py in the checkout; fix the command in {entry}")
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
    path is the file, or a folder above it below the top level (`www` stands for the site, not its scripts).
    With `listing`, appends one line per file found and what covers it."""
    problems = [f"ALLOWED entry {key} in {ME} has no reason" for key, why in allowed.items() if not why.strip()]
    used: set[str] = set()
    for what, found in (("script", scripts), ("output", outputs)):
        for path, where in sorted(found.items()):
            covered = path if path in node_paths else _first_above(path, node_paths, 2)
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
                listing.append(f"{what:6} {path:64} " + (f"node {node_paths[covered]}" if covered else
                                                            f"allowed: {allow}" if allow else "MISSING"))
    problems += [f"ALLOWED entry {key} matches nothing the scan finds; remove it from {ME}"
                 for key in sorted(set(allowed) - used)]
    return problems


def agent_doc_gaps(docs: list[str], node_paths: dict[str, str], graph_name: str,
                   listing: list[str] | None = None) -> list[str]:
    """Each agent doc (a file matching GLOBS in tools/ops/agent_docs_map.py: skills, subagents, commands) that is no
    box. The build draws every tracked one, so a gap is a new file not yet added to git or a graph not rebuilt."""
    problems = []
    for path in sorted(set(docs)):
        covered = path if path in node_paths else _first_above(path, node_paths, 2)
        if not covered:
            problems.append(f"agent doc {path} is not in the map: git add it, then run python3 "
                            f"tools/ops/build_pipeline_map.py, which draws every file matching GLOBS in "
                            f"tools/ops/agent_docs_map.py into {graph_name}")
        if listing is not None:
            listing.append(f"{'doc':6} {path:64} " + (f"node {node_paths[covered]}" if covered else "MISSING"))
    return problems


def check(graph: Path, listing: list[str] | None = None) -> list[str]:
    """The problems for this checkout. Raises GraphError or CoverageError when the graph or the scan cannot be read."""
    data = BUILD.load(graph)
    node_paths = {n["path"].rstrip("/"): n["id"] for n in data["nodes"] if n.get("path")}
    # new files not yet added count too, so a check before the commit does not call them gone
    files = frozenset(_git_files() + _git_files("--others", "--exclude-standard"))
    scripts, outputs = scan(files, _submodules(), lambda f: (ROOT / f).read_text())
    shown = graph.relative_to(ROOT) if graph.is_relative_to(ROOT) else graph
    try:
        docs = BUILD.AGENT_DOCS.glob_files() + BUILD.AGENT_DOCS.glob_files(others=True)
    except BUILD.AGENT_DOCS.AgentDocsMapError as err:
        raise CoverageError(str(err)) from None
    return (gaps(scripts, outputs, node_paths, ALLOWED, str(shown), listing)
            + agent_doc_gaps(docs, node_paths, str(shown), listing))


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
