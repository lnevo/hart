#!/usr/bin/env python3
"""Traced stamps for the jobs of tools/check.sh: a job whose recorded reads are unchanged since its last pass is skipped.

    check_stamps.py current NAME [--save FILE]           exit 0 when NAME's stamp still holds (skip the job),
                                                         1 when it must run (and may record: FILE is written),
                                                         2 when NAME is not stampable now (run it, record nothing)
    check_stamps.py current-batch NAMES DIR [--why]      `current` for every job of a check.sh run, in one process:
                                                         NAMES has one job name per line; job i (from 0) gets
                                                         DIR/i.stamp (--save) and DIR/i.stamplog (--why), and
                                                         DIR/verdicts "i<TAB>0|1|2" per job once all are checked;
                                                         exit 3 and no verdicts when it cannot check them all
    check_stamps.py record  NAME FILE --trace LOG [--skipped N] [--audit-fails]
                                                         record NAME's stamp from the trace of the run that passed
                                                         (N: the skipped tests its output shows); --audit-fails: exit
                                                         1, recording nothing, when the declaration audit warns
    check_stamps.py why     NAME                         say why NAME is not current
    check_stamps.py declared NAME                        the patterns NAME falls back to (an untraceable program)
    check_stamps.py audit [NAME...]                      the reads of a manifest job's last recorded pass that its
                                                         steps do not declare in tools/pipeline/checks.toml (every
                                                         manifest job when no NAME); exit 1 with any, 2 when one
                                                         cannot be audited (no stamp, a manifest that will not read)
    check_stamps.py audit-report DIR [-v]                compare the files a CHECK_AUDIT run opened with the declarations
                                                         (-v: for every job, the first two path parts
                                                         of each file it read)

check.sh runs each job under the trace hook of tools/audit/traced.py (shared with make panels): every repo file the
job's Python processes open, probe and find absent, every folder they list and every subprocess they start goes to
a log. After a pass the stamp records that read set with its hashes and a key: panel_stamps.digest over the job
name, tools/check.sh and the hook, the Python, the plugin's state, what the job reads from outside the repo
(outside_state; for a step manifest job also a digest of its entry and the git refs its `git` field names, so an
edited entry reruns that job only), and the output of each read-only git command it ran (run again at compare time).
The next run skips the job only when the key and every read-set entry match. A unit job whose tests skipped records
them (id and reason, from the hook) in its key; what they skipped on is an input like any other: a file or folder
the trace saw, a shutil.which lookup (looked up again), the interpreters' packages, a git command or a REFS_OF ref.
RETIRED job names have their stamps dropped by every current-batch, the one process that checks every job of a
check.sh run before any starts. A job that ran a program the hook cannot see (bash, a writing git, a Python child
with the hook dropped) inside the checkout falls back to its declaration (`declared`, wide on purpose: whole folders).
Nothing is skipped or recorded while HART_TABLES is set or the plugin is off its pin (panel_stamps.unstampable), for
a trace that is missing or short of a Python process, or when a file the job read changed while it ran; check.sh
never skips when CI is set, FULL=1 or CHECK_AUDIT (FULL=1 still records). Stamps hold content hashes and repo paths,
so one per-user folder (<main checkout>/.cache/hart/check-stamps, or CHECK_STAMPS_DIR) serves every worktree; the
Windows box keeps one per ref (tools/hosts/win_run.sh); a file hash is reused while its size and mtime stay.

tests/test_check_stamps.py checks that a recorded read set holds everything an independent audit hook
(tools/audit/stamp_audit/sitecustomize.py, CHECK_AUDIT) saw the same jobs open or list. What neither hook can see:
the plugin's files (covered by its commit).

The declaration audit (ADR-037 stages 4a, 4c): after a step-manifest job's traced pass, `record` takes the files
its Python processes read (step_reads; each job is one step), keeps them in the stamp, and names each one its step
does not declare in tools/pipeline/checks.toml; `audit` prints it again from the stamp against the manifest now. It
changes no key and no verdict. It warns, or with --audit-fails (check.sh in a CHECK_AUDIT run and the weekly full run)
fails the job, as does an audit that cannot run (STAMP AUDIT FAILED). The CHECK_AUDIT hook and audit-report above
check the unit jobs' BY_KIND declarations instead.

This file is the entry point, the CLI and the declarations (FILES lists it with its parts): stamps_cache.py holds the
walk, the file-hash cache and the Checker, stamps_audit.py the audits; both are re-exported here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import cast

HERE = Path(__file__).resolve().parent
# The parts (FILES) import each other by name, from any cwd and under any load name (check.sh runs this file by path;
# the tests import it as check_stamps): this folder goes first on sys.path while they are imported and comes off again
# after, as tools/pipeline/manifest.py does for its parts.
_added = str(HERE) not in sys.path
if _added:
    sys.path.insert(0, str(HERE))
try:
    import stamps_cache
    import stamps_audit
finally:
    if _added:
        sys.path.remove(str(HERE))
PARTS = (stamps_cache, stamps_audit)
_stray = [f"{m.__name__} from {getattr(m, '__file__', None)}" for m in PARTS
          if not getattr(m, "__file__", None) or Path(m.__file__).resolve().parent != HERE]
if _stray:      # a part already imported from another folder (a second checkout in one process): never mix the two
    raise ImportError(f"check_stamps.py: its parts must be the files beside it in {HERE}, not {', '.join(_stray)}")
from stamps_audit import (AUDIT_FAILS, AUDIT_HOW, AuditError, _reaches, audit_lines, audit_stamp,  # noqa: E402,F401
                          manifest_steps, read_audit, step_reads)
from stamps_cache import (LITTER, MANIFEST, PRUNE, PRUNE_PATHS, ROOT, Checker, HashCache,  # noqa: E402,F401
                          _file, _import, _pruned, _run, cache_dir, main_checkout, pm, ps, traced, venv_state, walk)

# This file and its parts, from the repo root. A part is covered wherever this file is: tools/ci/stamp_gate.MACHINERY
# lists each, TOOLS covers them for the unit jobs, and none is in ALWAYS, as this file is not.
FILES = tuple(Path(f).resolve().relative_to(ROOT).as_posix() for f in (__file__, *(m.__file__ for m in PARTS)))

STORE = Path(os.environ.get("CHECK_STAMPS_DIR") or cache_dir("check-stamps", ROOT))

# Folder groups. TOOLS is the code and its tests; LAYOUT the shared source and generated data every build reads.
TOOLS = ("tools/**/*",)
LAYOUT = ("jmri/**/*", "cats/**/*")
# Under .claude/: the code (settings, hooks, commands, the skills' scripts and pages) is in CODE. The skills' and
# subagents' Markdown is AGENT_DOCS, declared only by the tests that read it, so a change to it alone is docs
# (tools/ci/changed_kind.py CLAUDE_DOCS) and the docs path runs those tests (tools/ci/docs_unit_tests.py). A test
# checks that every tracked file under .claude/ is in one of the two.
CLAUDE_CODE = (".claude/*", ".claude/hooks/**/*", ".claude/commands/**/*", ".claude/skills/**/*.sh",
               ".claude/skills/**/*.html")
AGENT_DOCS = (".claude/skills/**/*.md", ".claude/agents/**/*.md")
REPO_FILES = ("Makefile", "AGENTS.md", "requirements.txt", ".github/**/*", ".githooks/**/*", *CLAUDE_CODE,
              ".cursor/**/*", ".vscode/**/*")
CODE = (*TOOLS, *LAYOUT, *REPO_FILES)       # what a unit job reads unless it says more
SITE = ("www/**/*", "ops/**/*", "docs/**/*", "wiki/**/*", "media/**/*", "archive/**/*", "external/**/*")
EVERYTHING = ("**/*",)
# The files of ops/hart-ops/data/ that unit-hart-ops reads (a trace of the whole suite, the sts-helpers tests
# included): the rest of that folder (trains.csv, locos.csv, the queues, the sidecars) is not its input.
UNIT_HART_OPS_DATA = ("HART_MergedCarRoster.xml", "OperationsCarRoster.xml", "OperationsEngineRoster.xml",
                      "crew.json", "image_metadata.csv", "industries.csv", "industry_notes.csv", "industry_sheet.csv",
                      "loco_models.csv", "roads.csv", "spot_assignments.csv", "spot_usages.csv")

# job-name prefix -> patterns (tools/check.sh is always added): what a CHECK_AUDIT run saw each unit job read
# (`check_stamps.py audit-report DIR`), widened to whole folders. Other manifest jobs fall back to MANIFEST_CHECK.
BY_KIND: dict[str, tuple[str, ...]] = {
    "public-text": EVERYTHING,
    # ruff (a program the trace cannot see) reads every .py and ruff.toml, and skips what .gitignore files ignore; the
    # version is requirements.txt's pin
    "ruff": ("**/*.py", "ruff.toml", "requirements.txt", ".gitignore", "**/.gitignore"),
    "portal": (*CODE, *SITE),
    # its node scripts (www/scripts/tests/*.js, build_exam_answers.js, build_play_answers.js) read only www/, and a
    # package.json on the way up from them (none today) would set how node loads them. Outside www/ its Python reads
    # the pages' sources (docs/ops, the helix models, the pipeline map, docs/INDEX.md, the inventory workbook in
    # docs/wiring), the crew master and the waybill data the crew pages use, and the card and publication code. The
    # wiki and agent-doc Markdown it reads for the repo guide and the map lanes is in its trace only (docs-path files,
    # left off on purpose: tests/test_check_stamps.py NARROWED). www/ stays whole: node and the deploy script's bash
    # run untraced, so this declaration is its stamp, and its Python and node read files in most of www/'s folders
    "unit-portal": (*CODE, "www/**/*", "package.json", "docs/INDEX.md", "docs/ops/**/*", "docs/benchwork/**/*",
                    "docs/pipeline-map/**/*", "docs/wiring/*.xlsx", "ops/hart-ops/AGENTS.md",
                    "ops/hart-ops/card_pipeline/**/*", "ops/hart-ops/publications/**/*", "ops/station_maps/**/*",
                    "ops/hart-ops/data/crew.json",
                    "ops/hart-ops/data/HART_Spot_Waybills.csv", "ops/hart-ops/data/industries.csv",
                    "ops/hart-ops/data/spot_assignments.csv"),
    # the car cards and publications (it starts no program): their code, tests, assets and logos, the station map
    # scripts, the masters and Operations Pro rosters below, the gitignored photo folders car_paths probes, its pinned
    # test packages (CI installs them), the documents in docs/ops it rebuilds and compares, the site's crew.json, and
    # the STS seed in external/sts-helpers
    "unit-hart-ops": (*CODE, "ops/hart-ops/card_pipeline/**/*", "ops/hart-ops/publications/**/*",
                      "ops/hart-ops/tests/**/*", "ops/hart-ops/operator_logos/**/*", "ops/station_maps/**/*",
                      *(f"ops/hart-ops/data/{name}" for name in UNIT_HART_OPS_DATA), "ops/hart-ops/requirements*.txt",
                      "ops/car-cards/**/*", "ops/hart-ops/CarImagesCardFill*/**/*", "docs/ops/**/*",
                      "www/data/crew.json", "external/sts-helpers/**/*"),
    # build_panels.sh (bash, untraced) runs stand-in steps in test_build_panels; test_panel_stamps runs every real
    # step under its own audit hook (untraced here too). Outside CODE those steps read only what the schematic step
    # does: docs/ops, the crew master and industries.csv through the publications code, the station map pages and
    # the site's crew.json and publications.json (tools/pipeline/panels.toml, step "schematic")
    "unit-schematic": (*CODE, "docs/ops/**/*", "docs/pipeline-map/pipeline_map.json", "wiki/pipelines/**/*",
                       "www/crew/maps/**/*", "www/data/crew.json", "www/data/publications.json",
                       "ops/hart-ops/data/crew.json", "ops/hart-ops/data/industries.csv",
                       "ops/hart-ops/publications/**/*"),
    # test_levels_page compares the article it builds; nothing under docs/ is read
    "unit-anyrail": (*CODE, "www/build/**/*"),
    # test_block_lengths reads every tracked .py; test_roads reads the car pipeline's roads and models
    "unit-hartlib": (*CODE, "**/*.py", "ops/hart-ops/data/roads.csv", "ops/hart-ops/data/loco_models.csv"),
    "unit-mimic": CODE,
    "unit-cats": CODE,
    "unit-jmri-scripts": CODE,
    "unit-jmri": CODE,
    "unit-hosts": CODE,
    "unit-guards": CODE,
}
# What a manifest job with no BY_KIND line falls back to after a program the trace cannot see: every file. A
# Python step that starts no such program is keyed on its trace alone.
MANIFEST_CHECK = EVERYTHING
# Job names check.sh no longer runs, whose stamps every current-batch drops: "static" (the read-only checks as
# one job until ADR-037 stage 4b) and "panels" (build_panels.sh --check as one job until stage 6).
RETIRED = ("static", "panels")

# The masters outside CODE that the data checks' tests read on the real checkout: those with a sidecar
# (tools/ops/check_data.py master_files), and docs/data/entities.csv with the CSV masters it names
# (hartlib.hand_tables.master_files). tests/test_unit_declarations.py checks each list against its source.
SIDECAR_MASTERS = ("docs/wiring/lcos/lcos_signal_logic.csv", "docs/wiring/lcos/lcos_signal_plan_notes.csv",
                   "ops/hart-ops/data/HART_Spot_Waybills.csv", "ops/hart-ops/data/industries.csv",
                   "ops/hart-ops/data/industry_notes.csv", "ops/hart-ops/data/industry_sheet.csv",
                   "ops/hart-ops/data/loco_models.csv", "ops/hart-ops/data/locos.csv", "ops/hart-ops/data/roads.csv",
                   "ops/hart-ops/data/spot_assignments.csv", "ops/hart-ops/data/spot_usages.csv",
                   "ops/hart-ops/data/trains.csv", "www/scripts/archive_catalogue.csv")
ENTITY_MASTERS = ("docs/data/entities.csv", "docs/wiring/lcos/lcos_signal_logic.csv",
                  "docs/wiring/lcos/lcos_signal_plan_notes.csv", "ops/hart-ops/data/HART_Spot_Waybills.csv",
                  "ops/hart-ops/data/image_metadata.csv", "ops/hart-ops/data/industries.csv",
                  "ops/hart-ops/data/industry_sheet.csv", "ops/hart-ops/data/loco_models.csv",
                  "ops/hart-ops/data/locos.csv", "ops/hart-ops/data/roads.csv",
                  "ops/hart-ops/data/spot_assignments.csv", "ops/hart-ops/data/spot_usages.csv",
                  "ops/hart-ops/data/trains.csv", "ops/hart-ops/docs/print/waybills/HART_CC_Waybill_Inventory.csv",
                  "www/scripts/archive_catalogue.csv")

# "kind test" (the test file, before any ".Class") -> patterns added to its kind's: the files that read the site.
EXTRA: dict[str, tuple[str, ...]] = {
    # cs105_roster_sync.sh (bash) refuses when the submodule is not checked out, and the test skips on that answer
    "unit-hosts test_pi_ssh_scripts": ("external/jmri-cs105-roster-sync/**/*",),
    # build_layout_index.py --check (the PNG stamp of the schematic) and check.sh's start, whose verdict
    # (tools/ci/changed_kind.py) reads the pipeline map
    "unit-guards test_check_sh_tables": ("www/scripts/**/*", "www/assets/layout/*.png",
                                         "docs/pipeline-map/pipeline_map.json"),
    # tools/ops/status_counts.py reads wiki/status/ (ADR-038); its git status only compares the tree before and after
    # the www/scripts table writers it runs are .py files
    "unit-guards test_hart_tables_writers": ("wiki/status/**/*", "tools/ops/status_counts.py", "www/scripts/*.py"),
    # it lists the STL folder to check every file there is classified
    "unit-guards test_helix_stl_index": ("www/scripts/*.py", "docs/benchwork/helix/stl/**/*"),
    # git ls-files "*.sh" "*.ps1" "*.py": those files anywhere in the checkout, nothing else
    "unit-guards test_jmri_process_patterns": ("**/*.sh", "**/*.ps1", "**/*.py"),
    # the map build draws the agent-doc lane from the wiki and docs/INDEX.md too (tools/ops/agent_docs_map.py)
    # the map build also reads .gitmodules (the submodule nodes) and lists ops/hart-ops/card_pipeline (a folder node
    # of the map, docs/pipeline-map/pipeline_map.json)
    "unit-guards test_pipeline_map": ("docs/pipeline-map/**/*", "www/scripts/**/*", "wiki/**/*",
                                      "docs/INDEX.md", "ops/hart-ops/AGENTS.md", ".gitmodules",
                                      "ops/hart-ops/card_pipeline/**/*", *AGENT_DOCS),
    # the map and the entry files outside CODE (www/scripts/deploy_hartrailroad.sh); its output roots are in CODE
    "unit-guards test_pipeline_map_coverage": ("docs/pipeline-map/**/*", "www/scripts/**/*", "wiki/**/*",
                                               "docs/INDEX.md", "ops/hart-ops/AGENTS.md", *AGENT_DOCS),
    # the step manifest's loader checks domains, edge sides and local nodes against the map (manifest.repo())
    "unit-guards test_pipeline_manifest": ("docs/pipeline-map/pipeline_map.json",),
    # and its DocsUnitTests list every tracked file under .claude/ (CLAUDE_CODE or AGENT_DOCS, never neither)
    "unit-guards test_check_docs_only": ("docs/pipeline-map/pipeline_map.json", ".claude/**/*"),
    # check_sh_problems takes the steps' scripts from manifest.repo(), which reads the map
    "unit-guards test_stamp_gate": ("docs/pipeline-map/pipeline_map.json",),
    # it loads changed_kind's declarations, the map's boxes among them
    "unit-guards test_unit_declarations": ("docs/pipeline-map/pipeline_map.json",),
    # SkipConditionTest reads every tracked tests/test*.py (git ls-files), ops/ and www/ included: .py files only
    "unit-guards test_stamps_keys": ("**/*.py",),
    # the scanners' scan lists against the manifest: the map (manifest.repo()), the site build's sources and imports
    # and check_hand_tables' scan list, whose CSV masters entities.csv names (hartlib.hand_tables.master_files)
    "unit-guards test_manifest_scans": ("docs/pipeline-map/pipeline_map.json", "docs/data/entities.csv",
                                        "www/scripts/**/*", "ops/hart-ops/card_pipeline/**/*", *AGENT_DOCS),
    "unit-guards test_agent_docs_map": ("docs/pipeline-map/**/*", "www/scripts/**/*", "wiki/**/*", "docs/INDEX.md",
                                        "ops/hart-ops/AGENTS.md", ".gitmodules", *AGENT_DOCS),
    # it builds the committed map with both lanes, as test_agent_docs_map does
    "unit-guards test_map_lane": ("docs/pipeline-map/**/*", "www/scripts/**/*", "wiki/**/*", "docs/INDEX.md",
                                  "ops/hart-ops/AGENTS.md", ".gitmodules", *AGENT_DOCS),
    # the agent-doc cells it checks are in the wiki (home.md, the decisions, pipelines, projects, STATUS.md)
    # and check_agent_docs.py's PATTERNS hold .claude/**, the skills and subagents included
    "unit-guards test_agent_docs_cells": ("wiki/**/*", *AGENT_DOCS),
    # check_ai_speak.DEFAULT_GLOBS (a test keeps the two the same): it lists their folders and fails a glob that
    # matches nothing
    "unit-guards test_ai_speak": ("www/ai/*.html", "www/library/*.html", "www/behind/*.html", "www/guides/*.html",
                                  "www/ap/*.html", "www/exam/index.html", "www/exam/run.html"),
    # check_public_text.py imports private_name from ops/hart-ops/card_pipeline (on sys.path)
    "unit-guards test_public_text": ("ops/hart-ops/card_pipeline/**/*",),
    # both read the real wiki/status/ entries (ADR-038); test_status_merge also merges under .gitattributes
    "unit-guards test_status_merge": ("wiki/status/**/*", "tools/ops/status_counts.py", ".gitattributes"),
    "unit-guards test_status_counts": ("wiki/status/**/*", "tools/ops/status_counts.py"),
    # the merge drivers run under the repo's own .gitattributes in a scratch repo
    "unit-guards test_merge_pipeline_map": (".gitattributes",),
    "unit-guards test_portal_inputs": ("www/scripts/**/*",),
    # the drawings it compares in docs/ops, and hartlib.map_revision's pages: www/data/crew.json from the crew master
    # (ops/hart-ops/data/crew.json through ops/hart-ops/publications), publications.json and the map pages
    "unit-guards test_publish_draft": ("docs/ops/**/*", "ops/hart-ops/data/crew.json", "ops/hart-ops/publications/**/*",
                                       "www/data/**/*", "www/crew/**/*"),
    "unit-guards test_site_device_names": ("www/assets/layout/*.png", "www/scripts/**/*"),  # the PNG stamp, ADR-036
    "unit-guards test_write_inventory": ("docs/wiring/LCOS_Layout_Inventory_v*.xlsx",),  # write_inventory.OUT
    # TheRepo checks every sidecar git lists (check_data.SCAN_GLOBS) against its master, and builds the map's step
    "unit-guards test_check_data": ("**/*.columns.csv", *SIDECAR_MASTERS, "docs/pipeline-map/pipeline_map.json"),
    # Repo runs check_hand_tables.py on the checkout: entities.csv and the CSV masters it names
    "unit-guards test_check_hand_tables": ENTITY_MASTERS,
    # the gallery against the loco master and the photo metadata
    "unit-guards test_check_fleet_gallery": ("ops/hart-ops/data/locos.csv", "ops/hart-ops/data/image_metadata.csv",
                                             "www/data/fleet-gallery.json"),
    # check_locos.py on the checkout, and publish on copies of the master and the queue
    "unit-guards test_check_locos": ("ops/hart-ops/data/locos.csv", "ops/hart-ops/data/locos.columns.csv",
                                     "ops/hart-ops/data/loco_queue.csv"),
    "unit-guards test_check_roster": ("ops/hart-ops/data/locos.csv",),
    "unit-guards test_check_json": ("www/scripts/published-files.json",),
    # the step manifest's writers against the map's boxes (manifest.repo())
    "unit-guards test_manifest_writers": ("docs/pipeline-map/pipeline_map.json",),
    # the map's lines, facets and step times on the committed map and docs/pipeline-map/timings.json
    "unit-guards test_pipeline_map_eff": ("docs/pipeline-map/pipeline_map.json", "docs/pipeline-map/timings.json"),
    "unit-guards test_pipeline_map_facets": ("docs/pipeline-map/pipeline_map.json", "docs/pipeline-map/timings.json"),
    "unit-guards test_pipeline_map_line": ("docs/pipeline-map/pipeline_map.json",),
    "unit-guards test_step_timings": ("docs/pipeline-map/timings.json",),
    # its run of orient.py's short form on the checkout lists wiki/projects/ and reads each page's status
    "unit-guards test_orient": ("wiki/projects/*.md",),
    # it runs check_data_readers.py over every tracked .py (docs/, ops/ and www/ included)
    "unit-guards test_check_data_readers": ("**/*.py",),
    # the card pipeline's car tools and the host packages' files it compares with the hosts' copies
    "unit-hosts test_host_copies": ("ops/hart-ops/card_pipeline/**/*", "ops/packages/**/*"),
    # the roster master's link to the loco master
    "unit-hosts test_roster_master": ("ops/hart-ops/data/locos.csv",),
    # test_docs_index, test_live_paths and test_pull_tables run their tools in scratch trees only: no line here
    "unit-jmri test_infer_block_lengths": ("docs/jmri/speedmatching/profile-2026-11-08/block_events.csv",),
    "unit-jmri test_speedmatch": ("docs/jmri/speedmatching/profile-2026-11-08/block_events.csv",),
    "unit-jmri test_speedmatch_distance": ("docs/jmri/speedmatching/RUNBOOK.md",),
    # the speed table from the 2026-11-08 profile's laps and results
    "unit-jmri test_speedmatch_speed_table": ("docs/jmri/speedmatching/profile-2026-11-08/manual_laps.csv",
                                              "docs/jmri/speedmatching/profile-2026-11-08/results.csv"),
    # the committed track-length page it compares
    "unit-jmri test_export_track_lengths": ("docs/jmri/TRACK_LENGTHS.md",),
    # the website page shares the live page's ids; its node run reads stdin only
    "unit-jmri test_speedmatch_site_export": ("www/ai/speed-runs.html",),
}
# "kind test" of EXTRA -> the -k filter tools/ci/docs_unit_tests.py runs it with: the one class that reads docs
DOCS_K: dict[str, str] = {"unit-jmri test_speedmatch_distance": "RunnerSource.",
                          "unit-guards test_check_docs_only": "DocsUnitTests.",
                          "unit-guards test_agent_docs_map": "AgentFrontMatter."}  # RUNBOOK.md's log tags


# "kind test" -> folders the job only lists (a bare exists-or-not look; no file in them is read), left out of the stamp.
LISTED_ONLY: dict[str, tuple[str, ...]] = {
    "unit-hosts test_deploy_preflight": ("www",),
}


# The quick jobs tests/test_check_stamps.py runs under CHECK_AUDIT: one of each kind of folder a job tests.
AUDIT_SAMPLE = ("unit-hartlib", "unit-mimic", "unit-anyrail", "unit-cats", "unit-jmri-scripts",
                "unit-guards test_turnout_startup", "unit-hosts test_load_env", "unit-jmri test_speedmatch_distance")
# "kind test" -> the jobs it runs through a check.sh of its own (bash, untraced: its stamp falls back to its
# declaration): what their declarations name (its AuditTest checks they cover what each read), and RUNS_JOBS_ALSO:
# .gitmodules (check.sh's start-up) and .gitignore (git check-ignore and ls-files). The rest of the start-up reads
# tools/, except portal_inputs.py, whose answer only names the portal job, which CHECK_ONLY leaves out of that run.
RUNS_JOBS: dict[str, tuple[str, ...]] = {
    "unit-guards test_check_stamps": AUDIT_SAMPLE,
}
RUNS_JOBS_ALSO = (".gitmodules", ".gitignore")


def _test_key(name: str) -> str | None:
    """"kind test" for job `name` ("unit-hosts test_deploy_gates.SomeTest" -> "unit-hosts test_deploy_gates"), or
    None for a job named by its kind alone."""
    parts = name.split(" ", 2)
    return f"{parts[0]} {parts[1].split('.')[0]}" if len(parts) > 1 else None


def _manifest_name(name: str) -> bool:
    """Whether `name` has the shape of a step manifest job (a step name: no space, not a unit-* kind). Whether the
    manifest really holds it is manifest_key's to say, when the key is made (a ManifestError: run, record nothing)."""
    return bool(pm.NAME_RE.fullmatch(name)) and not name.startswith("unit-")


