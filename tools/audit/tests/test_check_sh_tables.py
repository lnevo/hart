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

    def test_check_sh_uses_the_builds_schematic_cache(self) -> None:
        """check.sh turns the plugin's cache on in the folder the builds use, unless the caller set the variable."""
        sys.path.insert(0, str(ROOT / "tools/schematic"))
        import publish_draft
        text = CHECK.read_text(encoding="utf-8")
        self.assertEqual(Path.home() / ".cache/hart/schematic", publish_draft.CACHE)
        self.assertIn('export SCHEMATIC_CACHE="$HOME/.cache/hart/schematic"', text)
        self.assertIn('if [[ -z "${SCHEMATIC_CACHE+set}" ]]; then', text)
        self.assertIn("path: ~/.cache/hart/schematic", (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8"))

    def test_a_missing_hart_tables_file_stops_check_sh_at_once(self) -> None:
        env = {**os.environ, "HART_TABLES": "/nowhere/tables.xml"}
        done = subprocess.run(["bash", str(CHECK)], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(1, done.returncode)
        self.assertIn("HART_TABLES=/nowhere/tables.xml: no such file", done.stdout)

    def resolve(self, value: str, cwd: Path, home: Path) -> subprocess.CompletedProcess:
        """Run check.sh's HART_TABLES block (the lines before ROOT=) from `cwd`, then print the result."""
        text = CHECK.read_text(encoding="utf-8")
        block = text[text.index("if [[ -n \"${HART_TABLES:-}\" ]]"):text.index('ROOT="$(cd')]
        env = {**os.environ, "HART_TABLES": value, "HOME": str(home)}
        return subprocess.run(["bash", "-c", block + 'echo "RESOLVED=$HART_TABLES"'], cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=30)

    def test_a_relative_or_tilde_hart_tables_is_the_callers(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            (d / "sub").mkdir()
            (d / "sub" / "cand.xml").write_text("<layout-config/>")
            done = self.resolve("sub/cand.xml", d, d)
            self.assertIn(f"RESOLVED={d}/sub/cand.xml", done.stdout, done.stderr)
            done = self.resolve("~/sub/cand.xml", ROOT, d)
            self.assertIn(f"RESOLVED={d}/sub/cand.xml", done.stdout, done.stderr)
            self.assertIn("no such file", self.resolve("nope.xml", d, d).stdout)


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
