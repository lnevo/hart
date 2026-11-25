"""mast_rule's band levels (read from the plan overrides, not a title's first word), and tracks() reading a crossover's
halves and a loop from the plan's structure, not from a label's suffix or a track's name."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools/hartlib/src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mast_rule as mr  # noqa: E402
from test_mast_plan import end, link, node  # noqa: E402


class BandLevels(unittest.TestCase):
    def test_levels_come_from_the_entries_not_the_title(self):
        got = mr.band_levels({"levels": {"bands": [{"name": "Lower deck", "level": 2, "below": 5},
                                                   {"name": "Top deck, 4 in", "level": 3, "below": 99}]}})
        self.assertEqual(got, {"Lower deck": 2, "Top deck, 4 in": 3})
        self.assertEqual(mr.band_level("Lower deck", got), 2)
        self.assertIsNone(mr.band_level("Main level", got))        # a title the file does not hold is no level
        self.assertIsNone(mr.band_level("", got))

    def test_a_one_band_input_has_its_own_level(self):
        self.assertEqual(mr.band_levels({"level_title": "Staging level", "level": 1}), {"Staging level": 1})

    def test_a_band_with_no_level_stops(self):
        with self.assertRaisesRegex(mr.MapError, "Main level.*level None"):
            mr.band_levels({"levels": {"bands": [{"name": "Main level", "below": 5}]}})
        with self.assertRaisesRegex(mr.MapError, "level_title.*level None"):
            mr.band_levels({"level_title": "Staging level"})

    def test_an_unknown_level_stops(self):
        for bad in (0, 4, "2", True, 2.0):
            with self.subTest(level=bad), self.assertRaisesRegex(mr.MapError, "not 1, 2 or 3"):
                mr.band_levels({"levels": {"bands": [{"name": "Main level", "level": bad}]}})

    def test_two_bands_with_one_title_stop(self):
        with self.assertRaisesRegex(mr.MapError, "two bands are titled"):
            mr.band_levels({"levels": {"bands": [{"name": "A", "level": 2}, {"name": "A", "level": 3}]}})

    def test_no_band_stops(self):
        with self.assertRaisesRegex(mr.MapError, "name no band"):
            mr.band_levels({})

    def test_the_repo_files_give_staging_main_and_upper(self):
        import build_device_map as bdm
        import device_map_masts as bsm
        self.assertEqual(bsm.LEVELS, {"Staging level": 1})
        self.assertEqual(sorted(bdm.LEVELS.values()), [2, 3])
        self.assertFalse(set(bdm.LEVELS) & set(bsm.LEVELS), "a band title is in both overrides files")
        self.assertEqual([lv for lv in (*bdm.LEVELS.values(), *bsm.LEVELS.values()) if lv == 1], [1])


def band(nodes, strands):
    for sid, s in strands.items():
        s.update(edge=sid, cm=10.0, main=False)
    return [("Main level", {"nodes": nodes, "strands": strands, "R": {"srow": {}}}, {})]


class CrossoverAndLoopByStructure(unittest.TestCase):
    LV = {"Main level": 2}

    def halves(self, la, lb):
        n = {"P": node(la, {"A": "pa", "B": "pb", "C": "x"}), "Q": node(lb, {"A": "qa", "B": "qb", "C": "x"}),
             "O1": end("pa", "open"), "O2": end("pb", "open"), "O3": end("qa", "open"), "O4": end("qb", "open")}
        st = {"x": link(("P", "C"), ("Q", "C")), "pa": link(("P", "A"), ("O1", "E")),
              "pb": link(("P", "B"), ("O2", "E")), "qa": link(("Q", "A"), ("O3", "E")),
              "qb": link(("Q", "B"), ("O4", "E"))}
        return band(n, st)

    def between(self, bands):
        return mr.tracks(bands, lambda b: [(("P", "C"), [("x", None)], ("Q", "C"))], {}, {}, self.LV)

    def test_the_track_between_halves_is_no_track_whatever_the_labels(self):
        for la, lb in (("7A", "7B"), ("7", "7"), ("7B", "7A")):
            with self.subTest(labels=(la, lb)):
                self.assertEqual(self.between(self.halves(la, lb)), [])

    def test_two_different_switches_keep_their_track(self):
        self.assertEqual(len(self.between(self.halves("7", "9"))), 1)

    def test_a_loop_is_the_tracks_flag_not_its_name(self):
        n = {"P": node("7", {"A": "pa", "B": "x", "C": "x"}), "O1": end("pa", "open")}
        st = {"x": link(("P", "B"), ("P", "C")), "pa": link(("P", "A"), ("O1", "E"))}
        found = mr.tracks(band(n, st), lambda b: [(("P", "B"), [("x", None)], ("P", "C"))], {}, {}, self.LV)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["loop"])


if __name__ == "__main__":
    unittest.main()