def declared(name: str) -> tuple[str, ...] | None:
    """The patterns job `name`'s stamp covers, or None when it is not a stampable job (a "... skipped" placeholder)."""
    if re.search(r" skipped\b", name):
        return None
    pats = BY_KIND.get(name.split(" ", 1)[0])
    if pats is None and _manifest_name(name):
        pats = MANIFEST_CHECK
    if pats is None:
        return None
    tk = _test_key(name)
    extra = EXTRA.get(tk, ()) if tk else ()
    inner = (*(p for job in RUNS_JOBS[tk] for p in _declared_job(job)), *RUNS_JOBS_ALSO) if tk in RUNS_JOBS else ()
    return tuple(dict.fromkeys((*pats, *extra, *inner, "tools/check.sh")))


def _declared_job(job: str) -> tuple[str, ...]:
    """declared(job) for a job a table names: one that is not stampable is an error in the table."""
    pats = declared(job)
    if pats is None:
        raise ValueError(f"check_stamps.RUNS_JOBS names {job!r}, which is not a stampable job")
    return pats


def check_tables() -> None:
    """The tables keyed by "kind test" name a kind in BY_KIND, and RUNS_JOBS does not nest (a job that runs a job
    that runs jobs) and names only stampable jobs. Raises ValueError."""
    for label, table in (("EXTRA", EXTRA), ("LISTED_ONLY", LISTED_ONLY), ("RUNS_JOBS", RUNS_JOBS)):
        for tk in table:
            parts = tk.split(" ")
            if len(parts) != 2 or parts[0] not in BY_KIND or not parts[1]:
                raise ValueError(f"check_stamps.{label}: {tk!r} is not \"<kind in BY_KIND> <test file>\"")
    for tk, jobs in RUNS_JOBS.items():
        for job in jobs:
            if _test_key(job) in RUNS_JOBS:
                raise ValueError(f"check_stamps.RUNS_JOBS: {tk!r} runs {job!r}, which runs jobs of its own")
            _declared_job(job)
    if set(GIT_REFS) != set(pm.GIT_REFS):
        raise ValueError(f"check_stamps.GIT_REFS ({', '.join(GIT_REFS)}) and manifest.GIT_REFS "
                         f"({', '.join(pm.GIT_REFS)}) name other refs")
    for job, refs in REFS_OF.items():
        if declared(job) is None:
            raise ValueError(f"check_stamps.REFS_OF: {job!r} is not a stampable job")
        if from_manifest(job):
            raise ValueError(f"check_stamps.REFS_OF: {job!r} is a job of {MANIFEST.as_posix()}, whose `git` field "
                             f"names its refs")
        unknown = [r for r in refs if r not in GIT_REFS]
        if unknown:
            raise ValueError(f"check_stamps.REFS_OF: {job!r} names {', '.join(unknown)}, not in GIT_REFS")


