"""check_stamps: the declarations (what a job's stamp falls back to, and the tables that say so), and the audit that
a recorded read set holds what an independent audit hook saw the same jobs read (a quick sample here, run through
check.sh: this file's job runs jobs, check_stamps.RUNS_JOBS). The rest of the stamp tests are test_stamps_*.py."""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_stamps as cs  # noqa: E402

REPO = cs.ROOT
CHECK_SH = (REPO / "tools" / "check.sh").read_text(encoding="utf-8")
# Jobs the audit runs for real (check_stamps.AUDIT_SAMPLE, which this test's own declaration is built from).
# check.sh matches CHECK_ONLY with bash's =~ (POSIX ERE), so the names are joined as they are: letters, digits,
# "_", "-" and spaces only (DeclarationTest.test_the_audit_sample_names_are_plain).
AUDITED = "^(" + "|".join(cs.AUDIT_SAMPLE) + ")$"
# Jobs whose declarations were narrowed off the wiki from what the audit saw them read (2026-11-24).
NARROWED = ("unit-guards test_check_stamps", "unit-hosts test_deploy_stage", "unit-guards test_hart_tables_writers",
            "unit-portal")
# What the 2026-11-24 audit (CHECK_AUDIT=DIR FULL=1 tools/check.sh) saw each narrowed job read outside CODE: each must
# stay covered by its declaration (the audit sees Python only; the comments in check_stamps.EXTRA say what the
# untraced programs read).
NARROWED_READS: dict[str, tuple[set[str], set[str]]] = {   # job -> (files read, folders listed)
    "unit-guards test_hart_tables_writers": ({"wiki/status/current/backups.md", "www/scripts/build_layout_index.py"},
                                             {"www/scripts"}),
    "unit-portal": ({"docs/ops/stations/barn.md", "docs/wiring/LCOS_Layout_Inventory_v86.xlsx",
                     "www/scripts/tests/test_x.py", "www/play/runs.js", "www/index.html"},
                    {"docs/ops/stations", "docs/wiring", "ops/hart-ops/card_pipeline", "www/crew/maps/barn",
                     "www/scripts/tests"}),
    # the files the deploy's bash copies (stage.sh), which no hook sees; the reference CSV moved to jmri/ on 2026-11-25
    "unit-hosts test_deploy_stage": ({"jmri/layouts/hart/data/speed_by_step_2026-11-08.csv",
                                      "jmri/layouts/hart/output/tables.xml", "cats/scripts/install_ops_files.sh",
                                      "tools/hosts/pi/apply_hart_package_local.sh"}, {"jmri/resources/jmri-web"}),
}

# What the 2026-11-24 audit (CHECK_AUDIT=DIR FULL=1 tools/check.sh on dc25d8ea) saw each of these jobs read or list
# outside its old declaration (audit-report called them UNCOVERED), and a read just past the widened one, which must
# still be reported: each declaration was widened to those folders and no further.
WIDENED_READS: dict[str, tuple[set[str], set[str], str]] = {   # job -> (files read, folders listed, still outside)
    "unit-guards test_agent_docs_cells": ({"wiki/AGENTS_GIT.md", "wiki/REPOS.md", "wiki/STATUS.md", "wiki/home.md",
                                           "wiki/decisions/ADR-001-layout-identity.md", "AGENTS.md"},
                                          {"wiki/decisions", "wiki/pipelines", "wiki/projects"}, "docs/INDEX.md"),
    "unit-guards test_agent_docs_map": ({".gitmodules", "wiki/STATUS.md"}, set(), ".gitattributes"),
    "unit-guards test_ai_speak": (set(), {"www/ai", "www/ap", "www/behind", "www/guides", "www/library"},
                                  "www/crew/index.html"),
    "unit-guards test_helix_stl_index": ({"docs/benchwork/helix/stl/a.stl"}, {"docs/benchwork/helix/stl"},
                                         "docs/benchwork/helix/notes.md"),
    "unit-guards test_pipeline_map": ({".gitmodules"}, {"ops/hart-ops/card_pipeline"}, "ops/hart-ops/README.md"),
    "unit-guards test_public_text": ({"ops/hart-ops/card_pipeline/private_name.py"}, {"ops/hart-ops/card_pipeline"},
                                     "ops/hart-ops/README.md"),
    "unit-guards test_status_merge": ({".gitattributes", "wiki/status/current/backups.md"}, set(), "wiki/STATUS_LOG.md"),
}


