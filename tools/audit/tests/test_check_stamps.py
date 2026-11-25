"""check_stamps: the traced stamps that let tools/check.sh skip a job whose reads are what its last pass saw, and the
audit that a recorded read set holds what an independent audit hook saw the same jobs read (a quick sample here)."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
    "unit-portal": ({"docs/ops/stations/barn.md", "docs/wiring/inventory.md", "www/scripts/tests/test_x.py",
                     "www/play/runs.js", "www/index.html"},
                    {"docs/ops/stations", "docs/wiring", "ops/hart-ops/card_pipeline", "www/crew/maps/barn",
                     "www/scripts/tests"}),
    # the files the deploy's bash copies (stage.sh), which no hook sees
    "unit-hosts test_deploy_stage": ({"docs/jmri/speedmatching/profile-2026-11-08/speed_by_step.csv",
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


class SkipConditionTest(unittest.TestCase):
    def test_every_environment_variable_a_test_skips_on_is_in_the_key(self) -> None:
        """A job whose tests skipped is stamped with the skips in its key; what they skip on must be in the key too.
        An environment variable read in a skip decorator, or in the lines before a skipTest, is in KEY_ENV."""
        tracked = subprocess.run(["git", "ls-files", "*tests/test*.py"], cwd=REPO, capture_output=True, text=True,
                                 check=True).stdout.split()
        read = re.compile(r"""os\.(?:environ\.get|getenv)\(\s*["']([A-Z_0-9]+)["']|os\.environ\[["']([A-Z_0-9]+)["']\]""")
        found = {}
        for rel in tracked:
            if rel.startswith(("jmri/layouts/hart/parked/", "archive/")):
                continue
            lines = (REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines):
                if "skipIf" in line or "skipUnless" in line or "skipTest" in line or "SkipTest" in line:
                    for near in lines[max(0, i - 3):i + 1]:
                        for m in read.finditer(near):
                            found.setdefault(m.group(1) or m.group(2), rel)
        # SCHEMATIC_PLUGIN is in the key through the plugin's state (panel_stamps.plugin_state)
        missing = {k: v for k, v in found.items() if k not in cs.KEY_ENV and k != "SCHEMATIC_PLUGIN"}
        self.assertEqual(missing, {})
        self.assertIn("CHECK_AUDIT", found, "the scan no longer sees test_check_stamps' own skip")

    def test_the_cache_folder_and_the_jmri_guard_are_in_the_key(self) -> None:
        """HART_CACHE_DIR picks the cache folders a job reads (the trace leaves .cache paths out), and
        HART_GUARD_JMRI_RUNNING forces the answer the table writers and their tests refuse or skip on: a job run with
        either changed must run again, whatever it read."""
        self.assertIn("HART_CACHE_DIR", cs.KEY_ENV)
        self.assertIn("HART_GUARD_JMRI_RUNNING", cs.KEY_ENV)
        ck = cs.Checker(Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()))
        for var, value in (("HART_CACHE_DIR", "/elsewhere/cache"), ("HART_GUARD_JMRI_RUNNING", "1"),
                           ("HART_GUARD_JMRI_RUNNING", "0")):
            with self.subTest(var=var, value=value):
                env = {k: v for k, v in os.environ.items() if k not in ("HART_CACHE_DIR", "HART_GUARD_JMRI_RUNNING")}
                with unittest.mock.patch.dict(os.environ, env, clear=True):
                    base = cs.outside_state("unit-mimic", ck)
                    with unittest.mock.patch.dict(os.environ, {var: value}):
                        self.assertNotEqual(cs.outside_state("unit-mimic", ck), base)
                        self.assertIn(f"{var}={value}", cs.outside_state("unit-mimic", ck))

    def test_the_environment_and_the_user_are_in_the_key(self) -> None:
        ck = cs.Checker(Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()))
        base = cs.outside_state("unit-mimic", ck)
        self.assertRegex(base, r"(?m)^euid=\d+$")
        with unittest.mock.patch.dict(os.environ, {"CHECK_AUDIT": "/x"}):
            self.assertNotEqual(cs.outside_state("unit-mimic", ck), base)


class StoreTest(unittest.TestCase):
    def test_default_store_is_in_the_main_checkout_and_git_ignored(self) -> None:
        main = cs.main_checkout()
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(main.resolve(), Path(common).parent.resolve())
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CHECK_STAMPS_DIR", None)
            os.environ.pop("HART_CACHE_DIR", None)
            import importlib
            fresh = importlib.reload(cs)
            self.addCleanup(importlib.reload, cs)
            self.assertEqual(fresh.STORE, main / ".cache" / "hart" / "check-stamps")
        ignored = subprocess.run(["git", "check-ignore", "-q", ".cache/hart/check-stamps/x.sha256"], cwd=REPO)
        self.assertEqual(ignored.returncode, 0, "the stamp folder is not git-ignored")


# A step manifest for the fake repos: the jobs check.sh runs from it, one per step (a and b in the static group, a
# keyed on HEAD and the merge base, b on no ref, and three in no group). Only manifest.job_keys reads it here, which
# does not check paths against git or the map.
MANIFEST = "".join(f'[[step]]\nname = "{name}"\nrunner = "check"\n{group}cmd = ["python3", "tools/{name}.py"]\n'
                   f'git = {refs}\n'
                   for name, group, refs in (("a", 'group = "static"\n', '["head", "base"]'),
                                             ("b", 'group = "static"\n', "[]"), ("public-text", "", "[]"),
                                             ("ruff", "", "[]"), ("portal", "", '["head", "base"]')))


