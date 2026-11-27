"""block_pieces.py: the OS block a link joins (at its lower-numbered switch, or across from a home mast facing it)
and the pieces of a track block_overrides.csv gives to OS blocks, with every stop, on tracks made here (no drawing,
no plugin)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))

import block_pieces as BP  # noqa: E402
from plan_tracks import Track  # noqa: E402


def track(a: str, b: str, cm: float, **more: Any) -> Track:
    """A track from switch `a` (node na, leg A) to switch `b` (node nb, leg B), one strand."""
    t = {"name": f"Track {a}-{b}", "ends": (("sw", a), ("sw", b)), "legs": [("n" + a, "A"), ("n" + b, "B")],
         "cm": cm, "strands": ["s1"], "level": 2, **more}
    return cast(Track, t)


class Links(unittest.TestCase):
    def test_a_link_is_short_and_between_two_switches(self) -> None:
        self.assertTrue(BP.is_link(track("1", "3", BP.LINK_CM - 0.1)))
        self.assertFalse(BP.is_link(track("1", "3", BP.LINK_CM)))
        self.assertFalse(BP.is_link(track("1", "1", 10.0)))                 # a loop back to its switch

    def test_the_lower_numbered_switch_s_block_or_the_one_on_the_band(self) -> None:
        self.assertEqual("OS Switch 9", BP.link_block({"10": "OS Switch 10", "9": "OS Switch 9"}))
        self.assertEqual("OS Switch 10", BP.link_block({"10": "OS Switch 10", "9": None}))
        self.assertIsNone(BP.link_block({"9": None}))

    def test_a_home_mast_facing_the_link_sends_it_to_the_other_end(self) -> None:
        bad: list[str] = []
        ends = {"1": "OS Switch 1", "3": "OS Switch 3"}
        block, why = BP.masted_block(track("1", "3", 20.0), ends, {"1": "2L"}, 2, "o.csv", bad)
        self.assertEqual("OS Switch 3", block)
        self.assertIn("Mast 2L stands at Switch 1", why or "")
        self.assertEqual((None, None), BP.masted_block(track("1", "3", 20.0), ends, {"1": "2L", "3": "4R"}, 2,
                                                       "o.csv", bad))
        self.assertIn("a home mast facing it at both ends", bad[0])

    def test_a_double_crossover_end_takes_its_corner_block(self) -> None:
        t = track("5", "7", 30.0)
        nodes = {"n5": {"kind": "dx"}, "n7": {"kind": "switch"}}
        os_ = {"n5": "OS Switch 5", "n7": "OS Switch 7"}
        bad: list[str] = []
        self.assertEqual({"5": "OS 5 A", "7": "OS Switch 7"},
                         BP.end_blocks(t, nodes, os_, {"5": {"A": "OS 5 A"}}, 2, bad))
        self.assertEqual({"5": None, "7": "OS Switch 7"}, BP.end_blocks(t, nodes, os_, {}, 2, bad))
        self.assertIn("double crossover 5 at leg A, which has no corner block", bad[0])


class Pieces(unittest.TestCase):
    ENDS = {"1": "OS Switch 1", "3": "OS Switch 3"}

    def pieces(self, ex: dict[str, BP.OsGift], cm: float = 40.0) -> tuple[list[BP.Piece] | None, list[str]]:
        bad: list[str] = []
        return BP.exception_pieces(track("1", "3", cm), ex, "Track 1-3", self.ENDS, "o.csv", bad), bad

    def test_the_whole_track_is_one_part(self) -> None:
        got, _ = self.pieces({"": ("OS Switch 3", 4, None)})
        self.assertEqual([BP.Piece("Track 1-3", "OS Switch 3", 4, 40.0)], got)

    def test_pieces_at_both_ends_share_the_track(self) -> None:
        got, _ = self.pieces({"1": ("OS Switch 1", 4, None), "3": ("OS Switch 3", 5, None)}, cm=41.0)
        self.assertEqual([BP.Piece("Track 1-3 at 1", "OS Switch 1", 4, 20.5),
                          BP.Piece("Track 1-3 at 3", "OS Switch 3", 5, 20.5)], got)

    def test_a_piece_at_one_end_leaves_the_rest_its_own_block(self) -> None:
        got, _ = self.pieces({"3": ("OS Switch 3", 4, 15.0)})
        self.assertEqual([BP.Piece("Track 1-3", "Track 1-3", 0, 25.0),
                          BP.Piece("Track 1-3 at 3", "OS Switch 3", 4, 15.0)], got)

    def test_each_bad_row_stops_naming_its_line(self) -> None:
        for ex, why in (({"": ("OS Switch 3", 4, 5.0)}, "only a piece at one end takes its length"),
                        ({"": ("OS Switch 9", 4, None)}, "the OS block of neither"),
                        ({"1": ("OS Switch 3", 4, 5.0)}, "not that switch's OS block OS Switch 1"),
                        ({"1": ("OS Switch 1", 4, 5.0), "3": ("OS Switch 3", 5, None)}, "share the track evenly"),
                        ({"1": ("OS Switch 1", 4, None)}, "give its cm"),
                        ({"1": ("OS Switch 1", 4, 40.0)}, "is not under the track's 40")):
            with self.subTest(why=why):
                got, bad = self.pieces(ex)
                self.assertIsNone(got)
                self.assertRegex(bad[0], rf"^o\.csv line 4: .*{why}")


if __name__ == "__main__":
    unittest.main()
