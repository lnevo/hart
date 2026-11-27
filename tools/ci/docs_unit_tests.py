#!/usr/bin/env python3
"""The unit tests a docs-only change runs (tools/ci/docs_checks.sh), from the stamp declarations of what reads docs.

    python3 tools/ci/docs_unit_tests.py      one shell line per test file: its name, then its unittest command

A unit test whose stamp declaration (tools/audit/check_stamps.py: BY_KIND, EXTRA, the manifest checks' fallback,
RUNS_JOBS) covers a Markdown file under docs/, wiki/, .claude/skills/ or .claude/agents/ can break on a docs-only
change, so the docs-only path runs it, unless LEFT_OUT says why not (a short list: whole suites that only partly read
docs stay out). Its -k filter, when only one class reads docs, is check_stamps.DOCS_K's. A line is the stamp name with a hyphen
("unit-guards-test_name_copies"), then `python3 -m unittest discover -b -q -s DIR -p FILE [-k K]`, the form
docs_checks.sh reads for the manifest's lines.

Exit 1, naming each problem, when no test is left, a declaration on docs is a whole kind or a folder check.sh does
not test here (it must go in LEFT_OUT), a test file is gone, LEFT_OUT or DOCS_K names a test no longer declared on
docs, or a -k filter is no single word: a docs-only run never passes with its unit tests quietly dropped.
"""
from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "audit"))
import check_stamps  # noqa: E402

# check.sh's unit job kinds by test folder (tools/check.sh), for the stamp names of the tests this runs.
KIND_DIRS = {"unit-guards": "tools/audit/tests", "unit-hosts": "tools/hosts/tests",
             "unit-schematic": "tools/schematic/tests", "unit-jmri": "jmri/layouts/hart/scripts/tests"}
# The declarations that cover Markdown under docs/ or wiki/ but whose tests the docs-only path leaves out, each with
# why. A new or changed declaration on docs/ or wiki/ runs on the docs-only path unless it is listed here.
LEFT_OUT = {
    # check_stamps.MANIFEST_CHECK: a read-only check's fallback after bash (every file), one job per step since ADR-037
    # stage 4b
    "manifest checks": "the ones a docs-only change can break are docs_only steps, run from docs_checks.sh's list",
    "public-text": "check_public_text.py is in docs_checks.sh's list",
    "portal": "the portal build stays with the website deploy, as in CI (owner, 2026-11-24)",
    "unit-portal": "whole suite of site builders (39 s); reads docs/ops and docs/wiring only as page sources",
    "unit-hart-ops": "whole suite (car cards, publications); reads docs only in part",
    "unit-schematic": "whole suite; reads wiki/pipelines/ only in part",
    "unit-anyrail": "whole suite; reads docs/ only for the track plan article",
    "unit-guards test_check_stamps": "the stamp machinery's own tests (38 s); declared on its sample jobs' "
                                     "declarations (RUNS_JOBS), docs/ through unit-anyrail's",
    "unit-guards test_hart_tables_writers": "runs each table writer only to see it refuse to write under "
                                            "HART_TABLES; status_counts.py reads wiki/status/ on the way",
    "unit-guards test_jmri_process_patterns": "reads the .sh, .ps1 and .py files git lists, docs/ included; no Markdown",
    "unit-guards test_pipeline_map": "its real-map tests read the graph and the pages, which only a full-path change "
                                     "(docs/pipeline-map/) alters; both pages are the pipeline-map check",
    "unit-guards test_docs_index": "builds fake docs trees; the real index is the docs-index check",
    "unit-guards test_map_lane": "its tests on the real map (the committed graph is current, a hand edit fails) are "
                                 "what the pipeline-map check's build_pipeline_map.py --check also fails on",
    "unit-guards test_agent_docs_cells": "its runs of check_agent_docs.py on the real wiki and AGENTS.md are what "
                                         "the agent-docs check in docs_checks.sh's list checks",
    "unit-guards test_status_merge": "its tests on the built page (no doubled entries) are what the status-counts "
                                     "check in docs_checks.sh's list also fails on",
    "unit-guards test_status_counts": "its tests on the real wiki/status/ are what the status-counts check in "
                                      "docs_checks.sh's list also fails on",
    "unit-guards test_helix_stl_index": "lists the docs/benchwork/helix/stl/ models, no Markdown",
    "unit-guards test_publish_draft": "reads docs/ops/ drawings and JSON, no Markdown",
    "unit-guards test_write_inventory": "reads docs/wiring/ CSV, no Markdown",
    "unit-hosts test_live_paths": "reads the docs/ paths the deploy scripts name, not Markdown text",
    "unit-jmri test_infer_block_lengths": "reads docs/jmri/ data files, no Markdown",
    "unit-jmri test_speedmatch": "reads docs/jmri/ data files (block_events.csv), no Markdown",
    "unit-jmri test_speedmatch_dashboard": "reads docs/jmri/ data files, no Markdown",
    "unit-jmri test_speedmatch_publish_live": "reads docs/jmri/ data files, no Markdown",
    "unit-jmri test_speedmatch_site_export": "reads docs/jmri/ and www/ai/ data files, no Markdown",
}
K_RE = re.compile(r"[A-Za-z_]\w*\.?")      # a class ("Name.") or a word, as check.sh writes its -k filters


