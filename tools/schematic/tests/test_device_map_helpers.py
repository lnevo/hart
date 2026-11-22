"""The device map's small readers and staging helpers that had no test of their own: helix_pins, read_places,
loop_placeholder, helix_ends, line_cp, part_row, piece_trials, alias_note, new_spare, wire_block, staging_field and
taken_bean_names. They pin the behaviour the split of build_device_map.py into device_map_inputs.py and
device_map_staging.py keeps; none needs the schematic plugin."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(ROOT / "tools/hartlib/src")]
import build_device_map as bdm  # noqa: E402
import device_map_inputs as inputs  # noqa: E402
import device_map_staging as staging  # noqa: E402
from hartlib import devices, railroad, wiring  # noqa: E402

WIRING_HEAD = ",".join(wiring.COLUMNS) + "\n"
STATIONS_HEAD = "level,station,switches,tracks,desk_code,desk_plate,notes\n"
INTERLOCKINGS_HEAD = "level,interlocking,switches,area,notes\n"


class TempFiles(unittest.TestCase):
    def file(self, name: str, text: str) -> Path:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / name
        p.write_text(text, encoding="utf-8")
        return p


class Readers(TempFiles):
    def test_helix_pins_are_the_named_main_and_upper_detectors(self):
        p = self.file("wiring.csv", WIRING_HEAD
                      + "3,detector,Track Helix Outer,,,,,41,2,,,planned,\n"
                        "2,detector,,107,109,,,42,1,,,planned,\n"
                        "1,detector,Track Barn,,,,,13,1,,,wired,\n")
        self.assertEqual(bdm.helix_pins(p), {"Track Helix Outer": (41, 1)})

    def test_helix_pins_of_the_committed_file(self):
        self.assertEqual(bdm.helix_pins()["Track Helix Outer"], (41, 1))

    def test_a_bad_wiring_file_is_a_map_error(self):
        p = self.file("wiring.csv", WIRING_HEAD + "3,detector,Track Helix Outer,,,,,41,9,,,planned,\n")
        with self.assertRaisesRegex(bdm.MapError, "index is 1 to 8"):
            bdm.helix_pins(p)

    def places(self, stations: str, interlockings: str):
        return bdm.read_places(self.file("stations.csv", STATIONS_HEAD + stations),
                               self.file("interlockings.csv", INTERLOCKINGS_HEAD + interlockings))

    def test_read_places(self):
        got = self.places('1,West Yard,"3,5",W-1;W-2,WY,,\n2,Princess,131,none,PR,,\n',
                          '1,Brick,"1,3",,\n2,CP 127,"127,129",West,\n')
        self.assertEqual(got.of, {"3": ("West Yard",), "5": ("West Yard",), "131": ("Princess",), "1": ("Brick",),
                                  "127": ("CP 127",), "129": ("CP 127",)})
        self.assertEqual(got.order, {"West Yard": 0, "Princess": 1, "Brick": 2, "CP 127": 3})
        self.assertEqual(got.level, {"West Yard": 1, "Princess": 2, "Brick": 1, "CP 127": 2})
        self.assertEqual(got.tracks, {"Track W-1": ["West Yard"], "Track W-2": ["West Yard"]})

    def test_a_place_on_two_levels_stops(self):
        with self.assertRaisesRegex(bdm.MapError, "Brick is a station or control point of levels 1 and 2"):
            self.places("1,Brick,3,none,BK,,\n", "2,Brick,127,West,\n")

    def test_an_unreadable_places_file_is_a_map_error(self):
        with self.assertRaisesRegex(bdm.MapError, "stations.csv"):
            self.places("1,,3,none,BK,,\n", "")

    def test_loop_placeholder(self):
        self.assertEqual(bdm.loop_placeholder("Track 107 Loop", 2), "Track 107 Loop 2")
        self.assertEqual(bdm.loop_placeholder("Track 107-109", None), "Track 107-109")

    def test_staging_nodes_are_lcos_nodes_level_1(self):
        want = {n.node for n in railroad.read_lcos_nodes(railroad.Sources.under().lcos_nodes) if n.level == 1}
        self.assertEqual(bdm.staging_nodes(), want)
        self.assertTrue(want)


class Places(unittest.TestCase):
    PLACES = bdm.Places(of={"57": ("Princess",), "131": ("CP 127",), "3": ("West Yard",)},
                        order={"West Yard": 0, "Princess": 1, "CP 127": 2},
                        level={"West Yard": 1, "Princess": 2, "CP 127": 2},
                        tracks={"Track Helix Outer": ["West Yard"]})

    def test_helix_ends_are_both_levels_switches(self):
        helix = {"x": {"block": "Track Helix Outer", "staging_switch": "57", "level_switch": "131A"}}
        self.assertEqual(bdm.helix_ends(helix), {"Track Helix Outer": {"57", "131"}})

    def test_line_cp_puts_the_rows_own_level_first(self):
        track = {"ends": [("sw", "131"), ("helix", "x")]}
        ends = {"Track Helix Outer": {"57", "131"}}
        self.assertEqual(bdm.line_cp("Track Helix Outer", 2, track, self.PLACES, ends), "Princess;CP 127;West Yard")
        self.assertEqual(bdm.line_cp("Track Helix Outer", "1", track, self.PLACES, ends), "West Yard;Princess;CP 127")
        self.assertEqual(bdm.line_cp("Track Helix Outer", 2, track, self.PLACES), "CP 127;West Yard")

    def test_a_block_in_no_place_has_no_cp(self):
        self.assertEqual(bdm.line_cp("Track 9-11", 1, {"ends": [("sw", "9"), ("sw", "11")]}, self.PLACES), "")


class StagingHelpers(unittest.TestCase):
    def test_part_row(self):
        part = {"track": {"cm": 30, "ends": [("sw", "5"), ("sw", "3")]}, "part_of": "OS Switch 3", "why": "a link"}
        row = bdm.part_row("1", "Track 3-5", part, "Track 3B")
        self.assertEqual(set(row), set(devices.COLUMNS))
        self.assertEqual((row["level"], row["layer"], row["role"], row["assignment"], row["part_of"], row["trial_name"],
                          row["written_by"]),
                         ("1", "block", "part", "none", "OS Switch 3", "Track 3B", "build_device_map.py"))
        self.assertEqual(row["notes"], "a piece of the 30 cm track from Switch 3 to Switch 5, part of OS Switch 3 "
                                       "(a link)")
        self.assertTrue(row["description"])

    def test_piece_trials_keys_each_strand_and_skips_one_inside_a_crossover(self):
        got = bdm.piece_trials({0: {"s1": ["Track A", "Track B"], "s2": ["OS Switch 9"]}}, {0: {"s1": ("3B-5A", True)}},
                               {0: {"OS Switch 9"}})
        self.assertEqual(got, {"Track A": ["Track 3B-5A 2/2"], "Track B": ["Track 3B-5A 1/2"]})

    def test_piece_trials_stops_on_a_strand_with_no_key(self):
        with self.assertRaisesRegex(bdm.MapError, "strand s1 of band 0 has blocks"):
            bdm.piece_trials({0: {"s1": ["Track A"]}}, {0: {}}, {0: set()})

    def test_alias_note(self):
        self.assertEqual(bdm.alias_note("Switch 1", "M2T408"), "LCC alias of Switch 1 (M2T408)")
        with self.assertRaisesRegex(bdm.MapError, "LCC alias DCC Switch 1: Switch 1 has no turnout row"):
            bdm.alias_note("Switch 1", "")

    def test_new_spare_is_named_by_its_input(self):
        row = bdm.new_spare(bdm.StagingPin(3, "", 13, 0))
        self.assertEqual((row["level"], row["layer"], row["role"], row["user_name"], row["assignment"], row["node"],
                          row["system_name"], row["jmri_name"], row["wiring"]),
                         ("1", "occupancy", "spare", "unused Block 13-1", "spare", "13", "M2S1300", "M2S1300",
                          "Node: 13 Block: 1"))

    def test_wire_block_fills_the_occupancy_mark(self):
        row = {"user_name": "Track Barn", "jmri_comment": f"Barn track; {devices.OCCUPANCY_MARK}"}
        got = bdm.wire_block(row, 13, 1)
        self.assertEqual((got["node"], got["jmri_comment"]), ("13", "Barn track; occupancy Block 13-2 / M2S1301"))

    def test_wire_block_stops_on_a_comment_with_no_mark(self):
        with self.assertRaisesRegex(bdm.MapError, "Track Barn: its jmri_comment 'Barn track' has no"):
            bdm.wire_block({"user_name": "Track Barn", "jmri_comment": "Barn track"}, 13, 1)

    def test_staging_field_is_full_rows_of_staging_block_and_occupancy(self):
        got = bdm.staging_field()
        self.assertTrue(got)
        self.assertEqual({layer for layer, _n in got}, {"block", "occupancy"})
        self.assertTrue(all(set(r) == set(devices.COLUMNS) and r["level"] == "1" for r in got.values()))

    def test_taken_bean_names_leave_out_staging_parts_own(self):
        def row(level, role, *names):
            return dict(level=level, role=role, system_name=names[0], jmri_name=names[1], layout_block=names[2])
        got = bdm.taken_bean_names([row("1", "part", "", "IB:AUTO:0060", "ILB60"),
                                    row("2", "part", "", "IB:AUTO:0061", "ILB61"),
                                    row("1", "track", "IB:AUTO:0010", "", "ILB10")])
        self.assertNotIn("IB:AUTO:0060", got)
        self.assertNotIn("ILB60", got)
        self.assertLessEqual({"IB:AUTO:0061", "ILB61", "IB:AUTO:0010", "ILB10"}, got)


class TheSplit(TempFiles):
    """The readers live in device_map_inputs.py, which never loads the builder; build_device_map re-exports them."""
    READERS = ("CPS", "FIELD_LEVEL", "NODES", "OS_BLOCK", "PINS", "STATIONS", "UID", "WIRING", "Places", "StagingPin",
               "frozen_wires", "helix_pins", "loop_placeholder", "read_places", "read_staging_pins", "staging_nodes",
               "wiring_rows")

    def test_the_builder_re_exports_the_readers(self):
        for name in self.READERS:
            with self.subTest(name=name):
                self.assertIs(getattr(bdm, name), getattr(inputs, name))
        self.assertIs(bdm.SOURCES, inputs.SOURCES)

    STAGING = ("BEAN_NAME", "FIELD_LAYERS", "PART_BLOCK_FIRST", "STAGING_SHEET", "WIRED_LAYERS", "alias_note",
               "field_row", "helix_ends", "level_trials", "line_cp", "new_spare", "part_bean_names", "part_row",
               "piece_trials", "staging_field", "staging_layer", "staging_part_names", "staging_rows",
               "staging_trials", "staging_wired_rows", "taken_bean_names", "wire_block", "wire_occupancy")

    def test_the_builder_re_exports_the_staging_layer(self):
        for name in self.STAGING:
            with self.subTest(name=name):
                self.assertIs(getattr(bdm, name), getattr(staging, name))

    def test_neither_module_loads_the_builder_at_import(self):
        for mod in ("device_map_inputs", "device_map_staging"):
            with self.subTest(mod=mod):
                code = f"import sys; import {mod}; sys.exit('build_device_map' in sys.modules)"
                got = subprocess.run([sys.executable, "-c", code], cwd=HERE.parent, capture_output=True, text=True)
                self.assertEqual(got.returncode, 0, got.stderr)

    def test_the_staging_layer_reads_the_builders_paths_when_called(self):
        """builder() is the builder as it is then: a patched OUT reaches staging_field, as it did in one module."""
        self.assertIs(staging.builder(), bdm)
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.object(bdm, "OUT", Path(d) / "devices.csv"):
            with self.assertRaises(railroad.FactsError):     # no field file there: read from the patched folder
                staging.staging_field()

    def test_read_pins_needs_its_tracks(self):
        """The reader takes the tracks it resolves against; the builder's read_pins gives the solved schematic's."""
        with self.assertRaises(TypeError):
            inputs.read_pins(None)          # pylint: disable=no-value-for-parameter
        p = self.file("wiring.csv", WIRING_HEAD + "2,detector,OS Switch 123,,,,,42,1,,,planned,\n")
        self.assertEqual(inputs.read_pins(p, [], set()), {"OS Switch 123": (42, 0)})
        self.assertEqual(bdm.read_pins(p, found=[], split=set()), {"OS Switch 123": (42, 0)})


if __name__ == "__main__":
    unittest.main()