def plan_file() -> Path:
    """The AnyRail plan levels_svg.py and plan_lengths.py read (private, never in the repo)."""
    return Path(os.environ.get("ANYRAIL_PLAN") or Path.home() / "Documents/Layout/Lee Nevo Design Version 5.3c.any")


# The git refs a job's key holds besides the git commands its trace replays: a manifest job's `git`, else REFS_OF.
# test_redeploy_commit's deploy script (bash) stages HEAD's tree and refuses a commit not on origin/main (its tests
# skip by that); test_deploy_stage stages from a clone of HEAD while its read set hashes the tree.
GIT_REFS = {"head": ("rev-parse", "HEAD"), "base": ("merge-base", "HEAD", "origin/main"),
            "origin": ("rev-parse", "origin/main")}
REFS_OF: dict[str, tuple[str, ...]] = {
    "unit-hosts test_redeploy_commit": ("head", "base", "origin"),
    "unit-hosts test_deploy_stage": ("head",),
}


# The environment that picks other inputs, and what tests skip on (tests/test_stamps_keys.py: every variable a
# test's skip reads is here): CHECK_AUDIT (test_check_stamps in an audit run), UPDATE_GOLDEN (golden files rewritten),
# HART_CACHE_DIR (moves every shared cache folder, hartlib.paths.cache_dir: .cache paths are in no read set, so it is
# the only trace of which cache a job read), HART_GUARD_JMRI_RUNNING (forces hartlib.tables.jmri_running's answer,
# which the table writers and their tests refuse or skip on; set by hand only, so a local skip is where it matters).
KEY_ENV = ("ANYRAIL_PLAN", "JMRI_LAYOUT", "SCHEMATIC_CACHE", "SCHEMATIC_REQUIRED", "CHECK_AUDIT", "UPDATE_GOLDEN",
           "HART_CACHE_DIR", "HART_GUARD_JMRI_RUNNING")


