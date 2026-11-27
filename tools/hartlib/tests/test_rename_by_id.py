"""A rename in devices_field.csv alone reaches every file keyed by device ID (naming-layers step 5).

A copy of the committed data renames a staging track (Track East Lead, block:33A-35A) and a staging OS block (OS
Switch 19, os:19) in its field file, as the owner would, and nothing else; then:
- the merged device master follows the renames into part_of and blocks (hartlib.devices.follow_renames);
- wiring.csv names the detectors by the new names (hartlib.wiring.read, by id);
- block_lengths.csv's labels come out renamed and its lengths unchanged (plan_lengths.labelled);
- switches.csv's staging rows read the new names by their IDs (railroad.read_switch_rows), the file unedited;
- main_lines.csv's stop 35@block:33A-35A reads 35@Princess Lead (build_main_route.read_lines).
A second copy (step 5b, RenameInPreferencesAndStations) renames Track S-1 (block:17C-29C) and a West Yard track,
Track W-1 (block:3B-end), and checks that preferences.json and stations.csv, which name tracks by block ID, are left
as they are while the merged preferences the plugin reads, the station's tracks (build_staging_sets, read_places)
and the left end take the new names.
A third (RenameCrossoverHalf) renames a staging crossover half, OS Switch 23a (os:23:A-1A), whose letter is its
crossover_half row's, by its ID, and not its name's.
The whole build on such a copy was run by hand for each step (wiki/projects/naming-layers-handoff.md, step 5 and 5b
findings, and "Left after the plan"); this pins the readers without the schematic plugin.
"""
from __future__ import annotations

import csv
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent / "src"), str(ROOT / "tools/schematic")]
from hartlib import devices, paths, railroad, wiring  # noqa: E402

RENAMES = {("1", "block:33A-35A"): "Track Princess Lead", ("1", "os:19"): "OS South 19"}
OLD = {"Track East Lead", "OS Switch 19"}


def rename(field: Path) -> None:
    """Give the field rows of RENAMES their new user names, by id, as the owner edits devices_field.csv."""
    rows = list(csv.DictReader(io.StringIO(field.read_text(encoding="utf-8"))))
    hit = 0
    for r in rows:
        if (r["level"], r["id"]) in RENAMES:
            r["user_name"] = RENAMES[(r["level"], r["id"])]
            hit += 1
    assert hit == len(RENAMES), hit
    field.write_text(devices.master_text(rows), encoding="utf-8")


