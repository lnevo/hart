"""hartlib.device_ids: the ID grammar (ADR-033), and the committed device master's ids: every row with a level has
one, unique on its level, and no block or mast id carries the device's user name."""
from __future__ import annotations

import re
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import device_ids as I  # noqa: E402
from hartlib import devices as D  # noqa: E402


class TheGrammar(unittest.TestCase):
    def test_switch_alias_and_feedback(self):
        self.assertEqual((I.switch_id("101"), I.dcc_id(101), I.fb_id("7", "R")), ("switch:101", "dcc:101", "fb:7:R"))
        for bad in (lambda: I.switch_id("101A"), lambda: I.fb_id("7", "X")):
            with self.assertRaises(ValueError):
                bad()

    def test_a_block_from_its_strands(self):
        self.assertEqual(I.block_id([I.strand_key("1B-3A", 1, 2)]), "block:1B-3A:1/2")
        self.assertEqual(I.block_id([I.strand_key("107B-107C #1")]), "block:107B-107C#1")
        self.assertEqual(I.block_id([I.strand_key("1C-5A #1"), I.strand_key("1C-5A #2")]), "block:1C-5A#1+1C-5A#2")
        with self.assertRaises(ValueError):
            I.block_id([])

    def test_os_blocks_halves_and_corners(self):
        self.assertEqual((I.os_id("1"), I.os_id("7", "A-13C"), I.os_id("225", "D")),
                         ("os:1", "os:7:A-13C", "os:225:D"))

    def test_detectors_masts_heads_and_lamps(self):
        self.assertEqual(I.det_id("os:7:A-13C"), "det:os:7:A-13C")
        self.assertEqual(I.spare_id("M2S201"), "spare:M2S201")
        home = I.home_mast_id("101A", "B", "east")
        self.assertEqual(home, "mast:101A:B:east")
        self.assertEqual(I.block_mast_id("block:3B-end", "west"), "mast:block:3B-end:west")
        self.assertEqual([I.head_id(home, I.head_place(i, 2)) for i in (0, 1)],
                         ["mast:101A:B:east:top", "mast:101A:B:east:bottom"])
        self.assertEqual(I.head_place(0, 1), "single")
        self.assertEqual(I.panel_id("status", "IH9990"), "panel:status:IH9990")
        for bad in (lambda: I.det_id("Track 5"), lambda: I.home_mast_id("7", "E", "west"),
                    lambda: I.block_mast_id("Track W-1", "west"), lambda: I.head_place(2, 2)):
            with self.assertRaises(ValueError):
                bad()


class TheChecks(unittest.TestCase):
    def test_check_rows_wants_an_id_unique_on_its_level(self):
        from test_devices import blank, problems, turnout
        self.assertIn("id is empty", problems([turnout(id="")]))
        twice = [turnout(id="switch:1"), turnout("Switch 3", system_name="M2T409", jmri_name="M2T409", id="switch:1")]
        self.assertIn("id 'switch:1' is Switch 1 (level 1, turnout)'s as well", problems(twice))
        other = turnout(level="2", system_name="M2T3408", jmri_name="M2T3408", id="switch:1")
        D.check_rows([turnout(id="switch:1"), other])                     # another level may share it
        self.assertIn("id is empty", problems([blank(level="1", layer="block", role="os", user_name="OS Switch 1",
                                                     assignment="none", description="Block.", id="")]))

    def test_a_mast_at_a_block_names_that_blocks_id(self):
        from test_devices import blank, problems
        block = blank(level="1", layer="block", role="track", user_name="Track W-1", assignment="none",
                      description="Block.", id="block:3B-end")
        mast = blank(level="1", layer="mast", role="hidden", user_name="Mast 4LA", assignment="none",
                     description="Mast.", facing="Track W-1", dir="west", id="mast:block:3B-end:west")
        D.check_rows([block, mast])
        self.assertIn("Mast 4LA (level 1, mast): id 'mast:block:9B-end:west' does not name the block it faces, "
                      "Track W-1 (id 'block:3B-end')", problems([block, dict(mast, id="mast:block:9B-end:west")]))

    def test_a_field_row_may_not_hold_an_id(self):
        from test_devices import blank
        row = blank(level="1", layer="turnout", user_name="Switch 1", id="switch:1")
        with self.assertRaisesRegex(D.DevicesError, "id set; a field row holds only"):
            D.check_field([row])


class Committed(unittest.TestCase):
    """The committed master as the builders wrote it."""

    @classmethod
    def setUpClass(cls):
        cls.rows = D.load()

    def test_every_row_with_a_level_has_an_id_unique_on_its_level_and_a_store_row_none(self):
        placed = [r for r in self.rows if r["level"]]
        self.assertFalse([D.key_of(r) for r in placed if not r["id"]])
        twice = [k for k, n in Counter((r["level"], r["id"]) for r in placed).items() if n > 1]
        self.assertEqual(twice, [])
        self.assertFalse([D.key_of(r) for r in self.rows if not r["level"] and r["id"]])

    def test_each_kind_follows_the_grammar(self):
        want = {"turnout": r"switch:\d+", "lcc_alias": r"dcc:\d+", "fb": r"fb:\d+:[NR]",
                "os": r"os:\d+(:A-\d+[A-D])?", "xover_corner": r"os:\d+:(A-\d+[A-D]|[A-D])",
                "home": r"mast:\d+[A-Z]?:[A-D]:(east|west)", "intermediate": r"mast:block:\S+:(east|west)",
                "hidden": r"mast:block:\S+:(east|west)", "spare": r"spare:M2S\d+",
                "panel_status": r"panel:\w+:\S+"}
        for kind in ("track", "spur", "loop_half", "helix", "part"):
            want[kind] = r"block:[^+\s]+(\+[^+\s]+)*"
        bad = []
        for r in self.rows:
            if not r["level"]:
                continue
            if r["layer"] == "occupancy" and r["role"] != "spare":
                ok = re.fullmatch(r"det:(block|os):\S+", r["id"])
            elif r["layer"] == "head" and r["role"] == "head":
                ok = re.fullmatch(r"mast:\S+:(top|bottom|single)", r["id"])
            else:
                ok = re.fullmatch(want[r["role"]], r["id"])
            if not ok:
                bad.append((D.key_of(r), r["role"], r["id"]))
        self.assertEqual(bad, [])

    def test_a_detector_takes_its_blocks_id(self):
        block = {(r["level"], r["user_name"]): r["id"] for r in self.rows if r["layer"] == "block"}
        for r in self.rows:
            if r["layer"] == "occupancy" and r["role"] != "spare":
                with self.subTest(r["user_name"]):
                    self.assertEqual(r["id"], "det:" + block[(r["level"], r["blocks"])])

    def test_no_block_or_mast_id_holds_its_user_name(self):
        """The ID comes from the plan ends, not the name: no name (Track Barn, Track 29-31, Mast 8LA, Head 2L Top)
        is in it. An OS block's name and ID both hold the switch number, so they are left out."""
        bad = []
        for r in self.rows:
            if r["level"] and r["layer"] in ("block", "mast", "head") and r["role"] not in D.OS_ROLES:
                bare = re.sub(r"^(Track|Mast|Head) ", "", r["user_name"])
                if bare in r["id"]:
                    bad.append((r["user_name"], r["id"]))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
