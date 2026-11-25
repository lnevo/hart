"""A rename in devices_field.csv alone reaches every file keyed by device ID (naming-layers step 5).

A copy of the committed data renames a staging track (Track East Lead, block:33A-35A) and a staging OS block (OS
Switch 19, os:19) in its field file, as the owner would, and nothing else; then:
- the merged device master follows the renames into part_of and blocks (hartlib.devices.follow_renames);
- wiring.csv names the detectors by the new names (hartlib.wiring.read, by id);
- block_lengths.csv's labels come out renamed and its lengths unchanged (plan_lengths.labelled);
- switches.csv's staging labels come out renamed (build_hands.apply);
- main_lines.csv's stop 35@block:33A-35A reads 35@Princess Lead (build_main_route.read_lines).
The whole build on such a copy was run by hand for the step (wiki/projects/naming-layers-handoff.md, step 5
findings); this pins the readers without the schematic plugin.
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
                     "block_lengths.csv", "switches.csv"):
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
        part = next(r for r in rows if r["level"] == "1" and r["user_name"] == "Track 19-21")
        self.assertEqual(part["part_of"], "OS South 19")
        cells = [r[c] for r in rows for c in devices.BLOCK_REFS if r["level"] == "1"]
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

    def test_block_lengths_relabel_and_keep_their_lengths(self) -> None:
        import plan_lengths
        text = plan_lengths.labelled(self.data / "block_lengths.csv", self.files)
        rows = {(r["level"], r["id"]): r for r in csv.DictReader(io.StringIO(text))}
        old = {(r["level"], r["id"]): r for r in csv.DictReader(io.StringIO(self.before["block_lengths.csv"].decode()))}
        for key, name in RENAMES.items():
            self.assertEqual(rows[key]["user_name"], name)
            self.assertEqual({k: v for k, v in rows[key].items() if k != "user_name"},
                             {k: v for k, v in old[key].items() if k != "user_name"})
        self.assertEqual(len(rows), len(old))

    def test_switches_csv_labels_follow_the_store(self) -> None:
        import build_hands
        path = self.data / "switches.csv"
        hands = {r.half: r.hand for r in railroad.read_switch_rows(path) if r.level in railroad.LEVEL_NUMBERS and r.hand}
        text = build_hands.apply(path, hands, self.names)
        labels = [c for r in csv.DictReader(io.StringIO(text)) if r["level"] == "1"
                  for c in (r["os_block"], r["closed_leg"], r["thrown_leg"])]
        self.assertEqual(labels.count("OS South 19"), 2)     # Switch 19's own row and Switch 17's closed leg
        self.assertFalse(set(labels) & OLD)

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
        import mast_rule
        rows = mast_rule.read_block_overrides(paths.LAYOUT_DATA / "schematic" / mast_rule.OVERRIDES_NAME, ("track",))
        got = {r["id"]: r["block"] for r in rows}
        self.assertEqual(got["os:15"], "OS Switch 15")
        self.assertEqual(got["os:35:A-39A"], "OS Switch 35b")        # a half by its crossover_half row
        self.assertEqual(mast_rule.os_block_name("1", "os:7:A-5B", {("1", "7", "5"): "OS Switch 7b"}), "OS Switch 7b")
        with self.assertRaisesRegex(mast_rule.MapError, "no crossover_half row"):
            mast_rule.os_block_name("1", "os:7:A-9B", {})
        with self.assertRaisesRegex(mast_rule.MapError, "no OS block ID"):
            mast_rule.os_block_name("1", "OS Switch 7", {})

    def test_a_double_crossover_corner_is_named_by_the_master(self) -> None:
        import mast_rule
        self.assertEqual(mast_rule.os_block_name("3", "os:225:C", {}, {("3", "os:225:C"): "OS Switch 225a"}),
                         "OS Switch 225a")
        with self.assertRaisesRegex(mast_rule.MapError, "no level 3 OS block"):
            mast_rule.os_block_name("3", "os:225:D", {}, {})

    def test_le_tables_reads_its_numbering_on_first_use_not_at_import(self) -> None:
        import importlib
        import le_tables
        from unittest import mock
        with mock.patch.object(devices, "user_names", side_effect=devices.DevicesError("the master is broken")):
            mod = importlib.reload(le_tables)                   # importing it reads no master
            with self.assertRaisesRegex(devices.DevicesError, "the master is broken"):
                mod.numbering()
        importlib.reload(le_tables)
        self.assertIn("Track 107 Loop 2", le_tables.numbering()[1])

    def test_block_numbering_names_its_ids(self) -> None:
        import le_tables
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "block_numbering.csv"
            path.write_text("id,numbered_as,append_order,retired,notes\n"
                            "block:107B-107C#1,Track 107 Loop,,,\nblock:107B-107C#2,,1,,\n,,,Track 131-H1,\n",
                            encoding="utf-8")
            names = {("2", "block:107B-107C#1"): "Track Loop A", ("2", "block:107B-107C#2"): "Track Loop B"}
            self.assertEqual(le_tables.load_numbering(path, names),
                             ({"Track Loop A": "Track 107 Loop"}, ("Track Loop B",), ("Track 131-H1",)))
            path.write_text("id,numbered_as,append_order,retired,notes\nblock:9X-9Y,,1,,\n", encoding="utf-8")
            with self.assertRaisesRegex(le_tables.BuildError, "no main or upper device"):
                le_tables.load_numbering(path, names)


if __name__ == "__main__":
    unittest.main()