class RepoCase(unittest.TestCase):
    """A fake repo with a store of its own; the job is a script run under the real trace hook."""

    JOB = "open('tools/x/tests/test_a.py').read()\n"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root, self.store = self.tmp / "repo", self.tmp / "store"
        for rel in ("tools/check.sh", "tools/x/tests/test_a.py", "jmri/layouts/hart/data/switches.csv",
                    "www/index.html", "docs/a.md", ".claude/worktrees/other/tools/y.py"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("v1\n")
        (self.root / cs.MANIFEST).parent.mkdir(parents=True, exist_ok=True)
        (self.root / cs.MANIFEST).write_text(MANIFEST)
        for target, value in (("plugin_state", "plugin"),):
            patch = unittest.mock.patch.object(cs.ps, target, return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = unittest.mock.patch.object(cs, "main_checkout", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def run_job(self, code: str | None = None, script: str = "job.py") -> Path:
        log = self.tmp / "trace.log"
        log.write_text("0\tb\n")
        (self.root / script).write_text(code or self.JOB)
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_TRACE")}
        env.update(HART_TRACE_LOG=str(log), HART_TRACE_ROOT=str(self.root), PYTHONPATH=cs.traced.HOOK_DIR)
        subprocess.run([sys.executable, script], cwd=self.root, env=env, check=True, capture_output=True)
        return log

    def record(self, name: str = "unit-hartlib", code: str | None = None, script: str = "job.py") -> str | None:
        return cs.record(name, self.run_job(code, script), self.root, self.store)

    def current(self, name: str = "unit-hartlib") -> bool:
        return cs.is_current(name, self.root, self.store)


class StampTest(RepoCase):
    def test_hit_after_record_and_miss_after_a_file_it_read_changes(self) -> None:
        self.assertFalse(self.current())
        self.assertIsNone(self.record())
        self.assertTrue(self.current())
        (self.root / "tools/x/tests/test_a.py").write_text("v2\n")
        self.assertFalse(self.current())

    def test_a_data_file_the_job_did_not_read_is_no_input(self) -> None:
        self.record()
        (self.root / "jmri/layouts/hart/data/switches.csv").write_text("v2\n")
        self.assertTrue(self.current())

    def test_check_sh_is_an_input(self) -> None:
        self.record()
        (self.root / "tools/check.sh").write_text("v2\n")
        self.assertFalse(self.current())

    def test_an_untraceable_program_falls_back_to_the_declaration(self) -> None:
        code = self.JOB + "import subprocess\nsubprocess.run(['sh', '-c', 'true'])\n"
        self.assertIsNone(self.record(code=code))
        self.assertTrue(self.current())
        (self.root / "jmri/layouts/hart/data/switches.csv").write_text("v2\n")
        self.assertFalse(self.current(), "a declared file the shell may have read")
        self.record(code=code)
        (self.root / "www/index.html").write_text("v2\n")
        self.assertTrue(self.current(), "outside unit-hartlib's declaration")

    def test_another_worktree_inside_the_checkout_is_not_an_input(self) -> None:
        self.record("a", code=self.JOB + "import subprocess\nsubprocess.run(['sh', '-c', 'true'])\n")
        (self.root / ".claude/worktrees/other/tools/y.py").write_text("v2\n")
        self.assertTrue(self.current("a"))

    def test_the_private_plan_and_the_interpreter_packages_are_inputs(self) -> None:
        plan = self.tmp / "plan.any"
        plan.write_text("p1\n")
        with unittest.mock.patch.dict(os.environ, {"ANYRAIL_PLAN": str(plan)}):
            self.record("a")
            self.assertTrue(self.current("a"))
            plan.write_text("p2\n")
            self.assertFalse(self.current("a"))
            self.record("a")
            with unittest.mock.patch.object(cs, "venv_state", return_value="other interpreter"):
                self.assertFalse(self.current("a"))

    def test_a_stamp_helper_answer_other_than_0_or_1_is_not_a_skip(self) -> None:
        self.assertEqual(cs.main(["current", "no such job"]), 2)

    def test_the_hops_venv_is_an_input_of_its_jobs(self) -> None:
        hops = self.root / "ops/hart-ops/.venv/bin"
        hops.mkdir(parents=True)
        (hops / "python").write_text("")
        site = self.root / "ops/hart-ops/.venv/lib/python3.13/site-packages/numpy-1.0.dist-info"
        site.mkdir(parents=True)
        self.record("unit-hart-ops")
        self.assertTrue(self.current("unit-hart-ops"))
        site.rename(site.with_name("numpy-2.0.dist-info"))
        self.assertFalse(self.current("unit-hart-ops"))

    def test_the_job_name_is_in_the_stamp(self) -> None:
        self.record("unit-hartlib")
        stamp = cs.traced.load(cs._file("unit-hartlib", self.store))
        cs.traced.save(cs._file("unit-mimic", self.store), stamp)
        self.assertFalse(self.current("unit-mimic"))

    def test_the_file_hash_cache_follows_a_change_of_size(self) -> None:
        self.record()
        (self.root / "tools/x/tests/test_a.py").write_text("v1\nand more\n")
        self.assertFalse(self.current())

    def test_outside_state_that_changed_while_the_job_ran_records_nothing(self) -> None:
        plan = self.tmp / "plan.any"
        plan.write_text("p1\n")
        with unittest.mock.patch.dict(os.environ, {"ANYRAIL_PLAN": str(plan)}):
            before = cs.snapshot("a", self.root, self.store)
            log = self.run_job()
            plan.write_text("p2\n")             # the job saw p1; the key worked out now would hold p2
            self.assertIn("changed while the job ran", cs.record("a", log, self.root, self.store, before=before))
            self.assertFalse(self.current("a"))

    def test_a_job_that_is_one_bash_program_records_on_its_declaration(self) -> None:
        """check.sh's panels job: bash alone, with no Python process in its trace. It records, keyed on every file,
        so any edit reruns it (in the one static job, the other checks' processes carried such a trace)."""
        log = self.tmp / "bash.log"
        log.write_text(f"0\tt\t{time.time_ns()}\n0\tx\tcheck.sh-run\t{self.root}\tbash\ttools/b.sh\t--check\n")
        self.assertIsNone(cs.record("a", log, self.root, self.store))
        self.assertTrue(self.current("a"))
        (self.root / "docs/a.md").write_text("edited while it ran\n")
        self.assertIn("docs/a.md changed while the job ran", cs.record("a", log, self.root, self.store))
        log.write_text(f"0\tt\t{time.time_ns()}\n0\tx\tcheck.sh-run\t{self.root}\tbash\ttools/b.sh\t--check\n")
        self.assertIsNone(cs.record("a", log, self.root, self.store))
        self.assertTrue(self.current("a"))
        self.assertEqual(cs.traced.load(cs._file("a", self.store))["programs"], ["bash"])
        (self.root / "docs/a.md").write_text("v2\n")
        self.assertFalse(self.current("a"))

    def test_a_short_trace_records_nothing_and_drops_the_old_stamp(self) -> None:
        self.record()
        log = self.tmp / "short.log"
        log.write_text("0\tb\n")
        self.assertIn("did not load", cs.record("unit-hartlib", log, self.root, self.store))
        self.assertFalse(self.current())


class BatchTest(RepoCase):
    """current-batch checks every job in one process with one Checker (shared hash cache, git, plugin state, walks and
    snapshots); each job alone gets a Checker of its own, as one `current` process per job did. Both must give the same
    verdict, reason and snapshot for every job, whatever changed."""

    SHELL = RepoCase.JOB + "import subprocess\nsubprocess.run(['sh', '-c', 'true'])\n"
    NAMES = ["unit-hartlib", "unit-mimic", "a", "unit-hosts test_redeploy_commit", "unit-jmri test_x",
             "unit-hart-ops skipped (no ops/hart-ops/.venv)"]

    def setUp(self) -> None:
        super().setUp()
        patch = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        self.unstampable = patch.start()
        self.addCleanup(patch.stop)
        self.record("unit-hartlib")
        self.record("unit-mimic")
        # an untraceable program: the declaration (every file for a manifest check, CODE for unit-jmri)
        self.record("a", code=self.SHELL, script="shell_job.py")
        self.record("unit-jmri test_x", code=self.SHELL, script="shell_job.py")
        # unit-hosts test_redeploy_commit has no stamp; the placeholder is not stampable

    def alone(self) -> list[tuple[int, str | None, str | None]]:
        out = []
        for i, name in enumerate(self.NAMES):
            save = self.tmp / f"alone-{i}.stamp"
            save.unlink(missing_ok=True)
            ck = cs.Checker(self.root, self.store)
            try:
                code, reason = cs.verdict(name, ck, save)
            finally:
                ck.cache.save()
            out.append((code, reason, save.read_text() if save.exists() else None))
        return out

    def batch(self) -> list[tuple[int, str | None, str | None]]:
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        codes = cs.current_batch(self.NAMES, folder, True, self.root, self.store)
        lines = (folder / "verdicts").read_text().splitlines()
        self.assertEqual(lines, [f"{i}\t{c}" for i, c in enumerate(codes)])
        out = []
        for i, code in enumerate(codes):
            log, stamp = folder / f"{i}.stamplog", folder / f"{i}.stamp"
            reason = log.read_text().removeprefix("runs: ").removesuffix("\n") if log.exists() else None
            out.append((code, reason, stamp.read_text() if stamp.exists() else None))
        return out

    def same(self, want: list[int]) -> list[tuple[int, str | None, str | None]]:
        alone, batch = self.alone(), self.batch()
        self.assertEqual(batch, alone)
        self.assertEqual([v[0] for v in batch], want)
        return batch

    def test_no_change(self) -> None:
        got = self.same([0, 0, 0, 1, 0, 2])
        self.assertEqual(got[3][1], "no stamp")
        self.assertIn("not a stampable job", got[5][1])
        self.assertIsNone(got[5][2], "no snapshot for a job that is not stampable")

    def test_an_edit_to_a_file_the_jobs_read(self) -> None:
        (self.root / "tools/x/tests/test_a.py").write_text("v2\n")
        self.same([1, 1, 1, 1, 1, 2])

    def test_an_edit_only_the_declarations_cover(self) -> None:
        """The jobs that ran an untraceable program fall back to their declarations; the traced ones did not read it."""
        (self.root / "www/index.html").write_text("v2\n")           # in a's declaration, not in CODE
        self.same([0, 0, 1, 1, 0, 2])
        (self.root / "jmri/layouts/hart/data/switches.csv").write_text("v2\n")
        self.same([0, 0, 1, 1, 1, 2])

    def test_a_missing_stamp(self) -> None:
        cs._file("unit-mimic", self.store).unlink()
        self.assertEqual(self.same([0, 1, 0, 1, 0, 2])[1][1], "no stamp")

    def test_a_plugin_change(self) -> None:
        cs.ps.plugin_state.return_value = "another plugin commit"
        self.same([1, 1, 1, 1, 1, 2])

    def test_nothing_is_stampable_while_the_tables_or_plugin_say_so(self) -> None:
        self.unstampable.return_value = "HART_TABLES is set (x): the steps run on another tables file"
        got = self.same([2, 2, 2, 2, 2, 2])
        self.assertTrue(all(v[2] is None for v in got))

    def test_a_job_whose_check_fails_runs_records_nothing_and_loses_its_stamp(self) -> None:
        """Only that job: the others keep their verdicts; its stamp is dropped, so its next pass records afresh."""
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        real = cs.why_not_current

        def fail_on_mimic(name, *args, **kwargs):
            if name == "unit-mimic":
                raise OSError("disk gone")
            return real(name, *args, **kwargs)
        with unittest.mock.patch.object(cs, "why_not_current", side_effect=fail_on_mimic):
            codes = cs.current_batch(self.NAMES, folder, False, self.root, self.store)
        self.assertEqual(codes, [0, 2, 0, 1, 0, 2])
        self.assertIn("OSError: disk gone", (folder / "1.stamplog").read_text())
        self.assertFalse((folder / "1.stamp").exists())
        self.assertFalse(cs._file("unit-mimic", self.store).exists())
        self.assertEqual(self.alone()[1][:2], (1, "no stamp"))

    def test_a_retired_job_loses_its_stamp_and_may_not_be_queued(self) -> None:
        """The one static job's stamp (until ADR-037 stage 4b) is dropped by the first batch; queueing it is an error,
        not a job that quietly runs or skips."""
        old = cs._file("static", self.store)
        old.write_text("{}")
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        cs.current_batch(["unit-mimic"], folder, False, self.root, self.store)
        self.assertFalse(old.exists())
        with unittest.mock.patch.object(Path, "unlink", side_effect=PermissionError("read-only")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(cs.current_batch(["unit-mimic"], folder, False, self.root, self.store), [0])
            self.assertIn("cannot drop the retired 'static' stamp: read-only", err.getvalue())
        with self.assertRaisesRegex(cs.BatchError, "'static', a job name check_stamps.RETIRED says it no longer runs"):
            cs.current_batch(["unit-mimic", "static"], folder, False, self.root, self.store)

    def test_a_batch_that_cannot_check_at_all_gives_no_verdicts(self) -> None:
        folder = self.tmp / "absent"
        with self.assertRaisesRegex(cs.BatchError, "is not a folder"):
            cs.current_batch(self.NAMES, folder, False, self.root, self.store)

    def test_the_names_and_the_folder_are_checked_first(self) -> None:
        names = self.tmp / "names"
        for text, says in (("", "names no job"), ("unit-mimic\n\nunit-hartlib\n", "line 2"),
                           (" unit-mimic\n", "line 1")):
            with self.subTest(text=text):
                names.write_text(text)
                with self.assertRaisesRegex(cs.BatchError, says):
                    cs.read_names(names)
        names.write_text("unit-mimic\nunit-cats\n")
        self.assertEqual(cs.read_names(names), ["unit-mimic", "unit-cats"])
        with self.assertRaisesRegex(cs.BatchError, "cannot read"):
            cs.read_names(self.tmp / "absent")
        with self.assertRaisesRegex(cs.BatchError, "is not a folder"):
            cs.current_batch(["unit-mimic"], self.tmp / "absent", False, self.root, self.store)

    def test_the_command_line(self) -> None:
        """`current` per job and one `current-batch`, as processes in this checkout with a scratch store."""
        names = ["unit-mimic", "unit-cats", "unit-hart-ops skipped (no ops/hart-ops/.venv)"]
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HART_TRACE", "HART_TABLES"))}
        env["CHECK_STAMPS_DIR"] = str(self.store)
        tool = [sys.executable, str(REPO / "tools/audit/check_stamps.py")]

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([*tool, *args], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
        alone = [run("current", n, "--why").returncode for n in names]
        folder = self.tmp / "cli"
        folder.mkdir()
        (self.tmp / "names").write_text("".join(n + "\n" for n in names))
        done = run("current-batch", str(self.tmp / "names"), str(folder), "--why")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((folder / "verdicts").read_text(), "".join(f"{i}\t{c}\n" for i, c in enumerate(alone)))
        for args in (("current-batch", str(self.tmp / "names"), str(self.tmp / "nowhere")),
                     ("current-batch", str(self.tmp / "no-names"), str(folder))):
            with self.subTest(args=args[1:]):
                done = run(*args)
                self.assertEqual(done.returncode, 3)
                self.assertRegex(done.stderr, r"^check_stamps.py current-batch: ")
                self.assertNotIn("Traceback", done.stderr)
        done = run("record", "unit-mimic", str(folder / "0.stamp"), "--trace", "x", "--skipped", "two")
        self.assertEqual(done.returncode, 2)
        self.assertIn("--skipped takes a count", done.stdout)


class SkipStampTest(RepoCase):
    """A unit job whose tests skipped records its stamp with the skipped tests' ids and reasons in its key; what they
    skipped on (here a tool shutil.which does not find) is an input like any read file."""

    TESTS = ("import shutil, unittest\n"
             "TOOL = shutil.which('hart-no-such-tool')\n\n"
             "class S(unittest.TestCase):\n"
             "    @unittest.skipUnless(TOOL, 'no hart-no-such-tool')\n"
             "    def test_needs_the_tool(self):\n"
             "        pass\n\n"
             "    def test_plain(self):\n"
             "        open('tools/x/tests/test_a.py').read()\n")

    def setUp(self) -> None:
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        patch = unittest.mock.patch.dict(os.environ, {"PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}"})
        patch.start()
        self.addCleanup(patch.stop)
        (self.root / "tools/x/tests/test_s.py").write_text(self.TESTS)

    def run_tests(self) -> tuple[Path, str]:
        log = self.tmp / "trace.log"
        log.write_text("0\tb\n")
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_TRACE")}
        env.update(HART_TRACE_LOG=str(log), HART_TRACE_ROOT=str(self.root), PYTHONPATH=cs.traced.HOOK_DIR)
        done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-b", "-q", "-s", "tools/x/tests",
                               "-p", "test_s.py"], cwd=self.root, env=env, capture_output=True, text=True, check=True)
        return log, done.stderr

    def test_a_job_with_a_skipped_test_records_and_reruns_when_the_tool_appears(self) -> None:
        log, out = self.run_tests()
        self.assertIn("OK (skipped=1)", out)
        self.assertIsNone(cs.record("unit-guards test_s", log, self.root, self.store, skipped=1))
        stamp = cs.traced.load(cs._file("unit-guards test_s", self.store))
        self.assertEqual(stamp["skips"], [["test_s.S.test_needs_the_tool", "no hart-no-such-tool"]])
        self.assertTrue(self.current("unit-guards test_s"))
        (self.bin / "hart-no-such-tool").write_text("#!/bin/sh\n")
        (self.bin / "hart-no-such-tool").chmod(0o755)
        self.assertIn("hart-no-such-tool", cs.why_not_current("unit-guards test_s", self.root, self.store))

    def test_an_edit_still_reruns_it(self) -> None:
        log, _ = self.run_tests()
        self.assertIsNone(cs.record("unit-guards test_s", log, self.root, self.store, skipped=1))
        (self.root / "tools/x/tests/test_a.py").write_text("v2\n")
        self.assertFalse(self.current("unit-guards test_s"))

    def test_the_key_holds_which_tests_skipped_and_why(self) -> None:
        log, _ = self.run_tests()
        self.assertIsNone(cs.record("unit-guards test_s", log, self.root, self.store, skipped=1))
        path = cs._file("unit-guards test_s", self.store)
        good = cs.traced.load(path)
        for skips in ([["test_s.S.test_needs_the_tool", "another reason"]],
                      [["test_s.S.test_plain", "no hart-no-such-tool"]],
                      [*good["skips"], ["test_s.S.test_plain", "no hart-no-such-tool"]]):
            with self.subTest(skips=skips):
                cs.traced.save(path, {**good, "skips": skips})
                self.assertIn("the code, command", cs.why_not_current("unit-guards test_s", self.root, self.store))
        ck = cs.Checker(self.root, self.store)
        self.assertEqual(cs.key("unit-mimic", ck, [], []), cs.key("unit-mimic", ck, [], [], skips=[]),
                         "a job with no skips keeps the key it had")

    def test_fewer_skips_in_the_trace_than_the_output_shows_records_nothing(self) -> None:
        log, _ = self.run_tests()
        self.assertIsNone(cs.record("unit-guards test_s", log, self.root, self.store, skipped=1))
        reason = cs.record("unit-guards test_s", log, self.root, self.store, skipped=2)
        self.assertIn("the output shows 2 skipped tests and the trace holds 1", reason)
        self.assertFalse(self.current("unit-guards test_s"), "the old stamp is dropped")


class GitRefsTest(RepoCase):
    def git(self, *args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=self.root,
                       check=True, capture_output=True)

    def test_the_redeploy_job_reruns_when_head_moves(self) -> None:
        """test_redeploy_commit's deploy script (bash) stages HEAD and checks origin/main, which no trace sees."""
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "one")
        name = "unit-hosts test_redeploy_commit"
        ck = cs.Checker(self.root, self.store)
        state = cs.outside_state(name, ck)
        for ref in ("head=", "base=", "origin="):
            self.assertRegex(state, f"(?m)^{ref}")
        self.assertNotRegex(cs.outside_state("a", ck), "(?m)^origin=")
        self.assertNotRegex(cs.outside_state("unit-mimic", ck), "(?m)^(head|base|origin)=")
        self.assertIsNone(self.record(name))
        self.assertTrue(self.current(name))
        self.git("commit", "-q", "--allow-empty", "-m", "two")
        self.assertFalse(self.current(name))

    def test_a_manifest_job_holds_the_refs_its_git_field_names(self) -> None:
        """A read-only check whose entry names head reruns after a commit that changes nothing it read; one whose entry
        says [] (its trace replays every git read it makes) stays current; a unit job's REFS_OF is not consulted."""
        unstamp = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        unstamp.start()
        self.addCleanup(unstamp.stop)
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "one")
        ck = cs.Checker(self.root, self.store)
        self.assertRegex(cs.outside_state("a", ck), "(?m)^head=[0-9a-f]{40}\nbase=")
        self.assertNotRegex(cs.outside_state("b", ck), "(?m)^(head|base|origin)=")
        for name in ("a", "b"):
            self.assertIsNone(self.record(name))
            self.assertTrue(self.current(name))
        self.git("commit", "-q", "--allow-empty", "-m", "two")
        self.assertFalse(self.current("a"), "HEAD moved: a's key holds it")
        self.assertTrue(self.current("b"), "b names no ref and read nothing that changed")
        self.assertIn("the code, command", cs.why_not_current("a", self.root, self.store))

    def test_a_git_command_a_check_ran_is_replayed_without_head_in_its_key(self) -> None:
        """What lets a check drop HEAD: a read-only git command its trace holds is run again at compare time, so a
        commit that changes its answer reruns the check, and one that does not leaves it current."""
        unstamp = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        unstamp.start()
        self.addCleanup(unstamp.stop)
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "one")
        code = "import subprocess\nsubprocess.run(['git', 'ls-files', 'tools'], check=True, capture_output=True)\n"
        self.assertIsNone(self.record("b", code=code))
        stamp = cs.traced.load(cs._file("b", self.store))
        self.assertEqual((stamp["programs"], [c[1:] for c in stamp["git"]]), ([], [["git", "ls-files", "tools"]]))
        self.git("commit", "-q", "--allow-empty", "-m", "two")
        self.assertTrue(self.current("b"), "the same answer: b reads nothing that changed")
        (self.root / "tools/new.txt").write_text("n\n")
        self.git("add", "tools/new.txt")
        self.assertFalse(self.current("b"), "git ls-files answers otherwise now")

    def test_the_deploy_stage_job_reruns_when_an_edit_in_the_tree_is_committed(self) -> None:
        """test_deploy_stage stages a git clone of HEAD (its setUpClass), not the working tree its read set hashes."""
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "one")
        name = "unit-hosts test_deploy_stage"
        ck = cs.Checker(self.root, self.store)
        self.assertRegex(cs.outside_state(name, ck), "(?m)^head=[0-9a-f]{40}$")
        self.assertNotRegex(cs.outside_state(name, ck), "(?m)^(base|origin)=")
        (self.root / "tools/edit.txt").write_text("in the tree, not yet committed\n")
        self.assertIsNone(self.record(name, code="open('tools/edit.txt').read()\n"))
        self.assertTrue(self.current(name))
        status = ["git", "status", "--porcelain", "tools/edit.txt"]
        self.assertEqual(subprocess.run(status, cwd=self.root, capture_output=True, text=True).stdout,
                         "?? tools/edit.txt\n", "the job read an edit that is in the tree, not in HEAD")
        self.git("add", "tools/edit.txt")
        self.git("commit", "-q", "-m", "two")
        self.assertEqual(subprocess.run(status, cwd=self.root, capture_output=True, text=True).stdout, "")
        self.assertFalse(self.current(name), "the commit changed nothing in the tree, but HEAD moved")


