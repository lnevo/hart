"""build_hands.py: hands.csv is current and holds the plan hands, not the drawn ones."""
from __future__ import annotations

import csv
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_hands", ROOT / "tools/schematic/build_hands.py")
BH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BH)

# Drawn hands on REV 5 (wiki/projects/schematic-maps-handoff.md), in the numbers of 2026-11-19 (121 and 125 crossovers)
DRAWN_R = "101A 101B 105 107 115 119A 119B 121B 125A 129 131A 131B 211A 211B 221A 221B 223 227 233 231 235 241".split()
DRAWN_L = ("103A 103B 109 111 113 117 121A 123 127A 125B 127B 201 203 205 209 207 213 215 217A 217B 219 229 237 "
           "243A 243B 239 245A 245B").split()
FLIPPED = "101A 101B 103A 103B 105 107 109 111".split()


def hands():
    with BH.OUT.open() as f:
        return {r["switch"]: r["hand"] for r in csv.DictReader(f)}


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


class Refusals(unittest.TestCase):
    """Edits or graph values it cannot vouch for stop the build instead of writing a quietly wrong file."""

    def build_with(self, change):
        import json
        import tempfile
        d = json.loads(BH.OVERRIDES.read_text())
        change(d)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(d, f)
        saved, BH.OVERRIDES = BH.OVERRIDES, Path(f.name)
        try:
            with self.assertRaises(SystemExit):
                BH.build()
        finally:
            BH.OVERRIDES = saved
            Path(f.name).unlink()

    def test_an_edit_it_does_not_read(self):
        self.build_with(lambda d: d["edits"].append({"op": "remove", "switches": ["T1"]}))

    def test_a_relabel_key_with_no_plan_switch(self):
        self.build_with(lambda d: d["edits"][0]["map"].update({"T99999": "999"}))

    def test_a_move_edit_naming_no_plan_switch(self):
        self.build_with(lambda d: d["edits"].append({"op": "move", "switch": "223", "hand": "R"}))   # no move since 5.3c


if __name__ == "__main__":
    unittest.main()