class RenameById(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name)
        for name in (devices.GENERATED_FILE, devices.FIELD_FILE, "devices.columns.csv", "wiring.csv",
                     "block_lengths.csv", "block_lengths_measured.csv", "switches.csv"):
            shutil.copy(paths.LAYOUT_DATA / name, cls.data / name)
        (cls.data / "schematic").mkdir()
        shutil.copy(paths.LAYOUT_DATA / "schematic/main_lines.csv", cls.data / "schematic/main_lines.csv")
        cls.before = {p.name: p.read_bytes() for p in cls.data.glob("*.csv")}
        rename(devices.field_path(cls.data))
        cls.files = devices.Files.under(cls.data)
        cls.names = devices.user_names(cls.files)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_only_the_field_file_was_edited(self) -> None:
        changed = {p.name for p in self.data.glob("*.csv") if p.read_bytes() != self.before[p.name]}
        self.assertEqual(changed, {devices.FIELD_FILE})

    def test_the_merged_master_follows_the_renames(self) -> None:
        rows = devices.load(self.files)
        for key, name in RENAMES.items():
            self.assertEqual(self.names[key], name)
        part = next(r for r in rows if r.level == 1 and r.user_name == "Track 19-21")
        self.assertEqual(part.part_of, "OS South 19")
        cells = [r.cells()[c] for r in rows for c in devices.BLOCK_REFS if r.level == 1]
        self.assertFalse([c for c in cells if set(c.split(devices.LIST)) & OLD])

    def test_wiring_names_its_devices_by_id(self) -> None:
        got = {w.id: w.device for w in wiring.read(self.data / "wiring.csv")}
        self.assertEqual(got["det:os:19"], "OS South 19")
        self.assertEqual(got["det:block:33A-35A"], "Track Princess Lead")
        self.assertEqual(got["switch:19"], "Switch 19")

    def test_staging_wiring_names_come_from_the_field_file_alone(self) -> None:
        # a field row with no user_name: a turnout takes the name its id gives; the generated file is never read
        tmp = Path(tempfile.mkdtemp())
        for name in (devices.FIELD_FILE, "wiring.csv"):
            shutil.copy(self.data / name, tmp / name)
        rows = list(csv.DictReader(io.StringIO((tmp / devices.FIELD_FILE).read_text(encoding="utf-8"))))
        for r in rows:
            if (r["level"], r["id"]) == ("1", "switch:19"):
                r["user_name"] = ""
        (tmp / devices.FIELD_FILE).write_text(devices.master_text(rows), encoding="utf-8")
        files = devices.Files(tmp / "absent_generated.csv", tmp / "devices.columns.csv", tmp / devices.FIELD_FILE)
        got = {w.id: w.device for w in wiring.read(tmp / "wiring.csv", levels=(1,), files=files)}
        self.assertEqual((got["switch:19"], got["det:os:19"]), ("Switch 19", "OS South 19"))

    def test_block_lengths_take_the_new_names_and_keep_their_lengths(self) -> None:
        from hartlib import block_lengths
        got = {(b.level, b.id): b for b in block_lengths.plan_blocks(self.data / "block_lengths.csv", self.files).values()}
        before = {(b.level, b.id): b for b in block_lengths.plan_blocks(block_lengths.PLAN).values()}
        for key, name in RENAMES.items():
            if key in got:
                self.assertEqual(got[key].user_name, name)
                self.assertEqual(got[key].plan_in, before[key].plan_in)
        self.assertEqual(len(got), len(before))

    def test_switches_csv_labels_follow_the_store(self) -> None:
        """switches.csv gives IDs only: its rows read the new names from the master beside it, the file unedited
        (test_only_the_field_file_was_edited) and nothing for build_hands.py to write."""
        import build_hands
        path = self.data / "switches.csv"
        labels = [c for r in railroad.read_switch_rows(path) if r.level == 1
                  for c in (r.os_block, r.closed_leg, r.thrown_leg)]
        self.assertEqual(labels.count("OS South 19"), 2)     # Switch 19's own row and Switch 17's closed leg
        self.assertFalse(set(labels) & OLD)
        hands = {r.half: r.hand for r in railroad.read_switch_rows(path) if r.level in railroad.LEVEL_NUMBERS and r.hand}
        self.assertEqual(build_hands.apply(path, hands), path.read_text(encoding="utf-8"))

    def test_main_lines_name_the_renamed_track(self) -> None:
        import build_main_route
        rows = build_main_route.read_lines("staging", self.data / "schematic/main_lines.csv", self.names)
        stops = [s for r in rows for c in build_main_route.STOP_CELLS for s in build_main_route.split(r[c])]
        self.assertIn("35@Princess Lead", stops)
        self.assertNotIn("35@East Lead", stops)

    def test_a_stop_by_name_is_refused(self) -> None:
        import build_main_route
        with self.assertRaisesRegex(build_main_route.RouteError, "give its block id"):
            build_main_route.resolve_stop("35@East Lead", self.names, "here")