def from_manifest(name: str) -> bool:
    """Whether check.sh runs job `name` from the step manifest: every stampable job but the unit tests (one job per
    step of tools/pipeline/checks.toml)."""
    return declared(name) is not None and not name.split(" ", 1)[0].startswith("unit-")


def manifest_key(name: str, ck: Checker) -> "pm.JobKey":
    """A manifest job's entry digest and git refs. Raises manifest.ManifestError when the manifest cannot be read or
    holds no such job (check.sh then runs the job and records nothing)."""
    keys = ck.manifest()
    if name not in keys:
        raise pm.ManifestError(f"{MANIFEST.as_posix()} has no job {name!r}, which check.sh runs from it "
                               f"(its jobs: {', '.join(keys)})")
    return keys[name]


def outside_state(name: str, ck: Checker, wide: bool = False) -> str:
    """What the jobs read from outside the traced files: the private AnyRail plan, the interpreters and their
    packages, the environment that picks other inputs, the git refs the job's manifest entry names (REFS_OF for a
    unit job), and for a manifest job the digest of its entry (manifest_key). `wide` (a job that ran an untraceable program) adds the names of the
    files git tracks or would add."""
    plan = plan_file()
    parts = [f"plan={ck.cache(plan) if plan.is_file() else 'absent'}",
             f"python3={ck.venv(Path(sys.executable))}"]
    if wide:
        parts.append("tracked=" + hashlib.sha256(ck.git("ls-files", "-co", "--exclude-standard").encode()).hexdigest())
    hops = ck.root / "ops/hart-ops/.venv/bin/python"
    if name in ("unit-hart-ops", "public-text") and hops.exists():
        parts.append(f"hops={ck.venv(hops)}")
    entry = manifest_key(name, ck) if from_manifest(name) else None
    refs = entry.git if entry else REFS_OF.get(name) or REFS_OF.get(_test_key(name) or "", ())
    for ref in refs:
        parts.append(f"{ref}=" + ck.git(*GIT_REFS[ref]).strip())
    if entry:
        parts.append(f"manifest={entry.digest}")
    parts += [f"{k}={os.environ.get(k, '')}" for k in KEY_ENV]
    parts.append(f"euid={os.geteuid() if hasattr(os, 'geteuid') else ''}")    # test_operating skips as root
    return "\n".join(parts)