class ManifestKeyTest(RepoCase):
    """A manifest job's key holds its own entries (tools/pipeline/checks.toml): an edit to one entry reruns that job
    and no other, and a manifest that cannot be read leaves the job to run and record nothing."""
    JOBS = ("a", "b", "public-text", "ruff", "portal", "unit-hartlib", "unit-guards test_x")

    def setUp(self) -> None:
        super().setUp()
        patch = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def keys(self) -> dict[str, str]:
        ck = cs.Checker(self.root, self.store)
        return {name: cs.key(name, ck, [], []) for name in self.JOBS}

    def edit(self, old: str, new: str) -> None:
        path = self.root / cs.MANIFEST
        text = path.read_text()
        self.assertEqual(text.count(old), 1, old)
        path.write_text(text.replace(old, new))

    def rerun_after(self, old: str, new: str) -> list[str]:
        before = self.keys()
        self.edit(old, new)
        after = self.keys()
        return [name for name in self.JOBS if before[name] != after[name]]

    def test_an_edited_cmd_reruns_its_own_job_only(self) -> None:
        self.assertEqual(self.rerun_after('"tools/ruff.py"]', '"tools/ruff.py", "--fix"]'), ["ruff"])
        self.assertEqual(self.rerun_after('"tools/b.py"]', '"tools/b.py", "--check"]'), ["b"])
        self.assertEqual(self.rerun_after('"tools/portal.py"]', '"tools/portal2.py"]'), ["portal"])

    def test_a_step_added_to_the_static_group_reruns_no_other_job(self) -> None:
        self.assertEqual(self.rerun_after('[[step]]\nname = "public-text"',
                                          '[[step]]\nname = "c"\nrunner = "check"\ngroup = "static"\n'
                                          'cmd = ["python3", "tools/c.py"]\ngit = []\n[[step]]\nname = "public-text"'),
                         [])

    def test_an_edited_git_field_reruns_its_own_job_only(self) -> None:
        self.assertEqual(self.rerun_after('cmd = ["python3", "tools/b.py"]\ngit = []',
                                          'cmd = ["python3", "tools/b.py"]\ngit = ["origin"]'), ["b"])

    def test_a_git_field_the_key_cannot_use_is_an_error_not_a_skip(self) -> None:
        self.edit('cmd = ["python3", "tools/b.py"]\ngit = []', 'cmd = ["python3", "tools/b.py"]\ngit = ["tip"]')
        with self.assertRaisesRegex(cs.pm.ManifestError, "step 'b': git: 'tip': not a ref name"):
            cs.outside_state("a", cs.Checker(self.root, self.store))

    def test_a_comment_reruns_nothing(self) -> None:
        self.assertEqual(self.rerun_after('[[step]]\nname = "a"', '# why a\n[[step]]\nname = "a"'), [])

    def test_check_sh_and_the_loader_rerun_every_job(self) -> None:
        before = self.keys()
        for rel in ("tools/check.sh", *cs.pm.FILES):     # FILES: manifest.py and its parts (test_stamp_gate counts them)
            (self.root / rel).write_text("edited\n")
            after = self.keys()
            self.assertEqual([n for n in self.JOBS if before[n] == after[n]], [], rel)
            before = after

    def test_the_stamp_follows_the_entry(self) -> None:
        self.assertIsNone(self.record("ruff"))
        self.assertIsNone(self.record("public-text"))
        self.assertTrue(self.current("ruff"))
        self.edit('"tools/ruff.py"]', '"tools/ruff.py", "--fix"]')
        self.assertFalse(self.current("ruff"))
        self.assertTrue(self.current("public-text"))
        self.assertIn("the code, command", cs.why_not_current("ruff", self.root, self.store))

    def test_an_entry_edited_while_the_job_ran_records_nothing(self) -> None:
        before = cs.snapshot("ruff", self.root, self.store)
        log = self.run_job()
        self.edit('"tools/ruff.py"]', '"tools/ruff.py", "--fix"]')
        self.assertIn("tools/pipeline/checks.toml changed while the job ran",
                      cs.record("ruff", log, self.root, self.store, before=before))

    def test_a_manifest_that_cannot_be_read_or_lacks_the_job_is_an_error_not_a_skip(self) -> None:
        ck = cs.Checker(self.root, self.store)
        self.assertNotIn("manifest=", cs.outside_state("unit-hartlib", ck))
        self.edit('name = "ruff"', 'name = "ruff2"')
        with self.assertRaisesRegex(cs.pm.ManifestError, "has no job 'ruff'"):
            cs.outside_state("ruff", cs.Checker(self.root, self.store))
        (self.root / cs.MANIFEST).write_text("[[step]\n")
        with self.assertRaisesRegex(cs.pm.ManifestError, "not valid TOML"):
            cs.outside_state("a", cs.Checker(self.root, self.store))
        # a unit job does not read the manifest
        self.assertNotIn("manifest=", cs.outside_state("unit-hartlib", cs.Checker(self.root, self.store)))

    def test_the_batch_runs_a_job_whose_key_cannot_be_made_and_records_nothing(self) -> None:
        out = self.tmp / "batch"
        out.mkdir()
        (self.root / cs.MANIFEST).unlink()
        self.assertEqual(cs.current_batch(["ruff", "unit-hartlib"], out, why=False, root=self.root, store=self.store),
                         [2, 1])
        self.assertIn("checks.toml: cannot read it", (out / "0.stamplog").read_text())

    def test_the_command_line_says_so_without_a_traceback(self) -> None:
        self.assertIsNone(self.record("a"))                # a stamp, so `why` works out the key
        (self.root / cs.MANIFEST).write_text("[[step]\n")
        err = io.StringIO()
        real = cs.Checker
        with unittest.mock.patch.object(cs, "Checker", lambda *a, **k: real(self.root, self.store)), \
                contextlib.redirect_stderr(err):
            rc = cs.main(["why", "a"])
        self.assertEqual(rc, 2)
        self.assertIn("check_stamps.py: not stamped:", err.getvalue())
        self.assertIn("not valid TOML", err.getvalue())