class RenameInPreferencesAndStations(unittest.TestCase):
    """Step 5b: preferences.json and stations.csv name tracks by block ID, so renaming Track S-1 and Track W-1 in the
    field file alone renames them wherever those files' tracks are read."""

    RENAMES = {("1", "block:17C-29C"): "Track South 1", ("1", "block:3B-end"): "Track Brick 1"}

    @classmethod
    def setUpClass(cls) -> None:
        from hartlib import track_names
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name)
        for name in (devices.GENERATED_FILE, devices.FIELD_FILE, "devices.columns.csv"):
            shutil.copy(paths.LAYOUT_DATA / name, cls.data / name)
        cls.schematic = cls.data / "schematic"
        shutil.copytree(paths.LAYOUT_DATA / "schematic", cls.schematic, symlinks=True)
        track_names.repo_inputs(cls.schematic)
        cls.before = {p.relative_to(cls.data): p.read_bytes() for p in cls.data.rglob("*") if p.is_file()}
        field = devices.field_path(cls.data)
        rows = list(csv.DictReader(io.StringIO(field.read_text(encoding="utf-8"))))
        hit = 0
        for r in rows:
            if (r["level"], r["id"]) in cls.RENAMES:
                r["user_name"] = cls.RENAMES[(r["level"], r["id"])]
                hit += 1
        assert hit == len(cls.RENAMES), hit
        field.write_text(devices.master_text(rows), encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_only_the_field_file_was_edited(self) -> None:
        changed = {str(k) for k, v in self.before.items() if (self.data / k).read_bytes() != v}
        self.assertEqual(changed, {devices.FIELD_FILE})

    def test_the_merged_preferences_take_the_new_names(self) -> None:
        from hartlib import layer_files
        got = layer_files.merged(self.schematic, "preferences")
        labels = got["staging"]["le_labels"]
        self.assertEqual(labels["name_columns"], [["S-R", "South 1", "S-2", "S-3", "S-4"]])
        self.assertEqual(labels["extra_follow"], [["Track Brick 1", "Track W-2"]])
        self.assertEqual(got["main_upper"]["track_labels"], {"Helix Outer": "McKees Rocks", "Helix Inner": "McKeesport"})
        self.assertEqual(layer_files.merged(self.schematic)["staging"]["left_end"], "Brick 1")

    def test_the_station_tracks_take_the_new_names(self) -> None:
        import build_staging_sets
        import device_map_inputs
        stations = self.schematic / "stations.csv"
        self.assertEqual(railroad.station_tracks(railroad.read_stations(stations), stations),
                         {"West Yard": ("Track Brick 1", "Track W-2")})
        _areas, sets = build_staging_sets.read_masters(stations, build_staging_sets.staging_switches())
        self.assertEqual(next(s.tracks for s in sets if s.name == "West Yard"), ("Brick 1", "W-2"))
        places = device_map_inputs.read_places(stations)
        self.assertEqual(places.tracks, {"Track Brick 1": ["West Yard"], "Track W-2": ["West Yard"]})


class RenameCrossoverHalf(unittest.TestCase):
    """A staging crossover half's OS block (OS Switch 23a, os:23:A-1A) is renamed by its field row alone: its letter
    is block_overrides.csv's crossover_half row's, by its ID, so the device master, the switch labels, the desk
    areas, the desk's half label and plate and the staging beans of tables.xml take the new name, and nothing reads
    a letter off it. The whole build on such a copy was run by hand (wiki/projects/naming-layers-handoff.md)."""

    ID, NEW, OLD = "os:23:A-1A", "OS East West", "OS Switch 23a"

    @classmethod
    def setUpClass(cls) -> None:
        from hartlib import track_names
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name)
        for name in (devices.GENERATED_FILE, devices.FIELD_FILE, "devices.columns.csv", "wiring.csv",
                     "block_lengths.csv", "block_lengths_measured.csv", "switches.csv"):
            shutil.copy(paths.LAYOUT_DATA / name, cls.data / name)
        cls.schematic = cls.data / "schematic"
        shutil.copytree(paths.LAYOUT_DATA / "schematic", cls.schematic, symlinks=True)
        track_names.repo_inputs(cls.schematic)
        cls.before = {p.relative_to(cls.data): p.read_bytes() for p in cls.data.rglob("*") if p.is_file()}
        field = devices.field_path(cls.data)
        rows = list(csv.DictReader(io.StringIO(field.read_text(encoding="utf-8"))))
        hit = [r for r in rows if (r["level"], r["id"]) == ("1", cls.ID)]
        assert len(hit) == 1 and hit[0]["user_name"] == cls.OLD, hit
        hit[0]["user_name"] = cls.NEW
        field.write_text(devices.master_text(rows), encoding="utf-8")
        cls.files = devices.Files.under(cls.data)
        cls.names = devices.user_names(cls.files)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def relabelled_switches(self) -> Path:
        """switches.csv as committed: it gives IDs only, so its rows read the renamed store beside it."""
        return self.data / "switches.csv"

    def test_only_the_field_file_was_edited(self) -> None:
        changed = {str(k) for k, v in self.before.items() if (self.data / k).read_bytes() != v}
        self.assertEqual(changed, {devices.FIELD_FILE})

    def test_the_merged_master_follows_the_rename(self) -> None:
        rows = devices.load(self.files)
        self.assertEqual(self.names[("1", self.ID)], self.NEW)
        det = next(r for r in rows if (r.level, r.id) == (1, "det:" + self.ID))
        self.assertEqual((det.user_name, det.blocks), ("BS Switch 23a", self.NEW))
        cells = [r.cells()[c] for r in rows for c in devices.BLOCK_REFS if r.level == 1]
        self.assertFalse([c for c in cells if self.OLD in c.split(devices.LIST)])
        self.assertIn(self.NEW, [r.protects for r in rows if r.id.startswith("mast:23:A-1A:")])

    def test_the_letter_comes_from_the_overrides_by_id(self) -> None:
        from hartlib import hand_lists
        letters = hand_lists.half_letters(self.schematic / hand_lists.OVERRIDES_NAME)
        self.assertEqual({k: v for k, v in letters.items() if k[1].startswith("os:23:")},
                         {("1", "os:23:A-1A"): "a", ("1", "os:23:A-31B"): "b"})
        rows = hand_lists.read_block_overrides(self.schematic / hand_lists.OVERRIDES_NAME, ("track",), self.names)
        self.assertNotIn(self.NEW, {r["block"] for r in rows})    # a track row's OS block by its generated name

    def test_switch_labels_and_desk_areas_follow(self) -> None:
        from hartlib import railroad_facts
        path = self.relabelled_switches()
        rows = [r for r in railroad.read_switch_rows(path) if r.level == 1 and r.switch == 23]
        self.assertEqual([(r.os_id, r.os_block) for r in rows],
                         [("os:23:A-1A", self.NEW), ("os:23:A-31B", "OS Switch 23b")])
        self.assertEqual(rows[1].thrown_leg, self.NEW)
        stations = self.schematic / "stations.csv"
        areas = {r["cp_name"]: r["switches"] for r in railroad_facts.station_group_rows(stations, path)}
        self.assertIn("23a,23b", areas["East End"])

    def test_the_desk_labels_and_plates_the_half_by_its_letter(self) -> None:
        import cats_panel
        from hartlib import hand_lists, railroad_facts
        path = self.relabelled_switches()
        sw = railroad_facts.staging_switches(railroad.read_switch_rows(path), path, self.files.master,
                                             railroad_facts.read_staging_rows(self.files))[23]
        letters = hand_lists.half_letters(self.schematic / hand_lists.OVERRIDES_NAME)
        self.assertEqual([cats_panel.half_label(sw, leg, letters) for leg in sw.legs], ["23A", "23B"])

        class F:
            switches, half_letters = {23: sw}, letters
        self.assertEqual(cats_panel.os_plates(F), {self.NEW: "23a", "OS Switch 23b": "23b"})

    def test_the_staging_beans_take_the_new_name(self) -> None:
        from hartlib import block_lengths, tables_build
        lengths = block_lengths.operating_lengths(self.data / "block_lengths.csv", self.files)
        beans = tables_build.master_beans([r.cells() for r in devices.load(self.files)], lengths, ("1",))
        names = {(e.tag, e.findtext("userName")) for section in beans.values() for e in section}
        self.assertIn(("block", self.NEW), names)
        self.assertFalse([n for n in names if n[1] == self.OLD])


