"""build_cats_layout_index.py joins desk masts and switch cells to the layout index by name or OS block, and stops
with CatsIndexError when one has no device there instead of guessing a name."""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_cats_layout_index as cats_index  # noqa: E402
import build_layout_index as le_index  # noqa: E402


def device(kind: str, public: str, block: str = "", comment: str = "") -> le_index.Item:
    return le_index.item(f"id-{public}", kind, None, f"sys {public}", public, "Brick", "M2T1", "topic", comment, block)


def signal(name: str, loc: str | None) -> ET.Element:
    panel = "" if loc is None else f'<PANELSIGNAL SIGLOCATION="{loc}" />'
    return ET.fromstring(f"<SECSIGNAL>{name}{panel}</SECSIGNAL>")


class JoinKeysTest(unittest.TestCase):
    def test_items_are_found_by_names_and_os_block_only(self) -> None:
        it = device("turnout", "Switch 9", block="OS Switch 9")
        by = cats_index.le_by_keys([it])
        self.assertEqual(sorted(by), ["m2t1", "switch 9", "sys switch 9"])

    def test_the_first_item_to_use_a_name_keeps_it(self) -> None:
        os_block = device("occupancy", "OS Switch 9", block="OS Switch 9")
        turnout = device("turnout", "Switch 9", block="OS Switch 9")
        self.assertIs(cats_index.le_by_keys([os_block, turnout])["switch 9"], os_block)

    def test_a_layout_index_item_without_every_field_stops_the_build(self) -> None:
        with self.assertRaisesRegex(cats_index.CatsIndexError, "lacks block, comment"):
            cats_index.le_items({"items": [{k: v for k, v in device("signal", "Mast 1").items()
                                            if k not in ("block", "comment")}]})
        with self.assertRaisesRegex(cats_index.CatsIndexError, "not an object"):
            cats_index.le_items({"items": ["Mast 1"]})


class MatchTurnoutTest(unittest.TestCase):
    def test_a_corner_block_names_its_crossovers_turnout_not_the_block(self) -> None:
        turnout = device("turnout", "Switch 225")
        by = {"switch 225": turnout, "switch 225b": device("occupancy", "OS Switch 225b")}
        self.assertIs(cats_index.match_turnout(by, {"OS Switch 225b"}), turnout)
        self.assertIs(cats_index.match_turnout(by, {"OS Switch 225"}), turnout)

    def test_a_block_that_names_no_turnout_matches_nothing(self) -> None:
        by = {"switch 9": device("occupancy", "OS Switch 9")}
        self.assertIsNone(cats_index.match_turnout(by, {"OS Switch 9"}))


class PlantTest(unittest.TestCase):
    """A points cell's hotspot: its own OS block, else the OS around it; never a made-up name."""

    by = {"switch 9": device("turnout", "Switch 9", block="OS Switch 9")}

    def test_a_points_cell_takes_its_turnouts_fields(self) -> None:
        it = cats_index.plant_item((1, 2), (60.0, 90.0), {"OS Switch 9"}, {}, self.by)
        self.assertEqual((it["publicName"], it["block"], it["cp"], it["x"], it["y"]),
                         ("Switch 9", "OS Switch 9", "Brick", 90.0, 120.0))
        self.assertEqual(it["comment"], "Digicon plant @ 1,2; OS OS Switch 9")

    def test_the_turnouts_own_comment_wins(self) -> None:
        by = {"switch 9": device("turnout", "Switch 9", comment="DCC: 9")}
        self.assertEqual(cats_index.plant_item((1, 2), (0.0, 0.0), {"OS Switch 9"}, {}, by)["comment"], "DCC: 9")

    def test_a_bare_points_cell_takes_the_os_around_it(self) -> None:
        near = {(4, 3): ["OS Switch 9"], (6, 3): ["OS Switch 9"], (5, 2): ["OS Switch 8"]}
        it = cats_index.plant_item((5, 3), (0.0, 0.0), set(), near, self.by)
        self.assertEqual(it["publicName"], "Switch 9")
        self.assertEqual(it["comment"], "Digicon plant @ 5,3; OS OS Switch 9")

    def test_a_bare_points_cell_with_no_os_around_it_stops(self) -> None:
        with self.assertRaisesRegex(cats_index.CatsIndexError, "at 1,2 has no OS block, nor do the cells"):
            cats_index.plant_item((1, 2), (0.0, 0.0), set(), {}, self.by)

    def test_a_tie_between_two_surrounding_blocks_stops(self) -> None:
        near = {(4, 3): ["OS Switch 9"], (6, 3): ["OS Switch 8"]}
        with self.assertRaisesRegex(cats_index.CatsIndexError, "OS Switch 9 and OS Switch 8 as often"):
            cats_index.plant_item((5, 3), (0.0, 0.0), set(), near, self.by)

    def test_a_block_that_names_no_turnout_stops(self) -> None:
        with self.assertRaisesRegex(cats_index.CatsIndexError, r"at 1,2 \(OS OS Switch 7\) names no turnout"):
            cats_index.plant_item((1, 2), (0.0, 0.0), {"OS Switch 7"}, {}, self.by)


