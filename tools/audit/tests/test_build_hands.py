"""build_hands.py: switches.csv holds the current plan hands (not the drawn ones), and only plan rows are rewritten;
staging rows, which give IDs only, are left as they are."""
from __future__ import annotations

import csv
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_hands", ROOT / "tools/schematic/build_hands.py")
BH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BH)

# Drawn hands on REV 5 (archive/history/wiki/projects/schematic-maps-handoff.md), in the numbers of 2026-11-19 (121 and 125 crossovers)
DRAWN_R = "101A 101B 105 107 115 119A 119B 121B 125A 129 131A 131B 211A 211B 221A 221B 223 227 233 231 235 241".split()
DRAWN_L = ("103A 103B 109 111 113 117 121A 123 127A 125B 127B 201 203 205 209 207 213 215 217A 217B 219 229 237 "
           "243A 243B 239 245A 245B").split()
FLIPPED = "101A 101B 103A 103B 105 107 109 111".split()


def hands():
    """{half: hand} of the main and upper rows of switches.csv that give a hand."""
    with BH.OUT.open() as f:
        return {r["half"]: r["hand"] for r in csv.DictReader(f) if r["level"] in ("2", "3") and r["hand"]}


class BuildHands(unittest.TestCase):
    def test_unknown_argument_is_refused(self):
        self.assertEqual(BH.main(["--chek"]), 2)

    def test_flipped_are_opposite_drawn_rest_equal(self):
        h = hands()
        for s in DRAWN_R + DRAWN_L:
            drawn = "R" if s in DRAWN_R else "L"
            opposite = "L" if drawn == "R" else "R"
            self.assertEqual(h[s], opposite if s in FLIPPED else drawn, s)

    def test_t300_is_223_right(self):
        self.assertEqual(hands()["223"], "R")

    def test_double_crossover_has_no_hand(self):
        self.assertNotIn("225", hands())
        self.assertEqual(len(hands()), len(DRAWN_R) + len(DRAWN_L))

    def test_the_committed_file_is_current(self):
        self.assertEqual(BH.main(["--check"]), 0)


HEADER = ",".join(BH.railroad.SWITCH_COLUMNS) + "\n"
# a staging row gives its OS block and legs by device ID only (os_id, closed_id, thrown_id); their names are the name
# store's, which the reader looks up (railroad.read_switch_rows)
STAGING = "1,1,,os:1,os:3,block:1C-5A#1+1C-5A#2,L,owner,,TO1,no,3,yes,\n"


