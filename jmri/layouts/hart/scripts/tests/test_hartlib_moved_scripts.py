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


def run(script: str, *args: str, home: Path, jmri_running: str = "0") -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home), HART_GUARD_JMRI_RUNNING=jmri_running)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, env=env, cwd=home,
    )


class DefaultPathsTest(unittest.TestCase):
    def test_default_tables_are_this_checkouts_file(self):
        for name, attr in (
            ("add_digicon_le_signal_icons", "DEFAULT_PANEL"),
            ("add_yard_ladder_le_icons", "DEFAULT_PANEL"),
            ("annotate_mqtt_sensors_and_dispatcher", "TABLES"),
            ("apply_le_cleanup", "DEFAULT"),
            ("apply_le_sml_facing", "DEFAULT_PANEL"),
            ("apply_public_names", "DEFAULT_TABLES"),
            ("apply_yard_throat_blocks", "DEFAULT"),
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
        self.assertEqual(paths.CATS_DIR / "data" / "occupancy_bindings.csv",
                         load("annotate_mqtt_sensors_and_dispatcher").OCC_CSV)
        self.assertEqual(paths.PUBLIC_NAME_MAP, load("apply_public_names").DEFAULT_MAP)
        self.assertEqual(paths.JMRI_USER_FILES / "tables.xml", load("apply_le_sml_facing").PREF_TABLES)


class WritersOnACopyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)

    def copy(self, name: str) -> Path:
        path = self.home / name
        shutil.copy(TABLES, path)
        return path

    def test_le_cleanup_edits_then_is_idempotent(self):
        panel = self.copy("cleanup.xml")
        first = run("apply_le_cleanup.py", "--panel", str(panel), home=self.home)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertRegex(first.stdout, r"cleanup\.xml: \d+ edits")
        after_first = panel.read_bytes()
        second = run("apply_le_cleanup.py", "--panel", str(panel), home=self.home)
        self.assertIn(": 0 edits", second.stdout)
        self.assertEqual(after_first, panel.read_bytes())

    def test_digicon_icons_dry_run_writes_nothing(self):
        panel = self.copy("digicon.xml")
        before = panel.read_bytes()
        result = run("add_digicon_le_signal_icons.py", "--dry-run", "--panel", str(panel), home=self.home)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("DRY", result.stdout)
        self.assertEqual(before, panel.read_bytes())

    def test_sml_facing_dry_run_writes_nothing(self):
        panel = self.copy("facing.xml")
        before = panel.read_bytes()
        result = run("apply_le_sml_facing.py", "--dry-run", "--panel", str(panel), home=self.home)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, panel.read_bytes())

    def test_sml_facing_leaves_the_profile_copy_alone_while_jmri_runs(self):
        panel = self.copy("facing.xml")
        pref = self.home / "JMRI_UserFiles" / "tables.xml"
        pref.parent.mkdir(parents=True, exist_ok=True)
        pref.write_bytes(b"profile copy held by the running JMRI")
        before = panel.read_bytes()
        result = run("apply_le_sml_facing.py", "--panel", str(panel), home=self.home, jmri_running="1")
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("not changed", result.stderr)
        self.assertEqual(before, panel.read_bytes(), "panel must stay untouched when the sync is refused")
        self.assertEqual(b"profile copy held by the running JMRI", pref.read_bytes())
        result = run("apply_le_sml_facing.py", "--panel", str(panel), home=self.home)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(panel.read_bytes(), pref.read_bytes())


class AnnotateWritePathTest(unittest.TestCase):
    def test_write_path_completes_on_a_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            module = load("annotate_mqtt_sensors_and_dispatcher")
            module.TABLES = tmp / "tables.xml"
            shutil.copy(TABLES, module.TABLES)
            module.TRAININFO_DIR = tmp / "traininfo"
            home = tmp / "JMRI_UserFiles"
            home.mkdir()
            (home / "tables.xml").write_text("old")
            module.MAC_PROFILE = home
            module.main()
            self.assertEqual(module.TABLES.read_bytes(), (home / "tables.xml").read_bytes())
            self.assertTrue(any((home / "dispatcher" / "traininfo").glob("*.xml")))
            self.assertTrue(any(module.TRAININFO_DIR.glob("*.xml")))


class CommentNodeTest(unittest.TestCase):
    def test_mast_slot_insert_skips_a_comment_inside_a_layoutturnout(self):
        import xml.etree.ElementTree as ET
        throat = load("apply_yard_throat_blocks")
        to = ET.fromstring("<layoutturnout ident='T1'><!--note--><sensorA>x</sensorA></layoutturnout>")
        # ET.fromstring drops comments; build the node by hand as hartlib's loader keeps it.
        to.insert(0, ET.Comment("note"))
        self.assertEqual(1, throat._ensure_turnout_mast(to, "signalAMast", "Mast 1"))
        tags = [c.tag for c in to if isinstance(c.tag, str)]
        self.assertEqual(["signalAMast", "sensorA"], tags)


class AuditTest(unittest.TestCase):
    def test_panel_contract_audit_passes_on_the_repo_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run("audit_panel_contracts.py", home=Path(tmp))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("RESULT: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