def not_stampable(name: str, ck: Checker | None = None) -> str | None:
    if declared(name) is None:
        return f"{name} is not a stampable job"
    # also while HART_TABLES is set, for every job: the unit jobs run without it
    return ck.unstampable() if ck else cast("str | None", ps.unstampable(ROOT))


# check.sh, the loader that makes the manifest's job lines (manifest.py and its parts, pm.FILES), and the hook: an edit
# to one reruns every job. tools/pipeline/checks.toml is not here: each job's key holds its own entry (manifest_key).
ALWAYS = ("tools/check.sh", *pm.FILES, *traced.HOOK_FILES)


def _patterns(name: str, programs: list[str], ck: Checker) -> tuple[str, ...]:
    """What the key hashes: check.sh, the hook, a panels job's outputs and panel_stamps.CODE, and declared(name)."""
    entry = manifest_key(name, ck) if from_manifest(name) else None
    base = (*ALWAYS, *entry.panel, *ps.CODE) if entry and entry.panel is not None else ALWAYS
    return (*base, *(declared(name) or ())) if programs else base


def skip_list(skips: Iterable[Sequence[object]]) -> list[list[str]]:
    """The skipped tests a stamp holds: [test id, reason] pairs, sorted, each once."""
    return [list(s) for s in sorted({(str(i), str(r)) for i, r in skips})]


