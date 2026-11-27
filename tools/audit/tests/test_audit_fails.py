"""The declaration audit as a failure (ADR-037 stage 4c): a step-manifest job that read a file its step does not
declare fails in an audit run (CHECK_AUDIT) and with CHECK_AUDIT_FAILS=1 (the weekly full run), and only warns in any
other run; a job with no stamp yet is audited from its own trace. check_stamps.py record's exit, check.sh's use of it
(with a stand-in check_stamps.py in a scratch repo) and the workflow's weekly run."""
from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_stamps as cs  # noqa: E402
from stamps_case import RepoCase  # noqa: E402
from test_pipeline_manifest import OWN, STATIC, scratch_check_sh  # noqa: E402

WORKFLOW = (cs.ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8")
READS = "open('jmri/layouts/hart/data/switches.csv').read()\n"     # a read step a declares nowhere


class RecordTest(RepoCase):
    """check_stamps.py record NAME FILE --trace LOG [--audit-fails] in a fake repo (RepoCase's manifest: step a)."""

    def setUp(self) -> None:
        super().setUp()
        patch = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def record_cmd(self, name: str, log: Path, *flags: str) -> tuple[int, str]:
        snap = self.tmp / "before"
        snap.write_text(cs.snapshot(name, self.root, self.store) + "\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            args = cs.build_parser().parse_args(["record", name, str(snap), "--trace", str(log), *flags])
            rc = cs.record_cmd(args, self.root, self.store)
        return rc, out.getvalue()

    def stamp(self, name: str = "a"):
        return cs.traced.load(cs._file(name, self.store))

    def test_an_undeclared_read_fails_with_the_flag_and_records_nothing(self) -> None:
        log = self.run_job(READS, script="tools/a.py")
        self.assertEqual(self.record_cmd("a", log)[0], 0)          # an older stamp, which the failure leaves alone
        old = self.stamp()
        self.assertIsNotNone(old)
        (self.root / "jmri/layouts/hart/data/switches.csv").write_text("v2\n")
        log = self.run_job(READS, script="tools/a.py")
        rc, out = self.record_cmd("a", log, "--audit-fails")
        self.assertEqual(rc, 1, out)
        self.assertIn("WARNING: stamp audit: a: 1 read(s) not declared", out)
        self.assertIn("this run fails on it (ADR-037 stage 4c", out)
        self.assertIn("    a: jmri/layouts/hart/data/switches.csv", out)
        self.assertIn("not stamped: the declaration audit below failed", out)
        self.assertEqual(self.stamp(), old, "the failed audit recorded this run, or dropped the older stamp")
        self.assertFalse(self.current("a"), "the older stamp holds for the changed input")

    def test_a_plain_run_warns_and_records(self) -> None:
        rc, out = self.record_cmd("a", self.run_job(READS, script="tools/a.py"))
        self.assertEqual(rc, 0, out)
        self.assertIn("WARNING: stamp audit: a: 1 read(s) not declared", out)
        self.assertIn("warn only in this run", out)
        self.assertIsNotNone(self.stamp())

    def test_a_job_with_no_stamp_yet_is_audited_from_its_own_trace(self) -> None:
        """The weekly run records into a folder of its own: no job has a stamp there. Its trace is what is audited,
        so a declared read passes and the stamp is recorded; the stale-stamp rows of `audit` do not arise."""
        path = self.root / cs.MANIFEST
        path.write_text(path.read_text().replace('name = "a"\n', 'name = "a"\n'
                                                 'quiet_inputs = ["jmri/layouts/hart/data/switches.csv"]\n'))
        self.assertIsNone(self.stamp())
        rc, out = self.record_cmd("a", self.run_job(READS, script="tools/a.py"), "--audit-fails")
        self.assertEqual(rc, 0, out)
        self.assertIn("stamp audit: a: every data read is declared", out)
        self.assertIsNotNone(self.stamp())

    def test_an_audit_that_cannot_run_fails_with_the_flag_only(self) -> None:
        log = self.tmp / "hand.trace"
        log.write_text(f"0\tb\n5\tr\t{self.root}/data/in.csv\n")       # a Python step's trace with no process in it
        rc, out = self.record_cmd("a", log, "--audit-fails")
        self.assertEqual(rc, 1, out)
        self.assertIn("STAMP AUDIT FAILED: a: the trace of a", out)
        self.assertNotIn("the job passes", out)
        rc, out = self.record_cmd("a", log)
        self.assertEqual(rc, 0, out)
        self.assertIn("(the job passes; warn only in this run", out)

    def test_what_audits_nothing_says_so_with_the_flag(self) -> None:
        """3: a unit job, a bash step, a job not stampable now. check.sh lets the job pass and names it unaudited."""
        rc, out = self.record_cmd("unit-hartlib", self.run_job(), "--audit-fails")
        self.assertEqual((rc, out), (3, ""))
        self.assertIsNotNone(self.stamp("unit-hartlib"))
        path = self.root / cs.MANIFEST
        path.write_text(path.read_text().replace('cmd = ["python3", "tools/b.py"]', 'cmd = ["bash", "tools/b.sh"]'))
        log = self.tmp / "bash.trace"
        log.write_text(f"0\tt\t1\n0\tx\tcheck.sh-run\t{self.root}\tbash\ttools/b.sh\n")
        rc, out = self.record_cmd("b", log, "--audit-fails")
        self.assertEqual(rc, 3, out)
        self.assertIn("(b: bash, which the trace cannot see, so not audited)", out)
        self.assertEqual(self.record_cmd("b", log)[0], 0)
        with unittest.mock.patch.object(cs.ps, "unstampable", return_value="HART_TABLES is set"):
            self.assertEqual(self.record_cmd("a", self.run_job(READS, script="tools/a.py"), "--audit-fails"), (3, ""))

    def test_a_call_of_another_shape_is_refused(self) -> None:
        for argv, says in ((["record", "a", "snap", "--trace"], "--trace: expected one argument"),
                           (["record", "a", "snap", "--trace", "log", "--audit-fails", "x"],
                            "unrecognized arguments: x")):
            err = io.StringIO()
            with self.subTest(argv=argv), contextlib.redirect_stderr(err), \
                    unittest.mock.patch.object(cs, "record_cmd") as record:
                self.assertEqual(cs.main(argv), 2)
                record.assert_not_called()
            self.assertIn("usage: check_stamps.py", err.getvalue())
            self.assertIn(says, err.getvalue())


# The stand-in stamp helper: every job runs and may record; job "one" read a file its step does not declare.
STUB_STAMPS = '''import pathlib, sys
cmd, args = sys.argv[1], sys.argv[2:]
if cmd == "current-batch":
    names, out = pathlib.Path(args[0]).read_text().splitlines(), pathlib.Path(args[1])
    for i, _ in enumerate(names):
        (out / f"{i}.stamp").write_text("snapshot\\n")
    (out / "verdicts").write_text("".join(f"{i}\\t1\\n" for i in range(len(names))))
elif cmd == "record":
    fails = args[-1] == "--audit-fails"
    if args[0] == "one":
        print("WARNING: stamp audit: one: 1 read(s) not declared; " + ("this run fails" if fails else "warn only"))
        sys.exit(1 if fails else 0)
    if args[0] == "shell":     # bash: nothing audited
        print("stamp audit: shell: (shell: bash, which the trace cannot see, so not audited)")
        sys.exit(3 if fails else 0)
    print(f"stamp audit: {args[0]}: every data read is declared")
'''
QUIET = "^(one|two|panels-tables|shell|skippy)$"


class CheckShTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.s = scratch_check_sh(Path(cls.tmp.name))
        cls.s.write("tools/audit/check_stamps.py", STUB_STAMPS)
        cls.s.write("tools/s.py", "print('SKIPPED skippy: no plan here')\n")
        cls.s.commit("stamp stub")
        cls.out = Path(cls.tmp.name) / "out"           # outside the scratch checkout

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_check(self, **env: str):
        base = {"STUB_PIN": "", "STUB_STATIC": STATIC + "skippy python3 tools/s.py\n", "STUB_OWN": OWN, "FULL": "1",
                "CHECK_ONLY": QUIET}
        return self.s.check_sh(**{**base, **env})

    def assertJobFailedByAudit(self, done) -> None:
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("--- one FAILED", done.stdout)
        self.assertIn("one: FAILED by the declaration audit above", done.stdout)
        self.assertRegex(done.stdout, r"(?m)^--- two \(\d+s\)$")
        self.assertEqual(done.stdout.splitlines()[-1], "FAILED")

    def test_a_plain_run_warns(self) -> None:
        done = self.run_check()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^--- one \(\d+s\)$")
        self.assertIn("WARNING: stamp audit: one: 1 read(s) not declared; warn only", done.stdout)
        self.assertNotIn("declaration audit:", done.stdout)
        self.assertEqual(done.stdout.splitlines()[-1], "ALL PASSED")

    def test_an_audit_run_fails_the_job_and_names_the_unaudited(self) -> None:
        done = self.run_check(CHECK_AUDIT=str(self.out / "audit"))
        self.assertJobFailedByAudit(done)
        self.assertIn("this run fails", done.stdout)
        self.assertIn("declaration audit: 2 of 4 passing step-manifest job(s) not audited (bash, or not traced): "
                      "shell skippy", done.stdout)

    def test_the_weekly_run_fails_the_job(self) -> None:
        """What .github/workflows/check.yml gives check.sh on its schedule: CI, a record folder, CHECK_AUDIT_FAILS."""
        self.assertJobFailedByAudit(self.run_check(CI="true", FULL="", CHECK_AUDIT_FAILS="1",
                                                   CHECK_RECORD_TO=str(self.out / "weekly-stamps")))

    def test_a_pull_request_run_records_nothing_and_passes(self) -> None:
        done = self.run_check(CI="true", FULL="")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("stamp audit", done.stdout)

    def test_a_run_that_audits_no_manifest_job_fails(self) -> None:
        for only in ("^skippy$", "^shell$"):
            with self.subTest(only=only):
                done = self.run_check(CHECK_AUDIT=str(self.out / "audit"), CHECK_ONLY=only)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn("declaration audit: no step-manifest job was audited", done.stdout)

    def test_a_failing_audit_that_cannot_audit_is_refused_before_any_job(self) -> None:
        for env, said in (({"CI": "true", "FULL": "", "CHECK_AUDIT_FAILS": "1"}, "records no stamp"),
                          ({"CHECK_AUDIT_FAILS": "yes"}, "CHECK_AUDIT_FAILS=yes: it is 1 or unset"),
                          ({"CHECK_AUDIT": str(self.s.repo / "audit")}, "is inside the checkout")):
            with self.subTest(env=env):
                done = self.run_check(**env)
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertIn(said, done.stderr)
                self.assertNotIn("ran ", done.stdout)


class WorkflowTest(unittest.TestCase):
    def test_only_the_weekly_run_fails_on_the_audit_and_it_records_somewhere_unsaved(self) -> None:
        keys = re.findall(r"(?m)^ +(CHECK_AUDIT\w*|CHECK_RECORD_TO): (.*)$", WORKFLOW)
        self.assertEqual([k for k, _ in keys], ["CHECK_RECORD_TO", "CHECK_AUDIT_FAILS"],
                         "the workflow sets the audit variables in another place, or CHECK_AUDIT itself")
        env = dict(keys)
        self.assertEqual(env["CHECK_AUDIT_FAILS"], "${{ github.event_name == 'schedule' && '1' || '' }}")
        self.assertIn("github.event_name == 'schedule' && format('{0}/weekly-stamps', runner.temp)",
                      env["CHECK_RECORD_TO"])
        self.assertEqual(WORKFLOW.count("weekly-stamps"), 1, "the weekly run's stamps are saved or read somewhere")


if __name__ == "__main__":
    unittest.main()