# the end of both check_stamps.record refusals for a change while a job ran (the git state, or a file it read)
MOVED_MID_RUN = "changed while the job ran"


# ---- reading the nested check.sh run's output: which audited job failed, and why one recorded no stamp ----

# the heading check.sh's collect prints before each job's log: "--- NAME (12s)", "--- NAME FAILED (12s)", or
# "--- NAME FAILED (killed before it finished, no s)"; the "--- stamps (NAME):" lines inside a log end with ":"
HEADING = re.compile(r"(?m)^--- (?P<name>.+?) (?P<failed>FAILED )?\((?P<took>[^()\n]*)s\)$")
# unittest's summary line for one failing or erroring test: "FAIL: test_x (module.Class.test_x)"
FAILED_TEST = re.compile(r"(?m)^(?:FAIL|ERROR): (?P<test>\S+)(?: \((?P<id>[^)\n]+)\))?")
# the line check.sh adds to a job's log when the declaration audit, not the job's own tests, failed it
AUDIT_FAILED_JOB = "FAILED by the declaration audit"


class JobSection(NamedTuple):
    """One job's part of a check.sh run's output: its heading and the log printed under it."""
    name: str
    failed: bool
    text: str


def job_sections(stdout: str) -> dict[str, JobSection]:
    """The jobs check.sh's collect printed in `stdout`, by name, each with the text up to the next heading."""
    heads = list(HEADING.finditer(stdout))
    ends = [h.start() for h in heads[1:]] + [len(stdout)]
    return {h["name"]: JobSection(h["name"], bool(h["failed"]), stdout[h.end():end]) for h, end in zip(heads, ends)}


def failed_tests(text: str) -> list[str]:
    """The tests a job's unittest output names as failing or erroring, by full id where unittest gives one; a test
    module that failed to import (unittest's _FailedTest) is named as such."""
    return list(dict.fromkeys(f"{m['test']} (the module failed to import)"
                              if (m["id"] or "").startswith("unittest.loader._FailedTest.") else m["id"] or m["test"]
                              for m in FAILED_TEST.finditer(text)))


def failure_lines(sections: dict[str, JobSection], names: Sequence[str]) -> list[str]:
    """One line for each job in `names` that failed in the nested run: on its own tests, or by the declaration audit
    (an undeclared read, which is what this audit is for)."""
    lines = []
    for name in names:
        sec = sections.get(name)
        if sec is None or not sec.failed:
            continue
        if AUDIT_FAILED_JOB in sec.text or "STAMP AUDIT FAILED" in sec.text:
            said = [ln for ln in sec.text.splitlines() if "UNCOVERED" in ln or "STAMP AUDIT FAILED" in ln
                    or ln.startswith("not stamped:") or AUDIT_FAILED_JOB in ln]
            lines.append(f"inner job {name} failed by the declaration audit:\n  " + "\n  ".join(said))
            continue
        tests = failed_tests(sec.text)
        lines.append(f"inner job {name} failed on its own tests; fix that job first (its own check.sh job shows the "
                     "cause). This audit says nothing about declarations until it passes"
                     + (f". Failing: {', '.join(tests)}" if tests else "")
                     + ". If that job passes outside the audit, the audit run's hooks (tools/audit/stamp_audit, "
                       "tools/audit/trace_hook on PYTHONPATH) changed what it can import")
    return lines


def why_unstamped(sections: dict[str, JobSection], name: str) -> str:
    """Why `name` recorded no stamp, as far as the nested run's output says: the job failed, HEAD, origin/main or a
    file it read changed while it ran (MOVED_MID_RUN), or neither."""
    sec = sections.get(name)
    if sec is None:
        return f"{name} recorded no stamp: the nested run printed no heading for it"
    said = [ln for ln in sec.text.splitlines() if ln.startswith("not stamped:")]
    if sec.failed:
        why = "the job failed"
    elif MOVED_MID_RUN in sec.text:
        why = "HEAD, origin/main or a file it read changed while it ran, on both tries"
    else:
        why = "the job passed and neither HEAD, origin/main nor a file it read changed while it ran"
    return f"{name} recorded no stamp: {why}" + "".join(f"\n  {ln}" for ln in said)


