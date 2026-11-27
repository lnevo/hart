"""le_names on small made-up bands and rows (no plugin, no solve): the track runs through turnbacks, the crossover
tracks, the staging and main lengths, the LCOS head rule from signal_coordinator.py's sml_lcos.py and its guard, and
the device-map names put in place of the placeholders."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import le_names  # noqa: E402
from hartlib import coordinator  # noqa: E402
from le_common import BuildError  # noqa: E402


def strand(src, dst, cm=10.0, edge="e"):
    return {"src": src, "dst": dst, "cm": cm, "edge": edge}


# end - switch 101A - (C to C) - switch 101B; 101A's B leg runs through a turnback to an end bumper
BAND = {
    "nodes": {
        "end1": {"kind": "end"}, "end2": {"kind": "end"},
        "sw1": {"kind": "switch", "label": "101A"}, "sw2": {"kind": "switch", "label": "101B"},
        "tb": {"kind": "turnback"},
    },
    "strands": {
        "s1": strand(("end1", "A"), ("sw1", "A")),
        "s2": strand(("sw1", "C"), ("sw2", "C")),
        "s3": strand(("sw1", "B"), ("tb", "A")),
        "s4": strand(("tb", "B"), ("end2", "A")),
    },
}


class Runs(unittest.TestCase):
    def test_a_track_through_a_turnback_is_one_run(self):
        runs = le_names.runs(BAND)
        self.assertIn((("sw1", "B"), [("s3", False), ("s4", False)], ("end2", "A")), runs)
        self.assertIn((("end1", "A"), [("s1", False)], ("sw1", "A")), runs)
        self.assertEqual(sorted(s for _a, chain, _b in runs for s, _r in chain), ["s1", "s2", "s3", "s4"])

    def test_skipped_tracks_start_no_run(self):
        runs = le_names.runs(BAND, skip={"s2"})
        self.assertNotIn("s2", [s for _a, chain, _b in runs for s, _r in chain])

    def test_a_turnback_only_one_track_reaches_stops(self):
        band = {"nodes": {"tb": {"kind": "turnback"}, "e": {"kind": "end"}},
                "strands": {"s1": strand(("tb", "A"), ("e", "A"))}}
        with self.assertRaisesRegex(BuildError, "turnback tb: only track s1 reaches it"):
            le_names.runs(band)

    def test_a_closed_loop_of_turnbacks_stops(self):
        band = {"nodes": {"t1": {"kind": "turnback"}, "t2": {"kind": "turnback"}},
                "strands": {"s1": strand(("t1", "A"), ("t2", "A")), "s2": strand(("t2", "B"), ("t1", "B"))}}
        with self.assertRaisesRegex(BuildError, "closed loop of turnbacks"):
            le_names.runs(band)


class Crossovers(unittest.TestCase):
    def test_the_track_inside_a_crossover(self):
        """Two switches of one label joined C to C, as the plugin draws a single crossover (staging's 7)."""
        band = {"nodes": {k: dict(v, label="7") if v["kind"] == "switch" else v for k, v in BAND["nodes"].items()},
                "strands": BAND["strands"]}
        self.assertEqual(le_names.crossover_strands(band), {"s2"})
        self.assertEqual(le_names.crossover_strands(BAND), set())      # 101A and 101B: two labels

    def test_inside_crossover_reads_the_two_labels(self):
        self.assertTrue(le_names.inside_crossover("101A", "101B"))
        self.assertFalse(le_names.inside_crossover("101A", "103B"))
        self.assertFalse(le_names.inside_crossover("101A", ""))
        self.assertFalse(le_names.inside_crossover("XA", "XB"))

    def test_an_end_label_is_the_switch_or_nothing(self):
        bands = [("Main", BAND, {})]
        self.assertEqual(le_names._end_label(bands, {}, 0, "sw1"), "101A")
        self.assertEqual(le_names._end_label(bands, {}, 0, "end1"), "")


class Lengths(unittest.TestCase):
    NAMES = {"blocks": {"s1": ["Track A"], "s2": ["Track B", "Track A"]}}

    def test_each_drawn_block_takes_its_plan_length(self):
        self.assertEqual(le_names.staging_lengths(self.NAMES, {"Track A": 12, "Track B": 3.5, "Track C": 1}),
                         {"Track A": 12.0, "Track B": 3.5})

    def test_a_drawn_block_with_no_plan_length_stops(self):
        with self.assertRaisesRegex(BuildError, r"no plan length for drawn staging blocks \['Track B'\]"):
            le_names.staging_lengths(self.NAMES, {"Track A": 12})


class SharedTurnouts(unittest.TestCase):
    def test_a_turnout_on_two_bands_is_shared_and_skipped_bands_are_left(self):
        names = {"Main": {"turnouts": {"n1": "Switch 127", "n2": "Switch 105"}},
                 "Upper": {"turnouts": {"n3": "Switch 127"}},
                 "Staging": {"turnouts": {"n4": "Switch 127"}}}
        le_names.shared_turnouts(names, {"Staging"})
        self.assertEqual(names["Main"]["shared_turnouts"], ["Switch 127"])
        self.assertEqual(names["Upper"]["shared_turnouts"], ["Switch 127"])
        self.assertNotIn("shared_turnouts", names["Staging"])


class LcosRule(unittest.TestCase):
    def setUp(self):
        le_names.lcos_rule.cache_clear()
        self.addCleanup(le_names.lcos_rule.cache_clear)

    def test_the_rule_is_signal_coordinators_module(self):
        is_lcos, in_mast = le_names.lcos_rule()
        self.assertTrue(is_lcos("IH3332"))                  # node 33, signal 32
        self.assertFalse(is_lcos("IH3348"))                 # signal 48: past the LCOS signal numbers
        self.assertFalse(is_lcos("IH832"))                  # node 8: not an octal digit
        self.assertFalse(is_lcos("IH:HART:C3:108LA"))
        self.assertEqual(in_mast.findall("IF$shsm:basic:one-low(IH3332)(IH:HART:1)"), ["(IH3332)"])
        self.assertEqual(le_names.lcos_named(["IT:HART:1", "IH3332", "IF$shsm:basic:one-low(IH3332)",
                                              "IF$shsm:basic:one-low(IH:HART:C3:108LA)"]),
                         ["IF$shsm:basic:one-low(IH3332)", "IH3332"])

    def test_a_rule_that_cannot_be_loaded_is_a_build_error(self):
        with mock.patch.object(coordinator, "lcos_rule", side_effect=coordinator.CoordinatorError("gone")), \
                self.assertRaisesRegex(BuildError, "gone"):
            le_names.lcos_rule()


class LcosGuard(unittest.TestCase):
    """read_level_masts stops on a mast or head of an added level that signal_coordinator.py would enrol."""

    ROW = {"mast": "Mast 108LA", "system_name": "IF$shsm:basic:one-low(IH3332)",
           "device_system_name": "IF$shsm:basic:one-low(IH:HART:C3:108LA)", "heads": [("IH3332", "Head 108LA")]}

    def read(self, row):
        with mock.patch.object(le_names.level_masts_lib, "read", return_value=[row]):
            return le_names.read_level_masts(Path("masts.csv"))

    def test_an_lcos_head_before_the_cut_over_stops_the_build(self):
        with self.assertRaisesRegex(BuildError, r"names signal_coordinator\.py takes for LCOS heads.*"
                                                r"\['IF\$shsm:basic:one-low\(IH3332\)', 'IH3332'\]"):
            self.read(self.ROW)

    def test_a_head_swapped_in_by_its_device_row_passes(self):
        row = dict(self.ROW, device_system_name=self.ROW["system_name"])
        self.assertEqual(self.read(row), [row])

    def test_internal_names_pass(self):
        row = dict(self.ROW, system_name="IF$shsm:basic:one-low(IH:HART:C3:108LA)",
                   heads=[("IH:HART:C3:108LA", "Head 108LA")])
        self.assertEqual(self.read(row), [row])


class LevelNames(unittest.TestCase):
    PLACEHOLDERS = le_names.Placeholders(
        {"Main": {"turnouts": {"n1": "Switch 101"}, "os": {"n1": "OS Switch 101"},
                  "xover_blocks": {}, "blocks": {"s1": ["101:B"]}}},
        {"OS Switch 101": 0.0, "101:B": 100.0})
    DEVICE = {"Switch 101": "Switch 101", "OS Switch 101": "OS Switch 101", "101:B": "Track 101-103"}

    def run_it(self, device, plan):
        with mock.patch.object(le_names, "placeholder_names", return_value=self.PLACEHOLDERS), \
                mock.patch.object(le_names, "plan_lengths", return_value=plan):
            return le_names.level_names([], None, device)

    def test_each_placeholder_takes_its_device_map_name_and_plan_length(self):
        got = self.run_it(self.DEVICE, {"OS Switch 101": 1.0, "Track 101-103": 10.0})
        self.assertEqual(got.names["Main"]["blocks"], {"s1": ["Track 101-103"]})
        self.assertEqual(got.lengths, {"OS Switch 101": 25.4, "Track 101-103": 254.0})

    def test_a_placeholder_the_map_does_not_name_stops(self):
        device = {k: v for k, v in self.DEVICE.items() if k != "101:B"}
        with self.assertRaisesRegex(BuildError, r"names nowhere: \['101:B'\]"):
            self.run_it(device, {})

    def test_a_map_name_the_drawing_does_not_use_stops(self):
        with self.assertRaisesRegex(BuildError, r"does not have: \['Switch 999'\]"):
            self.run_it(dict(self.DEVICE, **{"Switch 999": "Switch 999"}), {})

    def test_a_block_with_no_plan_length_stops(self):
        with self.assertRaisesRegex(BuildError, r"no plan length for main and upper blocks \['Track 101-103'\]"):
            self.run_it(self.DEVICE, {"OS Switch 101": 1.0})


if __name__ == "__main__":
    unittest.main()
