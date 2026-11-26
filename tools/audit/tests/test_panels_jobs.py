"""The panels checks as check.sh jobs of their own (ADR-037 stage 6): checks.toml's panels step stands for one job per
step of tools/pipeline/panels.toml, panels-<step>, which runs that step's check. Each job's key holds its own
panels.toml entry and the panels step's, the step's outputs and make panels' code (panel_stamps.CODE) whole, and the
merge base for a step that publishes, so a change reruns the panels jobs it can reach and no other; their reads are
not audited (panels.toml's inputs are map edges)."""
from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_stamps as cs  # noqa: E402
from stamps_case import RepoCase  # noqa: E402

M = cs.pm
REAL_PANELS = M.PANELS.read_text(encoding="utf-8")
ANCHOR = ('[[step]]\nname = "panels"\nrunner = "check"\ngroup = "static"\n'
          'cmd = ["bash", "tools/schematic/build_panels.sh", "--check"]\ngit = []\n')
OTHER = '[[step]]\nname = "a"\nrunner = "check"\ngroup = "static"\ncmd = ["python3", "tools/a.py"]\ngit = []\n'


class ManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.checks, self.panels = self.tmp / "checks.toml", self.tmp / "panels.toml"
        self.checks.write_text(OTHER + ANCHOR)
        self.panels.write_text(REAL_PANELS)

    def keys(self) -> dict:
        return M.job_keys(self.checks)

    def test_the_jobs_are_the_panels_steps_with_their_check_args(self) -> None:
        steps = M.panel_steps()
        self.assertEqual(M.panel_check_lines(steps),
                         [" ".join(("panels-" + s.name, *s.cmd, *s.check_args)) for s in steps])
        self.assertEqual(list(self.keys()), ["a", *("panels-" + s.name for s in steps)])
        with self.assertRaisesRegex(M.ManifestError, "no panels step"):
            M.panel_check_lines(())

    def test_an_edited_step_reruns_its_own_job_and_the_panels_step_reruns_them_all(self) -> None:
        before = self.keys()
        self.panels.write_text(REAL_PANELS.replace('cmd = ["python3", "tools/schematic/build_hands.py"]\n',
                                                   'cmd = ["python3", "tools/schematic/build_hands.py", "--x"]\n'))
        after = self.keys()
        changed = sorted(k for k in before if before[k].digest != after[k].digest)
        self.assertEqual(changed, ["panels-hands"])
        self.panels.write_text(REAL_PANELS)
        self.checks.write_text(OTHER + ANCHOR.replace('group = "static"\n', 'group = "static"\nlabel = "x"\n'))
        again = self.keys()
        self.assertEqual(sorted(k for k in before if before[k].digest != again[k].digest),
                         sorted(k for k in before if k.startswith("panels-")))

    def test_refs_outputs_and_names(self) -> None:
        keys = self.keys()
        publishing = {"panels-" + s.name for s in M.panel_steps() if s.publishes}
        self.assertIn("panels-schematic", publishing)
        for job, key in keys.items():
            with self.subTest(job=job):
                if job == "a":
                    self.assertIsNone(key.panel)
                    continue
                self.assertEqual(key.git, ("base",) if job in publishing else ())
        self.assertIn("jmri/layouts/hart/data/switches.csv", keys["panels-hands"].panel)
        self.assertEqual(keys["panels-sml-current"].panel, ())         # a guard: no outputs, still a panels job
        self.checks.write_text(OTHER + ANCHOR.replace("git = []", 'git = ["head"]'))
        self.assertEqual(self.keys()["panels-schematic"].git, ("head", "base"))

    def test_a_job_name_that_is_also_a_check_is_refused(self) -> None:
        self.checks.write_text(OTHER.replace('name = "a"', 'name = "panels-hands"') + ANCHOR)
        for read in (M.job_keys, M.declarations):
            with self.subTest(read=read.__name__):
                with self.assertRaisesRegex(M.ManifestError, "its check.sh job 'panels-hands' is also a step"):
                    read(self.checks)

    def test_a_panels_manifest_that_does_not_load_stops_the_keys(self) -> None:
        self.panels.write_text("[[step]\n")
        with self.assertRaises(M.ManifestError):
            self.keys()

    def test_declarations_name_each_panels_job_unaudited(self) -> None:
        d = M.declarations(self.checks)
        self.assertEqual(d["a"][0].unaudited, "")
        self.assertEqual({d[k][0].unaudited for k in d if k != "a"}, {M.PANELS_UNAUDITED})
        self.assertEqual(d["panels-tables"][0].script, "tools/schematic/build_tables.py")


class StampTest(RepoCase):
    """A panels job's stamp in a fake repo: its key hashes its outputs and make panels' code, read or not."""

    def setUp(self) -> None:
        super().setUp()
        (self.root / cs.MANIFEST).write_text(OTHER + ANCHOR)
        (self.root / cs.MANIFEST).with_name("panels.toml").write_text(REAL_PANELS)
        for rel in ("tools/schematic/helper.py", "jmri/layouts/hart/data/switches.csv", "www/index.html"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("v1\n")
        patch = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_code_or_output_change_reruns_it_and_another_file_does_not(self) -> None:
        self.assertIsNone(self.record("panels-hands", script="tools/schematic/build_hands.py"))
        self.assertTrue(self.current("panels-hands"))
        (self.root / "www/index.html").write_text("v2\n")                    # neither read nor hashed
        self.assertTrue(self.current("panels-hands"))
        for rel in ("tools/schematic/helper.py", "jmri/layouts/hart/data/switches.csv"):
            with self.subTest(rel=rel):
                self.assertIsNone(self.record("panels-hands", script="tools/schematic/build_hands.py"))
                self.assertTrue(self.current("panels-hands"))
                (self.root / rel).write_text("v3\n")
                self.assertFalse(self.current("panels-hands"), f"{rel} changed and the job would be skipped")

    def test_another_steps_entry_does_not_rerun_it(self) -> None:
        self.assertIsNone(self.record("panels-hands", script="tools/schematic/build_hands.py"))
        panels = (self.root / cs.MANIFEST).with_name("panels.toml")
        panels.write_text(REAL_PANELS.replace('cmd = ["python3", "tools/schematic/build_masts.py"]\n',
                                              'cmd = ["python3", "tools/schematic/build_masts.py", "--x"]\n'))
        self.assertTrue(self.current("panels-hands"))
        panels.write_text(REAL_PANELS.replace('cmd = ["python3", "tools/schematic/build_hands.py"]\n',
                                              'cmd = ["python3", "tools/schematic/build_hands.py", "--x"]\n'))
        self.assertFalse(self.current("panels-hands"))

    def test_its_reads_are_not_audited_and_that_is_said(self) -> None:
        log = self.run_job(script="tools/schematic/build_hands.py")
        lines, audit, bad = cs.audit_trace("panels-hands", log, self.root, fails=True)
        self.assertEqual((audit, bad), (None, 0))
        self.assertEqual(lines, [f"stamp audit: panels-hands: not audited: {M.PANELS_UNAUDITED}"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = cs.audit_stamp(["panels-hands"], self.root, self.store)
        self.assertEqual(rc, 0)
        self.assertIn("panels-hands: not audited", out.getvalue())

    def test_the_old_one_panels_job_is_retired(self) -> None:
        self.assertIn("panels", cs.RETIRED)


if __name__ == "__main__":
    unittest.main()
