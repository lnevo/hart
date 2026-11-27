"""How the Layout Editor build finds a band: by its level and height, from the plan overrides (the band entries'
`level`, and `below`, the height in cm its track lies under), never by its title. Also the Layout
Editor look rules each sheet's section of preferences.json holds and HART reads (le_band_align,
le_nested_station_labels), and the three stops:
a band with no level, two bands at one level and height, and a rule naming no band.

The bands here carry made-up titles, so a lookup that matched a title word ("Staging", "Main") would fail them.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools/hartlib/src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import le_common  # noqa: E402
import le_names  # noqa: E402
from map_error import MapError  # noqa: E402
import plan_bands  # noqa: E402
from le_common import BuildError  # noqa: E402


def overrides(staging=None, levels=None) -> dict:
    """A plan_overrides.json of two sections: a one-band staging sheet and a sheet of `levels` bands."""
    return {"_sections": True,
            "staging": staging if staging is not None else {"level_title": "Cellar deck", "level": 1},
            "main_upper": {"levels": {"bands": levels if levels is not None else [
                {"name": "Lower deck", "level": 2, "below": 5},
                {"name": "Top deck, 4 in", "level": 3, "below": 99}]}}}


class Folder:
    """A data folder holding `plan` as plan_overrides.json and `prefs` as preferences.json, made publish_draft's DATA
    (which le_common reads) while the block runs."""

    def __init__(self, plan, prefs=None):
        self.plan = plan
        self.prefs = prefs if prefs is not None else {"_sections": True, "staging": {}, "main_upper": {}}

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name)
        (folder / "plan_overrides.json").write_text(json.dumps(self.plan), encoding="utf-8")
        (folder / "preferences.json").write_text(json.dumps(self.prefs), encoding="utf-8")
        self.patch = mock.patch.object(le_common.pd, "DATA", folder)
        self.patch.start()
        return folder

    def __exit__(self, *exc):
        self.patch.stop()
        self.tmp.cleanup()


BANDS = [("Cellar deck", {}, {}), ("Lower deck", {}, {}), ("Top deck, 4 in", {}, {})]


class BandPlaces(unittest.TestCase):
    """plan_bands.band_places: each band entry's level and height (its `below`); a one-band sheet has no height."""

    def test_level_and_height_from_the_entries(self):
        self.assertEqual(plan_bands.band_places(overrides()["main_upper"]),
                         {"Lower deck": (2, 5), "Top deck, 4 in": (3, 99)})
        self.assertEqual(plan_bands.band_places(overrides()["staging"]), {"Cellar deck": (1, None)})

    def test_band_levels_is_band_places_without_the_height(self):
        self.assertEqual(plan_bands.band_levels(overrides()["main_upper"]), {"Lower deck": 2, "Top deck, 4 in": 3})

    def test_one_level_at_two_heights_is_two_places(self):
        got = plan_bands.band_places({"levels": {"bands": [{"name": "Lower deck", "level": 3, "below": 5},
                                                   {"name": "Peninsula", "level": 3, "below": 99}]}})
        self.assertEqual(got, {"Lower deck": (3, 5), "Peninsula": (3, 99)})

    def test_two_bands_at_one_level_and_height_stop(self):
        for heights in ((5, 5), (None, None)):
            entries = [dict(name=n, level=2, **({"below": h} if h is not None else {}))
                       for n, h in zip(("Lower deck", "Peninsula"), heights)]
            with self.subTest(heights=heights), self.assertRaisesRegex(
                    MapError, r"'Lower deck' and 'Peninsula' are both at level 2, (height 5|no height)"):
                plan_bands.band_places({"levels": {"bands": entries}})

    def test_a_height_that_is_not_a_number_stops(self):
        for bad in ("5", True, 0, -1):
            with self.subTest(below=bad), self.assertRaisesRegex(MapError, "'Lower deck' has height"):
                plan_bands.band_places({"levels": {"bands": [{"name": "Lower deck", "level": 2, "below": bad}]}})


