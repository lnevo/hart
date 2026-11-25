#!/usr/bin/env python3
"""manifest.py

Load and check the step manifest, tools/pipeline/checks.toml (ADR-037; docs/pipeline-map/build-graph-design.md), and
print the lists its runners will read.

    python3 tools/pipeline/manifest.py check                       exit 1 and name each problem in the manifest
    python3 tools/pipeline/manifest.py list                        one line per step: name, group, script, edges
    python3 tools/pipeline/manifest.py jobs check [--group static | --ungrouped | --docs-only]
                                                                   one shell line per step: its name, then its command

tools/check.sh runs every step as a job of its own, named after the step (ADR-037 stage 4b): the static group's
ahead of the unit tests, the steps in no group after them; tools/ci/docs_checks.sh runs the docs-only steps. Both
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
GIT_REFS. Every problem is reported, each naming the file, the step and the field.

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
if str(HERE) not in sys.path:       # the parts import each other by name, from any cwd and under any load name
    sys.path.insert(0, str(HERE))

import manifest_base  # noqa: E402
import manifest_checks  # noqa: E402
import manifest_jobs  # noqa: E402
import manifest_panels  # noqa: E402
from manifest_base import (MANIFEST, NAME_RE, PROGRAM_RE, ROOT, Edge, ManifestError,  # noqa: E402,F401
                           Repo, _shown, glob_regex, is_glob, path_problem, pipeline_map, read, repo, repo_from,
                           tracked_files)
from manifest_checks import (EDGE_KEYS, FIELDS, GIT_REFS, GROUPS, MODULE_RE, PLAIN_DIR_RE,  # noqa: E402,F401
                             PYTHON, RUNNERS, SHELL_PYTHON, WHOLE_REPO, Step, git_problem, load, parse, select,
                             shell_line)
from manifest_jobs import Declared, JobKey, covers, declarations, job_keys, undeclared  # noqa: E402,F401
from manifest_panels import (PANEL_BOX_TEXT, PANEL_EDGE_KEYS, PANEL_FIELDS, PANEL_MODES,  # noqa: E402,F401
                             PANEL_WORD_RE, PANELS, PANELS_RUNNER, PanelStep, load_panels, panel_lines,
                             panel_order_problems, panel_steps, parse_panels)

PARTS = (manifest_base, manifest_checks, manifest_jobs, manifest_panels)
_stray = [f"{m.__name__} from {m.__file__}" for m in PARTS if Path(m.__file__).resolve().parent != HERE]
if _stray:      # another module of a part's name came first on sys.path: refuse it, never run a stranger's code
    raise ImportError(f"manifest.py: its parts must be the files beside it in {HERE}, not {', '.join(_stray)}")
# This file and its parts, from the repo root: an edit to any of them reruns every check.sh job (check_stamps.ALWAYS)
FILES = tuple(Path(f).resolve().relative_to(ROOT).as_posix() for f in (__file__, *(m.__file__ for m in PARTS)))


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
        steps = load(args.manifest)
        if args.command == "jobs":
            lines = [shell_line(s) for s in select(steps, args.runner, args.group, args.ungrouped, args.docs_only)]
        elif args.command == "list":
            lines = ["\t".join((s.name, s.runner, s.group or "-", "docs" if s.docs_only else "-", s.domain, s.script,
                                f"{len(s.inputs)} in", f"{len(s.outputs)} out")) for s in steps]
        else:
            lines = [f"{_shown(args.manifest)}: {len(steps)} steps, all checked",
                     f"{_shown(args.panels)}: {len(load_panels(args.panels))} steps, all checked"]
    except ManifestError as err:
        print(f"manifest.py: {err}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
