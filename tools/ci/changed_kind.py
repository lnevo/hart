#!/usr/bin/env python3
"""Say whether a change needs the full checks, the light checks (tools/ci/light_checks.sh) or only the quick docs
checks (tools/ci/docs_checks.sh).

    git diff --name-only A B | changed_kind.py [--compare A] [--why]
                                      print "docs", "light" or "full" for the paths on stdin (CI); --why prints the
                                      verdict with its reason; --compare is the ref the changed files are compared
                                      with (the pipeline map's light case needs it)
    changed_kind.py --git [--base origin/main]
                                      the same for this checkout's changes (tools/check.sh, make pr-kind): print
                                      "docs: <why>", "light: <why>", "full: <why>" or "unknown: <why>"
    changed_kind.py --jobs (--git [--base B] | --compare A)
                                      the check.sh jobs a light change runs, one per line; exit 1 when it is not light

"docs" only when every path is prose that the quick docs checks cover: Markdown outside the agent rules (CLAUDE.md
and the folders' AGENTS.md; the root AGENTS.md is docs, ROOT_AGENTS) and the generated map folder, and under .claude/
only the skills' and subagents' (CLAUDE_DOCS); the pipeline map beside them is docs too when it changes only in its
agent-doc lane (AGENT_LANE). "light"
when every path is docs or a data file that no code, host or full-only test depends on (light_problem says each
rule), so make static, the static checks that read it and the quick docs checks cover it. Anything else, and an
empty list, is "full". The paths are
repo-relative with "/" separators (git diff --name-only).

Which checks read a data file comes from the declarations, never a list here: each check.sh job's step in
tools/pipeline/checks.toml (inputs, quiet_inputs, outputs, programs; manifest.declarations), the unit jobs' stamp
declarations in tools/audit/check_stamps.py (BY_KIND, EXTRA, RUNS_JOBS: check_stamps.declared), and the writers of
each box of docs/pipeline-map/pipeline_map.json. A path those cannot settle is full, with the reason.

With --git the paths are the branch against its merge base with --base, plus uncommitted and untracked files, read
the way the portal job reads them (tools/audit/portal_inputs.changed_files). "unknown" means git could not say what
changed (no merge base: a shallow clone, no origin/main); the caller runs the full checks and prints the reason.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple, TypedDict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "audit"))
from portal_inputs import ChangedFilesError, changed_files, git_lines  # noqa: E402

# Rules for agents: tools/audit/check_agent_docs.py reads these and the rest of check.sh follows from them.
AGENT_FILES = {"AGENTS.md", "CLAUDE.md"}
# The root AGENTS.md is docs: its readers are the agent-docs and pipeline-map checks, both on the
# docs path. A folder's AGENTS.md stays full: jmri/ and cats/ are code, and unit jobs declare the others.
ROOT_AGENTS = "AGENTS.md"
# Generated from the repo and compared by tests that only the full run executes.
GENERATED = ("docs/pipeline-map/",)
# The folders under .claude/ whose Markdown is docs: the skills and the subagents. The unit suites that read them
# declare them (tools/audit/check_stamps.py AGENT_DOCS) and the docs path runs those (tools/ci/docs_unit_tests.py).
# Every other file under .claude/ (hooks, settings, commands) is code or agent rules.
CLAUDE_DOCS = (".claude/skills/", ".claude/agents/")
# Code, for the light rule: the suffixes of programs, configuration and JMRI or CATS files, and the folders whose every
# file is code or rules (the JMRI and CATS trees, CI, git hooks, the agent rules). check.sh and checks.toml are .sh
# and .toml files.
CODE_SUFFIXES = (".py", ".js", ".mjs", ".sh", ".ps1", ".php", ".toml", ".xml")
CODE_PREFIXES = ("jmri/", "cats/", ".github/", ".githooks/", ".claude/", ".cursor/")
CODE_FILES = {"Makefile"}
# Data files a light change may hold; any other suffix (a page, an image, a binary) is full.
DATA_SUFFIXES = (".json", ".csv", ".tsv", ".txt", ".md")
LIVE_PATHS = "tools/hosts/live_paths.txt"
MAP = "docs/pipeline-map/pipeline_map.json"
# The map's keys that only the map pages read: the Start menu's presets. build_pipeline_map.py checks each (its focus
# is a box) and hands the list to the page (pipeline_map_view_input.js); the graph's readers (manifest.repo(),
# pipeline_query.py, the map lanes, the coverage check, the tests on the real map) read domains, nodes and edges only.
# The pipeline-map check (build_pipeline_map.py --check, static and docs_only) builds both pages from it.
MAP_DISPLAY_KEYS = ("presets",)
MAP_READER = "pipeline-map"
# The agent-doc lane's mark ("gen") on its boxes and links (tools/ops/agent_docs_map.py GEN), built from the agent docs
# alone. A map change limited to them is docs: the docs path runs the pipeline-map check
# (build_pipeline_map.py --check rebuilds the lane from the files) and the agent-docs check.
AGENT_LANE = "agent-docs"
MapChange = Literal["docs", "light"]

Kind = Literal["docs", "light", "full"]


@dataclass(frozen=True)
class Verdict:
    kind: Kind
    why: str
    jobs: tuple[str, ...] = ()          # light: the check.sh jobs to run, make static's first

    @property
    def line(self) -> str:
        """The verdict with its reason: "docs: ...", "light: ..." or "full: ..."."""
        return f"{self.kind}: {self.why}"


class JobDecl(NamedTuple):
    """A check.sh manifest job as the light rule reads it."""
    patterns: tuple[str, ...]       # its declared inputs, quiet inputs, outputs and programs
    on_light_path: bool             # in the static group or on the docs-only path


class MapNode(TypedDict, total=False):
    """A box of the pipeline map (the keys the light rule reads)."""
    id: str
    path: str
    kind: str


# A link of the pipeline map (the keys the light rule reads); "from" is a Python keyword, hence the functional form
MapEdge = TypedDict("MapEdge", {"from": str, "to": str, "side": str}, total=False)


@dataclass
class Declarations:
    """What the light rule reads, loaded once: check.sh's manifest jobs, the unit jobs' stamp declarations, the
    paths the deploy ships, and the pipeline map's boxes and links."""
    jobs: dict[str, JobDecl]
    static: tuple[str, ...]                 # make static's jobs: the static group less the panels-* jobs
    units: dict[str, tuple[str, ...]]
    live: tuple[str, ...]
    nodes: list[MapNode]
    edges: list[MapEdge]
    # manifest.covers(pattern, path): a declared path or glob. The unit jobs' stamp declarations are matched by it
    # too: on a plain path (plain()) it agrees with the stamps' own glob rule, which a test checks on every
    # declared pattern
    covers: Callable[[str, str], bool]