class FindBand(unittest.TestCase):
    """le_common.find_band: the one drawn band at a level (and height), from every section of the plan overrides."""

    def test_by_level(self):
        with Folder(overrides()):
            self.assertEqual([le_common.find_band(BANDS, lv) for lv in (1, 2, 3)], [0, 1, 2])
            self.assertEqual(le_common.band_places(BANDS), [(1, None), (2, 5), (3, 99)])

    def test_by_level_and_height(self):
        plan = overrides(levels=[{"name": "Lower deck", "level": 3, "below": 5},
                                 {"name": "Top deck, 4 in", "level": 3, "below": 99}])
        with Folder(plan):
            self.assertEqual(le_common.find_band(BANDS, 3, 99), 2)
            self.assertEqual(le_common.find_band(BANDS, 3, 5), 1)
            with self.assertRaisesRegex(BuildError, r"2 bands are at level 3 \('Lower deck' at height 5, "
                                                    r"'Top deck, 4 in' at height 99\): give the height"):
                le_common.find_band(BANDS, 3)

    def test_no_band_at_the_level_stops_naming_the_bands(self):
        with Folder(overrides()), self.assertRaisesRegex(
                BuildError, r"no band is at level 2, height 7 \(bands: 'Cellar deck' at level 1, 'Lower deck' at "
                            r"level 2, height 5, 'Top deck, 4 in' at level 3, height 99\)"):
            le_common.find_band(BANDS, 2, 7)

    def test_a_band_with_no_level_stops(self):
        with Folder(overrides()), self.assertRaisesRegex(BuildError, "gives no level to band 'Attic'"):
            le_common.find_band([*BANDS, ("Attic", {}, {})], 1)

    def test_two_bands_at_one_level_and_height_stop(self):
        plan = overrides(staging={"level_title": "Cellar deck", "level": 2})
        plan["main_upper"]["levels"]["bands"][0].pop("below")
        with Folder(plan), self.assertRaisesRegex(
                BuildError, r"plan_overrides.json: bands 'Cellar deck' \(section staging\) and 'Lower deck' "
                            r"\(section main_upper\) are both at level 2, no height"):
            le_common.find_band(BANDS, 3)

    def test_one_band_drawn_twice_stops(self):
        with Folder(overrides()), self.assertRaisesRegex(BuildError, r"bands 0 and 2 are both 'Cellar deck'"):
            le_common.band_places([BANDS[0], BANDS[1], BANDS[0]])

    def test_base_keys_are_the_base_levels_bands(self):
        with Folder(overrides()):
            self.assertEqual(le_common.base_keys(BANDS), {"Cellar"})
            self.assertEqual(le_common.base_band(BANDS), 0)
        with Folder(overrides(staging={"level_title": "Cellar deck", "level": 3},
                              levels=[{"name": "Lower deck", "level": 2, "below": 5},
                                      {"name": "Top deck, 4 in", "level": 1, "below": 99}])):
            self.assertEqual(le_common.base_keys(BANDS), {"Top"})       # level 1, whatever its title
            self.assertEqual(le_common.base_band(BANDS), 2)

    def test_no_base_band_stops(self):
        with Folder(overrides(staging={"level_title": "Cellar deck", "level": 3},
                              levels=[{"name": "Lower deck", "level": 2, "below": 5}])):
            with self.assertRaisesRegex(BuildError, r"no band is at level 1"):
                le_common.base_band(BANDS[:2])

    def test_a_module_the_plugin_lacks_is_a_build_error(self):
        with self.assertRaisesRegex(BuildError, r"has no schematic\.no_such_module: update it"):
            le_common.plugin_module("no_such_module")

    def test_band_key_is_the_plugins(self):
        draw = le_common.plugin_module("draw")
        for title in ("Cellar deck", "Top deck, 4 in", "", "One"):
            self.assertEqual(le_common.band_key(title), draw.band_key(title))

    def test_the_committed_bands_are_found_by_level(self):
        bands, _page = le_common.schematic()
        self.assertEqual([le_common.find_band(bands, lv) for lv in (1, 2, 3)], [0, 1, 2])
        self.assertEqual(le_common.base_band(bands), 0)


