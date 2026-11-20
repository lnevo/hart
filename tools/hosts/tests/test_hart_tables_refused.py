"""HART_TABLES (hartlib.paths) points the table checks at another file; a deploy ships the checkout's tables.xml,
so the deploy and redeploy scripts stop at once while it is set, before any host is reached."""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class HartTablesRefused(unittest.TestCase):
    def test_deploy_scripts_stop_while_hart_tables_is_set(self) -> None:
        env = {**os.environ, "HART_TABLES": "/nowhere/tables.xml", "HART_PI_SSH": "nobody@example.invalid",
               "HART_WIN_SSH": "nobody@example.invalid"}
        scripts = (("tools/hosts/sync_hart_package.sh", ["--stage-only", "/nowhere/stage"]),
                   ("tools/hosts/redeploy_commit.sh", ["HEAD", "--pi"]),
                   ("tools/hosts/run_panelpro_roundtrip.sh", []))
        for script, args in scripts:
            with self.subTest(script=script):
                done = subprocess.run(["bash", str(ROOT / script), *args], env=env, capture_output=True,
                                      text=True, timeout=30)
                self.assertEqual(1, done.returncode)
                self.assertIn("HART_TABLES is set (/nowhere/tables.xml): it is for checks only", done.stderr)
                self.assertEqual("", done.stdout)


    def test_panelpro_wrappers_stop_while_hart_tables_is_set(self) -> None:
        env = {**os.environ, "HART_TABLES": "/nowhere/tables.xml", "JMRI_HOME": "/nowhere"}
        for name in ("run_panelpro_stage1.sh", "run_nx_discover.sh", "run_sml_discover.sh",
                     "run_panelpro_traininfo_repair.sh", "run_panelpro_smoke_test.sh"):
            with self.subTest(script=name):
                done = subprocess.run(["bash", str(ROOT / "jmri/layouts/hart/scripts" / name)], env=env,
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(1, done.returncode)
                self.assertIn("HART_TABLES is set (/nowhere/tables.xml): it is for checks only", done.stderr)


    def test_one_shared_refusal(self) -> None:
        guard = (ROOT / "tools/hosts/profile_tables_guard.sh").read_text(encoding="utf-8")
        self.assertIn("refuse_hart_tables()", guard)
        users = ["tools/hosts/sync_hart_package.sh", "tools/hosts/redeploy_commit.sh",
                 "tools/hosts/run_panelpro_roundtrip.sh"] + [
            f"jmri/layouts/hart/scripts/{n}" for n in ("run_panelpro_stage1.sh", "run_nx_discover.sh",
                                                     "run_sml_discover.sh", "run_panelpro_traininfo_repair.sh",
                                                     "run_panelpro_smoke_test.sh")]
        for rel in users:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("refuse_hart_tables ", text, rel)
            self.assertEqual(1, text.count('if [[ -n "${HART_TABLES:-}" ]]') + 1, rel)   # no private copy


if __name__ == "__main__":
    unittest.main()
