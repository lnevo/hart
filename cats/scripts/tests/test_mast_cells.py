"""Each mast sits in one CATS desk cell, and the desk builder and the USS board agree on it.

wire_digicon.py names the SECSIGNAL in that cell; gen_ctc_track_plan.py draws the
USS signal icon from the same cell. A mast moved in one and not the other used to
pass every check until the boards were compared by eye.
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
from check_layout_facts import desk_signals  # noqa: E402

DESKS = (ROOT / "cats/panels/HART_CTC.xml", ROOT / "cats/panels/HART_ABS.xml")


class MastCellsTest(unittest.TestCase):
    def test_desk_builder_and_uss_board_use_the_same_cell(self) -> None:
        named = {mast: (x, y) for (x, y, _edge), mast in wire.SIGNAL_NAMES.items()}
        drawn = {mast: (x, y) for mast, x, y, *_rest in gen.SIGNALS}
        self.assertEqual(named, drawn)

    def test_each_desk_names_exactly_these_signals_on_these_edges(self) -> None:
        for desk in DESKS:
            with self.subTest(desk=desk.name):
                self.assertEqual(desk_signals(desk), wire.SIGNAL_NAMES)

    def test_mast_32r_lamp_sits_below_right_of_switch_31(self) -> None:
        for desk in DESKS:
            sec = ET.parse(desk).getroot().find("TRACKPLAN/SECTION[@X='42'][@Y='7']")
            pan = sec.find("SEC_EDGE[@EDGE='BOTTOM']/SECSIGNAL/PANELSIGNAL")
            with self.subTest(desk=desk.name):
                self.assertEqual((pan.get("SIGLOCATION"), pan.get("SIGORIENT")), ("LOWRIGHT", "TOP"))


if __name__ == "__main__":
    unittest.main()
