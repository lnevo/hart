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
    "unit-guards test_status_merge": ({".gitattributes", "wiki/STATUS.md"}, set(), "wiki/STATUS_LOG.md"),
}


class DeclarationTest(unittest.TestCase):
    def test_every_job_kind_in_check_sh_is_declared(self) -> None:
        kinds = {m.group(1) for m in re.finditer(r"^\s*(?:unit|later)\s+\"?(unit-[a-z-]+|static)\b", CHECK_SH, re.M)}
        kinds |= {"unit-jmri", "unit-hosts", "unit-guards"}     # their names are built in a loop
        kinds |= set(cs.pm.job_digests())                        # the jobs check.sh queues from the step manifest
        self.assertTrue(kinds)
        for kind in sorted(kinds):
            with self.subTest(kind=kind):
                self.assertIsNotNone(cs.declared(kind), f"{kind} has no declaration in check_stamps.BY_KIND")

    def test_a_placeholder_job_is_not_stampable(self) -> None:
        self.assertIsNone(cs.declared("unit-hart-ops skipped (no ops/hart-ops/.venv)"))
        self.assertIsNone(cs.declared("portal skipped in CI"))

    def test_the_manifest_jobs_are_the_stampable_jobs_that_are_not_unit_tests(self) -> None:
        """check_stamps.from_manifest says which jobs' keys hold manifest entries: exactly the manifest's jobs."""
        theirs = {k for k in cs.BY_KIND if cs.from_manifest(k)}
        self.assertEqual(theirs, set(cs.pm.job_digests()), "a job of tools/pipeline/checks.toml needs a BY_KIND "
                                                           "declaration, and BY_KIND's other kinds are unit-*")
        self.assertFalse(cs.from_manifest("portal skipped in CI"))
        self.assertFalse(cs.from_manifest("unit-guards test_x"))

    def test_check_sh_is_an_input_of_every_job(self) -> None:
        for kind in cs.BY_KIND:
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
                             (cs.REFS_OF, {"portal skipped in CI": ("head",)})):
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


# A step manifest for the fake repos: the jobs check.sh runs from it (static, and three jobs of their own). Only
# manifest.job_digests reads it here, which does not check paths against git or the map.
MANIFEST = "".join(f'[[step]]\nname = "{name}"\nrunner = "check"\n{group}cmd = ["python3", "tools/{name}.py"]\n'
                   for name, group in (("a", 'group = "static"\n'), ("b", 'group = "static"\n'), ("public-text", ""),
                                       ("ruff", ""), ("portal", "")))


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


class BatchTest(RepoCase):
    """current-batch checks every job in one process with one Checker (shared hash cache, git, plugin state, walks and
    snapshots); each job alone gets a Checker of its own, as one `current` process per job did. Both must give the same
    verdict, reason and snapshot for every job, whatever changed."""

    SHELL = RepoCase.JOB + "import subprocess\nsubprocess.run(['sh', '-c', 'true'])\n"
    NAMES = ["unit-hartlib", "unit-mimic", "static", "unit-hosts test_redeploy_commit", "unit-jmri test_x",
             "unit-hart-ops skipped (no ops/hart-ops/.venv)"]

    def setUp(self) -> None:
        super().setUp()
        patch = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        self.unstampable = patch.start()
        self.addCleanup(patch.stop)
        self.record("unit-hartlib")
        self.record("unit-mimic")
        # an untraceable program: the declaration (every file for static, CODE for unit-jmri)
        self.record("static", code=self.SHELL, script="shell_job.py")
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
        (self.root / "www/index.html").write_text("v2\n")           # in static's declaration, not in CODE
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
        self.assertNotRegex(cs.outside_state("static", ck), "(?m)^origin=")
        self.assertNotRegex(cs.outside_state("unit-mimic", ck), "(?m)^(head|base|origin)=")
        self.assertIsNone(self.record(name))
        self.assertTrue(self.current(name))
        self.git("commit", "-q", "--allow-empty", "-m", "two")
        self.assertFalse(self.current(name))

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
    JOBS = ("static", "public-text", "ruff", "portal", "unit-hartlib", "unit-guards test_x")

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
        self.assertEqual(self.rerun_after('"tools/b.py"]', '"tools/b.py", "--check"]'), ["static"])
        self.assertEqual(self.rerun_after('"tools/portal.py"]', '"tools/portal2.py"]'), ["portal"])

    def test_a_step_added_to_the_static_group_reruns_static_only(self) -> None:
        self.assertEqual(self.rerun_after('[[step]]\nname = "public-text"',
                                          '[[step]]\nname = "c"\nrunner = "check"\ngroup = "static"\n'
                                          'cmd = ["python3", "tools/c.py"]\n[[step]]\nname = "public-text"'),
                         ["static"])

    def test_a_comment_reruns_nothing(self) -> None:
        self.assertEqual(self.rerun_after('[[step]]\nname = "a"', '# why a\n[[step]]\nname = "a"'), [])

    def test_check_sh_and_the_loader_rerun_every_job(self) -> None:
        before = self.keys()
        for rel in ("tools/check.sh", "tools/pipeline/manifest.py"):
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
            cs.outside_state("static", cs.Checker(self.root, self.store))
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
        self.assertIsNone(self.record("static"))           # a stamp, so `why` works out the key
        (self.root / cs.MANIFEST).write_text("[[step]\n")
        err = io.StringIO()
        real = cs.Checker
        with unittest.mock.patch.object(cs, "Checker", lambda *a, **k: real(self.root, self.store)), \
                contextlib.redirect_stderr(err):
            rc = cs.main(["why", "static"])
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


if __name__ == "__main__":
    unittest.main()
