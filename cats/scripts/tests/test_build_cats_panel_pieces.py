"""tools/schematic/build_cats_panel.py: the small helpers the facts, staging, level and dress steps share.

The bigger steps are tested in test_build_cats_panel_bindings.py; these are the functions it leaves alone, so a
move of the code into sibling modules is held to the same behaviour.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_cats_panel as B  # noqa: E402
from test_build_cats_panel_bindings import block, device, facts, node  # noqa: E402


class Facts(unittest.TestCase):
    def test_load_facts_reads_the_repo(self):
        f = B.load_facts()
        self.assertIsInstance(f, B.Facts)
        self.assertIsInstance(f.layout, B.StagingTracks)
        self.assertTrue(f.switches and f.occupancy and f.masts and f.level_masts and f.helix)
        self.assertTrue(f.masts <= set(f.mast_system))

    def test_mast_type_from_the_system_name(self):
        self.assertEqual(B.mast_type("IF$shsm:basic:one-low(IH1)"), "one-low")
        self.assertEqual(B.mast_type("IF$vsm:basic:two-searchlight(IH1)"), "two-searchlight")
        self.assertIsNone(B.mast_type("IF$xyz:basic:one-low"))
        self.assertIsNone(B.mast_type(None))

    def test_device_map_errors_name_the_script(self):
        with self.assertRaisesRegex(SystemExit, "^build_cats_panel.py: "):
            B.load_device_map(ROOT / "no/such/device_map.csv")


class Staging(unittest.TestCase):
    def test_track_block_helix_else_track_name(self):
        self.assertEqual(B.track_block("Yard", {}), "Track Yard")
        self.assertEqual(B.track_block("H1", {"H1": "Track Helix Outer"}), "Track Helix Outer")

    def test_legs_and_switch_lookup(self):
        d = node("1", "T1", {"A": "w"}, {"B": "s12", "C": "y"})
        self.assertEqual(B.legs_of(d), {"A": "w", "B": "s12", "C": "y"})
        self.assertEqual(B.switch_of(facts(), d).number, 1)
        with self.assertRaisesRegex(SystemExit, "not in switches.csv"):
            B.switch_of(facts(), node("77", "", {}, {}))
        with self.assertRaisesRegex(SystemExit, "not in switches.csv"):
            B.switch_of(facts(), node("x", "", {}, {}))


class Levels(unittest.TestCase):
    def test_loop_halves_and_plan_edges(self):
        self.assertEqual(B.loop_half_edge("e33", 1), "e33~1")
        self.assertEqual(B.plan_edge({"edge": "e34x"}), "e34")
        self.assertEqual(B.plan_edge({"edge": "e33~1", "plan_edge": "e33"}), "e33")
        self.assertEqual(B.plan_edge({"edge": "e5"}), "e5")

    def test_placeholder_is_the_strands_trial_key(self):
        """name_loop_halves keys each main and upper strand by switch and leg (staging_device_map.band_refs, one grammar
        for every level); placeholder reads that key and stops on a strand that has none."""
        self.assertEqual(B.placeholder({"edge": "e33", "loop_half": 1, "trial": "Track 107B-107C #1"}),
                         "Track 107B-107C #1")
        with self.assertRaisesRegex(SystemExit, "strand e34y has no trial key"):
            B.placeholder({"edge": "e34y"})

    def test_name_loop_halves_keys_every_main_and_upper_strand(self):
        import build_layout_le as bl
        sheet, _le_mod, _core = bl.plugin()
        bands = B.name_loop_halves(B.pd.solved_sheet(sheet).bands)
        main = next(b for t, b, _o in bands if B.bdm.band_level(t) == 2)
        self.assertEqual({s["trial"] for s in main["strands"].values() if s.get("loop_half")},
                         {"Track 107B-107C #1", "Track 107B-107C #2"})
        self.assertFalse([s for t, b, _o in bands if B.bdm.band_level(t) for s in b["strands"].values()
                          if "trial" not in s])

    def test_xover_corners_only_those_the_device_map_has(self):
        rows = {f"OS Switch 225{c}": block(f"OS Switch 225{c}") for c in "abc"}
        f = facts(device=B.DeviceMap(blocks=rows))
        self.assertEqual(B.xover_corners("OS Switch 225", f), ["OS Switch 225a", "OS Switch 225b", "OS Switch 225c"])
        self.assertEqual(B.xover_corners("OS Switch 9", f), [])

    def test_spec_by_sensor_prefix(self):
        self.assertEqual(B.spec("M2S3300", "BS 1")["occupied"],
                         {"DECADDR": "3300", "JMRIPREFIX": "M2S", "USER_NAME": "BS 1", "command": "close"})
        got = B.spec("IS:HART:C3:B:OS101", "BS Switch 101")
        self.assertEqual((got["occupied"]["JMRIPREFIX"], got["occupied"]["DECADDR"]), ("IS", ":HART:C3:B:OS101"))
        self.assertEqual(got["unoccupied"], {"DECADDR": ":HART:C3:B:OS101", "JMRIPREFIX": "IS", "command": "throw"})
        with self.assertRaisesRegex(SystemExit, "neither M2S nor internal"):
            B.spec("LS5", "x")

    def test_level_bands_skips_the_bound_band(self):
        bands = [("Staging level", {}, {"a": 1}), ("Main level", {}, {"b": 2}), ("Upper level, 4.25 in", {}, {"c": 3})]
        self.assertEqual([bi for bi, _b, _o in B.level_bands(bands, 0)], [1, 2])

    def test_virtual_and_planned_sensors(self):
        f = facts(device=device())
        self.assertEqual(B.virtual_sensor("OS Switch 101", f)["occupied"]["USER_NAME"], "BS Switch 101")
        self.assertIsNone(B.virtual_sensor("OS Switch 999", f))
        self.assertEqual(B.planned_sensor("OS Switch 101", f)["occupied"]["DECADDR"], "3300")
        self.assertIsNone(B.planned_sensor("OS Switch 103", f))


class Dress(unittest.TestCase):
    def test_plate_box_uses_plate_font_sizes_first(self):
        class C:
            TEXT_PX = {"FONT_LABEL": (7, 12)}
            seen = None

            @staticmethod
            def frill_box(cell, loc, w, h):
                C.seen = (cell, loc, w, h)
                return (0, 0, w, h)
        B.plate_box(C, (1, 2), "N", "abcd", "FONT_SUBTITLE")
        self.assertEqual(C.seen, ((1, 2), "N", 9 * 4 + 4, 15))
        B.plate_box(C, (1, 2), "N", "abcd", "FONT_OTHER")
        self.assertEqual(C.seen, ((1, 2), "N", 7 * 4 + 4, 12))

    def test_frozen_header_splits_plate_from_header(self):
        els, plate = B.frozen_header()
        self.assertTrue(all(el.tag != "TRACKPLAN" for el in els))
        self.assertTrue({"SIGNALTEMPLATE", "JMRINAME"} <= {el.tag for el in els})
        self.assertTrue(all(sec.find("SEC_NAME") is not None for sec in plate))

    def test_order_places_every_header_tag(self):
        self.assertEqual(len(set(B.ORDER)), len(B.ORDER))
        els, _plate = B.frozen_header()
        self.assertTrue({el.tag for el in els} <= set(B.ORDER))

    def test_label_clashes_picks_the_two_kinds(self):
        log = ["no room for label X", "label A crosses B", "label C fine", "other"]
        self.assertEqual(B.label_clashes(log), ["no room for label X", "label A crosses B"])


if __name__ == "__main__":
    unittest.main()
