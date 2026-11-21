"""Each visible staging mast (schematic/masts.csv, placed by rule per ADR-024) is on the live CATS desks once,
its lamp on the edge of the block it protects."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "jmri/layouts/hart/scripts"))
sys.path.insert(0, str(ROOT / "tools/audit"))

import check_layout_facts as facts_check  # noqa: E402
import desks  # noqa: E402  (cats/scripts/tests/desks.py: the live desks)


class MastCellsTest(unittest.TestCase):
    def test_each_live_desk_has_each_mast_once_on_the_block_it_protects(self) -> None:
        # staging's visible masts (virtual ones have no lamp); the main and upper masts (masts.csv) are
        # check_layout_facts' check_level_desk
        want = {m["mast"] for m in facts_check.staging_mast_rows() if not m["system_name"].startswith("IF$vsm:")}
        protects = facts_check.protected_blocks()
        level = facts_check.level_masts.names((2, 3))
        self.assertFalse(want & level)
        for desk in desks.LIVE:
            with self.subTest(desk=desk.name):
                have = {m: lamps for m, lamps in facts_check.desk_mast_blocks(desk).items() if m not in level}
                self.assertEqual(set(have), want)
                self.assertEqual({m: lamps for m, lamps in have.items()}, {m: [protects[m]] for m in want})

    def test_mast_32r_lamp_guards_switch_31(self) -> None:
        for desk in desks.LIVE:
            with self.subTest(desk=desk.name):
                self.assertEqual(facts_check.desk_mast_blocks(desk)["Mast 32R"], ["OS Switch 31"])


if __name__ == "__main__":
    unittest.main()
