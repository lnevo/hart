"""hartlib.railroad_facts: the stations of stations.csv, staging's desk areas built from their desk codes (the stations
that share a code, a nested station's switches its own), and station_group_rows, the desk areas in the older
control_points.csv shape (level-unification step 8; owner 2026-11-20)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import paths, railroad_facts as rf  # noqa: E402

STATIONS = paths.LAYOUT_DATA / "schematic" / "stations.csv"
LEGS = paths.LAYOUT_DATA / "switch_legs.csv"
HEAD = "level,station,switches,tracks,desk_code,notes\n"
LEGS_HEAD = "switch,os_block\n"


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

    def test_the_station_group_rows(self):
        rows = {r["cp_name"]: r for r in rf.station_group_rows(STATIONS, LEGS)}
        self.assertEqual(rows["East End"]["switches"].split(",")[:2], ["25", "27"])
        self.assertIn("23a", rows["East End"]["switches"].split(","))
        self.assertEqual(rows["Barn"]["switches"], "7,7b")
        self.assertEqual(rows["Engine House"]["cp_id"], "engine_house")
        self.assertEqual({r["level"] for r in rows.values()}, {"1"})


class DeskAreas(Files):
    def test_stations_that_share_a_code_are_one_area_named_by_the_first(self):
        areas = self.areas('1,Brick,"1,3",none,BK,a\n1,West Yard,3,W-1;W-2,BK,b\n1,Plane,5,,PL,\n')
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
                   "switch 5")

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
    def test_a_station_inside_another_is_nested_and_equal_or_apart_is_not(self):
        self.assertEqual(rf.nested_stations({"Barn": ["7", "9", "11", "13"], "EH": [9, 11, 13], "Yard": ["15"]}),
                         {"EH"})
        self.assertEqual(rf.nested_stations({"A": ["1", "3"], "B": ["3", "1"]}), set())

    def test_only_a_station_nested_in_another_desk_area_is_an_area_of_its_own(self):
        rows = rf.read_stations(STATIONS)
        self.assertEqual(rf.nested_own_areas(rows), {"Engine House"})        # not West Yard, nested in Brick (BK)


class StationGroupRows(Files):
    def files(self, stations: str, legs: str) -> tuple[Path, Path]:
        d = self.dir()
        (d / "stations.csv").write_text(HEAD + stations)
        (d / "legs.csv").write_text(LEGS_HEAD + legs)
        return d / "stations.csv", d / "legs.csv"

    def test_a_crossover_is_listed_by_its_halves_in_order(self):
        st, legs = self.files('1,X Y,"7,5",,XX,n\n', "7,OS Switch 7b\n7,OS Switch 7\n5,OS Switch 5\n")
        self.assertEqual(rf.station_group_rows(st, legs),
                         [dict(cp_id="x_y", cp_name="X Y", level="1", switches="7,7b,5", notes="n", code="XX")])

    def test_errors_name_the_file_and_line(self):
        st, legs = self.files("1,X,9,,XX,\n", "5,OS Switch 5\n")
        with self.assertRaisesRegex(rf.FactsError, r"stations.csv line 2 \(X\): switch 9 has no OS block in legs.csv"):
            rf.station_group_rows(st, legs)
        st, legs = self.files("1,X,5,,XX,\n", "5,Track 5\n")
        with self.assertRaisesRegex(rf.FactsError, r"legs.csv line 2: 'Track 5' is not an OS Switch block"):
            rf.station_group_rows(st, legs)


if __name__ == "__main__":
    unittest.main()
