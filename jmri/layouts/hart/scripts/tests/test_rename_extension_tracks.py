"""rename_extension_tracks.py: old East/West Main Ext names in speed-match logs become East/West Ext."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "jmri/layouts/hart/scripts/speedmatch"))
import rename_extension_tracks as ren  # noqa: E402

OLD_LOG = (
    "1000.000 RUN loco=2121 direction=forward\n"
    'LENGTHS {"BS East Main Ext": 1000, "BS Switch 7b": 200}\n'
    "MEASURE 8 from=BS_East_Main_Ext\n"
    "BLOCK 8 block=BS_West_Main_Ext mm=1 dt=2\n"
    "SENS BS West Main Ext ACTIVE\n"
    "row,Track East Main Ext,Main East Bypass\n"
)


class RenameTest(unittest.TestCase):
    def test_every_form_keeps_its_style(self):
        new, n = ren.rename(OLD_LOG)
        self.assertEqual(n, 5)
        self.assertNotIn("Main_Ext", new)
        self.assertNotIn("Main Ext", new)
        self.assertIn("MEASURE 8 from=BS_East_Ext", new)
        self.assertIn("block=BS_West_Ext mm=1", new)
        self.assertIn('"BS East Ext": 1000', new)
        self.assertIn("row,Track East Ext,Main East Bypass", new)

    def test_other_names_are_left_alone(self):
        text = "BS Main East, Track Main West, East Lead, Track East Lead\n"
        self.assertEqual(ren.rename(text), (text, 0))

    def test_dry_run_changes_nothing_and_apply_does(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "steprun_a.log"
            p.write_text(OLD_LOG, encoding="utf-8")
            self.assertEqual(ren.convert_file(p), 5)
            self.assertEqual(p.read_text(encoding="utf-8"), OLD_LOG)
            self.assertEqual(ren.convert_file(p, apply=True), 5)
            self.assertNotIn("Main Ext", p.read_text(encoding="utf-8"))
            self.assertEqual(ren.convert_file(p, apply=True), 0)

    def test_main_defaults_to_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "block_events.csv"
            p.write_text("CSX 2121,a.log,1,1,East Main Ext,2235.2\n", encoding="utf-8")
            ren.main([str(p)])
            self.assertIn("East Main Ext", p.read_text(encoding="utf-8"))
            ren.main(["--apply", str(p)])
            self.assertEqual(p.read_text(encoding="utf-8"), "CSX 2121,a.log,1,1,East Ext,2235.2\n")

    def test_binary_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.bin"
            p.write_bytes(b"\xff\xfe East Main Ext \x80")
            self.assertEqual(ren.convert_file(p, apply=True), 0)


if __name__ == "__main__":
    unittest.main()
