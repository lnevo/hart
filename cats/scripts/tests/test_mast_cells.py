"""Each mast is on the live CATS desks once, its lamp on the edge of the block it protects, and the hand-wired desk
builder's cells (wire_digicon.py, retired) and the USS board (gen_ctc_track_plan.py, whose grid is that desk's)
agree on each mast's cell. A mast moved in one and not the other used to pass every check until the boards were
compared by eye.
"""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "jmri/layouts/hart/scripts"))
sys.path.insert(0, str(ROOT / "tools/audit"))

import wire_digicon as wire  # noqa: E402
import gen_ctc_track_plan as gen  # noqa: E402
import check_layout_facts as facts_check  # noqa: E402
import desks  # noqa: E402  (cats/scripts/tests/desks.py: the live desks)



class MastCellsTest(unittest.TestCase):
    def test_desk_builder_and_uss_board_use_the_same_cell(self) -> None:
        named = {mast: (x, y) for (x, y, _edge), mast in wire.SIGNAL_NAMES.items()}
        drawn = {mast: (x, y) for mast, x, y, *_rest in gen.SIGNALS}
        self.assertEqual(named, drawn)

    def test_each_live_desk_has_each_mast_once_on_the_block_it_protects(self) -> None:
        want = {mast for mast, *_rest in gen.SIGNALS}
        protects = facts_check.protected_blocks()
        for desk in desks.LIVE:
            with self.subTest(desk=desk.name):
                have = facts_check.desk_mast_blocks(desk)
                self.assertEqual(set(have), want)
                self.assertEqual({m: lamps for m, lamps in have.items()}, {m: [protects[m]] for m in want})

    def test_mast_32r_lamp_guards_switch_31(self) -> None:
        for desk in desks.LIVE:
            with self.subTest(desk=desk.name):
                self.assertEqual(facts_check.desk_mast_blocks(desk)["Mast 32R"], ["OS Switch 31"])

if __name__ == "__main__":
    unittest.main()