class DeclarationTest(unittest.TestCase):
    def test_every_job_kind_in_check_sh_is_declared(self) -> None:
        kinds = {m.group(1) for m in re.finditer(r"^\s*(?:unit|later)\s+\"?(unit-[a-z-]+)\b", CHECK_SH, re.M)}
        kinds |= {"unit-jmri", "unit-hosts", "unit-guards"}     # their names are built in a loop
        kinds |= set(cs.pm.job_keys())                           # the jobs check.sh queues from the step manifest
        self.assertTrue(kinds)
        for kind in sorted(kinds):
            with self.subTest(kind=kind):
                self.assertIsNotNone(cs.declared(kind), f"{kind} has no declaration in check_stamps.BY_KIND")

    def test_a_placeholder_job_is_not_stampable(self) -> None:
        self.assertIsNone(cs.declared("unit-hart-ops skipped (no ops/hart-ops/.venv)"))
        self.assertIsNone(cs.declared("portal skipped in CI"))

    def test_the_manifest_jobs_are_the_stampable_jobs_that_are_not_unit_tests(self) -> None:
        """check_stamps.from_manifest says which jobs' keys hold manifest entries: every job of the manifest (one per
        step), and BY_KIND's other kinds are unit-*. A step with no BY_KIND line falls back to MANIFEST_CHECK."""
        jobs = set(cs.pm.job_keys())
        self.assertTrue(all(cs.from_manifest(job) for job in jobs))
        self.assertEqual({k for k in cs.BY_KIND if not k.startswith("unit-")} - jobs, set(),
                         "BY_KIND names a job that is neither a unit kind nor a step of tools/pipeline/checks.toml")
        self.assertEqual(cs.declared("phase02"), (*cs.MANIFEST_CHECK, "tools/check.sh"))
        self.assertFalse(cs.from_manifest("portal skipped in CI"))
        self.assertFalse(cs.from_manifest("unit-guards test_x"))
        self.assertFalse(cs.from_manifest("unit-mimic"))
        self.assertIsNone(cs.declared("Two Words"))

    def test_the_one_static_job_is_gone(self) -> None:
        """Its 35 checks are jobs of their own (ADR-037 stage 4b); a stamp left under its name is dropped."""
        self.assertNotIn("static", cs.BY_KIND)
        self.assertNotIn("static", cs.pm.job_keys())
        self.assertIn("static", cs.RETIRED)

    def test_check_sh_is_an_input_of_every_job(self) -> None:
        for kind in (*cs.BY_KIND, *cs.pm.job_keys()):
            self.assertIn("tools/check.sh", cs.declared(kind))

    def test_a_pattern_with_a_question_mark_is_walked_like_a_star(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("tools/x/run1.py", "tools/x/run22.py", "tools/check.sh", "tools/__pycache__/m.pyc"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x")
            self.assertEqual([p.relative_to(root).as_posix() for p in cs.walk(("tools/x/run?.py",), root)],
                             ["tools/x/run1.py"])
            self.assertEqual([p.relative_to(root).as_posix() for p in cs.walk(("tools/check.sh", "tools/x/*"), root)],
                             ["tools/check.sh", "tools/x/run1.py", "tools/x/run22.py"])
            self.assertEqual(cs.walk(("tools/absent.sh",), root), [])

    def test_the_tables_are_consistent(self) -> None:
        cs.check_tables()

    def test_the_audit_sample_names_are_plain(self) -> None:
        for job in cs.AUDIT_SAMPLE:
            self.assertRegex(job, r"^[A-Za-z0-9_ -]+$")
            self.assertIsNotNone(cs.declared(job), job)

    def test_a_job_that_runs_jobs_covers_their_declarations(self) -> None:
        for tk, jobs in cs.RUNS_JOBS.items():
            mine = set(cs.declared(tk))
            self.assertEqual(sorted(set(cs.RUNS_JOBS_ALSO) - mine), [])
            for job in jobs:
                with self.subTest(runner=tk, job=job):
                    self.assertEqual(sorted(set(cs.declared(job)) - mine), [])

    def test_a_wiki_edit_is_no_input_of_jobs_the_audit_shows_do_not_read_it(self) -> None:
        # each of these reran on a one-line ADR edit through a declaration wider than its reads (2026-11-24 audit)
        for name in NARROWED:
            with self.subTest(job=name):
                self.assertFalse(any(cs.ps._glob_match("wiki/decisions/ADR-001-layout-identity.md", p)
                                     for p in cs.declared(name)), cs.declared(name))

    def test_a_narrowed_declaration_covers_what_the_audit_saw_read(self) -> None:
        self.assertEqual(sorted(NARROWED_READS), sorted(set(NARROWED) - set(cs.RUNS_JOBS)))
        for name, (files, dirs) in NARROWED_READS.items():
            with self.subTest(job=name):
                self.assertEqual(cs.uncovered(name, files, dirs), [])
                # and the check compares what it claims: a read outside the declaration is reported
                self.assertEqual(cs.uncovered(name, files | {"wiki/decisions/ADR-001-layout-identity.md"}, dirs),
                                 ["wiki/decisions/ADR-001-layout-identity.md"])
                self.assertEqual(cs.uncovered(name, files, dirs | {"wiki/decisions", "media/photos"}),
                                 ["media/photos/", "wiki/decisions/"])

    def test_a_widened_declaration_covers_what_the_audit_saw_and_no_more(self) -> None:
        for name, (files, dirs, outside) in WIDENED_READS.items():
            with self.subTest(job=name):
                self.assertEqual(cs.uncovered(name, files, dirs), [])
                self.assertEqual(cs.uncovered(name, files | {outside}, dirs), [outside])
                self.assertEqual(cs.uncovered(name, files, dirs | {"media/photos"}), ["media/photos/"])

    def test_the_ai_speak_declaration_is_its_default_globs(self) -> None:
        spec = importlib.util.spec_from_file_location("check_ai_speak", REPO / "tools/audit/check_ai_speak.py")
        cas = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cas)
        self.assertEqual(cs.EXTRA["unit-guards test_ai_speak"], tuple(cas.DEFAULT_GLOBS))

    def test_a_listed_folder_is_covered_only_where_a_pattern_reaches(self) -> None:
        for d, pat, want in (("wiki", "wiki/STATUS.md", True), ("wiki/decisions", "wiki/STATUS.md", False),
                             ("media", "Makefile", False), ("media", "*.md", False), ("media/x", "**/*.py", True),
                             ("tools", "tools/**/*", True), ("tools/hosts/pi", "tools/**/*", True),
                             ("docs", "docs/jmri/**/*", True), ("docs/ops", "docs/jmri/**/*", False)):
            with self.subTest(folder=d, pattern=pat):
                self.assertEqual(cs._reaches(d, pat), want)

    def test_audit_report_takes_v_and_refuses_a_missing_folder(self) -> None:
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "0.name").write_text("unit-mimic\n")
            (Path(tmp) / "0.log").write_text("r\ttools/mqtt-mimic/x.py\nr\twiki/home.md\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cs.main(["audit-report", tmp, "-v"]), 1)
            self.assertIn("UNCOVERED wiki/home.md", out.getvalue())
            self.assertIn("reads: tools/mqtt-mimic, wiki/home.md", out.getvalue())
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(cs.main(["audit-report", f"{tmp}/none"]), 2)
                self.assertEqual(cs.main(["audit-report", tmp, "-x"]), 2)
            self.assertIn("is not a folder", err.getvalue())

    def test_a_bad_table_entry_is_a_clear_error(self) -> None:
        for table, entry in ((cs.EXTRA, {"no-such-kind test_x": ("a",)}), (cs.LISTED_ONLY, {"unit-guards": ("a",)}),
                             (cs.RUNS_JOBS, {"unit-guards test_x": ("unit-guards test_check_stamps",)}),
                             (cs.RUNS_JOBS, {"unit-guards test_x": ("portal skipped in CI",)}),
                             (cs.REFS_OF, {"unit-guards test_x": ("tip",)}),
                             (cs.REFS_OF, {"portal skipped in CI": ("head",)}),
                             (cs.REFS_OF, {"phase02": ("head",)}),
                             (cs.GIT_REFS, {"tip": ("rev-parse", "tip")})):
            with self.subTest(entry=entry), unittest.mock.patch.dict(table, entry):
                with self.assertRaises(ValueError):
                    cs.check_tables()
                with unittest.mock.patch("sys.stderr") as err:
                    self.assertEqual(cs.main(["declared", "unit-hartlib"]), 2)
                self.assertIn("check_stamps", "".join(c.args[0] for c in err.write.call_args_list))


class CommandLineTest(unittest.TestCase):
    """main() parses with argparse: a command line it does not take is a usage error (exit 2), checked before the
    tables or any stamp."""

    def run_main(self, argv: list[str]) -> tuple[int, str]:
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err), unittest.mock.patch.object(cs, "check_tables") as tables:
            rc = cs.main(argv)
        if rc == 2 and "usage:" in err.getvalue():
            tables.assert_not_called()
        return rc, err.getvalue()

    def test_an_unknown_argument_is_a_usage_error(self) -> None:
        for argv, says in ((["why", "unit-mimic", "--extra"], "unrecognized arguments: --extra"),
                           (["declared", "unit-mimic", "unit-hartlib"], "unrecognized arguments: unit-hartlib"),
                           (["current", "unit-mimic", "--sav", "x"], "unrecognized arguments: --sav x"),
                           (["audit-report", "x", "-x"], "unrecognized arguments: -x"),
                           (["record", "unit-mimic", "x"], "the following arguments are required: --trace"),
                           (["current-batch", "names"], "the following arguments are required: dir"),
                           (["no-such-command"], "invalid choice: 'no-such-command'"),
                           ([], "the following arguments are required: command")):
            with self.subTest(argv=argv):
                rc, err = self.run_main(argv)
                self.assertEqual(rc, 2)
                self.assertIn("usage: check_stamps.py", err)
                self.assertIn(says, err)
                self.assertNotIn("Traceback", err)

    def test_a_parsed_command_with_no_branch_is_refused(self) -> None:
        import argparse
        with self.assertRaisesRegex(AssertionError, "'new-command' but _main has no branch"):
            cs._main(argparse.Namespace(command="new-command"))

    def test_every_command_parses_its_documented_form(self) -> None:
        parse = cs.build_parser().parse_args
        args = parse(["current", "unit-mimic", "--save", "s", "--why"])
        self.assertEqual((args.name, args.save, args.why), ("unit-mimic", Path("s"), True))
        args = parse(["current-batch", "n", "d"])
        self.assertEqual((args.names, args.dir, args.why), (Path("n"), Path("d"), False))
        args = parse(["record", "unit-guards test_x", "f", "--trace", "t", "--skipped", "3", "--audit-fails"])
        self.assertEqual((args.name, args.file, args.trace, args.skipped, args.audit_fails),
                         ("unit-guards test_x", "f", "t", "3", True))
        self.assertEqual(parse(["record", "a", "f", "--trace", "t"]).skipped, "0")
        self.assertEqual(parse(["audit"]).names, [])
        self.assertEqual(parse(["audit", "a", "b"]).names, ["a", "b"])
        self.assertTrue(parse(["audit-report", "d", "-v"]).verbose)