class LeBandAlign(unittest.TestCase):
    """le_common.le_band_align: preferences.json's le_band_align ({level: side}) of each sheet's section, as the
    plugin's page band_align ({band key: side}) for the bands drawn."""

    def prefs(self, staging=None, main_upper=None):
        return {"_sections": True, "staging": staging or {}, "main_upper": main_upper or {}}

    def test_each_section_names_its_bands_by_level(self):
        prefs = self.prefs({"le_band_align": {"1": "left"}}, {"le_band_align": {"3": "right"}})
        with Folder(overrides(), prefs):
            self.assertEqual(le_common.le_band_align(BANDS), {"Cellar": "left", "Top": "right"})
            self.assertEqual(le_common.le_band_align(BANDS[:1]), {"Cellar": "left"})    # a band not drawn: no entry

    def test_none_set_is_none(self):
        with Folder(overrides(), self.prefs()):
            self.assertEqual(le_common.le_band_align(BANDS), {})

    def test_a_level_of_no_band_of_the_section_stops(self):
        for level in ("2", "4"):        # 2: a band of another section; 4: no band at all
            prefs = self.prefs({"le_band_align": {level: "left"}})
            with self.subTest(level=level), Folder(overrides(), prefs), self.assertRaisesRegex(
                    BuildError, rf"preferences.json section staging: le_band_align names level {level}, which no "
                                r"band of the section is at \(its bands: 'Cellar deck' at level 1\)"):
                le_common.le_band_align(BANDS)

    def test_a_bad_side_or_shape_stops(self):
        for bad, why in (({"1": "middle"}, r"level 1: 'middle' is not left, centre or right"),
                         ("left", r"must be an object of level: side"),
                         ({"one": "left"}, r"names level 'one', which is not a level number")):
            prefs = self.prefs({"le_band_align": bad})
            with self.subTest(bad=bad), Folder(overrides(), prefs), self.assertRaisesRegex(
                    BuildError, "preferences.json section staging: le_band_align" + ".*" + why):
                le_common.le_band_align(BANDS)

    def test_two_bands_at_the_level_stop(self):
        plan = overrides(levels=[{"name": "Lower deck", "level": 3, "below": 5},
                                 {"name": "Top deck, 4 in", "level": 3, "below": 99}])
        prefs = self.prefs(main_upper={"le_band_align": {"3": "left"}})
        with Folder(plan, prefs), self.assertRaisesRegex(
                BuildError, r"preferences.json section main_upper: le_band_align level 3: the section has 2 bands at "
                            r"that level \('Lower deck' at height 5, 'Top deck, 4 in' at height 99\)"):
            le_common.le_band_align(BANDS)

    def test_the_committed_preferences_align_staging_left(self):
        bands, _page = le_common.schematic()
        self.assertEqual(le_common.le_band_align(bands), {le_common.band_key(bands[0][0]): "left"})


class LabelRuleNamingNoBand(unittest.TestCase):
    """A sheet's label rule for one band (preferences.json[main_upper]'s le_band_labels) naming no band stops: the
    plugin's own reader (le_labels.options), which reads every sheet's label rules."""

    def test_le_band_labels_for_no_band_stops(self):
        labels = le_common.plugin_module("le_labels")
        core = le_common.plugin()[2]
        page = {"band_order": ["Cellar", "Lower"], "le_band_labels": {"Attic": {"names_last": True}}}
        bands = [("Cellar deck", {}, {}), ("Lower deck", {}, page)]
        with self.assertRaisesRegex(core.SchematicError, r"Lower deck: le_band_labels names Attic, which is no band"):
            labels.options(bands, page)

    def test_the_staging_rules_are_read_from_its_section(self):
        from hartlib import layer_files
        # as named in the merged view: the hand file gives the tracks' block IDs
        own = layer_files.merged(le_common.pd.DATA, "preferences")["staging"]["le_labels"]
        bands, page = le_common.schematic()
        labels = le_common.plugin_module("le_labels")
        opts = labels.options(bands, page)[le_common.base_band(bands)]
        for rule in ("extra_steps", "extra_follow", "name_columns", "name_steps"):
            self.assertEqual(opts[rule], own[rule], rule)


