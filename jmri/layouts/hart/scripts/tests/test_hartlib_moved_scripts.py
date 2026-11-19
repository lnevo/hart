"""Scripts moved onto hartlib: they find this checkout's files and edit a copy the same way.

Each writer runs on a copy of tables.xml in a temp folder with a throwaway HOME, so the repo
file and ~/JMRI_UserFiles stay untouched.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

TABLES = paths.TABLES_XML


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(script: str, *args: str, home: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home))
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, env=env, cwd=home,
    )


class DefaultPathsTest(unittest.TestCase):
    def test_default_tables_are_this_checkouts_file(self):
        for name, attr in (
            ("apply_le_sml_facing", "DEFAULT_PANEL"),
            ("apply_public_names", "DEFAULT_TABLES"),
            ("capture_public_name_baseline", "DEFAULT_TABLES"),
        ):
            with self.subTest(name):
                self.assertEqual(TABLES, getattr(load(name), attr))
        self.assertEqual([TABLES], load("apply_nx_layer").DEFAULTS)
        self.assertEqual(TABLES, load("audit_panel_contracts").DEFAULT_SOURCES[0][1])

    def test_other_inputs_are_in_this_checkout(self):
        audit = load("audit_panel_contracts")
        self.assertEqual(paths.LAYOUT_DATA / "le_signal_boundaries.csv", audit.BOUNDARIES)
        self.assertEqual(paths.LAYOUT_DIR / "dispatcher" / "traininfo", audit.TRAININFO)
        self.assertEqual(paths.PUBLIC_NAME_MAP, load("apply_public_names").DEFAULT_MAP)
        self.assertEqual(paths.JMRI_USER_FILES / "tables.xml", load("apply_le_sml_facing").PREF_TABLES)


class WritersOnACopyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)

    def copy(self, name: str) -> Path:
        """A writable copy of this checkout's tables.xml."""
        path = self.home / name
        shutil.copy(TABLES, path)
        path.chmod(0o644)
        return path

    def test_sml_facing_dry_run_writes_nothing(self):
        panel = self.copy("facing.xml")
        before = panel.read_bytes()
        result = run("apply_le_sml_facing.py", "--dry-run", "--panel", str(panel), home=self.home)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, panel.read_bytes())


class AuditTest(unittest.TestCase):
    def test_panel_contract_audit_passes_on_the_repo_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run("audit_panel_contracts.py", home=Path(tmp))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("RESULT: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
