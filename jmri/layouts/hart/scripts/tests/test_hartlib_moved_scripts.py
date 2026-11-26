"""Scripts moved onto hartlib: they find this checkout's files and edit a copy the same way.

Each writer runs on a copy of tables.xml in a temp folder with a throwaway HOME, so the repo
file and ~/JMRI_UserFiles stay untouched.
"""
from __future__ import annotations

import importlib.util
import os
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


def script_path(name):
    """The script's file: in scripts/, or in parked/ for the ones moved there."""
    here = SCRIPTS / f"{name}.py"
    return here if here.is_file() else SCRIPTS.parent / "parked" / f"{name}.py"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, script_path(name))
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
        self.assertEqual([TABLES], load("apply_nx_layer").DEFAULTS)
        self.assertEqual(TABLES, load("audit_panel_contracts").DEFAULT_SOURCES[0][1])

    def test_other_inputs_are_in_this_checkout(self):
        audit = load("audit_panel_contracts")
        self.assertEqual(paths.LAYOUT_DATA / "schematic" / "masts.csv", audit.MASTS)
        self.assertEqual(paths.LAYOUT_DIR / "dispatcher" / "traininfo", audit.TRAININFO)


class AuditTest(unittest.TestCase):
    def test_panel_contract_audit_passes_on_the_repo_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run("audit_panel_contracts.py", home=Path(tmp))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("RESULT: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