class FollowAcrossLevels(unittest.TestCase):
    """A reference to a block of another level (a main mast facing a helix block of the upper level) follows that
    block's rename; one whose name a block of another level still has is left alone."""

    @staticmethod
    def row(level, layer, ident, name, **cells):
        r = dict.fromkeys(devices.COLUMNS, "")
        r.update(level=level, layer=layer, id=ident, user_name=name, **cells)
        return r

    def test_a_cross_level_reference_follows_by_id(self) -> None:
        gen = [self.row("3", "block", "block:131BB-helix", "Track Helix Inner"),
               self.row("2", "mast", "mast:131B:B:east", "Mast 132RB", facing="Track Helix Inner")]
        merged = [self.row("3", "block", "block:131BB-helix", "Track Up"), gen[1]]
        got = devices.follow_renames(merged, gen)
        self.assertEqual(got[1]["facing"], "Track Up")

    def test_a_name_another_level_still_has_is_kept(self) -> None:
        gen = [self.row("1", "block", "block:37B-helix", "Track Helix Inner"),
               self.row("3", "block", "block:131BB-helix", "Track Helix Inner"),
               self.row("2", "mast", "mast:131B:B:east", "Mast 132RB", facing="Track Helix Inner")]
        merged = [self.row("1", "block", "block:37B-helix", "Track Up"), gen[1], gen[2]]
        self.assertEqual(devices.follow_renames(merged, gen)[2]["facing"], "Track Helix Inner")