class Problem(Exception):
    """The list cannot be made as the declarations stand; the message names each reason."""


# Where the Markdown docs are: docs/, wiki/, and the skills and subagents under .claude/ (changed_kind.CLAUDE_DOCS).
DOCS_ROOTS = ("docs/", "wiki/", ".claude/skills/", ".claude/agents/")


def covers_markdown_docs(patterns: tuple[str, ...]) -> bool:
    """Whether a stamp declaration covers a Markdown doc (DOCS_ROOTS), matched by the stamps' own rule
    (panel_stamps._glob_match). Each pattern under DOCS_ROOTS is probed with a path made from its own segments, a
    wildcard segment named "x" and the last one "x.md"."""
    probes = {"docs/x.md", "wiki/x.md", ".claude/skills/x/SKILL.md", ".claude/agents/x.md"}
    for p in patterns:
        if p.startswith(DOCS_ROOTS):
            parts = ["x" if "*" in part else part for part in p.split("/")]
            if not parts[-1].endswith(".md"):
                parts[-1] = "x.md"
            probes.add("/".join(parts))
    return any(check_stamps.ps._glob_match(probe, p) for p in patterns for probe in probes)


def on_docs(stamps=check_stamps) -> set[str]:
    """Every declaration that covers a Markdown doc. A job that runs other jobs (RUNS_JOBS) is declared on theirs
    too: its whole declaration."""
    declared = {**stamps.BY_KIND, **stamps.EXTRA, "manifest checks": stamps.MANIFEST_CHECK,
                **{k: stamps.declared(k) for k in stamps.RUNS_JOBS}}
    return {k for k, v in declared.items() if covers_markdown_docs(v)}


def tests(stamps=check_stamps, left_out=LEFT_OUT, root: Path = ROOT) -> list[tuple[str, str, str, str | None]]:
    """(stamp name, test folder, test file, -k filter or None) for each test to run, sorted; Problem otherwise."""
    found, problems = on_docs(stamps), []
    problems += [f"LEFT_OUT names {k!r}, no longer declared on docs/ or wiki/" for k in sorted(set(left_out) - found)]
    keys = getattr(stamps, "DOCS_K", {})
    problems += [f"check_stamps.DOCS_K names {k!r}, which this does not run" for k in sorted(set(keys) - found
                                                                                             - set(left_out))]
    problems += [f"check_stamps.DOCS_K names {k!r}, which LEFT_OUT leaves out" for k in sorted(set(keys) & set(left_out))]
    out = []
    for stamp in sorted(found - set(left_out)):
        kind, _, test = stamp.partition(" ")
        if kind not in KIND_DIRS or not re.fullmatch(r"test\w*", test):
            problems.append(f"{stamp!r} is declared on docs/ or wiki/ but is not one test file of "
                            f"{', '.join(KIND_DIRS)}: list it in LEFT_OUT with the reason")
            continue
        folder, k = KIND_DIRS[kind], keys.get(stamp)
        if not (root / folder / f"{test}.py").is_file():
            problems.append(f"{stamp!r}: {folder}/{test}.py is gone; drop its check_stamps.EXTRA line")
        if k is not None and not (isinstance(k, str) and K_RE.fullmatch(k)):
            problems.append(f"{stamp!r}: check_stamps.DOCS_K's -k {k!r} is not a class or test name")
        out.append((stamp, folder, f"{test}.py", k))
    if not out:
        problems.append("no unit test is declared on docs/ or wiki/ outside LEFT_OUT; a docs-only run would run none")
    if problems:
        raise Problem("\n".join(problems))
    return out


def lines(chosen) -> list[str]:
    """Each test as a docs_checks.sh line: its name, then its command, shell-quoted."""
    out = []
    for stamp, folder, file, k in chosen:
        argv = ["python3", "-m", "unittest", "discover", "-b", "-q", "-s", folder, "-p", file, *(["-k", k] if k else [])]
        out.append(" ".join(shlex.quote(w) for w in (stamp.replace(" ", "-"), *argv)))
    return out


def main() -> int:
    try:
        print("\n".join(lines(tests())))
    except Problem as err:
        print(f"docs_unit_tests.py: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
