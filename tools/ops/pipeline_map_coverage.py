#!/usr/bin/env python3
"""pipeline_map_coverage.py

Fail when the repo runs a script, or keeps a generated output, that docs/pipeline-map/pipeline_map.json does not know,
so the map agents query (tools/ops/pipeline_query.py) cannot fall behind without a check saying so.

    python3 tools/ops/pipeline_map_coverage.py          exit 1 and name each file the map lacks
    python3 tools/ops/pipeline_map_coverage.py --list   also print every file the scan found and what covers it

What must be in the map:

- Every script: each .py and .sh file, tracked or new and not ignored, outside EXCLUDED
  (archive/, external/, reference/, tools/cats/src-repo/) and outside tests (a tests/ or test/ folder, test_*.py,
  conftest.py) is a node of its own: a node whose path is the file, or a box named after it (its id is the file, as panels.toml's
  `box` names approval.py's box, which runs check_approved.py). The only other way is a folder node FAMILIES names, a
  library or a family of generators, each with its reason. A folder node not in FAMILIES covers no script under it,
  and ALLOWED does not apply to scripts. A FAMILIES entry that is no folder node, or covers no script, fails, so the
  list cannot go stale.
- Entry-file scripts: every tracked .py, .sh or .js file the pipeline's entry files (ENTRY_FILES: the Makefile, the layout
  deploy with its steps, the website deploy) name by path, or as
  `PYTHONPATH=<dir>[:<dir>...] python3 -m <module>` (the module from the first entry that holds its top package, as
  Python takes it). A plain path is read from the repo root, then from the entry file's
  folder. A path behind $ROOT is read from the entry's own ROOT (deploy_hartrailroad.sh's is www/), and one behind a
  variable the file sets from ROOT or REPO (`local sm="$ROOT/.../speedmatch"`) from that folder. A path behind any
  other variable ($dest/x.py, $PI_DROP/...) or a prefix (preference:jython/x.py) is a copy destination or a host
  path, not a call, and is not read; one inside a submodule belongs to that repo, and a module whose top package is
  not in <dir> (unittest) is not a repo script. Any other path that names no file in the checkout (tracked, or new
  and not ignored) fails: it is a call to a file that is gone. Comments are not read; a comment ends at its line, a
  trailing backslash in it included (in make's own text, outside a recipe, make carries it on), and an apostrophe
  in a word (don't) or one never closed on its line opens no quote. tools/check.sh is no entry
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

An entry-file script or an output is known when a node's path is the file or a folder above it, except a top-level
folder (a `www` box stands for the site, not for each script in it). A .py or .sh script the every-script rule checks
is reported by that rule alone. ALLOWED lists the deliberate exceptions to the entry-file and output rules, each with
its reason; an entry the scan no longer finds, or one that is also a node, fails so the list cannot go stale.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
from collections.abc import Container
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load {ROOT / 'tools/ops/build_pipeline_map.py'}")
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
ALLOWED: dict[str, str] = {
    # hand-kept files in an output folder
}
# The every-script rule: what it checks, and the folder nodes that stand for every script under them.
SCRIPT_EXTS = (".py", ".sh")
EXCLUDED = ("archive", "external", "reference", "tools/cats/src-repo")   # vendor code, submodules, frozen history
# A library or a family of generators, where one folder box is enough: path -> why. Any other
# folder node covers no script: each script under it needs a node of its own.
FAMILIES = {
    "tools/hartlib/src/hartlib": "the shared CPython library; the map links each module a step depends on",
    "ops/hart-ops/card_pipeline": "the car-card pipeline's modules and stage scripts",
    "ops/hart-ops/publications": "the publication rebuild scripts and their content modules (primer, crew and "
                                 "operating instructions, train list, station maps)",
    "ops/station_maps/scripts": "the station map drawing generators",
    "tools/hosts/pi-os": "the Pi SD-card image build (sdm plugins and their helpers), one job on the Mac",
}

# A path with a script extension and at least one folder, or behind a shell variable ($ROOT/, ${sm}/, captured so a
# repo path can be told from a host one), not inside a longer word, path or prefix (preference:).
PATH_RE = re.compile(r"(?<![\w./${}:-])(?:\$\{?(?P<var>\w+)\}?/(?P<vpath>(?:[\w.-]+/)*[\w.-]+\.(?:py|sh|js))"
                     r"|(?P<path>(?:\./)?(?:[\w.-]+/)+[\w.-]+\.(?:py|sh|js)))(?![\w.-])")
MODULE_RE = re.compile(r"PYTHONPATH=(?P<q>[\"']?)(?P<value>[^\s\"']*)(?P=q)\s+python3?\s+-m\s+(?P<mod>[\w.]+)")
# One PYTHONPATH entry: a folder behind a variable ($ROOT/lib, $ROOT) or a plain folder
PYTHONPATH_DIR_RE = re.compile(r"\$\{?(?P<var>\w+)\}?(?:/(?P<rel>[\w./-]*))?|(?P<dir>[\w./-]+)")
# An expansion with an operator, such as ${PYTHONPATH:+:$PYTHONPATH}: the caller's path, whose colons separate nothing
EXPANSION_RE = re.compile(r"\$\{\w+[:+=?#%-][^}]*\}")
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


def _strip_comment(line: str, quote: str = "") -> tuple[str, bool, str]:
    """(code, commented, quote) for one physical line: the code before a shell comment (a # at the start or after a
    space, outside quotes and not escaped), whether a comment ended the line, and the quote still open at its end.
    `quote` is the one a continued line left open. A single quote between two letters (don't, it's) is an apostrophe,
    not a quote (a double quote there still opens one); so is a quote that opens on this line and is still open at its end when the line does not continue (an
    apostrophe in a heredoc or in make's own text): the line is scanned again with it read as a plain character."""
    literal: set[int] = set()
    while True:
        q, opened, i = quote, -1, 0
        while i < len(line):
            ch = line[i]
            if q:
                if ch == "\\" and q == '"':
                    i += 1                  # \" and \\ inside double quotes
                elif ch == q:
                    q = ""
            elif ch == "\\":
                i += 1                      # an escaped character: \# \' \" are no comment and no quote
            elif ch in "'\"" and i not in literal and not (ch == "'" and _between_letters(line, i)):
                q, opened = ch, i
            elif ch == "#" and (i == 0 or line[i - 1].isspace()):
                return line[:i], True, ""
            i += 1
        if not q or opened < 0 or _continues(line):
            return line, False, q
        literal.add(opened)


def _between_letters(line: str, i: int) -> bool:
    return 0 < i < len(line) - 1 and line[i - 1].isalpha() and line[i + 1].isalpha()


def _continues(code: str) -> bool:
    """Whether a line's code ends in an unescaped backslash, which joins the next line to it."""
    return (len(code) - len(code.rstrip("\\"))) % 2 == 1


def _code_lines(text: str, makefile: bool) -> list[str]:
    """The file's logical lines without comments, and in a Makefile without the `## help` text after a target.

    A line whose code ends in a backslash joins the next one. A comment ends at the end of its line, as in the shell:
    a backslash at the end of a comment is part of the comment and joins nothing, so the next line is read as code.
    In a Makefile that holds for a recipe line (a tab first), which make hands to the shell; a comment in make's own
    text that ends in a backslash goes on to the next line, as make reads it."""
    lines: list[str] = []
    parts: list[str] = []           # the code of the logical line so far
    quote = ""                      # the quote a continued line left open
    recipe = False                  # the logical line is a Makefile recipe line
    make_comment = False            # inside a make comment that a trailing backslash continues
    for line in text.splitlines():
        if make_comment:
            make_comment = _continues(line)
            continue
        if not parts:
            recipe = makefile and line.startswith("\t")
            if makefile and not recipe and TARGET_RE.match(line):
                line = line.split("##", 1)[0]
        code, commented, quote = _strip_comment(line, quote)
        if not commented and _continues(code):
            parts.append(code[:-1])
            continue
        parts.append(code)
        make_comment = commented and makefile and not recipe and _continues(line)
        joined, parts, quote = " ".join(parts), [], ""
        if joined.strip():
            lines.append(joined)
    if parts and " ".join(parts).strip():
        lines.append(" ".join(parts))   # the file ends in a continued line
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


def _pythonpath_dirs(value: str, known: dict[str, str]) -> list[str | None]:
    """The folders of a PYTHONPATH value, in its order: a repo folder for each colon-separated entry that is a plain
    folder or a folder behind a variable `known` names, and None for an entry behind another variable ($dest/x, a
    host path), whose contents the checkout cannot show. The caller's ${PYTHONPATH:+...} is left out: it comes last."""
    dirs: list[str | None] = []
    for part in EXPANSION_RE.sub("", value).split(":"):
        m = PYTHONPATH_DIR_RE.fullmatch(part)
        if not m or m["var"] and m["var"] not in known:
            dirs.append(None)
            continue
        dirs.append(_join(known[m["var"]], m["rel"] or "") if m["var"] else _join("", m["dir"]))
    return dirs


def _module_folder(value: str, known: dict[str, str], module: str, files: frozenset[str]) -> str | None:
    """The repo folder Python takes the module's top package from: the first PYTHONPATH entry that holds it. None when
    no repo folder holds it (unittest and the like), or when an entry the checkout cannot see comes first, since that
    one may hold it at run time: such a call is a host's, not read."""
    for folder in _pythonpath_dirs(value, known):
        if folder is None:
            return None
        if _is_module_from(folder, module, files):
            return folder
    return None


def _is_module_from(folder: str, module: str, files: frozenset[str]) -> bool:
    top = _join(folder, module.split(".")[0])
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
                folder = _module_folder(m["value"], known, m["mod"], files)
                if folder is None:
                    continue    # a module from elsewhere (unittest and the like), or behind a host path
                base = _join(folder, m["mod"].replace(".", "/"))
                hit = next((t for t in (f"{base}.py", f"{base}/__main__.py") if t in files), None)
                if hit:
                    scripts.setdefault(hit, entry)
                else:
                    problems.append(f"{entry}: python3 -m {m['mod']} with PYTHONPATH={folder or '.'} finds no "
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


def _first_above(path: str, keys: Container[str], top: int) -> str | None:
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


def is_test(path: str) -> bool:
    """A test file: in a tests/ or test/ folder, or named test_*.py or conftest.py. A name ending in _test is no test:
    panelpro_smoke_test.py and speedmatch's stop_test.py are pipeline scripts."""
    p = PurePosixPath(path)
    return (any(part in ("tests", "test") for part in p.parts[:-1])
            or (p.name.startswith("test_") and p.suffix == ".py") or p.name == "conftest.py")


def rule_scripts(files: Iterable[str], excluded: Iterable[str] = EXCLUDED) -> list[str]:
    """The files the every-script rule checks: .py and .sh, not in an EXCLUDED folder, not tests."""
    skip = tuple(e.rstrip("/") + "/" for e in excluded)
    return sorted(f for f in files if f.endswith(SCRIPT_EXTS) and not f.startswith(skip) and not is_test(f))


def script_gaps(scripts: Iterable[str], node_paths: dict[str, str], node_ids: Iterable[str],
                families: dict[str, str], graph_name: str, listing: list[str] | None = None) -> list[str]:
    """Each script that is neither its own node (a node's path, or a box whose id is the script) nor under a folder
    node FAMILIES names, and each FAMILIES entry that is empty, no folder node or covers no script."""
    problems = [f"FAMILIES entry {key} in {ME} has no reason" for key, why in families.items() if not why.strip()]
    problems += [f"FAMILIES entry {key} in {ME} is no node's path in {graph_name}; add the folder node or remove "
                 f"the entry" for key in sorted(families) if key not in node_paths]
    ids = set(node_ids)
    used: set[str] = set()
    for path in scripts:
        own = node_paths.get(path) or (path if path in ids else None)
        family = None if own else _first_above(str(PurePosixPath(path).parent), families, 1)
        if family:
            used.add(family)
        if not own and not family:
            folder = _first_above(str(PurePosixPath(path).parent), node_paths, 1)
            if folder:
                problems.append(f"script {path} is only under folder node {node_paths[folder]!r} ({folder}), which "
                                f"FAMILIES in {ME} does not name: add a node for the script, with its edges, to "
                                f"{graph_name}, or add {folder} to FAMILIES with the reason if it is a library or a "
                                f"family of generators")
            else:
                problems.append(f"script {path} is not in the map: add a node for it, with the edges from what it "
                                f"reads and to what it writes, to {graph_name}")
        if listing is not None:
            listing.append(f"{'rule':6} {path:64} " + (f"node {own}" if own else
                                                         f"family: {family}" if family else "MISSING"))
    problems += [f"FAMILIES entry {key} in {ME} covers no script; remove it"
                 for key in sorted(set(families) - used) if key in node_paths]
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
        raise CoverageError(str(err)) from err
    ruled = rule_scripts(files)     # a new script fails before the commit, as it would after
    ruled_set = set(ruled)
    entry_only = {path: where for path, where in scripts.items() if path not in ruled_set}
    return (script_gaps(ruled, node_paths, (n["id"] for n in data["nodes"]), FAMILIES, str(shown), listing)
            + gaps(entry_only, outputs, node_paths, ALLOWED, str(shown), listing)
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