class SignalTest(unittest.TestCase):
    by = {"mast 12l": device("signal", "Mast 12L", block="OS Switch 11")}

    def test_a_mast_is_placed_by_its_siglocation(self) -> None:
        it = cats_index.signal_item(signal("Mast 12L", "UPLEFT"), "Mast 12L", (0, 0), (0.0, 0.0), self.by)
        fx, fy = cats_index.SIG_LOC["UPLEFT"]
        self.assertEqual((it["x"], it["y"]), (round(fx * cats_index.CELL, 1), round(fy * cats_index.CELL, 1)))
        self.assertEqual((it["id"], it["publicName"], it["block"]), ("cats-sig-Mast-12L", "Mast 12L", "OS Switch 11"))
        self.assertEqual(it["comment"], "Digicon SECSIGNAL @ cell (0,0) UPLEFT")

    def test_leftcent_is_placed_at_the_left_middle_of_its_cell(self) -> None:
        it = cats_index.signal_item(signal("Mast 12L", "LEFTCENT"), "Mast 12L", (0, 0), (0.0, 0.0), self.by)
        self.assertEqual((it["x"], it["y"]), (10.8, 30.0))
        self.assertTrue(it["comment"].endswith(" LEFTCENT"))

    def test_the_desks_leftcent_masts_sit_at_their_leftcent_place(self) -> None:
        # Mast 68 and Mast B92 are the desk's LEFTCENT masts: 0.18 of a cell from its left edge, at its middle height
        items = {it["publicName"]: it for it in cats_index.build()["items"] if it["kind"] == "signal"}
        self.assertEqual((items["Mast 68"]["x"], items["Mast 68"]["y"]), (3730.8, 300.0))
        self.assertEqual((items["Mast B92"]["x"], items["Mast B92"]["y"]), (3670.8, 1500.0))

    def test_another_location_sig_loc_lacks_stops(self) -> None:
        with self.assertRaisesRegex(cats_index.CatsIndexError, "SIGLOCATION RIGHTCENT, which SIG_LOC does not"):
            cats_index.signal_item(signal("Mast 12L", "RIGHTCENT"), "Mast 12L", (0, 0), (0.0, 0.0), self.by)

    def test_a_mast_with_no_siglocation_stops(self) -> None:
        with self.assertRaisesRegex(cats_index.CatsIndexError, "Mast 12L has no PANELSIGNAL SIGLOCATION"):
            cats_index.signal_item(signal("Mast 12L", None), "Mast 12L", (0, 0), (0.0, 0.0), self.by)

    def test_a_mast_the_layout_index_lacks_stops(self) -> None:
        # no bare-number guess: "12L" alone is not looked up as Mast 12L
        by = {"12l": device("signal", "Mast 12L")}
        with self.assertRaisesRegex(cats_index.CatsIndexError, "Mast 12L at cell 3,4 is not a device"):
            cats_index.signal_item(signal("Mast 12L", "UPLEFT"), "Mast 12L", (3, 4), (0.0, 0.0), by)


class DeskTest(unittest.TestCase):
    def test_a_section_without_whole_number_coordinates_stops(self) -> None:
        with self.assertRaisesRegex(cats_index.CatsIndexError, "X='a' Y=None"):
            cats_index.cell_of(ET.fromstring('<SECTION X="a" />'))

    def test_sections_that_share_a_cell_pool_their_blocks(self) -> None:
        sections = [ET.fromstring(f'<SECTION X="1" Y="2"><SEC_EDGE><BLOCK NAME="{n}" /></SEC_EDGE></SECTION>')
                    for n in ("OS Switch 1", "OS Switch 2")]
        sections.append(ET.fromstring('<SECTION X="3" Y="2"><SEC_EDGE /></SECTION>'))
        self.assertEqual({(1, 2): ["OS Switch 1", "OS Switch 2"]}, cats_index.blocks_by_cell(sections))

    def test_an_override_for_a_mast_the_desk_does_not_draw_stops(self) -> None:
        sections = [ET.fromstring('<SECTION X="0" Y="0"><SEC_EDGE /></SECTION>')]
        with self.assertRaisesRegex(cats_index.CatsIndexError, "HOTSPOT_OVERRIDE moves mast 32r"):
            cats_index.section_items(sections, {})

    def test_every_desk_mast_and_switch_cell_joins(self) -> None:
        # the real desk: a miss raises, so a clean build means every hotspot found its device
        items = cats_index.build()["items"]
        self.assertEqual({it["kind"] for it in items}, {"turnout", "signal"})
        self.assertTrue(all(it["publicName"] and it["systemName"] for it in items))


if __name__ == "__main__":
    unittest.main()
