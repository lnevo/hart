"""check_stamps' declaration audit of the step-manifest jobs (ADR-037 stages 4a, 4c; stamps_audit.py): step_reads,
audit_lines, manifest_steps, record's audit_trace and `check_stamps.py audit`."""
from __future__ import annotations

import contextlib
import io
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_stamps as cs  # noqa: E402
from stamps_case import RepoCase  # noqa: E402


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
        self.assertEqual(cs.audit_trace("unit-hartlib", self.trace(self.HAND), self.root), ([], None, 0))
        lines, audit, _ = cs.audit_trace("a", self.tmp / "gone.trace", self.root)
        self.assertIsNone(audit)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("STAMP AUDIT FAILED: a: cannot read the trace"), lines)
        (self.root / cs.MANIFEST).write_text("[[step]\n")
        lines, audit, _ = cs.audit_trace("a", self.trace(self.HAND), self.root)
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
        lines, audit, _ = cs.audit_trace("a", log, self.root)
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