class NamesSkipTheBaseByLevel(unittest.TestCase):
    """le_names skips the bands of a level the base holds (le_common.base_keys), found by level, not by title."""

    def test_named_bands_names_a_track_by_the_role_it_is_given_never_its_name(self):
        """A line block (devices.LINE_ROLES) is named on its longest track; any other is not; a block `roles` does
        not hold stops. The roles are the caller's (le_names.block_roles of the map the names came from)."""
        band = {"nodes": {"a": {"kind": "end"}, "b": {"kind": "end"}},
                "strands": {"s1": {"src": ("a", "A"), "dst": ("b", "B"), "cm": 5.0, "name": "plan"}}}
        empty = {"nodes": {}, "strands": {}}
        bands = [("Cellar deck", empty, {}), ("Lower deck", band, {}), ("Top deck, 4 in", empty, {})]
        names = {"Lower": dict(turnouts={}, blocks={"s1": ["Track 1-2"]}), "Top": dict(turnouts={}, blocks={})}
        with Folder(overrides()):
            named = lambda roles: le_names.named_bands(bands, names, roles)[1][1]["strands"]["s1"]["name"]  # noqa: E731
            self.assertEqual(named({"Track 1-2": "track"}), "1-2")
            self.assertEqual(named({"Track 1-2": "part"}), "1-2")
            self.assertEqual(named({"Track 1-2": "os"}), "")             # named like a track, but an OS block
            with self.assertRaisesRegex(BuildError, "no main or upper block row 'Track 1-2'"):
                named({"OS Switch 1": "os"})

    def test_named_bands_leaves_the_base_band_as_it_is(self):
        plan = overrides(staging={"level_title": "Cellar deck", "level": 2},
                         levels=[{"name": "Lower deck", "level": 1, "below": 5},
                                 {"name": "Top deck, 4 in", "level": 3, "below": 99}])
        bands = [(t, {"nodes": {}, "strands": {}}, {}) for t, _b, _o in BANDS]
        names = {"Cellar": dict(turnouts={}, blocks={}), "Top": dict(turnouts={}, blocks={})}
        with Folder(plan):
            out = le_names.named_bands(bands, names)
        self.assertIs(out[1][1], bands[1][1])               # level 1: the base's band, untouched
        self.assertIsNot(out[0][1], bands[0][1])            # titled like staging, but level 2: named
        self.assertIsNot(out[2][1], bands[2][1])

    def test_shared_turnouts_skip_the_keys_given(self):
        names = {"Cellar": dict(turnouts={"a": "Switch 1"}), "Lower": dict(turnouts={"b": "Switch 1"}),
                 "Top": dict(turnouts={"c": "Switch 1"})}
        le_names.shared_turnouts(names, {"Lower"})
        self.assertEqual(names["Cellar"]["shared_turnouts"], ["Switch 1"])
        self.assertNotIn("shared_turnouts", names["Lower"])

    def test_level_masts_skip_the_keys_given(self):
        row = dict(mast="Mast 1", system_name="IF$vsm:x", facing="Track A", protects="", switch="", leg="")
        names = {"Cellar": dict(blocks={"e": ["Track A"]}, os={}), "Lower": dict(blocks={"e": ["Track A"]}, os={})}
        with mock.patch.object(le_names.level_masts_lib, "is_level_virtual", return_value=True), \
                mock.patch.object(le_names.tables, "mast_icon_size", return_value=((10, 20), True)):
            le_names.level_masts(names, [row], {"Lower"})
        self.assertEqual([m["mast"] for m in names["Cellar"]["masts"]], ["Mast 1"])
        self.assertNotIn("masts", names["Lower"])


class ReviewFixes(unittest.TestCase):
    """The #817 review: a band with no height beside one with a height at one level, le_band_align finding its own
    section's band by level and height, the data folder given, and le_names stopping on a band the plan does not
    title."""

    PLAN = staticmethod(lambda: overrides(staging={"level_title": "Cellar deck", "level": 2}))  # 2 at no height and 5

    def test_a_band_with_no_height_beside_one_with_a_height_stops_with_a_build_error(self):
        with Folder(self.PLAN()), self.assertRaisesRegex(
                BuildError, r"2 bands are at level 2 \('Cellar deck' at no height, 'Lower deck' at height 5\): "
                            r"give the height"):
            le_common.find_band(BANDS, 2)

    def test_no_height_is_a_height_to_find_by(self):
        with Folder(self.PLAN()):
            self.assertEqual(le_common.find_band(BANDS, 2, None), 0)
            self.assertEqual(le_common.find_band(BANDS, 2, 5), 1)

    def test_bound_index_stops_with_its_message(self):
        import build_cats_panel as bcp
        plan = overrides(staging={"level_title": "Cellar deck", "level": 1},
                         levels=[{"name": "Lower deck", "level": 1, "below": 5},
                                 {"name": "Top deck, 4 in", "level": 3, "below": 99}])
        with Folder(plan), self.assertRaisesRegex(bcp.CatsPanelError, r"the band bound to the field: 2 bands are at level 1"):
            bcp.bound_index(BANDS)

    def test_le_band_align_finds_its_own_sections_band_by_height(self):
        prefs = {"_sections": True, "staging": {"le_band_align": {"2": "left"}},
                 "main_upper": {"le_band_align": {"2": "right"}}}
        with Folder(self.PLAN(), prefs):
            self.assertEqual(le_common.le_band_align(BANDS), {"Cellar": "left", "Lower": "right"})

    def test_le_band_align_reads_the_folder_it_is_given(self):
        prefs = {"_sections": True, "staging": {"le_band_align": {"1": "right"}}, "main_upper": {}}
        with Folder(overrides(staging={"level_title": "Cellar deck", "level": 1}), prefs) as folder:
            pass_folder = folder
            with mock.patch.object(le_common.pd, "DATA", Path("/nonexistent/folder")):
                self.assertEqual(le_common.le_band_align(BANDS, pass_folder), {"Cellar": "right"})
                self.assertEqual(le_common.find_band(BANDS, 1, data=pass_folder), 0)
                self.assertEqual(le_common.band_places(BANDS, pass_folder)[0], (1, None))

    def test_le_names_stops_on_a_band_the_plan_does_not_title(self):
        bands = [(t, {"nodes": {}, "strands": {}}, {}) for t, _b, _o in [*BANDS, ("Attic", None, None)]]
        le_mod = le_common.plugin()[1]
        with Folder(overrides()):
            for call in (lambda: le_names.named_bands(bands, {}), lambda: le_names.placeholder_names(bands, le_mod)):
                with self.assertRaisesRegex(BuildError, "gives no level to band 'Attic'"):
                    call()

    def test_the_build_hands_le_names_the_solved_titles(self):
        bands, page = le_common.schematic()
        drawn = le_common.plugin()[1].drawn_bands(bands, page)
        self.assertEqual([t for t, _b, _o in drawn], [t for t, _b, _o in bands])
        self.assertEqual(le_common.band_levels(drawn), [1, 2, 3])