class CheckShCacheTest(unittest.TestCase):
    """check.sh makes the checkout's .cache before any job starts: the panel check makes .cache/panel-stamps in a
    fresh worktree mid-run, and a job that listed the root before that recorded a listing the next run did not match
    (2026-11-24: 31 jobs reran on the second no-change run)."""

    LINE = 'if ! mkdir -p "$ROOT/.cache" 2>/dev/null; then'

    def test_it_comes_before_the_first_stamp_batch(self) -> None:
        self.assertEqual(CHECK_SH.count(self.LINE), 1)
        first_batch = CHECK_SH.index("\nstart_jobs\n")
        self.assertLess(CHECK_SH.index(self.LINE), first_batch)

    def block(self) -> str:
        start = CHECK_SH.index(self.LINE)
        return CHECK_SH[start:CHECK_SH.index("\nfi\n", start) + 4]

    def test_it_makes_the_folder_and_says_so_when_it_cannot(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            done = subprocess.run(["bash", "-c", f"set -uo pipefail\nROOT='{d}'\n{self.block()}"],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue((Path(d) / ".cache").is_dir())
            self.assertEqual(done.stdout, "")
            (Path(d) / "file").write_text("x")
            done = subprocess.run(["bash", "-c", f"set -uo pipefail\nROOT='{d}/file'\n{self.block()}"],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 0, "the run goes on")
            self.assertIn(f"cannot make {d}/file/.cache", done.stdout)


class RootListingTest(RepoCase):
    def test_a_root_name_added_after_a_pass_reruns_a_job_that_listed_the_root(self) -> None:
        """What check.sh's .cache line prevents, and the stamps' answer without it: the job reruns, never skips."""
        self.assertIsNone(self.record(code="import os\nos.listdir('.')\n"))
        self.assertTrue(self.current())
        (self.root / ".cache").mkdir()
        self.assertFalse(self.current())


class CheckShVerdictsTest(unittest.TestCase):
    """check.sh's read_verdicts, with a stand-in python3: the batch's answers count only when it exits 0 and answers
    once for each queued job; anything else runs every job, records no stamp, and says why."""

    def verdicts(self, stub: str, stamps: str = "1") -> tuple[subprocess.CompletedProcess, str]:
        start = CHECK_SH.index("batch_failed() {")
        end = CHECK_SH.index("\n}\n", CHECK_SH.index("read_verdicts() {")) + 3
        block = CHECK_SH[start:end]
        with tempfile.TemporaryDirectory() as d:
            stub_dir = Path(d) / "bin"
            stub_dir.mkdir()
            # the stand-in also leaves a reason for job 0, as a --why batch would
            (stub_dir / "python3").write_text('#!/bin/bash\ncp "$3" "$4/names.seen"\necho "runs: x" >"$4/0.stamplog"\n'
                                              + stub)
            (stub_dir / "python3").chmod(0o755)
            (Path(d) / "jobs").mkdir()
            script = (f"set -uo pipefail\nnames=(a 'b c' d)\nverdicts=()\nSTAMPS={stamps}\nRECORD={stamps}\n"
                      f"STAMP_ENV=()\nSTAMP_WHY=()\nJOBS='{d}/jobs'\n{block}read_verdicts\n"
                      'echo "VERDICTS=${verdicts[*]}"\n')
            done = subprocess.run(["bash", "-c", script], env={**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}"},
                                  capture_output=True, text=True, timeout=30)
            seen = Path(d) / "jobs/names.seen"
            self.left = (Path(d) / "jobs/0.stamplog").exists()
            return done, seen.read_text() if seen.exists() else ""

    def test_a_good_batch_gives_each_job_its_verdict(self) -> None:
        done, names = self.verdicts("printf '0\\t0\\n1\\t1\\n2\\t2\\n' >\"$4/verdicts\"\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("VERDICTS=0 1 2", done.stdout)
        self.assertEqual(names, "a\nb c\nd\n")
        self.assertNotIn("every job runs", done.stdout)
        self.assertTrue(self.left)

    def test_anything_else_runs_every_job_and_says_why(self) -> None:
        for stub, says in (("echo 'job 1 (b c): OSError: disk gone' >&2\nexit 3\n", "OSError: disk gone"),
                           ("exit 0\n", "wrote no verdicts"),
                           ("printf '0\\t0\\n1\\t0\\n' >\"$4/verdicts\"\n", "verdicts for 2 of 3 jobs in 2 lines"),
                           ("printf '0\\t0\\n0\\t0\\n1\\t0\\n' >\"$4/verdicts\"\n", "verdicts for 2 of 3 jobs in 3 lines"),
                           ("printf '0\\t0\\n1\\tx\\n2\\t0\\n' >\"$4/verdicts\"\n", "no verdict of a queued job"),
                           ("printf '0\\t0\\n1\\t0\\n5\\t0\\n' >\"$4/verdicts\"\n", "no verdict of a queued job")):
            with self.subTest(says=says):
                done, _ = self.verdicts(stub)
                self.assertIn("VERDICTS=2 2 2", done.stdout)
                self.assertIn(says, done.stdout)
                self.assertIn("every job runs and none records a stamp", done.stdout)
                self.assertFalse(self.left, "a reason the failed batch wrote for one job is left to be printed")

    def test_no_stamps_no_batch(self) -> None:
        done, names = self.verdicts("exit 3\n", stamps="0")
        self.assertIn("VERDICTS=2 2 2", done.stdout)
        self.assertEqual(names, "", "the batch ran")
        self.assertNotIn("every job runs", done.stdout)


class AuditTest(unittest.TestCase):
    """Runs check.sh for the quick jobs under CHECK_AUDIT (tools/audit/stamp_audit, an independent hook) while they
    record their traced stamps into a scratch store, and fails for any repo file or folder the audit saw a job touch
    that its read set lacks (or, for a job that ran an untraceable program, that its declaration does not cover)."""

    @unittest.skipIf(os.environ.get("CHECK_AUDIT"), "already inside an audit run")
    def test_the_traced_read_sets_hold_what_the_jobs_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k not in ("HART_TABLES", "FULL", "CI")
                   and not k.startswith("HART_TRACE")}
            env.update(CHECK_ONLY=AUDITED, CHECK_AUDIT=f"{tmp}/audit", CHECK_STAMPS_DIR=f"{tmp}/stamps")
            done = subprocess.run(["bash", str(REPO / "tools/check.sh")], cwd=REPO, env=env, capture_output=True,
                                  text=True, timeout=900)
            self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-2000:])
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
                    self.assertIsNotNone(stamp, f"{name} recorded no stamp:\n{done.stdout[-3000:]}")
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