def plain(path: str) -> str | None:
    """The path as a plain repo path, or None: git quotes a path with odd bytes in double quotes, and a "..", "." or
    empty segment could step out of the folders checked here."""
    path = path.strip().removeprefix("./")
    if not path or path.startswith('"') or any(part in ("", ".", "..") for part in path.split("/")):
        return None
    return path


def is_docs(path: str) -> bool:
    p = plain(path)
    if p is None or (p.split("/")[-1] in AGENT_FILES and p != ROOT_AGENTS) or p.startswith(GENERATED):
        return False
    if p.startswith(".claude/") and not p.startswith(CLAUDE_DOCS):
        return False
    return p.endswith(".md")


def load_declarations(root: Path = ROOT) -> Declarations:
    """The declarations from the files themselves. Raises (ImportError, OSError, ValueError, the manifest's error)
    when one cannot be read: the caller makes that a full verdict with the reason. They are this checkout's (ROOT):
    another `root` (a scratch repo) is refused rather than read half from each."""
    if root.resolve() != ROOT:
        raise ValueError(f"the declarations are read from {ROOT}, not {root}")
    import check_stamps
    pm = check_stamps.pm
    steps = pm.load()
    by_name = {s.name: s for s in steps}
    panels = next((s for s in steps if pm.runs_panels(s.cmd)), None)
    jobs: dict[str, JobDecl] = {}
    for job, (decl,) in pm.declarations().items():
        step = by_name.get(job) or (panels if job.startswith(pm.PANEL_JOB_PREFIX) else None)
        if step is None:
            raise ValueError(f"check.sh job {job!r} has no step in {pm.MANIFEST.as_posix()}")
        jobs[job] = JobDecl(tuple(decl.patterns), step.group == "static" or step.docs_only)
    static = tuple(s.name for s in pm.select(steps, "check", group="static") if not pm.runs_panels(s.cmd))
    units: dict[str, tuple[str, ...]] = {}
    for name in (*(k for k in check_stamps.BY_KIND if k.startswith("unit-")), *check_stamps.EXTRA,
                 *check_stamps.RUNS_JOBS):
        units[name] = tuple(p for p in (check_stamps.declared(name) or ()) if p != "tools/check.sh")
    live = tuple(line.strip() for line in (root / LIVE_PATHS).read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#"))
    graph = json.loads((root / MAP).read_text(encoding="utf-8"))
    return Declarations(jobs, static, units, live, graph["nodes"], graph["edges"], pm.covers)


def _less_agent_lane(graph: dict[str, object]) -> dict[str, object]:
    """The map without the agent-doc lane's boxes and links (AGENT_LANE)."""
    out = dict(graph)
    for key in ("nodes", "edges"):
        entries = out.get(key)
        if isinstance(entries, list):
            out[key] = [e for e in entries if not (isinstance(e, dict) and e.get("gen") == AGENT_LANE)]
    return out


def map_change(base_text: str | None, head_text: str | None) -> MapChange | str:
    """How the map's head differs from its base: "docs" when only in the agent-doc lane's boxes and links, "light"
    when only in MAP_DISPLAY_KEYS (with or without that lane), otherwise why it is neither."""
    if base_text is None or head_text is None:
        return "no base copy of the map to compare with" if base_text is None else "the map is gone"
    try:
        base, head = json.loads(base_text), json.loads(head_text)
    except ValueError as err:
        return f"a copy of the map is not JSON ({err})"
    if not isinstance(base, dict) or not isinstance(head, dict):
        return "a copy of the map is not a JSON object"
    if base == head:
        return f"its keys are the base's, {', '.join(MAP_DISPLAY_KEYS)} included: only the file's text differs"
    base, head = _less_agent_lane(base), _less_agent_lane(head)
    changed = [k for k in sorted(set(base) | set(head)) if base.get(k) != head.get(k)]
    rest = [k for k in changed if k not in MAP_DISPLAY_KEYS]
    if rest:
        return (f"it changes {', '.join(repr(k) for k in rest)}, not only {', '.join(MAP_DISPLAY_KEYS)} or the "
                f"agent-doc lane ('gen': '{AGENT_LANE}')")
    return "light" if changed else "docs"


def first_rule(p: str) -> str | None:
    """Why plain path `p` is not light by its name alone (code, or not a data file), or None."""
    name = p.split("/")[-1]
    if p.endswith(CODE_SUFFIXES):
        return f"is code or configuration ({'.' + name.rsplit('.', 1)[-1]})"
    if p.startswith(CODE_PREFIXES):
        return f"is under {p.split('/')[0]}/, where every file is code, JMRI or CATS data, or agent rules"
    if name in CODE_FILES or name in AGENT_FILES:
        return "is code or agent rules"
    if not p.endswith(DATA_SUFFIXES):
        return f"is not a data file ({', '.join(DATA_SUFFIXES)})"
    return None


def light_problem(p: str, d: Declarations) -> tuple[str | None, tuple[str, ...]]:
    """(why data path `p` is not light, or None; the panels-* jobs that read it, which make static leaves out).
    Light needs: no host gets it, a box of the map covers it and no generator writes that box, every check.sh job
    that declares it is in the static group or on the docs path, and no unit job's stamp declaration covers it."""
    shipped = [lp for lp in d.live if p == lp or p.startswith(lp.rstrip("/") + "/")]
    if shipped:
        return f"ships to the layout hosts ({LIVE_PATHS}: {shipped[0]})", ()
    ids = {n["id"] for n in d.nodes if isinstance(n.get("path"), str)
           and (p == n["path"] or p.startswith(n["path"].rstrip("/") + "/"))}
    if not ids:
        return f"is in no box of {MAP}, so whether a build writes it is unknown", ()
    generators = {n["id"] for n in d.nodes if n.get("kind") == "generator"}
    writers = sorted({e["from"] for e in d.edges if e.get("to") in ids and e.get("from") in generators
                      and e.get("side") != "pointer"})
    if writers:
        return f"is written by {writers[0]} ({MAP}): a built file, which full-only tests compare", ()
    readers = [j for j, job in d.jobs.items() if any(d.covers(pat, p) for pat in job.patterns)]
    heavy = [j for j in readers if not d.jobs[j].on_light_path]
    if heavy:
        return f"is read by check.sh job {', '.join(heavy)}, outside the static group and the docs path", ()
    units = [u for u, pats in d.units.items() if any(d.covers(pat, p) for pat in pats)]
    if units:
        more = f" and {len(units) - 1} more" if len(units) > 1 else ""
        return f"may be read by {units[0]}{more} (tools/audit/check_stamps.py), which only the full run runs", ()
    # a docs-only step in no group (public-text) runs from docs_checks.sh's list
    return None, tuple(j for j in readers if j.startswith("panels-"))


def _base_copy(root: Path, ref: str | None, path: str) -> str | None:
    """`path` as `ref` holds it, or None (no ref, or not there)."""
    if ref is None:
        return None
    try:
        return "\n".join(git_lines(root, "show", f"{ref}:{path}"))
    except ChangedFilesError:
        return None


def _head_copy(root: Path, path: str) -> str | None:
    try:
        return (root / path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def verdict(paths: list[str], root: Path = ROOT, compare: str | None = None,
            load: Callable[[Path], Declarations] = load_declarations) -> Verdict:
    """The verdict for `paths`. `compare` is the git ref holding the base copies (the pipeline map's light case
    reads the map's); None leaves the map full."""
    paths = [p for p in paths if p.strip()]
    if not paths:
        return Verdict("full", "no changed paths")
    n = f"{len(paths)} changed path{'s' if len(paths) != 1 else ''}"
    if all(is_docs(p) for p in paths):
        return Verdict("docs", f"{n}, all Markdown docs")
    if [plain(p) for p in paths if not is_docs(p)] == [MAP] \
            and map_change(_base_copy(root, compare, MAP), _head_copy(root, MAP)) == "docs":
        return Verdict("docs", f"{n}, Markdown docs and the pipeline map's agent-doc lane")
    data: list[str] = []
    for raw in (p for p in paths if not is_docs(p)):
        p = plain(raw)
        if p is None:
            return Verdict("full", f"{raw.strip()} is not a plain repo path")
        why = first_rule(p)
        if why:
            return Verdict("full", f"{p} {why}")
        data.append(p)
    try:
        d = load(root)
    except Exception as err:   # noqa: BLE001 - a declaration that cannot be read makes the run full, with the reason
        return Verdict("full", f"the declarations cannot be read ({type(err).__name__}: {err})")
    extra: list[str] = []
    for p in data:
        if p == MAP:
            change = map_change(_base_copy(root, compare, p), _head_copy(root, p))
            if change not in ("docs", "light"):
                return Verdict("full", f"{p}: {change}")
            extra.append(MAP_READER)
            continue
        why, jobs = light_problem(p, d)
        if why:
            return Verdict("full", f"{p} {why}")
        extra += jobs
    shown = ", ".join(data[:3]) + (f" and {len(data) - 3} more" if len(data) > 3 else "")
    return Verdict("light", f"{n}, docs or data that only static checks read: {shown}",
                   tuple(dict.fromkeys((*d.static, *extra))))


def merge_base(root: Path, base: str) -> str | None:
    try:
        found = git_lines(root, "merge-base", base, "HEAD")
    except ChangedFilesError:
        return None
    return found[0] if len(found) == 1 else None


def checkout(root: Path, base: str) -> Verdict | str:
    """This checkout's Verdict, or the "unknown: ..." line when git cannot say what changed."""
    try:
        paths = changed_files(root, base)
    except ChangedFilesError as e:
        return f"unknown: {e}"
    return verdict(paths, root, merge_base(root, base))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--git", action="store_true", help="read this checkout's changes from git, not stdin")
    parser.add_argument("--base", help="with --git: the branch to diff against (default origin/main)")
    parser.add_argument("--compare", help="without --git: the ref holding the base copies of the changed files")
    parser.add_argument("--why", action="store_true", help="without --git: print the verdict with its reason")
    parser.add_argument("--jobs", action="store_true", help="print the check.sh jobs of a light change")
    args = parser.parse_args(argv)
    if args.base is not None and not args.git:
        parser.error("--base goes with --git")
    if args.git and (args.compare is not None or args.why):
        parser.error("--compare and --why go without --git")
    for ref in (args.base, args.compare):
        if ref is not None and (not ref.strip() or ref.startswith("-")):
            parser.error(f"--base and --compare must name a branch or commit, not {ref!r}")
    v: Verdict | str
    if args.git:
        v = checkout(ROOT, args.base if args.base is not None else "origin/main")
    else:
        v = verdict(sys.stdin.read().splitlines(), compare=args.compare)
    line = v if isinstance(v, str) else v.line
    if args.jobs:
        if isinstance(v, str) or v.kind != "light":
            print(f"changed_kind.py: not a light change: {line}", file=sys.stderr)
            return 1
        print("\n".join(v.jobs))
    else:
        print(line if args.git or args.why or isinstance(v, str) else v.kind)
    return 0


if __name__ == "__main__":
    sys.exit(main())