STATIONS = {"Barn": ["7", "9", "11", "13"], "Engine House": {"switches": ["9", "11", "13"]}, "Yard": ["15", "17"],
            "Yard West": ["17"]}
STATIONS_CSV = ("level,station,switches,tracks,desk_code,notes\n1,Barn,\"7,9,11,13\",,BN,\n1,Engine House,\"9,11,13\",,EH,\n"
                "1,Yard,\"15,17\",,YD,\n1,Yard West,17,,YD,\n")


class LeNestedStationLabels(unittest.TestCase):
    """le_common.le_station_labels: a sheet section's le_nested_station_labels false leaves the stations nested in
    a station of another desk area (Engine House in Barn) out of the stations its bands hand the plugin's Layout
    Editor labeller, and keeps one nested in its own area (Yard West in Yard, as West Yard in Brick); true, or not set,
    hands every station."""

    def bands(self):
        return [("Cellar deck", {}, {"stations": dict(STATIONS), "station_tracks": {"Yard": ["Y-1"]}}),
                ("Lower deck", {}, {"stations": dict(STATIONS)}), ("Top deck, 4 in", {}, {})]

    def prefs(self, staging=None, main_upper=None):
        return {"_sections": True, "staging": staging or {}, "main_upper": main_upper or {}}

    def test_false_leaves_the_nested_stations_out_of_its_sections_bands(self):
        bands = self.bands()
        with Folder(overrides(), self.prefs({"le_nested_station_labels": False})) as folder:
            (folder / "stations.csv").write_text(STATIONS_CSV, encoding="utf-8")
            got = le_common.le_station_labels(bands)
        self.assertEqual(list(got[0][2]["stations"]), ["Barn", "Yard", "Yard West"])
        self.assertEqual(got[0][2]["station_tracks"], {"Yard": ["Y-1"]})        # the rest of the options as given
        self.assertEqual(list(got[1][2]["stations"]), list(STATIONS))           # another section's band: unchanged
        self.assertEqual(got[2], bands[2])
        self.assertEqual(list(bands[0][2]["stations"]), list(STATIONS))         # the bands given are not changed

    def test_true_or_not_set_hands_every_station(self):
        for prefs in (self.prefs({"le_nested_station_labels": True}), self.prefs()):
            bands = self.bands()
            with self.subTest(prefs=prefs), Folder(overrides(), prefs):
                self.assertEqual(le_common.le_station_labels(bands), bands)

    def test_a_bad_stations_file_stops_with_its_row(self):
        with Folder(overrides(), self.prefs({"le_nested_station_labels": False})) as folder, \
                self.assertRaisesRegex(BuildError, r"stations.csv line 2 \(Barn\): no desk code"):
            (folder / "stations.csv").write_text("level,station,switches,tracks,desk_code,notes\n1,Barn,7,,,\n")
            le_common.le_station_labels(self.bands())

    def test_a_value_that_is_not_true_or_false_stops(self):
        for bad in ("no", 0, None):
            with self.subTest(bad=bad), Folder(overrides(), self.prefs({"le_nested_station_labels": bad})), \
                    self.assertRaisesRegex(BuildError, r"preferences.json section staging: le_nested_station_labels "
                                                       r"is true or false, not "):
                le_common.le_station_labels(self.bands())

    def test_the_committed_preferences_leave_engine_house_off_staging(self):
        bands, _page = le_common.schematic()
        got = le_common.le_station_labels(bands)
        self.assertIn("Engine House", bands[0][2]["stations"])
        self.assertNotIn("Engine House", got[0][2]["stations"])
        self.assertIn("Barn", got[0][2]["stations"])
        self.assertIn("West Yard", got[0][2]["stations"])


if __name__ == "__main__":
    unittest.main()
