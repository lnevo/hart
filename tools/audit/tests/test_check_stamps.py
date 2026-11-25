"""check_stamps: the traced stamps that let tools/check.sh skip a job whose reads are what its last pass saw, and the
audit that a recorded read set holds what an independent audit hook saw the same jobs read (a quick sample here)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
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
    "unit-guards test_hart_tables_writers": ({"wiki/STATUS.md", "www/scripts/build_layout_index.py"},
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


class DeclarationTest(unittest.TestCase):
    def test_every_job_kind_in_check_sh_is_declared(self) -> None:
        kinds = {m.group(1) for m in re.finditer(r"^\s*(?:unit|later)\s+\"?(unit-[a-z-]+|public-text|portal|static)\b",
                                                 CHECK_SH, re.M)}
        kinds |= {"unit-jmri", "unit-hosts", "unit-guards"}     # their names are built in a loop
        self.assertTrue(kinds)
        for kind in sorted(kinds):
            with self.subTest(kind=kind):
                self.assertIsNotNone(cs.declared(kind), f"{kind} has no declaration in check_stamps.BY_KIND")

    def test_a_placeholder_job_is_not_stampable(self) -> None:
        self.assertIsNone(cs.declared("unit-hart-ops skipped (no ops/hart-ops/.venv)"))
        self.assertIsNone(cs.declared("portal skipped in CI"))

    def test_check_sh_is_an_input_of_every_job(self) -> None:
        for kind in cs.BY_KIND:
            self.assertIn("tools/check.sh", cs.declared(kind))

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
                             (cs.RUNS_JOBS, {"unit-guards test_x": ("portal skipped in CI",)})):
            with self.subTest(entry=entry), unittest.mock.patch.dict(table, entry):
                with self.assertRaises(ValueError):
                    cs.check_tables()
                with unittest.mock.patch("sys.stderr") as err:
                    self.assertEqual(cs.main(["declared", "unit-hartlib"]), 2)
                self.assertIn("check_stamps", "".join(c.args[0] for c in err.write.call_args_list))


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


class StampTest(unittest.TestCase):
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
        for target, value in (("plugin_state", "plugin"),):
            patch = unittest.mock.patch.object(cs.ps, target, return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = unittest.mock.patch.object(cs, "main_checkout", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def run_job(self, code: str | None = None) -> Path:
        log = self.tmp / "trace.log"
        log.write_text("0\tb\n")
        (self.root / "job.py").write_text(code or self.JOB)
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_TRACE")}
        env.update(HART_TRACE_LOG=str(log), HART_TRACE_ROOT=str(self.root), PYTHONPATH=cs.traced.HOOK_DIR)
        subprocess.run([sys.executable, "job.py"], cwd=self.root, env=env, check=True, capture_output=True)
        return log

    def record(self, name: str = "unit-hartlib", code: str | None = None) -> str | None:
        return cs.record(name, self.run_job(code), self.root, self.store)

    def current(self, name: str = "unit-hartlib") -> bool:
        return cs.is_current(name, self.root, self.store)

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
        self.record("static", code=self.JOB + "import subprocess\nsubprocess.run(['sh', '-c', 'true'])\n")
        (self.root / ".claude/worktrees/other/tools/y.py").write_text("v2\n")
        self.assertTrue(self.current("static"))

    def test_the_private_plan_and_the_interpreter_packages_are_inputs(self) -> None:
        plan = self.tmp / "plan.any"
        plan.write_text("p1\n")
        with unittest.mock.patch.dict(os.environ, {"ANYRAIL_PLAN": str(plan)}):
            self.record("static")
            self.assertTrue(self.current("static"))
            plan.write_text("p2\n")
            self.assertFalse(self.current("static"))
            self.record("static")
            with unittest.mock.patch.object(cs, "venv_state", return_value="other interpreter"):
                self.assertFalse(self.current("static"))

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
            before = cs.snapshot("static", self.root, self.store)
            log = self.run_job()
            plan.write_text("p2\n")             # the job saw p1; the key worked out now would hold p2
            self.assertIn("changed while the job ran", cs.record("static", log, self.root, self.store, before=before))
            self.assertFalse(self.current("static"))

    def test_a_short_trace_records_nothing_and_drops_the_old_stamp(self) -> None:
        self.record()
        log = self.tmp / "short.log"
        log.write_text("0\tb\n")
        self.assertIn("did not load", cs.record("unit-hartlib", log, self.root, self.store))
        self.assertFalse(self.current())


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
                    if stamp is None:
                        # check.sh records nothing for a job that skipped tests (their conditions are not stamped)
                        self.assertRegex(done.stdout, r"skipped=\d", f"{name} recorded no stamp")
                        continue
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
            self.assertGreaterEqual(verified, len(wanted) // 2, "too few audited jobs recorded a stamp to compare")


if __name__ == "__main__":
    unittest.main()