class NestedOutputTest(unittest.TestCase):
    """The helpers that read the nested check.sh run's output, on fake output in collect's format."""

    PASSED = "--- unit-mimic (4s)\n.....\nOK\n"
    OWN_FAIL = ("--- unit-hartlib FAILED (31s)\n"
                "======================================================================\n"
                "FAIL: test_one_path (test_devices_one_path.OnePathTest.test_one_path)\n"
                "----------------------------------------------------------------------\n"
                "AssertionError: 1 != 0\n"
                "ERROR: test_load (test_devices.LoadTest.test_load)\n"
                "ERROR: test_render (unittest.loader._FailedTest.test_render)\n"
                "FAILED (failures=1, errors=1)\n")
    MOVED = ("--- unit-cats (20s)\nOK\n--- stamps (unit-cats):\n"
             "not stamped: HEAD, origin/main, the plugin, an interpreter, the private plan or the job's entries in "
             "tools/pipeline/checks.toml changed while the job ran\n")
    AUDIT_FAIL = ("--- unit-anyrail FAILED (9s)\nOK\n--- stamps (unit-anyrail):\nnot stamped: the declaration audit "
                  "below failed\n  UNCOVERED ops/hart-ops/data/loco_models.csv\n"
                  "unit-anyrail: FAILED by the declaration audit above (ADR-037 stage 4c; check_stamps.py record "
                  "exited 1)\n")
    TAIL = "--- unit-jmri test_speedmatch_distance FAILED (killed before it finished, no s)\nFAILED\n"

    def test_the_sections_split_on_collect_headings(self) -> None:
        secs = job_sections("noise\n" + self.PASSED + self.OWN_FAIL + self.MOVED + self.TAIL)
        self.assertEqual(list(secs), ["unit-mimic", "unit-hartlib", "unit-cats", "unit-jmri test_speedmatch_distance"])
        self.assertEqual([s.failed for s in secs.values()], [False, True, False, True])
        self.assertIn("--- stamps (unit-cats):", secs["unit-cats"].text)   # a stamps line is no heading
        self.assertNotIn("unit-cats", secs["unit-hartlib"].text)

    def test_a_job_that_failed_on_its_own_is_named_with_its_tests(self) -> None:
        secs = job_sections(self.PASSED + self.OWN_FAIL + self.TAIL)
        said = failure_lines(secs, ("unit-mimic", "unit-hartlib"))
        self.assertEqual(len(said), 1)
        self.assertTrue(said[0].startswith("inner job unit-hartlib failed on its own tests; fix that job first"))
        self.assertIn("This audit says nothing about declarations until it passes", said[0])
        self.assertIn("test_devices_one_path.OnePathTest.test_one_path, test_devices.LoadTest.test_load, "
                      "test_render (the module failed to import)", said[0])

    def test_a_declaration_audit_failure_is_not_called_the_jobs_own(self) -> None:
        said = failure_lines(job_sections(self.AUDIT_FAIL), ("unit-anyrail",))
        self.assertEqual(len(said), 1)
        self.assertTrue(said[0].startswith("inner job unit-anyrail failed by the declaration audit:"))
        self.assertIn("UNCOVERED ops/hart-ops/data/loco_models.csv", said[0])
        self.assertNotIn("own tests", said[0])

    def test_no_audited_job_failed_says_nothing(self) -> None:
        self.assertEqual(failure_lines(job_sections(self.PASSED + self.MOVED + self.TAIL),
                                       ("unit-mimic", "unit-cats")), [])

    def test_why_a_job_recorded_no_stamp(self) -> None:
        secs = job_sections(self.PASSED + self.OWN_FAIL + self.MOVED)
        failed = why_unstamped(secs, "unit-hartlib")
        self.assertEqual(failed, "unit-hartlib recorded no stamp: the job failed")
        moved = why_unstamped(secs, "unit-cats")
        self.assertIn("unit-cats recorded no stamp: HEAD, origin/main or a file it read changed", moved)
        self.assertIn("\n  not stamped: HEAD, origin/main, the plugin", moved)
        neither = why_unstamped(secs, "unit-mimic")
        self.assertEqual(neither, "unit-mimic recorded no stamp: the job passed and neither HEAD, origin/main nor a "
                                  "file it read changed while it ran")
        self.assertIn("printed no heading", why_unstamped(secs, "unit-portal"))


