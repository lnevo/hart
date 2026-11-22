"""tools/check.sh with HART_TABLES: table checks read the named file, unit tests never see it."""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECK = ROOT / "tools/check.sh"


def imported_modules(source: str) -> set[str]:
    """Top-level names of the modules a source file imports, in any form (import a, import a as b, import a.b,
    from a import b, from a.b import c, from . import a) and at any depth (inside a function or a try as well)."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.ImportFrom):          # from . import a
            found |= {alias.name for alias in node.names}
    return found


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
        file that imports that module, directly or through another test file, is in LE_TESTS, and the per-file loop
        leaves those files out."""
        text = CHECK.read_text(encoding="utf-8")
        line = next(x for x in text.splitlines() if x.startswith("LE_TESTS="))
        names = line.split('"')[1].split()
        imports = {p.stem: imported_modules(p.read_text(encoding="utf-8"))
                   for p in (ROOT / "tools/audit/tests").glob("test*.py")}
        users = {"test_build_layout_le"}
        while True:
            more = {stem for stem, mods in imports.items() if mods & users} - users
            if not more:
                break
            users |= more
        self.assertEqual(sorted(users), sorted(names))
        self.assertIn('PYTHONPATH="tools/audit/tests${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m unittest -q \'"$LE_TESTS"',
                      text)
        self.assertIn('" $LE_TESTS " == *" ${f%.py} "* ]] && continue', text)

    def test_every_import_form_is_seen(self) -> None:
        for source in ("import test_build_layout_le", "import test_build_layout_le as T  # noqa",
                       "import os, test_build_layout_le", "from . import test_build_layout_le",
                       "from test_build_layout_le import built", "from test_build_layout_le import built as b, B",
                       "def f():\n    from test_build_layout_le import built\n",
                       "try:\n    import test_build_layout_le\nexcept ImportError:\n    pass\n"):
            self.assertIn("test_build_layout_le", imported_modules(source), source)
        for source in ("import test_build_layout_lex", "# import test_build_layout_le",
                       "x = 'import test_build_layout_le'"):
            self.assertNotIn("test_build_layout_le", imported_modules(source), source)

    def cache_block(self, home: Path, **env: str) -> subprocess.CompletedProcess:
        """Run check.sh's SCHEMATIC_CACHE block (cache folder HART_CACHE_DIR=home/.cache/hart unless given), then
        print the variable as the jobs see it."""
        text = CHECK.read_text(encoding="utf-8")
        start = text.index("# The schematic plugin's cache")
        block = text[start:text.index("\nfi\n", text.index('if [[ -z "${SCHEMATIC_CACHE+set}" ]]', start)) + 4]
        base = {k: v for k, v in os.environ.items() if k != "SCHEMATIC_CACHE"}
        return subprocess.run(["bash", "-c", f'ROOT="{ROOT}"\n' + block + 'echo "CACHE=${SCHEMATIC_CACHE-unset}"'],
                              env={**base, "HOME": str(home), "HART_CACHE_DIR": str(home / ".cache/hart"), **env},
                              capture_output=True, text=True, timeout=30)

    def test_ci_keys_the_schematic_cache_on_the_plugin_pin_and_warms_it_first(self) -> None:
        """A run restores a cache solved with its own plugin pin before main's latest, and a run on another pin
        solves the sheet once (build_panels.sh --check) before check.sh's parallel jobs start."""
        text = (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8")
        self.assertIn("key: schematic-${{ steps.pin.outputs.pin }}-", text)
        self.assertIn("            schematic-${{ steps.pin.outputs.pin }}-\n            schematic-\n", text)
        warm = text.index("name: Warm the schematic cache for a new plugin pin")
        self.assertIn("bash tools/schematic/build_panels.sh --check --full", text[warm:])
        # only for a new pin whose exact cache missed, never on the docs-only path: no time added to other runs
        self.assertIn("if: steps.kind.outputs.kind != 'docs' && steps.schematic-cache.outputs.cache-hit != 'true' "
                      "&& steps.pin.outputs.changed == 'true'", text[warm:])
        self.assertLess(warm, text.index("run: ./tools/check.sh"))

    def test_check_sh_turns_on_the_builds_schematic_cache(self) -> None:
        """The folder the builds use (publish_draft.CACHE), made private; read from the source, not imported."""
        source = (ROOT / "tools/schematic/publish_draft.py").read_text(encoding="utf-8")
        self.assertIn('CACHE = paths.cache_dir("schematic")', source)
        self.assertIn("path: .cache/hart/schematic", (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8"))
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