class PlanAndOwnerRows(unittest.TestCase):
    """build_hands.py rewrites the hand of a plan row only: an owner row, a staging row and every other cell stay as
    they are, byte for byte."""

    def apply(self, body, plan):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "switches.csv"
            p.write_text(HEADER + STAGING + body, encoding="utf-8")
            return BH.apply(p, plan)

    def test_a_plan_row_takes_the_plan_hand_and_an_owner_row_keeps_its_own(self):
        body = ("2,101,101A,,,,L,plan,Peninsula,,,,,Yard throat crossover\n"
                "2,101,101B,,,,L,owner,,,,,,\n"
                "2,105,105,,,,R,plan,West,,,,,\"Yard ladder, west\"\n")
        got = self.apply(body, {"101A": "R", "101B": "R", "105": "R"})
        self.assertEqual(got, HEADER + STAGING + "2,101,101A,,,,R,plan,Peninsula,,,,,Yard throat crossover\n"
                         "2,101,101B,,,,L,owner,,,,,,\n"
                         "2,105,105,,,,R,plan,West,,,,,\"Yard ladder, west\"\n")

    def test_a_file_already_current_comes_back_byte_for_byte(self):
        body = "2,105,105,,,,R,plan,West,,,,,\"Yard ladder\"\n"      # quoting the writer would not use is kept
        self.assertEqual(self.apply(body, {"105": "R"}), HEADER + STAGING + body)

    def test_a_new_plan_row_with_no_hand_is_filled(self):
        """The way to add a plan switch, as the no-row message says: a row with hand_source plan and the hand blank."""
        body = "2,105,105,,,,R,plan,West,,,,,\n3,247,247,,,,,plan,Helix,,,,,\n"
        self.assertEqual(self.apply(body, {"105": "R", "247": "L"}),
                         HEADER + STAGING + "2,105,105,,,,R,plan,West,,,,,\n3,247,247,,,,L,plan,Helix,,,,,\n")

    def test_cells_are_compared_as_the_reader_strips_them(self):
        body = "2,105,105 ,,,, L ,plan,West,,,,,\n"
        self.assertEqual(self.apply(body, {"105": "R"}), HEADER + STAGING + "2,105,105 ,,,,R,plan,West,,,,,\n")

    def test_a_plan_label_with_no_row_stops(self):
        with self.assertRaisesRegex(BH.HandsError, "plan switch 107 has no row; add one"):
            self.apply("2,105,105,,,,R,plan,West,,,,,\n", {"105": "R", "107": "L"})

    def test_a_plan_row_the_plan_has_no_hand_for_stops(self):
        with self.assertRaisesRegex(BH.HandsError, r"line 3 \(105\): hand_source plan, but the plan has no hand"):
            self.apply("2,105,105,,,,R,plan,West,,,,,\n", {})

    def test_a_plan_label_on_a_row_with_no_hand_source_stops(self):
        with self.assertRaisesRegex(BH.HandsError, r"line 3 \(105\): the plan has a hand for it \(R\); set hand_source"):
            self.apply("2,105,105,,,,,,West,,,,,\n", {"105": "R"})

    def test_a_staging_row_is_left_as_it_is(self):
        """naming-layers step 5: a staging row holds IDs only, so a renamed device changes no cell of it; the read
        checks the IDs against the name store given (or the repo's)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "switches.csv"
            p.write_text(HEADER + STAGING, encoding="utf-8")
            self.assertEqual(BH.apply(p, {}), HEADER + STAGING)              # the repo's name store
            names = {("1", "os:1"): "OS Switch 1", ("1", "os:3"): "OS Brick West",
                     ("1", "block:1C-5A#1+1C-5A#2"): "Track Brick"}
            self.assertEqual(BH.apply(p, {}, names), HEADER + STAGING)

    def test_a_staging_id_the_device_master_does_not_have_stops(self):
        with self.assertRaisesRegex(BH.HandsError, r"line 2 \(Switch 1\): thrown_id block:9Z-end is no level 1 device"):
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "switches.csv"
                p.write_text(HEADER + STAGING.replace("block:1C-5A#1+1C-5A#2", "block:9Z-end"), encoding="utf-8")
                BH.apply(p, {})

    def test_a_row_the_reader_refuses_stops_with_its_line(self):
        with self.assertRaisesRegex(BH.HandsError, r"switches.csv line 3 \(Switch 105\): a hand needs a hand_source"):
            self.apply("2,105,105,,,,R,,West,,,,,\n", {"105": "R"})


class Refusals(unittest.TestCase):
    """Edits or graph values it cannot vouch for stop the build instead of writing a quietly wrong file."""

    def build_with(self, change):
        import json
        import tempfile
        from hartlib import layer_files
        whole = layer_files.read_file("plan_overrides", BH.OVERRIDES.parent)
        change(whole["main_upper"])
        with tempfile.TemporaryDirectory() as tmp:
            copy = layer_files.path("plan_overrides", Path(tmp))
            copy.write_text(json.dumps(whole))
            saved, BH.OVERRIDES = BH.OVERRIDES, copy
            try:
                with self.assertRaises(BH.HandsError):
                    BH.build()
            finally:
                BH.OVERRIDES = saved

    def test_an_edit_it_does_not_read(self):
        self.build_with(lambda d: d["edits"].append({"op": "remove", "switches": ["T1"]}))

    def test_a_relabel_key_with_no_plan_switch(self):
        self.build_with(lambda d: d["edits"][0]["map"].update({"T99999": "999"}))

    def test_a_move_edit_is_not_read(self):
        # the plan 5.3c holds every hand, so the 5.3b `move` hand override is gone and an edit like it fails loudly
        self.build_with(lambda d: d["edits"].append({"op": "move", "switch": "T300", "hand": "R"}))


class MainExit(unittest.TestCase):
    def test_main_exits_with_the_hands_error(self):
        from unittest import mock
        with mock.patch.object(BH, "build", side_effect=BH.HandsError("build_hands.py: bad row")), \
                self.assertRaises(SystemExit) as stop:
            BH.main(["--check"])
        self.assertEqual(stop.exception.code, "build_hands.py: bad row")


if __name__ == "__main__":
    unittest.main()
