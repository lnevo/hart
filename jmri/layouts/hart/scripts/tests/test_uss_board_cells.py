"""The USS CTC board's grid is committed data (uss_board_cells.csv, uss_board_plants.csv), frozen from the hand-wired
CATS desk on 2026-11-15, so the board builds without a desk (CATS cut-over).

While the hand-wired desk is still in the repo, the frozen grid must be exactly what gen_ctc_track_plan.parse_cats
reads from it, in the same order, and the plant cells exactly wire_digicon's; once the desk is archived those two
tests skip. The loaders refuse a malformed file.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[3]
DESK = ROOT / "cats/panels/HART_CTC.xml"
sys.path.insert(0, str(SCRIPTS))
import layout_facts as facts  # noqa: E402


class FrozenGrid(unittest.TestCase):
    def test_cells_are_the_hand_wired_desks(self):
        if not DESK.is_file():
            self.skipTest("the hand-wired desk is archived")
        import gen_ctc_track_plan as gen
        self.assertEqual(list(facts.load_uss_cells().items()), list(gen.parse_cats(DESK).items()))

    def test_the_board_reads_the_frozen_plants(self):
        import gen_ctc_track_plan as gen
        self.assertEqual(list(gen.PLANT_CELLS.items()), list(facts.load_uss_plants().items()))
        self.assertEqual(len(gen.PLANT_CELLS), 23)
        self.assertEqual(next(iter(gen.PLANT_CELLS.items())), ((4, 8), "OS Switch 1"))   # the drawing order


class Malformed(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data)
        for name in (facts.USS_CELLS, facts.USS_PLANTS):
            shutil.copyfile(facts.DATA / name, self.data / name)

    def edit(self, name, old, new):
        p = self.data / name
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text)
        p.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_a_missing_note_line_stops(self):
        p = self.data / facts.USS_CELLS
        p.write_text(p.read_text(encoding="utf-8").split("\n", 1)[1], encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "the note line"):
            facts.load_uss_cells(self.data)

    def test_a_bad_track_or_block_stops(self):
        self.edit(facts.USS_CELLS, "HORIZONTAL", "SIDEWAYS")
        with self.assertRaisesRegex(ValueError, "tracks are"):
            facts.load_uss_cells(self.data)

    def test_a_plant_on_a_cell_with_no_track_stops(self):
        self.edit(facts.USS_PLANTS, "OS Switch 1,4,8", "OS Switch 1,4,5")      # (4, 5) is the BRICK label
        with self.assertRaisesRegex(ValueError, "no track in cell"):
            facts.load_uss_plants(self.data)

    def test_a_plant_given_twice_stops(self):
        self.edit(facts.USS_PLANTS, "OS Switch 3,", "OS Switch 1,")
        with self.assertRaisesRegex(ValueError, "given twice"):
            facts.load_uss_plants(self.data)


if __name__ == "__main__":
    unittest.main()
