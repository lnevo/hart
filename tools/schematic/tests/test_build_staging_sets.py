"""build_staging_sets.py: the master files give staging's control points, stations and sheets in every place they are
read, drift is caught by --check, and a bad master row stops with the file and line."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_staging_sets as S  # noqa: E402

CP_HEAD = "cp_id,cp_name,level,switches,area,code,notes\n"
SWITCHES = {"1", "3", "5"}


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, name, text):
        p = self.tmp / name
        p.write_text(text, encoding="utf-8")
        return p


class RealFiles(unittest.TestCase):
    def test_every_generated_file_is_current(self):
        want = S.wanted()
        for path, text in want.items():
            self.assertEqual(path.read_text(encoding="utf-8"), text, path.name)

    def test_the_legacy_file_lists_a_crossovers_halves_from_the_os_blocks(self):
        rows = {r.split(",")[0]: r for r in S.LEGACY.read_text(encoding="utf-8").splitlines()}
        self.assertIn('barn,Barn,1,"7,7b"', rows["barn"])
        self.assertIn('"25,27,29,31,23a,23b,33"', rows["east_end"])
        self.assertIn('"35a,35b,37,39"', rows["princess"])

    def test_a_sheet_is_the_sorted_union_of_its_stations(self):
        cps = S.read_control_points()
        stations = S.read_stations(cps)
        by = {s.name: s for s in S.read_sheets(stations)}
        self.assertEqual(S.sheet_switches(by["South Yard"], stations), ["7", "9", "11", "13", "15", "17", "19", "21"])
        self.assertEqual(len(S.sheet_switches(by["Staging level"], stations)), 20)

    def test_check_is_quiet_when_current_and_names_a_stale_file(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(S.main(["--check"]), 0)
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        stale = tmp / "staging.plan_overrides.json"
        over = json.loads(S.OVERRIDES.read_text(encoding="utf-8"))
        over["control_points"]["Brick"]["switches"] = ["1"]
        stale.write_text(json.dumps(over, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        err = io.StringIO()
        with mock.patch.object(S, "OVERRIDES", stale), contextlib.redirect_stderr(err):
            self.assertEqual(S.main(["--check"]), 1)
        self.assertIn("staging.plan_overrides.json is stale", err.getvalue())


class BadMasters(Tmp):
    def cps(self, body):
        return S.read_control_points(self.write("control_points_staging.csv", CP_HEAD + body), SWITCHES)

    def assertStops(self, call, *words):
        with self.assertRaises(S.SetsError) as ctx:
            call()
        for w in words:
            self.assertIn(w, str(ctx.exception))

    def test_a_good_file_reads(self):
        got = self.cps('cp_a,A,1,"1,3",A,AA,\ncp_b,B,1,5,B,BB,\n')
        self.assertEqual([c.switches for c in got], [("1", "3"), ("5",)])

    def test_an_unknown_switch_names_file_and_line(self):
        self.assertStops(lambda: self.cps('cp_a,A,1,"1,3",A,AA,\ncp_b,B,1,"5,99",B,BB,\n'),
                         "control_points_staging.csv line 3", "switch 99 is no staging switch")

    def test_a_switch_in_two_control_points_names_file_and_line(self):
        self.assertStops(lambda: self.cps('cp_a,A,1,"1,3",A,AA,\ncp_b,B,1,"3,5",B,BB,\n'),
                         "control_points_staging.csv line 3", "switch 3 is also in A")

    def test_a_staging_switch_in_no_control_point_stops(self):
        self.assertStops(lambda: self.cps('cp_a,A,1,"1,3",A,AA,\n'), "switch(es) 5 are in no control point")

    def test_a_repeated_code_names_both_lines(self):
        self.assertStops(lambda: self.cps('cp_a,A,1,"1,3",A,AA,\ncp_b,B,1,5,B,AA,\n'),
                         "line 3", "code 'AA' is also on line 2")

    def test_another_level_stops(self):
        self.assertStops(lambda: self.cps('cp_a,A,2,"1,3,5",A,AA,\n'), "line 2", "staging is 1")

    def test_a_station_switch_in_no_control_point_stops(self):
        cps = self.cps('cp_a,A,1,"1,3",A,AA,\ncp_b,B,1,5,B,BB,\n')
        path = self.write("stations_staging.csv", "station,switches,tracks,notes\nOne,1,,\nTwo,\"3,7\",,\n")
        self.assertStops(lambda: S.read_stations(cps, path), "stations_staging.csv line 3", "switch 7 is in no control point")

    def test_station_tracks_blank_none_and_names(self):
        cps = self.cps('cp_a,A,1,"1,3",A,AA,\ncp_b,B,1,5,B,BB,\n')
        path = self.write("stations_staging.csv",
                          'station,switches,tracks,notes\nOne,1,,\nTwo,3,none,\nThree,5,"X-1;X-2",\n')
        self.assertEqual([s.tracks for s in S.read_stations(cps, path)], [None, (), ("X-1", "X-2")])

    def test_a_sheet_naming_no_station_stops(self):
        cps = self.cps('cp_a,A,1,"1,3",A,AA,\ncp_b,B,1,5,B,BB,\n')
        stations = S.read_stations(cps, self.write("stations_staging.csv", "station,switches,tracks,notes\nOne,1,,\n"))
        path = self.write("sheets_staging.csv", "sheet,stations,notes\nS,One;Nowhere,\n")
        self.assertStops(lambda: S.read_sheets(stations, path), "sheets_staging.csv line 2", "Nowhere is no station")

    def test_a_missing_column_stops(self):
        path = self.write("control_points_staging.csv", "cp_id,cp_name,level,switches,area\ncp_a,A,1,1,A\n")
        self.assertStops(lambda: S.read_control_points(path, SWITCHES), "no column code")


if __name__ == "__main__":
    unittest.main()
