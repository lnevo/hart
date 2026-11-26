"""build_staging_sets.py: stations.csv and sheets.csv give staging's control points (desk areas), stations and sheets in every place they are
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
from hartlib import devices  # noqa: E402  (build_staging_sets put hartlib on the path)

HEAD = "level,station,switches,tracks,desk_code,notes\n"
SWITCHES = {"1", "3", "5"}
KINDS = ("plan_overrides", "plan_generated", "preferences", "preferences_generated")   # the layer files it reads


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

    def test_a_sheet_is_the_sorted_union_of_its_stations(self):
        _cps, stations = S.read_masters()
        by = {s.name: s for s in S.read_sheets(stations)}
        self.assertEqual(S.sheet_switches(by["South Yard"], stations), ["7", "9", "11", "13", "15", "17", "19", "21"])
        self.assertEqual(len(S.sheet_switches(by["Staging level"], stations)), 20)

    def test_check_is_quiet_when_current_and_names_a_stale_file(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(S.main(["--check"]), 0)
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for kind in KINDS:
            shutil.copyfile(S.layer_files.path(kind, S.pd.DATA), S.layer_files.path(kind, tmp))
        over = S.layer_files.read("plan_generated", "staging", tmp)
        over["control_points"]["Brick"]["switches"] = ["1"]
        S.layer_files.write_generated({"staging": over}, tmp)
        err = io.StringIO()
        with mock.patch.object(S.pd, "DATA", tmp), contextlib.redirect_stderr(err):
            self.assertEqual(S.main(["--check"]), 1)
        self.assertIn("plan_generated.json is stale", err.getvalue())
        self.assertNotIn("preferences", err.getvalue())

    def test_writes_only_staging_sections_of_the_generated_files(self):
        got = S.wanted()
        self.assertEqual(sorted(p.name for p in got), ["plan_generated.json", "preferences_generated.json"])
        for p, text in got.items():
            whole = json.loads(text)
            self.assertEqual(whole.get("main_upper"), json.loads(p.read_text(encoding="utf-8")).get("main_upper"),
                             p.name)

    def test_detail_sheets_reach_the_merged_preferences_and_not_the_hand_file(self):
        self.assertNotIn("detail_sheets", S.layer_files.read("preferences", "staging"))
        merged = S.layer_files.merged(kind="preferences")["staging"]["detail_sheets"]
        self.assertEqual(merged["South Yard"], ["7", "9", "11", "13", "15", "17", "19", "21"])
        self.assertIn("Main level", S.layer_files.read("preferences", "main_upper")["detail_sheets"])

    def test_a_hand_detail_sheets_in_staging_stops(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for kind in KINDS:
            shutil.copyfile(S.layer_files.path(kind, S.pd.DATA), S.layer_files.path(kind, tmp))
        prefs = S.layer_files.read("preferences", "staging", tmp)
        prefs["detail_sheets"] = {"Barn": ["7"]}
        S.layer_files.write({("preferences", "staging"): prefs}, tmp)
        with self.assertRaisesRegex(S.SetsError, r"preferences.json\[staging\] holds detail_sheets: .*delete the hand"):
            S.wanted(tmp)

    def test_a_hand_note_alone_does_not_stop(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for kind in KINDS:
            shutil.copyfile(S.layer_files.path(kind, S.pd.DATA), S.layer_files.path(kind, tmp))
        prefs = S.layer_files.read("preferences", "staging", tmp)
        prefs["_detail_sheets"] = "a hand note"
        S.layer_files.write({("preferences", "staging"): prefs}, tmp)
        S.wanted(tmp)  # no SetsError: a note hides no drawn value

    def test_a_missing_generated_preferences_file_stops_clearly(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for kind in KINDS[:-1]:
            shutil.copyfile(S.layer_files.path(kind, S.pd.DATA), S.layer_files.path(kind, tmp))
        with self.assertRaisesRegex(S.SetsError, "preferences_generated.json: cannot be read"):
            S.wanted(tmp)

    def test_a_missing_section_stops_clearly(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for kind in ("plan_generated", "preferences", "preferences_generated"):
            whole = S.layer_files.read_file(kind, S.pd.DATA)
            del whole["staging"]
            S.layer_files.path(kind, tmp).write_text(S.layer_files.dumps(whole), encoding="utf-8")
        with self.assertRaisesRegex(S.SetsError, "no section 'staging'"):
            S.wanted(tmp)


class BadMasters(Tmp):
    def masters(self, body):
        return S.read_masters(self.write("stations.csv", HEAD + body), SWITCHES)

    def assertStops(self, call, *words):
        with self.assertRaises(S.SetsError) as ctx:
            call()
        for w in words:
            self.assertIn(w, str(ctx.exception))

    def test_a_good_file_reads(self):
        cps, stations = self.masters('1,A,"1,3",,AA,\n1,B,5,,BB,\n')
        self.assertEqual([(c.name, c.switches) for c in cps], [("A", ("1", "3")), ("B", ("5",))])
        self.assertEqual([s.name for s in stations], ["A", "B"])

    def test_a_nested_station_gives_its_switches_to_its_own_control_point(self):
        cps, stations = self.masters('1,A,"1,3,5",,AA,\n1,B,"3,5",,BB,\n')
        self.assertEqual([(c.name, c.switches) for c in cps], [("A", ("1",)), ("B", ("3", "5"))])
        self.assertEqual([s.switches for s in stations], [("1", "3", "5"), ("3", "5")])

    def test_an_unknown_switch_names_file_and_line(self):
        self.assertStops(lambda: self.masters('1,A,"1,3",,AA,\n1,B,"5,99",,BB,\n'),
                         "stations.csv line 3 (B)", "switch 99 is no staging switch")

    def test_overlapping_stations_name_both(self):
        self.assertStops(lambda: self.masters('1,A,"1,3",,AA,\n1,B,"3,5",,BB,\n'),
                         "stations.csv lines 2 and 3", "A and B", "share switch 3")

    def test_a_staging_switch_in_no_desk_area_stops(self):
        self.assertStops(lambda: self.masters('1,A,"1,3",,AA,\n'), "switch(es) 5 are in no desk area")

    def test_a_station_with_no_code_stops(self):
        self.assertStops(lambda: self.masters('1,A,"1,3",,,\n1,B,5,,BB,\n'), "stations.csv line 2 (A)", "no desk code")

    def test_station_tracks_blank_none_and_ids_named_by_the_store(self):
        # the tracks cell gives block IDs; their names are the name store's (the field file beside the schematic
        # folder, else the generated file), so a rename there renames the station's tracks with no row changed
        folder = self.tmp / "schematic"
        folder.mkdir()
        for name in (devices.FIELD_FILE, devices.GENERATED_FILE):
            shutil.copyfile(devices.field_path().parent / name, self.tmp / name)
        path = folder / "stations.csv"
        path.write_text(HEAD + '1,One,1,,AA,\n1,Two,3,none,AA,\n1,Three,5,"block:3B-end;block:3C-end",BB,\n',
                        encoding="utf-8")
        _cps, stations = S.read_masters(path, SWITCHES)
        self.assertEqual([s.tracks for s in stations], [None, (), ("W-1", "W-2")])
        field = self.tmp / devices.FIELD_FILE
        field.write_text(field.read_text(encoding="utf-8").replace(",Track W-1,", ",Track Brick 1,"), encoding="utf-8")
        _cps, stations = S.read_masters(path, SWITCHES)
        self.assertEqual(stations[2].tracks, ("Brick 1", "W-2"))

    def test_a_station_track_by_name_or_unknown_id_stops(self):
        self.assertStops(lambda: self.masters('1,One,"1,3",,AA,\n1,Three,5,"W-1;W-2",BB,\n'),
                         "stations.csv line 3 (Three)", "block IDs", "'W-1'")
        folder = self.tmp / "schematic"
        folder.mkdir()
        shutil.copyfile(devices.field_path(), self.tmp / devices.FIELD_FILE)
        shutil.copyfile(devices.field_path().parent / devices.GENERATED_FILE, self.tmp / devices.GENERATED_FILE)
        path = folder / "stations.csv"
        path.write_text(HEAD + '1,One,"1,3",,AA,\n1,Three,5,block:3X-end,BB,\n', encoding="utf-8")
        self.assertStops(lambda: S.read_masters(path, SWITCHES), "stations.csv line 3 (Three) tracks",
                         "block:3X-end is no block")

    def test_a_sheet_naming_no_station_stops(self):
        _cps, stations = self.masters('1,One,"1,3,5",,AA,\n')
        path = self.write("sheets.csv", "level,sheet,stations,notes\n1,S,One;Nowhere,\n")
        self.assertStops(lambda: S.read_sheets(stations, path), "sheets.csv line 2", "Nowhere is no station")

    def test_a_row_of_another_level_stops(self):
        self.assertStops(lambda: self.masters('1,One,"1,3,5",,AA,\n2,Yard,107,,YD,\n'), "stations.csv line 3",
                         "level '2'; only staging")
        _cps, stations = self.masters('1,One,"1,3,5",,AA,\n')
        path = self.write("sheets.csv", "level,sheet,stations,notes\n3,Upper level,One,\n")
        self.assertStops(lambda: S.read_sheets(stations, path), "sheets.csv line 2", "level '3'; only staging")
        path = self.write("sheets.csv", "level,sheet,stations,notes\n1.0,S,One,\n")
        self.assertStops(lambda: S.read_sheets(stations, path), "sheets.csv line 2", "level '1.0' is not a level number")
        path = self.write("sheets.csv", "level,sheet,stations,notes\n01,S,One,\n")
        self.assertEqual([x.name for x in S.read_sheets(stations, path)], ["S"])

    def test_a_missing_column_stops(self):
        path = self.write("stations.csv", "level,station,switches,tracks,notes\n1,A,\"1,3,5\",,\n")
        self.assertStops(lambda: S.read_masters(path, SWITCHES), "no column desk_code")


if __name__ == "__main__":
    unittest.main()