def key(name: str, ck: Checker, programs: list[str], gits: list[list[str]],
        skips: Iterable[Sequence[object]] = ()) -> str:
    """The stamp key: job, check.sh and the hook, interpreter, plugin, outside state and git output now, for a job
    that ran an untraceable program every file its declaration names, and the tests its passing run skipped (their
    ids and reasons): what they skipped on is in the rest of the key and the read set."""
    pats = _patterns(name, programs, ck)
    extra = (outside_state(name, ck, bool(programs)) + f"\nprograms={','.join(programs)}"
             + f"\ngit={','.join(ck.replay(gits))}")
    if skips:
        extra += "\nskips=" + json.dumps(skip_list(skips))
    digest: str = ps.digest(f"check:{name}", (), pats, ck.root, hasher=ck.cache, files=ck.walk(pats), extra=extra,
                            plugin=ck.plugin())
    return digest


def why_not_current(name: str, root: Path = ROOT, store: Path = STORE, checker: Checker | None = None) -> str | None:
    """None when job `name` may be skipped, else why it must run. With no `checker`, one of its own (saved after)."""
    ck = checker or Checker(root, store)
    try:
        stamp = traced.load(_file(name, ck.store))
        if not stamp:
            return "no stamp"
        k = key(name, ck, stamp.get("programs", []), stamp.get("git", []), stamp.get("skips", []))
        return cast("str | None", traced.mismatch(stamp, k, str(ck.root), hasher=lambda p: ck.cache(Path(p))))
    finally:
        if checker is None:
            ck.cache.save()


