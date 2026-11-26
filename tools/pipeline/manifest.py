#!/usr/bin/env python3
"""manifest.py

Load and check the step manifest, tools/pipeline/checks.toml (ADR-037; docs/pipeline-map/build-graph-design.md), and
print the lists its runners will read.

    python3 tools/pipeline/manifest.py check                       exit 1 and name each problem in the manifest
    python3 tools/pipeline/manifest.py list                        one line per step: name, group, script, edges
    python3 tools/pipeline/manifest.py jobs check [--group static | --ungrouped | --docs-only]
                                                                   one shell line per step: its name, then its command

tools/check.sh runs every step as a job of its own, named after the step (ADR-037 stage 4b): the static group's
ahead of the unit tests, the steps in no group after them; tools/ci/docs_checks.sh runs the docs-only steps. The
panels step (the one that runs build_panels.sh) is one job per step of panels.toml instead, panels-<step>, which runs
that step's check (stage 6): its `jobs` lines and its job_keys and declarations are those jobs'. Both
stop, naming the error, when `jobs` fails. check.sh's stamps (tools/audit/check_stamps.py) key each job on its own
entry and on the git refs its `git` field names (job_keys), so an edited entry reruns that job only.

A `jobs` line is shell text for check.sh to eval: each word shell-quoted, except "{python}", which is written as
"$HOPS_PY", and an env PYTHONPATH=dir word, which is written as PYTHONPATH="dir${PYTHONPATH:+:$PYTHONPATH}" so the
caller's PYTHONPATH (the trace hook) stays on it, as check.sh writes it today. A selection with no step is an error,
so a runner reading it cannot pass with nothing run.

What the loader checks (the file's header lists the fields): the file is TOML with [[step]] tables and at least one
step; each field has its type and no other field is set; names are unique; the command is one check.sh takes
(python3, env PYTHONPATH=dir python3, or bash; "{python}" only for a step in no group) and names a tracked script,
or a -m module that is a tracked file under its PYTHONPATH; every input, output and program glob is a plain repo path
(no ./, ../, leading / or backslash) that names a tracked file or folder, or a map node marked "local"; the domain
and every edge side are the map's (docs/pipeline-map/pipeline_map.json); `git` names each ref at most once, from
GIT_REFS. Every problem is reported, each naming the file, the step and the field. load_both loads checks.toml and
panels.toml and then checks them against each other: no file is an output of a step in each, unless SHARED_OUTPUTS
(manifest_panels.py) lists it with the two steps and why (writer_problems; #1187 found crew.json with two writers).
`check` and the map lane load them this way.

The trace audit (ADR-037 stage 4a) reads the manifest through declarations(): each job's step with every path it
declares (inputs, quiet_inputs, outputs, programs). undeclared() names the data reads its processes made that none
of those cover; tools/audit/check_stamps.py takes those reads from the trace, leaving out the code the job imported
or ran (the trace's "c" lines), and makes the report; it warns only.

The code is in four modules beside this one, which this file imports and re-exports, so a caller loads this file by
path (under any name; put the module in sys.modules before it runs) and finds every name here: manifest_base.py (the
error, Edge, Repo, the path and glob rules, reading a manifest), manifest_checks.py (checks.toml: Step, load, the
`jobs` lines), manifest_jobs.py (check_stamps' job keys and the trace audit's declarations) and manifest_panels.py
(panels.toml). FILES lists all five, for what must rerun or be copied when one of them changes.
"""
from __future__ import annotations

import argparse
import subprocess  # noqa: F401 - re-exported: the tests patch subprocess.run through this module
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The parts import each other by name, from any cwd and under any load name: this folder goes first on sys.path while
# they are imported and comes off again after, so the importing process finds no other module here.
_added = str(HERE) not in sys.path
if _added:
    sys.path.insert(0, str(HERE))
try:
    import manifest_base
    import manifest_checks
    import manifest_jobs
    import manifest_panels
finally:
    if _added:
        sys.path.remove(str(HERE))
from manifest_base import (MANIFEST, NAME_RE, PROGRAM_RE, ROOT, Edge, ManifestError,  # noqa: E402,F401
                           Repo, _shown, glob_regex, is_glob, path_problem, pipeline_map, read, repo, repo_from,
                           tracked_files)
