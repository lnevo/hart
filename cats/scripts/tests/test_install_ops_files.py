"""The deploy installs the Operations Pro files without losing Pi session state."""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "cats/scripts/install_ops_files.sh"
FILES = ("Operations.xml", "OperationsCarRoster.xml", "OperationsEngineRoster.xml",
         "OperationsLocationRoster.xml", "OperationsRouteRoster.xml", "OperationsTrainRoster.xml")


class InstallOpsFiles(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.src, self.dest = self.tmp / "src", self.tmp / "dest"
        self.src.mkdir()
        self.fake_pgrep(1)
        for name in FILES:
            (self.src / name).write_text(f"repo {name}")

    def fake_pgrep(self, code):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir(exist_ok=True)
        pgrep = bin_dir / "pgrep"
        pgrep.write_text(f"#!/bin/sh\nexit {code}\n")
        pgrep.chmod(pgrep.stat().st_mode | stat.S_IEXEC)

    def run_it(self, *extra, **env):
        return subprocess.run(
            ["bash", str(SCRIPT), str(self.src), str(self.dest), *extra],
            capture_output=True, text=True,
            env={**os.environ, "PATH": f"{self.tmp / 'bin'}:{os.environ['PATH']}", **env},
        )

    def roster(self):
        return (self.dest / "OperationsCarRoster.xml").read_text()

    def test_installs_all_six(self):
        self.assertEqual(self.run_it("--guard").returncode, 0)
        self.assertEqual(sorted(p.name for p in self.dest.glob("*.xml")), sorted(FILES))

    def test_session_state_stops_the_deploy(self):
        self.run_it("--guard")
        (self.dest / "OperationsCarRoster.xml").write_text("session")
        (self.src / "OperationsCarRoster.xml").write_text("repo change")
        result = self.run_it("--guard")
        self.assertEqual(result.returncode, 1)
        self.assertIn("make ops-pull", result.stderr)
        self.assertEqual(self.roster(), "session")

    def test_override_replaces_and_keeps_a_backup(self):
        self.run_it("--guard")
        (self.dest / "OperationsCarRoster.xml").write_text("session")
        self.assertEqual(self.run_it("--guard", HART_OVERWRITE_OPS="1").returncode, 0)
        self.assertEqual(self.roster(), "repo OperationsCarRoster.xml")
        saved = list(self.dest.glob("backups/*/OperationsCarRoster.xml"))
        self.assertEqual(saved[0].read_text(), "session")

    def test_repo_change_installs_when_host_is_unchanged(self):
        self.run_it("--guard")
        (self.src / "OperationsCarRoster.xml").write_text("repo change")
        self.assertEqual(self.run_it("--guard").returncode, 0)
        self.assertEqual(self.roster(), "repo change")

    def test_running_jmri_skips_without_failing(self):
        self.fake_pgrep(0)
        result = self.run_it("--guard")
        self.assertEqual(result.returncode, 0)
        self.assertIn("SKIP", result.stdout)
        self.assertFalse((self.dest / "OperationsCarRoster.xml").exists())

    def test_host_without_guard_takes_the_repo(self):
        self.run_it()
        (self.dest / "OperationsCarRoster.xml").write_text("local")
        self.assertEqual(self.run_it().returncode, 0)
        self.assertEqual(self.roster(), "repo OperationsCarRoster.xml")


if __name__ == "__main__":
    unittest.main()
