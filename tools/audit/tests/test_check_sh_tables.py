"""tools/check.sh with HART_TABLES: table checks read the named file, unit tests never see it."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECK = ROOT / "tools/check.sh"


class CheckShTables(unittest.TestCase):
    def test_every_unittest_step_runs_without_hart_tables(self) -> None:
        text = CHECK.read_text(encoding="utf-8")
        steps = [line.strip() for line in text.splitlines() if "-m unittest" in line]
        self.assertTrue(steps)
        for line in steps:
            self.assertTrue(line.startswith("unit "), line)
        self.assertIn('env -u HART_TABLES "$@"', text)

    def test_a_missing_hart_tables_file_stops_check_sh_at_once(self) -> None:
        env = {**os.environ, "HART_TABLES": "/nowhere/tables.xml"}
        done = subprocess.run(["bash", str(CHECK)], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(1, done.returncode)
        self.assertIn("HART_TABLES=/nowhere/tables.xml: no such file", done.stdout)


class LayoutIndexSource(unittest.TestCase):
    def test_the_index_names_the_checkout_file_when_hart_tables_points_elsewhere(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "tables.xml"
            copy.write_bytes((ROOT / "jmri/layouts/hart/output/tables.xml").read_bytes())
            env = {**os.environ, "HART_TABLES": str(copy)}
            done = subprocess.run([sys.executable, str(ROOT / "www/scripts/build_layout_index.py"), "--check"],
                                  env=env, capture_output=True, text=True, timeout=300)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertRegex(done.stdout, re.compile(r"layout-index\.json is current"))


if __name__ == "__main__":
    unittest.main()