from manifest_checks import (EDGE_KEYS, FIELDS, GIT_REFS, GROUPS, MODULE_RE, PLAIN_DIR_RE,  # noqa: E402,F401
                             PYTHON, RUNNERS, SHELL_PYTHON, WHOLE_REPO, Step, git_problem, load, parse, select,
                             shell_line)
from manifest_jobs import Declared, JobKey, covers, declarations, job_keys, panel_jobs, undeclared  # noqa: E402,F401
from manifest_panels import (PANEL_BOX_TEXT, PANEL_EDGE_KEYS, PANEL_FIELDS, PANEL_JOB_PREFIX,  # noqa: E402,F401
                             PANEL_MODES, PANEL_WORD_RE, PANELS, PANELS_RUNNER, PANELS_UNAUDITED, SHARED_OUTPUTS,
                             PanelStep, load_panels, panel_check_lines, panel_lines, panel_order_problems,
                             panel_steps, parse_panels, runs_panels, writer_problems)

PARTS = (manifest_base, manifest_checks, manifest_jobs, manifest_panels)
_stray = [f"{m.__name__} from {m.__file__}" for m in PARTS if Path(m.__file__).resolve().parent != HERE]
if _stray:      # a part already imported from another folder (a second checkout in one process): never mix the two
    raise ImportError(f"manifest.py: its parts must be the files beside it in {HERE}, not {', '.join(_stray)}")
# This file and its parts, from the repo root: an edit to any of them reruns every check.sh job (check_stamps.ALWAYS)
FILES = tuple(Path(f).resolve().relative_to(ROOT).as_posix() for f in (__file__, *(m.__file__ for m in PARTS)))


def load_both(manifest: Path = MANIFEST, panels: Path = PANELS,
              where: Repo | None = None) -> tuple[tuple[Step, ...], tuple[PanelStep, ...]]:
    """checks.toml's and panels.toml's steps, each checked against git and the map (load, load_panels), and then
    against each other: no file is an output of a step in each (writer_problems). ManifestError listing every
    problem."""
    where = repo() if where is None else where
    steps, panel_steps_ = load(manifest, where), load_panels(panels, where)
    problems = writer_problems(steps, panel_steps_, _shown(manifest), _shown(panels))
    if problems:
        raise ManifestError("\n".join(problems))
    return steps, panel_steps_


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--manifest", type=Path, default=MANIFEST, help=f"default {_shown(MANIFEST)}")
    ap.add_argument("--panels", type=Path, default=PANELS, help=f"default {_shown(PANELS)}")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="check both manifests; exit 1 naming each problem")
    sub.add_parser("list", help="one line per step: name, runner, group, docs-only, domain, script, edge counts")
    jobs = sub.add_parser("jobs", help="one shell line per step of RUNNER: its name, then its command")
    jobs.add_argument("runner", choices=(*RUNNERS, "panels"))
    which = jobs.add_mutually_exclusive_group()
    which.add_argument("--group", choices=GROUPS)
    which.add_argument("--ungrouped", action="store_true", help="the steps that are jobs of their own")
    which.add_argument("--docs-only", action="store_true", help="the steps on the docs-only path")
    args = ap.parse_args(argv)
    try:
        if args.command == "jobs" and args.runner == "panels":
            if args.group or args.ungrouped or args.docs_only:
                raise ManifestError("jobs panels takes no --group, --ungrouped or --docs-only")
            print("\n".join(panel_lines(panel_steps(args.panels))))
            return 0
        if args.command == "check":
            steps, panels = load_both(args.manifest, args.panels)
            print("\n".join((f"{_shown(args.manifest)}: {len(steps)} steps, all checked",
                             f"{_shown(args.panels)}: {len(panels)} steps, all checked",
                             "no file is an output of a step in both")))
            return 0
        steps = load(args.manifest)
        if args.command == "jobs":       # the panels step is one job per panels step (stage 6), named as job_keys
            lines = []
            for s in select(steps, args.runner, args.group, args.ungrouped, args.docs_only):
                if not runs_panels(s.cmd):
                    lines.append(shell_line(s))
                    continue
                jobs = panel_jobs({}, args.panels, {t.name for t in steps})
                lines += panel_check_lines([step for _raw, step in jobs.values()])
        else:
            lines = ["\t".join((s.name, s.runner, s.group or "-", "docs" if s.docs_only else "-", s.domain, s.script,
                                f"{len(s.inputs)} in", f"{len(s.outputs)} out")) for s in steps]
    except ManifestError as err:
        print(f"manifest.py: {err}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
