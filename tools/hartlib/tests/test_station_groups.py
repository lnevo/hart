"""hartlib.railroad_facts: the stations of stations.csv, staging's desk areas built from their desk codes (the stations
that share a code, a nested station's switches its own), and station_group_rows, the desk areas in the older
control_points.csv shape (level-unification step 8; owner 2026-11-20)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import hand_lists, paths, railroad_facts as rf  # noqa: E402

STATIONS = paths.LAYOUT_DATA / "schematic" / "stations.csv"
SWITCHES = paths.LAYOUT_DATA / "switches.csv"
HEAD = "level,station,switches,tracks,desk_code,notes\n"
SW_HEAD = ",".join(rf.SWITCH_COLUMNS) + "\n"


class Files(unittest.TestCase):
    def dir(self) -> Path:
        return Path(self.enterContext(tempfile.TemporaryDirectory()))

    def stations(self, body: str) -> Path:
        path = self.dir() / "stations.csv"
        path.write_text(HEAD + body)
        return path

    def areas(self, body: str, switches=None):
        return rf.read_desk_areas(self.stations(body), switches)

    def stops(self, body: str, *parts: str, switches=None):
        with self.assertRaises(rf.FactsError) as ctx:
            self.areas(body, switches)
        for p in parts:
            self.assertIn(p, str(ctx.exception))


class TheRepo(Files):
    def test_the_desk_areas_are_todays(self):
        areas = rf.read_desk_areas(STATIONS)
        self.assertEqual([(a.name, a.code, a.switches) for a in areas], [
            ("Brick", "BK", ("1", "3")), ("Plane", "PL", ("5",)), ("Barn", "BN", ("7",)),
            ("South Yard", "SY", ("15", "17", "19", "21")),
            ("East End", "EE", ("25", "27", "29", "31", "23", "33")), ("Princess", "PR", ("35", "37", "39")),
            ("Engine House", "EH", ("9", "11", "13"))])
        self.assertEqual(areas[0].stations, ("Brick", "West Yard"))
        self.assertEqual({a.level for a in areas}, {1})

    def test_the_desk_plates_are_the_hand_built_desks_five(self):
        # owner, 2026-11-21: the control point plates the hand-built CATS desk had, now from stations.csv
        self.assertEqual([s.name for s in rf.read_stations(STATIONS) if s.desk_plate],
                         ["Brick", "Plane", "Barn", "East End", "Princess"])

    def test_desk_plate_is_yes_or_empty(self):
        path = self.dir() / "stations.csv"
        path.write_text("level,station,switches,tracks,desk_code,desk_plate,notes\n1,A,1,,AA,yes,\n1,B,3,,BB,,\n")
        self.assertEqual([s.desk_plate for s in rf.read_stations(path)], [True, False])
        path.write_text("level,station,switches,tracks,desk_code,desk_plate,notes\n1,A,1,,AA,no,\n")
        with self.assertRaisesRegex(rf.FactsError, "desk_plate is yes or empty, not 'no'"):
            rf.read_stations(path)

    def test_the_station_group_rows(self):
        rows = {r["cp_name"]: r for r in rf.station_group_rows(STATIONS, SWITCHES)}
        self.assertEqual(rows["East End"]["switches"].split(",")[:2], ["25", "27"])
        self.assertIn("23a", rows["East End"]["switches"].split(","))
        self.assertEqual(rows["Barn"]["switches"], "7,7b")
        self.assertEqual(rows["Engine House"]["cp_id"], "engine_house")
        self.assertEqual({r["level"] for r in rows.values()}, {"1"})


class StationTracks(Files):
    def test_an_empty_entry_or_a_name_in_tracks_stops(self):
        with self.assertRaisesRegex(rf.FactsError, "has an empty entry"):
            rf.read_stations(self.stations("1,West Yard,3,block:3B-end;;block:3C-end,BK,\n"))
        with self.assertRaisesRegex(rf.FactsError, "not 'W-1'"):
            rf.read_stations(self.stations("1,West Yard,3,W-1;block:3C-end,BK,\n"))
        st = rf.read_stations(self.stations("1,West Yard,3,block:3B-end;block:3C-end,BK,\n1,B,5,none,BB,\n1,C,7,,CC,\n"))
        self.assertEqual([s.track_ids for s in st], [("block:3B-end", "block:3C-end"), (), None])


class DeskAreas(Files):
    def test_stations_that_share_a_code_are_one_area_named_by_the_first(self):
        areas = self.areas('1,Brick,"1,3",none,BK,a\n1,West Yard,3,block:3B-end;block:3C-end,BK,b\n1,Plane,5,,PL,\n')
        self.assertEqual([(a.name, a.code, a.switches, a.stations, a.notes, a.line) for a in areas],
                         [("Brick", "BK", ("1", "3"), ("Brick", "West Yard"), "a", 2),
                          ("Plane", "PL", ("5",), ("Plane",), "", 4)])

    def test_a_nested_station_takes_its_switches_for_its_own_area(self):
        areas = self.areas('1,Barn,"7,9,11,13",,BN,\n1,Engine House,"9,11,13",,EH,\n')
        self.assertEqual([(a.name, a.switches) for a in areas], [("Barn", ("7",)), ("Engine House", ("9", "11", "13"))])

    def test_an_area_named_by_a_nested_station_comes_after_the_others(self):
        areas = self.areas('1,Barn,"7,9,11,13",,BN,\n1,Engine House,"9,11,13",,EH,\n1,South Yard,15,,SY,\n')
        self.assertEqual([a.name for a in areas], ["Barn", "South Yard", "Engine House"])

    def test_areas_follow_the_first_station_of_each_code(self):
        areas = self.areas('1,A,1,,AA,\n1,B,2,,BB,\n1,C,3,,AA,\n')
        self.assertEqual([(a.name, a.switches) for a in areas], [("A", ("1", "3")), ("B", ("2",))])

    def test_a_station_with_no_code_stops(self):
        self.stops("1,A,1,,,\n", "stations.csv line 2 (A)", "no desk code")

    def test_a_station_with_two_codes_stops(self):
        self.stops('1,A,1,,"BN,EH",\n', "stations.csv line 2 (A)", "two desk codes")
        self.stops("1,A,1,,BN;EH,\n", "stations.csv line 2 (A)", "two desk codes")
        self.stops("1,A,1,,BN EH,\n", "stations.csv line 2 (A)", "two desk codes")

    def test_a_code_that_is_not_capital_letters_stops(self):
        self.stops("1,A,1,,bn,\n", "stations.csv line 2 (A)", "'bn'")

    def test_partly_overlapping_stations_stop_naming_both(self):
        self.stops('1,A,"1,3",,AA,\n1,B,"3,5",,BB,\n', "stations.csv lines 2 and 3", "A and B",
                   "share switch 3")

    def test_stations_with_the_same_switches_stop_naming_both(self):
        self.stops('1,A,"1,3",,AA,\n1,B,"3,1",,BB,\n', "stations.csv lines 2 and 3", "A and B", "same switches")

    def test_a_switch_in_two_nested_stations_stops_naming_both(self):
        self.stops('1,A,"1,3,5",,AA,\n1,B,"3,5",,BB,\n1,C,5,,CC,\n', "stations.csv lines 3 and 4", "B and C",
                   "switch 5", "desk areas nested in another area's station")

    def test_stations_nested_in_their_own_area_do_not_clash(self):
        areas = self.areas('1,A,"1,3,5",,AA,\n1,B,"3,5",,AA,\n1,C,5,,AA,\n')
        self.assertEqual([(a.name, a.switches, a.stations) for a in areas], [("A", ("1", "3", "5"), ("A", "B", "C"))])

    def test_an_area_named_by_a_station_inside_one_of_its_own_stops(self):
        self.stops('1,West Yard,3,,BK,\n1,Brick,"1,3",none,BK,\n', "stations.csv line 2 (West Yard)",
                   "inside Brick (line 3)", "desk area BK")

    def test_an_area_nested_in_its_own_area_does_not_move_it_to_the_end(self):
        areas = self.areas('1,Brick,"1,3",,BK,\n1,West Yard,3,,BK,\n1,Barn,"7,9",,BN,\n1,EH,9,,EH,\n1,Yard,15,,SY,\n')
        self.assertEqual([a.name for a in areas], ["Brick", "Barn", "Yard", "EH"])

    def test_an_area_whose_switches_clash_with_another_stops(self):
        # a desk area clashes when its switches are another code's too: two codes on one switch, not nested
        self.stops('1,A,"1,3",,AA,\n1,B,"1,3,5",,BB,\n1,C,"5,7",,AA,\n', "B and C", "share switch 5")

    def test_an_area_left_with_no_switches_stops(self):
        self.stops('1,A,3,,AA,\n1,B,"3,5",,BB,\n1,C,5,,CC,\n', "desk area BB (B, stations.csv line 3)",
                   "no switches of its own")

    def test_one_code_on_two_levels_stops(self):
        self.stops("1,A,1,,AA,\n2,B,101,,AA,\n", "stations.csv line 3 (B)", "AA", "level 1", "line 2")

    def test_stations_of_other_levels_do_not_nest_in_staging(self):
        areas = self.areas('1,A,"1,3",,AA,\n2,B,3,,BB,\n')
        self.assertEqual([(a.name, a.switches) for a in areas], [("A", ("1", "3")), ("B", ("3",))])

    def test_bad_rows_stop_with_the_file_and_line(self):
        self.stops("1,A,,,AA,\n", "stations.csv line 2 (A)", "no switches")
        self.stops('1,A,"1,x",,AA,\n', "stations.csv line 2 (A)", "not '1,x'")
        self.stops('1,A,"1,1",,AA,\n', "stations.csv line 2 (A)", "switch 1 twice")
        self.stops("1,A,1,,AA,\n1,A,2,,BB,\n", "stations.csv line 3", "'A'", "line 2")
        self.stops("1,,1,,AA,\n", "stations.csv line 2", "no name")
        self.stops("4,A,1,,AA,\n", "stations.csv line 2 (A)", "level")

    def test_a_missing_column_stops(self):
        path = self.dir() / "stations.csv"
        path.write_text("level,station,switches,tracks,notes\n1,A,1,,\n")
        with self.assertRaisesRegex(rf.FactsError, "no column desk_code"):
            rf.read_desk_areas(path)

    def test_the_level_switches_given_are_each_in_one_area(self):
        self.stops("1,A,1,,AA,\n", "stations.csv: staging switch(es) 3, 5 are in no desk area", switches={"1", "3", "5"})
        self.stops("1,A,9,,AA,\n", "stations.csv line 2 (A)", "switch 9 is no staging switch", switches={"9x"})
        self.assertEqual(len(self.areas("1,A,1,,AA,\n2,B,101,,BB,\n", switches={"1"})), 2)


class NestedStations(unittest.TestCase):
    def test_only_a_station_nested_in_another_desk_area_is_an_area_of_its_own(self):
        rows = rf.read_stations(STATIONS)
        self.assertEqual(rf.nested_own_areas(rows), {"Engine House"})        # not West Yard, nested in Brick (BK)


class StationGroupRows(Files):
    def files(self, stations: str, os_blocks: str) -> tuple[Path, Path]:
        """stations.csv and a switches.csv whose rows are `os_blocks`: one "level,switch,os_block[,os_id]" per line,
        each given legs. A staging row's os_id is os:<switch> unless given; its legs' ids are placeholders (the reader
        holds only their shape)."""
        d = self.dir()
        (d / "stations.csv").write_text(HEAD + stations)
        rows = []
        for spec in os_blocks.splitlines():
            level, n, os_block, *os_id = spec.split(",")
            half = "" if level == "1" else n
            ids = f"{os_id[0] if os_id else 'os:' + n},block:A,block:B" if level == "1" else ",,"
            rows.append(f"{level},{n},{half},{os_block},Track A,Track B,{ids},,,,,,,,\n")
        (d / "switches.csv").write_text(SW_HEAD + "".join(rows))
        return d / "stations.csv", d / "switches.csv"

    def test_a_crossover_is_listed_by_its_halves_in_order(self):
        st, sw = self.files('1,X Y,"7,5",,XX,n\n', "1,7,OS Switch 7b,os:7:A-5B\n1,7,OS Switch 7,os:7:A-13C\n"
                                                        "1,5,OS Switch 5\n")
        self.assertEqual(rf.station_group_rows(st, sw),
                         [dict(cp_id="x_y", cp_name="X Y", level="1", switches="7,7b,5", notes="n", code="XX")])

    def test_every_level_is_given(self):
        st, sw = self.files("1,X,5,,XX,\n2,Y,105,,YY,\n", "1,5,OS Switch 5\n2,105,OS Switch 105\n")
        self.assertEqual([(r["cp_name"], r["level"]) for r in rf.station_group_rows(st, sw)], [("X", "1"), ("Y", "2")])

    def test_a_switch_with_no_os_block_names_the_station_that_holds_it(self):
        st, sw = self.files('1,Brick,"1,3",none,BK,\n1,West Yard,3,,BK,\n', "1,1,OS Switch 1\n")
        with self.assertRaisesRegex(rf.FactsError, r"stations.csv line 3 \(West Yard\): switch 3 has no OS block"):
            rf.station_group_rows(st, sw)

    def test_errors_name_the_file_and_line(self):
        st, sw = self.files("1,X,9,,XX,\n", "1,5,OS Switch 5\n")
        with self.assertRaisesRegex(rf.FactsError,
                                    r"stations.csv line 2 \(X\): switch 9 has no OS block in switches.csv"):
            rf.station_group_rows(st, sw)
        st, sw = self.files("2,X,105,,XX,\n", "2,105,Track 105\n")
        with self.assertRaisesRegex(rf.FactsError, r"switches.csv line 2 \(Switch 105\): os_block is OS Switch 105"):
            rf.station_group_rows(st, sw)

    def test_a_renamed_os_block_is_listed_by_its_switch(self):
        """naming-layers step 5: a staging OS block is keyed by its id, so an owner's name for it (os_block is the
        name store's label) still lists as its switch number, and a renamed crossover half as its number and the
        letter block_overrides.csv's crossover_half row gives its ID; with no such row it stops."""
        st, sw = self.files("1,X,5,,XX,\n", "1,5,OS Brick East\n")
        self.assertEqual(rf.station_group_rows(st, sw)[0]["switches"], "5")
        st, sw = self.files('1,X,"7",,XX,\n', "1,7,OS Barn West,os:7:A-13C\n1,7,OS Switch 7b,os:7:A-5B\n")
        overrides = st.parent / hand_lists.OVERRIDES_NAME
        overrides.write_text(",".join(hand_lists.OVERRIDE_COLUMNS) + "\n1,crossover_half,7,13,1,,os:7:A-13C,,,\n"
                             "1,crossover_half,7,5,2,,os:7:A-5B,,,\n")
        self.assertEqual(rf.station_group_rows(st, sw)[0]["switches"], "7a,7b")
        overrides.write_text(",".join(hand_lists.OVERRIDE_COLUMNS) + "\n1,crossover_half,7,5,2,,os:7:A-5B,,,\n")
        with self.assertRaisesRegex(rf.FactsError, r"switches.csv line 2 \(Switch 7\): os:7:A-13C is named "
                                                   r"'OS Barn West', and no crossover_half row"):
            rf.station_group_rows(st, sw)
        overrides.unlink()
        with self.assertRaisesRegex(rf.FactsError, "cannot read"):
            rf.station_group_rows(st, sw)


if __name__ == "__main__":
    unittest.main()
