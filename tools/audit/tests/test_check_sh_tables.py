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

    def test_the_layout_editor_files_run_as_one_job(self) -> None:
        """One process, so test_build_layout_le.built() (cached per process) builds the candidate once: every test
        file that imports that module is in LE_TESTS, and the per-file loop leaves those files out."""
        text = CHECK.read_text(encoding="utf-8")
        line = next(x for x in text.splitlines() if x.startswith("LE_TESTS="))
        names = line.split('"')[1].split()
        tests = ROOT / "tools/audit/tests"
        users = sorted(p.stem for p in tests.glob("test*.py") if p.stem == "test_build_layout_le" or any(
            x.startswith("import test_build_layout_le") for x in p.read_text(encoding="utf-8").splitlines()))
        self.assertEqual(users, sorted(names))
        self.assertIn('env PYTHONPATH=tools/audit/tests python3 -m unittest -q $LE_TESTS', text)
        self.assertIn('" $LE_TESTS " == *" ${f%.py} "* ]] && continue', text)

    def cache_block(self, home: Path, **env: str) -> subprocess.CompletedProcess:
        """Run check.sh's SCHEMATIC_CACHE block with HOME=home, then print the variable as the jobs see it."""
        text = CHECK.read_text(encoding="utf-8")
        start = text.index("# The schematic plugin's cache")
        block = text[start:text.index("\nfi\n", text.index('if [[ -z "${SCHEMATIC_CACHE+set}" ]]', start)) + 4]
        base = {k: v for k, v in os.environ.items() if k != "SCHEMATIC_CACHE"}
        return subprocess.run(["bash", "-c", block + 'echo "CACHE=${SCHEMATIC_CACHE-unset}"'],
                              env={**base, "HOME": str(home), **env}, capture_output=True, text=True, timeout=30)

    def test_check_sh_turns_on_the_builds_schematic_cache(self) -> None:
        """The folder the builds use (publish_draft.CACHE), made private; read from the source, not imported."""
        source = (ROOT / "tools/schematic/publish_draft.py").read_text(encoding="utf-8")
        self.assertIn('CACHE = Path.home() / ".cache/hart/schematic"', source)
        self.assertIn("path: ~/.cache/hart/schematic", (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            done = self.cache_block(Path(d))
            folder = Path(d) / ".cache/hart/schematic"
            self.assertIn(f"CACHE={folder}", done.stdout)
            self.assertEqual(0o700, folder.stat().st_mode & 0o777)

    def test_an_empty_or_set_schematic_cache_is_the_callers(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("CACHE=\n", self.cache_block(Path(d), SCHEMATIC_CACHE="").stdout)
            self.assertIn("CACHE=/elsewhere\n", self.cache_block(Path(d), SCHEMATIC_CACHE="/elsewhere").stdout)
            self.assertFalse((Path(d) / ".cache").exists())

    def test_a_cache_folder_that_cannot_be_made_leaves_it_off(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".cache").write_text("a file, not a folder")
            done = self.cache_block(Path(d))
            self.assertIn("CACHE=unset", done.stdout)
            self.assertIn("schematic cache off", done.stdout)

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