class DeclarationAuditTest(RepoCase):
    """The trace audit of a manifest job's declarations (ADR-037 stage 4a): every job is one step (stage 4b), so every
    process's reads are its step's; code is left out, undeclared reads are warned about and kept in the stamp for
    `check_stamps.py audit`, and nothing about it changes a key or a verdict. An audit that cannot run says so; it is
    never silent."""

    def setUp(self) -> None:
        super().setUp()
        patch = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def trace(self, lines: list[str]) -> Path:
        log = self.tmp / "hand.trace"
        log.write_text("".join(line.replace("{root}", str(self.root)) + "\n" for line in lines))
        return log

    HAND = ["0\tb",
            "100\ts\t50\t\t1\tpython3\ttools/a.py",
            "100\tr\t{root}/data/in.csv",
            "100\tc\t{root}/tools/lib/mod.py",                  # imported (a "c" line): code, not audited
            "100\tc\t{root}/jmri/scripts/x.py",                 # imported, and read as text below: audited
            "100\tr\t{root}/tools/levels/main.svg",             # data under tools/, and a .py read as text: audited
            "100\tr\t{root}/jmri/scripts/x.py",
            "100\tr\t{root}/.cache/hart/x.json",                # a shared cache: no input
            "100\tr\t/usr/lib/python3/x.txt",                   # outside the repo
            "100\tx\ttok1\t{root}\tbash\t-c\tpython3 helper.py",
            "200\ts\t999\ttok1\t2\tpython3\thelper.py",          # a's grandchild
            "200\tr\t{root}/data/helper.csv",
            "300\ts\t100\t\t3\tpython3\tother.py",              # a's child
            "300\tr\t{root}/data/child.csv",
            "300\ts\t300\tfork\t0\tfork",                       # its fork
            "500\tr\t{root}/data/nostart.csv"]                  # no start line: still the job's

    def test_every_process_of_a_job_is_its_steps(self) -> None:
        audit = cs.step_reads("a", self.trace(self.HAND), self.root, cs.manifest_steps("a", self.root))
        self.assertEqual(audit, {"steps": {"a": ["data/child.csv", "data/helper.csv", "data/in.csv",
                                                 "data/nostart.csv", "jmri/scripts/x.py", "tools/levels/main.svg"]},
                                 "unowned": {}, "absent": [], "bash": []})

    def test_a_job_of_more_than_one_step_is_refused(self) -> None:
        steps = (*cs.manifest_steps("a", self.root), *cs.manifest_steps("b", self.root))
        with self.assertRaisesRegex(cs.AuditError, "a has 2 steps in tools/pipeline/checks.toml; each job is one step"):
            cs.step_reads("a", self.trace(self.HAND), self.root, steps)

    def test_a_stamp_of_the_one_static_job_is_read_and_says_to_run_again(self) -> None:
        """Stage 4a's stamps held several steps per job; read against a job of one step, the others are named."""
        old = {"steps": {"a": [], "b": ["data/b.csv"]}, "unowned": {"python3 stray.py": ["data/stray.csv"]},
               "absent": [], "bash": []}
        lines, count = cs.audit_lines("a", old, cs.manifest_steps("a", self.root))
        self.assertEqual(count, 2)
        self.assertIn("    b: in the stamp, not in tools/pipeline/checks.toml now; run the job again", lines)
        self.assertIn("    no step started this process (python3 stray.py): data/stray.csv", lines)

    def test_a_step_added_after_the_stamp_is_not_reported_clean(self) -> None:
        audit = {"steps": {}, "unowned": {}, "absent": [], "bash": []}
        lines, count = cs.audit_lines("a", audit, cs.manifest_steps("a", self.root))
        self.assertEqual(count, 1)
        self.assertIn("    a: in tools/pipeline/checks.toml, not in the stamp; run the job again", lines)

    def test_the_report_names_each_undeclared_read_and_how_to_see_it_again(self) -> None:
        self.edit_step("a", 'inputs = ["data/in.csv"]\n'
                            'quiet_inputs = ["data/helper.csv", "tools/*/*.svg", "jmri/**/*.py"]\n')
        steps = cs.manifest_steps("a", self.root)
        lines, count = cs.audit_lines("a", cs.step_reads("a", self.trace(self.HAND), self.root, steps), steps)
        self.assertEqual(count, 2)
        self.assertTrue(lines[0].startswith("WARNING: stamp audit: a: 2 read(s) not declared"), lines[0])
        self.assertIn("warn only", lines[0])
        self.assertIn("    a: data/child.csv, data/nostart.csv", lines)
        self.assertEqual(lines[-1], "    again: python3 tools/audit/check_stamps.py audit a")

    def test_a_long_list_is_cut_in_the_run_and_whole_on_demand(self) -> None:
        steps = cs.manifest_steps("ruff", self.root)
        audit = {"steps": {"ruff": [f"data/{i:02}.csv" for i in range(12)]}, "unowned": {}, "absent": [], "bash": []}
        short, _ = cs.audit_lines("ruff", audit, steps)
        whole, count = cs.audit_lines("ruff", audit, steps, full=True)
        self.assertEqual(count, 12)
        self.assertIn("and 4 more", short[1])
        self.assertIn("data/11.csv", whole[1])

    def test_a_bash_step_is_named_as_not_audited(self) -> None:
        self.edit_step("b", "", cmd='["bash", "tools/b.sh"]')
        steps = cs.manifest_steps("b", self.root)
        audit = cs.step_reads("b", self.trace(["0\tx\tcheck.sh-run\t{root}\tbash\ttools/b.sh"]), self.root, steps)
        self.assertEqual(audit, {"steps": {}, "unowned": {}, "absent": [], "bash": ["b"]})
        self.assertEqual(cs.audit_lines("b", audit, steps),
                         (["stamp audit: b: every data read is declared in tools/pipeline/checks.toml "
                           "(the code the job imported or ran is not audited) "
                           "(b: bash, which the trace cannot see, so not audited)"], 0))

    def test_an_audit_that_cannot_run_says_so(self) -> None:
        with self.assertRaisesRegex(cs.AuditError, "cannot read the trace of a"):
            cs.step_reads("a", self.tmp / "gone.trace", self.root, cs.manifest_steps("a", self.root))
        with self.assertRaisesRegex(cs.AuditError, "holds no process start"):
            cs.step_reads("a", self.trace(["0\tb", "5\tr\t{root}/data/in.csv"]), self.root,
                          cs.manifest_steps("a", self.root))
        with self.assertRaisesRegex(cs.AuditError, "'unit-hartlib' is no job of"):
            cs.manifest_steps("unit-hartlib", self.root)
        with self.assertRaisesRegex(cs.AuditError, "'static' is no job of"):
            cs.manifest_steps("static", self.root)
        self.assertEqual(cs.audit_trace("unit-hartlib", self.trace(self.HAND), self.root), ([], None))
        lines, audit = cs.audit_trace("a", self.tmp / "gone.trace", self.root)
        self.assertIsNone(audit)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("STAMP AUDIT FAILED: a: cannot read the trace"), lines)
        (self.root / cs.MANIFEST).write_text("[[step]\n")
        lines, audit = cs.audit_trace("a", self.trace(self.HAND), self.root)
        self.assertIsNone(audit)
        self.assertIn("not valid TOML", lines[0])
        self.assertTrue(lines[0].startswith("STAMP AUDIT FAILED: a:"))

    def edit_step(self, name: str, fields: str, cmd: str | None = None) -> None:
        path = self.root / cs.MANIFEST
        text = path.read_text()
        head = f'[[step]]\nname = "{name}"\n'
        self.assertEqual(text.count(head), 1)
        if cmd:
            old = f'cmd = ["python3", "tools/{name}.py"]\n'
            self.assertEqual(text.count(old), 1)
            text = text.replace(old, f"cmd = {cmd}\n")
        path.write_text(text.replace(head, head + fields))

    def audit_cmd(self, *names: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cs.audit_stamp(list(names), self.root, self.store)
        return rc, out.getvalue(), err.getvalue()

    def test_the_stamp_keeps_the_audit_and_the_command_reads_it_against_the_manifest_now(self) -> None:
        log = self.run_job("open('jmri/layouts/hart/data/switches.csv').read()\n", script="tools/a.py")
        lines, audit = cs.audit_trace("a", log, self.root)
        self.assertEqual(audit["steps"]["a"], ["jmri/layouts/hart/data/switches.csv"])
        self.assertIn("    a: jmri/layouts/hart/data/switches.csv", lines)
        self.assertIsNone(cs.record("a", log, self.root, self.store, audit=audit))
        stamp = cs.traced.load(cs._file("a", self.store))
        self.assertEqual(stamp["audit"], audit)
        rc, out, _ = self.audit_cmd("a")
        self.assertEqual(rc, 1)
        self.assertIn("    a: jmri/layouts/hart/data/switches.csv", out)
        self.edit_step("a", 'quiet_inputs = ["jmri/layouts/hart/data/switches.csv"]\n')
        rc, out, _ = self.audit_cmd("a")
        self.assertEqual(rc, 0, out)
        self.assertIn("stamp audit: a: every data read is declared", out)

    def test_the_audit_is_in_no_key_and_changes_no_verdict(self) -> None:
        log = self.run_job("open('jmri/layouts/hart/data/switches.csv').read()\n", script="tools/a.py")
        self.assertIsNone(cs.record("a", log, self.root, self.store))
        plain = cs.traced.load(cs._file("a", self.store))
        self.assertNotIn("audit", plain)
        self.assertIsNone(cs.record("a", log, self.root, self.store, audit=cs.audit_trace("a", log, self.root)[1]))
        audited = cs.traced.load(cs._file("a", self.store))
        self.assertEqual(plain["key"], audited["key"])
        self.assertEqual(plain["state"], audited["state"])
        self.assertTrue(self.current("a"))

    def test_the_command_says_why_it_cannot_audit(self) -> None:
        rc, _, err = self.audit_cmd("a")
        self.assertEqual(rc, 2)
        self.assertIn("stamp audit: a: no stamp; a pass of the job records one", err)
        self.assertIsNone(self.record("a", script="tools/a.py"))                # a stamp with no audit in it
        rc, _, err = self.audit_cmd("a")
        self.assertEqual(rc, 2)
        self.assertIn("its stamp holds no audit", err)
        rc, _, err = self.audit_cmd("unit-hartlib")
        self.assertEqual(rc, 2)
        self.assertIn("unit-hartlib: no job of tools/pipeline/checks.toml", err)
        rc, _, err = self.audit_cmd()                                           # every manifest job: none stamped
        self.assertEqual(rc, 2)
        self.assertEqual(err.count("no stamp;") + err.count("holds no audit"), 5)
        (self.root / cs.MANIFEST).write_text("[[step]\n")
        rc, _, err = self.audit_cmd("a")
        self.assertEqual(rc, 2)
        self.assertIn("stamp audit: cannot run:", err)
        self.assertIn("not valid TOML", err)


if __name__ == "__main__":
    unittest.main()
