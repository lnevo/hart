"""The CPython scripts moved onto hartlib: paths, tables.xml reads and a clean save failure.

Proves what the move relied on: each script finds this checkout's files through
hartlib.paths, reads tables.xml through hartlib.tables (comments inside the file do not
break it), and a refused ``doc.save`` (JMRI open) is a clean exit, not a traceback.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[3]
TABLES = REPO / "jmri/layouts/hart/output/tables.xml"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod  # dataclasses look their module up here
    spec.loader.exec_module(mod)
    return mod


MINI = """<?xml version="1.0" encoding="UTF-8"?>
<layout-config>
  <!-- a comment the old ElementTree parse would have dropped -->
  <transits>
    <transit systemName="IZ:AUTO:0001" userName="Run via OS Switch 7"/>
    <!-- another -->
    <transit systemName="IZ:AUTO:0002" userName="Run via OS Switch 9"/>
  </transits>
  <layoutblocks blockrouting="yes"/>
  <LayoutEditor name="HART Railroad"/>
</layout-config>
"""


class PathsTest(unittest.TestCase):
    def test_every_moved_script_points_at_this_checkout(self):
        for name, attrs in {
            "cleanup_uss_ctc_leftovers": {"ROOT": REPO, "TABLES": [TABLES]},
            "disable_digicon_sml_in_tables": {
                "ROOT": REPO, "NEW_TABLES": TABLES,
                "WIRING": REPO / "docs/wiring/signals/signal_wiring.csv"},
            "polish_hart_layout_editor": {"ROOT": REPO, "DEFAULT_PANEL": TABLES},
            "reconcile_dispatcher_stations": {
                "ROOT": REPO, "DEFAULT_PANEL": TABLES, "SYNC_PANEL": TABLES},
            "refresh_bean_comments": {
                "ROOT": REPO, "TABLES": TABLES,
                "PUBLIC_NAME_MAP": REPO / "jmri/layouts/hart/data/public_name_map.csv"},
            "sync_public_name_map": {
                "ROOT": REPO, "TABLES": TABLES,
                "CSV_PATH": REPO / "jmri/layouts/hart/data/public_name_map.csv"},
            "layout_facts": {"DATA": REPO / "jmri/layouts/hart/data"},
        }.items():
            mod = load(name)
            for attr, want in attrs.items():
                with self.subTest(script=name, attr=attr):
                    self.assertEqual(want, getattr(mod, attr))

    def test_retarget_default_dirs_and_tables(self):
        mod = load("retarget_dispatcher_traininfo_transits")
        self.assertEqual(SCRIPTS.parent / "dispatcher/traininfo", mod.DEFAULT_DIRS[1])
        self.assertEqual(TABLES, mod.DEFAULT_TABLES[1])


class ReadsThroughHartlibTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mini = Path(self.tmp.name) / "tables.xml"
        self.mini.write_text(MINI, encoding="utf-8")

    def test_retarget_reads_transit_names_past_comments(self):
        mod = load("retarget_dispatcher_traininfo_transits")
        self.assertEqual({"Run via OS Switch 7", "Run via OS Switch 9"},
                         mod.live_transit_names(self.mini))
        self.assertEqual("Run via OS Switch 7", mod.rewrite_name("Run via Track 7"))

    def test_sync_public_name_map_live_names_come_from_the_beans(self):
        mod = load("sync_public_name_map")
        path = Path(self.tmp.name) / "beans.xml"
        path.write_text(
            "<layout-config><!-- c --><turnouts><turnout><systemName>MT1</systemName>"
            "<userName>Switch 1</userName></turnout></turnouts></layout-config>",
            encoding="utf-8")
        self.assertEqual({"MT1": "Switch 1"}, mod.live_usernames_by_system(path))

    def test_cleanup_drops_only_the_listed_leftovers(self):
        mod = load("cleanup_uss_ctc_leftovers")
        gone = sorted(mod.DELETE_SYSTEM_NAMES)[0]
        text = (f"  <sensors>\n    <sensor><systemName>{gone}</systemName></sensor>\n"
                "    <sensor><systemName>MTT1</systemName></sensor>\n  </sensors>\n")
        out, n = mod.delete_orphans(text)
        self.assertEqual(1, n)
        self.assertNotIn(gone, out)
        self.assertIn("MTT1", out)


class SaveFailureTest(unittest.TestCase):
    def test_jmri_open_is_a_clean_failure_not_a_traceback(self):
        polish = load("polish_hart_layout_editor")
        with tempfile.TemporaryDirectory() as tmp:
            panel = Path(tmp) / "tables.xml"
            panel.write_text(TABLES.read_text(encoding="utf-8"), encoding="utf-8")
            with mock.patch.object(polish.tables.Tables, "save",
                                   side_effect=RuntimeError("PanelPro or CATS is open")), \
                    mock.patch.object(polish, "apply_visual_standard",
                                      side_effect=RuntimeError("PanelPro or CATS is open")), \
                    mock.patch("sys.argv", ["polish", "--panel", str(panel)]):
                self.assertEqual(1, polish.main())


if __name__ == "__main__":
    unittest.main()