class AuditTest(unittest.TestCase):
    """Runs check.sh for the quick jobs under CHECK_AUDIT (tools/audit/stamp_audit, an independent hook) while they
    record their traced stamps into a scratch store, and fails for any repo file or folder the audit saw a job touch
    that its read set lacks (or, for a job that ran an untraceable program, that its declaration does not cover)."""

    def test_the_retry_text_is_the_refusal_check_stamps_prints(self) -> None:
        text = (REPO / "tools/audit/check_stamps.py").read_text(encoding="utf-8")
        self.assertEqual(text.count(MOVED_MID_RUN), 2, "both mid-run refusals end with the text the retry looks for")

    @unittest.skipIf(os.environ.get("CHECK_AUDIT"), "already inside an audit run")
    def test_the_traced_read_sets_hold_what_the_jobs_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k not in ("HART_TABLES", "FULL", "CI")
                   and not k.startswith("HART_TRACE")}
            env.update(CHECK_ONLY=AUDITED, CHECK_AUDIT=f"{tmp}/audit", CHECK_STAMPS_DIR=f"{tmp}/stamps")
            # check_stamps refuses to stamp a job when HEAD or origin/main moved while it ran (another session's
            # fetch or merge does that on a shared Mac); that refusal is right, so the run is tried once more then
            for attempt in (1, 2):
                for d in ("audit", "stamps"):
                    shutil.rmtree(f"{tmp}/{d}", ignore_errors=True)
                done = subprocess.run(["bash", str(REPO / "tools/check.sh")], cwd=REPO, env=env,
                                      capture_output=True, text=True, timeout=900)
                unstamped = [n for n in cs.AUDIT_SAMPLE
                             if cs.traced.load(cs._file(n, Path(f"{tmp}/stamps"))) is None]
                if attempt == 1 and unstamped and MOVED_MID_RUN in done.stdout:
                    continue
                break
            sections = job_sections(done.stdout)
            if done.returncode != 0:
                said = failure_lines(sections, cs.AUDIT_SAMPLE)
                self.assertEqual(done.returncode, 0, "\n".join(said) if said
                                 else done.stdout[-3000:] + done.stderr[-2000:])
            jobs = cs.read_audit(Path(f"{tmp}/audit"))
            wanted = list(cs.AUDIT_SAMPLE)
            self.assertEqual(sorted(jobs), sorted(wanted), "the jobs CHECK_ONLY matched are not the ones audited")
            skip = cs.traced._skip_prefixes(str(REPO))
            verified = 0
            for name, (files, dirs) in jobs.items():
                with self.subTest(job=name):
                    self.assertTrue(files, "the audit hook logged nothing")
                    stamp = cs.traced.load(cs._file(name, Path(f"{tmp}/stamps")))
                    # a job whose tests skipped records too, with the skips in its key
                    self.assertIsNotNone(stamp, why_unstamped(sections, name))
                    verified += 1
                    # every sample job, traced or not: this test's own declaration is built from theirs (RUNS_JOBS)
                    self.assertEqual(cs.uncovered(name, files, dirs - {"tools/audit/stamp_audit"}), [])
                    if stamp["programs"]:
                        continue
                    kept = {k for k in (cs.traced.keep(str(REPO / f), str(REPO), skip) for f in files) if k}
                    # the two hooks' own folders (sys.path entries the audit run adds) are no input
                    kept_dirs = {k for k in (cs.traced.keep(str(REPO / d), str(REPO), skip) for d in dirs) if k} \
                        - {"tools/audit/stamp_audit", "tools/audit/trace_hook"}
                    st = stamp["state"]
                    self.assertEqual(sorted(kept - set(st["files"])), [])
                    self.assertEqual(sorted(kept_dirs - set(st["dirs"]) - set(st["files"])), [])
            self.assertEqual(verified, len(wanted))
            # Two quick jobs again, not audited. CHECK_AUDIT is in the key (a test skips inside an audit run), so
            # the first plain run runs them; the second finds them current, checked in one stamp process and never
            # started.
            env.pop("CHECK_AUDIT")
            quick = ("unit-mimic", "unit-jmri test_speedmatch_distance")
            env["CHECK_ONLY"] = "^(" + "|".join(quick) + ")$"
            for run, want in ((1, "ran"), (2, "current")):
                again = subprocess.run(["bash", str(REPO / "tools/check.sh")], cwd=REPO, env=env,
                                       capture_output=True, text=True, timeout=900)
                self.assertEqual(again.returncode, 0, again.stdout[-3000:] + again.stderr[-2000:])
                for name in quick:
                    with self.subTest(run=run, job=name):
                        if want == "ran":
                            self.assertRegex(again.stdout, rf"(?m)^--- {re.escape(name)} \(\d+s\)$")
                        else:
                            self.assertIn(f"{name}: current, skipped", again.stdout)
            self.assertIn(f"{len(quick)} of {len(quick)} jobs current, skipped", again.stdout)


if __name__ == "__main__":
    unittest.main()