class OtherKeys(unittest.TestCase):
    """block_overrides.csv and block_numbering.csv name blocks by ID and come back by name."""

    def test_a_track_row_names_its_os_block_by_id(self) -> None:
        import block_override_rows as bor
        rows = bor.read_block_overrides(paths.LAYOUT_DATA / "schematic" / bor.OVERRIDES_NAME, ("track",))
        got = {r["id"]: r["block"] for r in rows}
        self.assertEqual(got["os:15"], "OS Switch 15")
        self.assertEqual(got["os:35:A-39A"], "OS Switch 35b")        # a half by its crossover_half row
        self.assertEqual(bor.os_block_name("1", "os:7:A-5B", {("1", "7", "5"): "OS Switch 7b"}), "OS Switch 7b")
        with self.assertRaisesRegex(bor.MapError, "no crossover_half row"):
            bor.os_block_name("1", "os:7:A-9B", {})
        with self.assertRaisesRegex(bor.MapError, "no OS block ID"):
            bor.os_block_name("1", "OS Switch 7", {})

    def test_a_double_crossover_corner_is_named_by_the_master(self) -> None:
        import block_override_rows as bor
        self.assertEqual(bor.os_block_name("3", "os:225:C", {}, {("3", "os:225:C"): "OS Switch 225a"}),
                         "OS Switch 225a")
        with self.assertRaisesRegex(bor.MapError, "no level 3 OS block"):
            bor.os_block_name("3", "os:225:D", {}, {})

    def test_le_tables_reads_its_numbering_on_first_use_not_at_import(self) -> None:
        import importlib
        import le_tables
        from unittest import mock
        with mock.patch.object(devices, "user_names", side_effect=devices.DevicesError("the master is broken")):
            mod = importlib.reload(le_tables)                   # importing it reads no master
            with self.assertRaisesRegex(devices.DevicesError, "the master is broken"):
                mod.numbering()
        importlib.reload(le_tables)
        self.assertIn("Track 107 Loop 2", le_tables.numbering().appended)
        self.assertEqual(le_tables.APPENDED_BLOCKS, le_tables.numbering().appended)     # the names build_layout_le re-exports
        self.assertEqual(le_tables.BLOCK_NUMBERED_AS, dict(le_tables.numbering().numbered_as))
        with self.assertRaises(AttributeError):
            le_tables.NOT_A_NAME  # noqa: B018

    def test_block_numbering_names_its_ids(self) -> None:
        import le_tables
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "block_numbering.csv"
            path.write_text("id,numbered_as,append_order,retired,notes\n"
                            "block:107B-107C#1,Track 107 Loop,,,\nblock:107B-107C#2,,1,,\n,,,Track 131-H1,\n",
                            encoding="utf-8")
            names = {("2", "block:107B-107C#1"): "Track Loop A", ("2", "block:107B-107C#2"): "Track Loop B"}
            got = le_tables.load_numbering(path, names)
            self.assertEqual((dict(got.numbered_as), got.appended, got.retired),
                             ({"Track Loop A": "Track 107 Loop"}, ("Track Loop B",), ("Track 131-H1",)))
            path.write_text("id,numbered_as,append_order,retired,notes\nblock:9X-9Y,,1,,\n", encoding="utf-8")
            with self.assertRaisesRegex(le_tables.BuildError, "no main or upper device"):
                le_tables.load_numbering(path, names)


if __name__ == "__main__":
    unittest.main()