def is_current(name: str, root: Path = ROOT, store: Path = STORE) -> bool:
    return why_not_current(name, root, store) is None


def snapshot(name: str, root: Path = ROOT, store: Path = STORE, checker: Checker | None = None) -> str:
    """traced.snapshot with the plugin's and `name`'s outside state: saved before the job, compared at record."""
    ck = checker or Checker(root, store)
    try:
        state: str = ck.snapshot(outside_state(name, ck, True))   # stamps_cache is imported by name: Any to mypy
        return state
    finally:
        if checker is None:
            ck.cache.save()


def verdict(name: str, ck: Checker, save: Path | None) -> tuple[int, str | None]:
    """`current`'s answer for job `name`: (0, None) when its stamp holds (skip it), (1, why) when it must run and may
    record, (2, why) when it is not stampable now (run it, record nothing). `save` gets the snapshot of a stampable
    job, taken before it runs, for `record`."""
    unstampable = not_stampable(name, ck)
    if unstampable:
        return 2, unstampable
    reason = why_not_current(name, checker=ck)
    if save:
        save.write_text(snapshot(name, checker=ck) + "\n")
    return (0, None) if reason is None else (1, reason)


class BatchError(Exception):
    """current-batch stopped: check.sh then runs every job and records none."""


def read_names(path: Path) -> list[str]:
    """The job names of a current-batch, one per line in check.sh's order (line i is job i). Raises BatchError."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise BatchError(f"cannot read the job names in {path}: {exc}") from exc
    names = text.split("\n")
    if names and names[-1] == "":
        names.pop()
    if not names:
        raise BatchError(f"{path} names no job")
    for i, name in enumerate(names):
        if not name.strip() or name != name.strip():
            raise BatchError(f"{path} line {i + 1}: {name!r} is no job name (empty, or spaces around it)")
    return names


def current_batch(names: list[str], out: Path, why: bool, root: Path = ROOT, store: Path = STORE) -> list[int]:
    """`current` for every job of one check.sh run in one process, with one Checker: job i (names[i]) gets out/i.stamp
    (the snapshot, for a stampable job) and, with `why`, out/i.stamplog ("runs: <why>"); out/verdicts gets "i<TAB>code"
    per job once all are checked (written whole or not at all). A job whose check raises gets 2 (run, record nothing),
    its stamp is dropped so its next pass records afresh, and its stamplog says why. Raises BatchError when it cannot
    check the batch at all (the folder): then no job may be skipped."""
    if not out.is_dir():
        raise BatchError(f"{out} is not a folder")
    ck = Checker(root, store)
    for old in RETIRED:
        if old in names:
            raise BatchError(f"check.sh queued {old!r}, a job name check_stamps.RETIRED says it no longer runs")
        try:
            _file(old, ck.store).unlink(missing_ok=True)
        except OSError as exc:      # a store this run cannot write (a restored cache): the stale file is only litter
            print(f"check_stamps.py current-batch: cannot drop the retired {old!r} stamp: {exc}", file=sys.stderr)
    verdicts = []
    try:
        for i, name in enumerate(names):
            log = out / f"{i}.stamplog"
            try:
                code, reason = verdict(name, ck, out / f"{i}.stamp")
            except Exception as exc:  # noqa: BLE001 - this job runs and records nothing; its stamp is dropped
                code, why_now = 2, f"the stamp check failed: {type(exc).__name__}: {exc}; its stamp is dropped"
                _file(name, ck.store).unlink(missing_ok=True)
                (out / f"{i}.stamp").unlink(missing_ok=True)
                log.write_text(f"runs: {why_now}\n")      # printed with the job's output, --why or not
            else:
                if why and reason:
                    log.write_text(f"runs: {reason}\n")
            verdicts.append(code)
    finally:
        ck.cache.save()
    if len(verdicts) != len(names):
        raise BatchError(f"{len(verdicts)} verdicts for {len(names)} jobs")
    tmp = out / f"verdicts.{os.getpid()}.tmp"
    tmp.write_text("".join(f"{i}\t{code}\n" for i, code in enumerate(verdicts)))
    os.replace(tmp, out / "verdicts")
    return verdicts


def record(name: str, trace_log: str | Path, root: Path = ROOT, store: Path = STORE, before: str | None = None,
           skipped: int = 0, audit: dict | None = None) -> str | None:
    """Record `name`'s stamp from `trace_log`; None when recorded, else why not (any old stamp is dropped).
    `before` is the snapshot() taken before the job: a different one now records nothing. `skipped` is the number of
    skipped tests the job's output shows: the trace must hold at least that many skips, with their ids and reasons.
    `audit` (a manifest job's step_reads) is kept in the stamp for `check_stamps.py audit`; it is not in the key."""
    t = traced.parse(trace_log)
    reason: str | None = traced.problem(t)
    ck = Checker(root, store)
    try:
        if reason is None and before is not None and before != snapshot(name, checker=ck):
            reason = ("HEAD, origin/main, the plugin, an interpreter, the private plan or the job's entries in "
                      "tools/pipeline/checks.toml changed while the job ran")
        if reason is None and len(t.skips) < skipped:
            reason = (f"the output shows {skipped} skipped tests and the trace holds {len(t.skips)}: which tests "
                      "skipped, and why, is not known")
        if reason is None:
            main = main_checkout(root)
            programs, gits = traced.untraced(t, str(root), (str(main),) if main else ())
            rs = traced.read_set(t, str(root))
            hashed = [p.relative_to(root).as_posix() for p in ck.walk(_patterns(name, programs, ck))]
            late = traced.changed_since(t, rs, str(root), hashed)
            if late:
                reason = f"{late[0]} changed while the job ran"
            else:
                skips = skip_list(t.skips)
                k = key(name, ck, programs, gits, skips)
                meta = {"programs": programs, "git": gits, **({"skips": skips} if skips else {}),
                        **({"audit": audit} if audit is not None else {})}
                traced.save(_file(name, store), traced.make_stamp(k, t, str(root), hasher=lambda p: ck.cache(Path(p)),
                                                                  **meta))
                return None
    finally:
        ck.cache.save()
    _file(name, store).unlink(missing_ok=True)
    return reason


# ---- the audits: what stays here reads the declarations above; the rest is stamps_audit.py ----

def uncovered(name: str, files: set[str], dirs: set[str]) -> list[str]:
    pats = declared(name)
    assert pats is not None
    # the shared build cache (<main checkout>/.cache/, hartlib.paths.cache_dir) is keyed on real inputs: no input itself
    files = {f for f in files if not f.startswith(".cache/")}
    dirs = {d for d in dirs if d != ".cache" and not d.startswith(".cache/")}
    bad = [f for f in sorted(files) if not any(ps._glob_match(f, p) for p in pats)]
    tk = _test_key(name)
    listed = LISTED_ONLY.get(tk, ()) if tk else ()
    for d in sorted(dirs):
        if d in (".", "") or d in listed:
            continue
        if not any(_reaches(d, pat) for pat in pats):
            bad.append(d + "/")
    return bad


def audit_trace(name: str, trace_log: str | Path, root: Path = ROOT, fails: bool = False) -> tuple[list[str], dict | None, int]:
    """`record`'s audit: (lines, the step_reads for the stamp or None, warnings: 1 for an audit that cannot run, which
    says so in one STAMP AUDIT FAILED line). `fails`: the lines say this run fails on a warning."""
    if not from_manifest(name):
        return [], None, 0
    how = AUDIT_FAILS if fails else AUDIT_HOW
    try:
        steps = manifest_steps(name, root)
        if steps[0].unaudited:
            return [f"stamp audit: {name}: not audited: {steps[0].unaudited}"], None, 0
        audit = step_reads(name, trace_log, root, steps)
    except (AuditError, pm.ManifestError) as exc:
        return [f"STAMP AUDIT FAILED: {name}: {exc} ({'' if fails else 'the job passes; '}{how})"], None, 1
    lines, count = audit_lines(name, audit, steps, how=how)
    return lines, audit, count


def record_cmd(args: list[str], root: Path = ROOT, store: Path = STORE) -> int:
    """`record NAME FILE --trace LOG [--skipped N] [--audit-fails]` (flags in that order): 0; with --audit-fails, 1
    when the audit warned (nothing recorded) and 3 when it audited nothing (not stampable now, bash, a unit job)."""
    fails, args = (True, args[:-1]) if args[-1:] == ["--audit-fails"] else (False, args)
    if len(args) not in (4, 6) or args[2] != "--trace" or args[4:5] not in ([], ["--skipped"]):
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    name, snap, trace, skipped = args[0], args[1], args[3], args[5] if len(args) == 6 else "0"
    if not skipped.isdigit():
        print(f"check_stamps.py record: --skipped takes a count, not {skipped!r}; not stamped")
        return 2
    if not_stampable(name) is not None:
        return 3 if fails else 0
    report, audit, bad = audit_trace(name, trace, root, fails=fails)
    reason = ("the declaration audit below failed" if fails and bad     # the job fails; any older stamp stays
              else record(name, trace, root, store, Path(snap).read_text().strip(), int(skipped), audit))
    if reason or report:
        print("\n".join([*([f"not stamped: {reason}"] if reason else []), *report]))
    return 0 if not fails else 1 if bad else 0 if audit is not None and not audit.get("bash") else 3


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        check_tables()
    except ValueError as exc:       # every job runs and records nothing (check.sh: an answer other than 0 or 1)
        print(f"check_stamps.py: {exc}", file=sys.stderr)
        return 2
    try:
        return _main(argv)
    except pm.ManifestError as exc:     # a manifest job's key cannot be made: it runs and records nothing
        print(f"check_stamps.py: not stamped: {exc}", file=sys.stderr)
        return 2


def _main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "current":
        name, save = argv[1], None
        if "--save" in argv:
            save = Path(argv[argv.index("--save") + 1])
        why = "--why" in argv              # say why it runs (a CI pull request run: check.sh CHECK_SKIP_FROM)
        ck = Checker(ROOT, STORE)
        try:
            code, reason = verdict(name, ck, save)
        finally:
            ck.cache.save()
        if reason and why:
            print(f"runs: {reason}")
        return code
    if argv[:1] == ["current-batch"] and len(argv) in (3, 4) and argv[3:] in ([], ["--why"]):
        try:
            current_batch(read_names(Path(argv[1])), Path(argv[2]), why=len(argv) == 4)
        except BatchError as exc:
            print(f"check_stamps.py current-batch: {exc}", file=sys.stderr)
            return 3
        return 0
    if len(argv) == 2 and argv[0] == "why":
        print(not_stampable(argv[1]) or why_not_current(argv[1]) or "current")
        return 0
    if argv[:1] == ["record"]:
        return record_cmd(argv[1:])
    if argv[:1] == ["audit"]:
        rc: int = audit_stamp(argv[1:], ROOT, STORE)
        return rc
    if len(argv) == 2 and argv[0] == "declared":
        print("\n".join(declared(argv[1]) or ()))
        return 0
    if argv[:1] == ["audit-report"] and (len(argv) == 2 or argv[2:] == ["-v"]):
        if not Path(argv[1]).is_dir():
            print(f"check_stamps.py audit-report: {argv[1]} is not a folder (CHECK_AUDIT=DIR FULL=1 tools/check.sh "
                  "writes one)", file=sys.stderr)
            return 2
        rc = 0
        for name, (files, dirs) in read_audit(Path(argv[1])).items():
            if declared(name) is None:
                continue
            bad = uncovered(name, files, dirs)
            tops = sorted({"/".join(f.split("/")[:2]) for f in files})
            print(f"{name}: {len(files)} files read{' ; UNCOVERED ' + ', '.join(bad[:20]) if bad else ''}")
            if "-v" in argv or bad:
                print("    reads:", ", ".join(tops))
            rc |= bool(bad)
        return rc
    print(__doc__.split("\n\n")[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
