"""hartlib.devices over its two files (ADR-029 amendment 2026-11-21): devices_generated.csv, the builders' rows, and
devices_field.csv, the owner's cells keyed by (level, layer, user_name), merged into the one view every reader gets."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import devices as D  # noqa: E402
from test_devices import BEAN, blank, mast, turnout, unplaced  # noqa: E402


def generated(**cells) -> dict:
    """A staging turnout as build_device_map.py writes it: its field cells (cp, dcc, role, assignment) left empty."""
    return turnout(**{"role": "", "assignment": "", "dcc": "", "written_by": "build_device_map.py", **cells})


def field(user="Switch 1", **cells) -> dict:
    """The field row of the staging turnout `user`: its key and the owner's cells."""
    return blank(**{"level": "1", "layer": "turnout", "user_name": user, "role": "turnout", "assignment": "field",
                    "dcc": "100", "cp": "Brick", **cells})


def block(**cells) -> dict:
    return blank(**{**dict(level="1", layer="block", role="os", user_name="OS Switch 1", assignment="field",
                           system_name="IB:AUTO:0033", jmri_name="IB:AUTO:0033", layout_block="ILB33",
                           jmri_comment="Brick CP, Switch 1; occupancy Block 4-2 / M2S401",
                           written_by="build_device_map.py", description="Block."), **cells})


def merged(g, f):
    return [dict(r) for r in D.merge(g, f)]


class TheMerge(unittest.TestCase):
    def test_a_field_cell_overrides_the_generated_one(self):
        got = merged([generated(notes="the rule's")], [field(notes="the owner's")])
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["notes"], got[0]["dcc"], got[0]["role"], got[0]["cp"]),
                         ("the owner's", "100", "turnout", "Brick"))
        self.assertEqual(got[0]["written_by"], "build_device_map.py")     # every other cell is the generated row's

    def test_an_empty_field_cell_means_no_override(self):
        got = merged([generated(notes="the rule's", trial_name="Switch 1")], [field()])
        self.assertEqual((got[0]["notes"], got[0]["trial_name"]), ("the rule's", "Switch 1"))

    def test_a_row_with_no_field_row_is_the_generated_row(self):
        self.assertEqual(merged([mast()], []), [mast()])

    def test_a_field_cell_outside_the_field_columns_is_refused(self):
        for col in ("wiring", "description", "facing", "jmri_bean"):
            with self.subTest(col), self.assertRaisesRegex(D.DevicesError, rf"{col} set; a field row holds only"):
                D.merge([generated()], [field(**{col: "x"})])

    def test_a_field_row_with_a_writer_is_refused(self):
        with self.assertRaisesRegex(D.DevicesError, "a field row has no writer"):
            D.merge([generated()], [field(written_by="build_device_map.py")])

    def test_a_keyed_field_row_with_no_generated_row_is_refused(self):
        with self.assertRaisesRegex(D.DevicesError, r"Switch 9 \(level 1, turnout\) has no row in "
                                                    r"devices_generated\.csv .*rename the field row .* or remove it"):
            D.merge([generated()], [field(), field("Switch 9")])

    def test_a_key_twice_in_the_field_file_is_refused(self):
        with self.assertRaisesRegex(D.DevicesError, "the key is twice"):
            D.merge([generated()], [field(), field()])

    def test_a_level_less_store_row_is_appended_after_every_level(self):
        got = merged([generated()], [field(), unplaced()])
        self.assertEqual([r["user_name"] for r in got], ["Switch 1", "Test 999"])
        self.assertEqual(got[1]["jmri_bean"], BEAN)

    def test_rows_are_sorted_into_the_masters_order(self):
        got = merged([generated(), mast()], [field()])
        self.assertEqual([r["layer"] for r in got], ["turnout", "mast"])

    def test_the_merged_view_is_checked(self):
        with self.assertRaisesRegex(D.DevicesError, "field, but system_name"):
            D.merge([generated()], [field(jmri_name="M2T999")])

    def test_a_generated_row_with_no_writer_or_level_is_refused_in_the_generated_file(self):
        with self.assertRaisesRegex(D.DevicesError, "written_by '' is not one of"):
            D.check_generated([generated(written_by="")])
        with self.assertRaisesRegex(D.DevicesError, "a level-less device .* is kept in devices_field.csv"):
            D.check_generated([unplaced()])

    def test_field_rows_out_of_order_are_refused(self):
        with self.assertRaisesRegex(D.DevicesError, "out of order"):
            D.check_field([blank(level="1", layer="mast", user_name="Mast 6LB", node="4"), field()])


class TheOccupancyMark(unittest.TestCase):
    """A wired block's comment: the owner's words in the field file, the detector's wiring.csv text filled in by the
    builder, so a moved pin changes no hand file."""
    F = blank(level="1", layer="block", user_name="OS Switch 1", role="os", assignment="field",
              jmri_comment="Brick CP, Switch 1; {occupancy}")

    def test_the_generated_comment_stands_when_it_fills_the_mark(self):
        got = merged([block(role="", assignment="")], [self.F])
        self.assertEqual(got[0]["jmri_comment"], "Brick CP, Switch 1; occupancy Block 4-2 / M2S401")

    def test_a_generated_comment_that_does_not_follow_the_owners_words_is_refused(self):
        with self.assertRaisesRegex(D.DevicesError, r"needs its \{occupancy\} filled"):
            D.merge([block(jmri_comment="Brick, Switch 1; occupancy Block 4-2 / M2S401")], [self.F])

    def test_fill_and_unmerge_keep_the_composed_comment(self):
        self.assertEqual(D.fill_occupancy(self.F["jmri_comment"], "occupancy Block 4-3 / M2S402"),
                         "Brick CP, Switch 1; occupancy Block 4-3 / M2S402")
        out = D.unmerge([block()], [self.F])
        self.assertEqual(out[0]["jmri_comment"], block()["jmri_comment"])
        self.assertEqual((out[0]["role"], out[0]["assignment"]), ("", ""))


class TheUnmerge(unittest.TestCase):
    def test_the_field_cells_are_left_empty(self):
        out = D.unmerge([turnout(cp="Brick", written_by="build_device_map.py")], [field()])
        self.assertEqual((out[0]["cp"], out[0]["dcc"], out[0]["role"], out[0]["assignment"]), ("", "", "", ""))
        self.assertEqual(out[0]["system_name"], "M2T408")

    def test_a_builder_value_other_than_the_owners_is_refused(self):
        with self.assertRaisesRegex(D.DevicesError, r"gives Switch 1 \(level 1, turnout\) dcc '101', but "
                                                    r"devices_field.csv holds '100'"):
            D.unmerge([turnout(dcc="101", cp="Brick", written_by="build_device_map.py")], [field()])

    def test_level_less_rows_stay_out_of_the_generated_file(self):
        self.assertEqual(D.unmerge([unplaced()], [unplaced()]), [])

    def test_redundant_cells_are_reported(self):
        got = D.redundant([generated(notes="same")], [field(notes="same")])
        self.assertEqual(len(got), 1)
        self.assertIn("notes 'same' is the generated value too", got[0])


class KeyedMessages(unittest.TestCase):
    """A message names a row by its key and the file that holds it, never a line (the view is two files)."""

    def test_a_staging_device_is_named_in_the_field_file_and_a_built_one_in_the_generated_file(self):
        rows = {D.key_of(r): r for r in D.load()}
        self.assertEqual(D.at(rows["1", "turnout", "Switch 1"]), "devices_field.csv: Switch 1 (level 1, turnout)")
        self.assertEqual(D.at(rows["2", "turnout", "Switch 101"]),
                         "devices_generated.csv: Switch 101 (level 2, turnout)")
        self.assertEqual(D.key_text(("", "turnout", "Test 999")), "Test 999 (no level, turnout)")

    def test_check_rows_names_keys_not_lines(self):
        with self.assertRaises(D.DevicesError) as cm:
            D.check_rows([turnout(), turnout(description="")])
        text = str(cm.exception)
        self.assertIn("Switch 1 (level 1, turnout): description is empty", text)
        self.assertNotIn("line ", text)


class ThePair(unittest.TestCase):
    """load, index, field_index, outputs_after and the writers over a copy of the two files."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        shutil.copyfile(D.Files.here().dictionary, self.tmp / "devices.columns.csv")
        self.files = D.Files(D.master_path(self.tmp), self.tmp / "devices.columns.csv", D.field_path(self.tmp))
        self.files.master.write_text(D.master_text([generated(), mast()]), encoding="utf-8")
        self.files.field.write_text(D.master_text([field(), unplaced()]), encoding="utf-8")

    def test_load_merges_the_two_files(self):
        rows = D.load(self.files)
        self.assertEqual([r["user_name"] for r in rows], ["Switch 1", "Mast 2L", "Test 999"])
        self.assertEqual(rows[0]["dcc"], "100")
        self.assertEqual(D.index(self.files).role("turnout", "Switch 1"), "turnout")

    def test_a_path_finds_the_field_file_beside_it(self):
        self.assertEqual(D.load(self.files.master), D.load(self.files))

    def test_the_cache_is_keyed_on_both_files(self):
        self.assertEqual(D.load(self.files)[0]["notes"], "")
        self.files.field.write_text(D.master_text([field(notes="new"), unplaced()]), encoding="utf-8")
        self.assertEqual(D.load(self.files)[0]["notes"], "new")
        self.files.master.write_text(D.master_text([generated(trial_name="T"), mast()]), encoding="utf-8")
        self.assertEqual(D.load(self.files)[0]["trial_name"], "T")

    def test_field_index_is_the_field_files_keyed_rows(self):
        got = D.field_index(self.files)
        self.assertEqual(list(got), [("1", "turnout", "Switch 1")])
        self.assertEqual(got["1", "turnout", "Switch 1"]["dcc"], "100")

    def test_allocated_names_are_the_generated_rows(self):
        got = D.allocated_names(("1",), "mast", files=self.files)
        self.assertEqual(got["Mast 2L"]["jmri_name"], "IF$vsm:basic:one-low($1)")

    def test_a_writer_writes_the_generated_file_with_the_field_cells_left_empty(self):
        mine = [dict(r) for r in D.load(self.files) if r["written_by"] == "build_device_map.py"]
        out = D.outputs_after_rows("build_device_map.py", mine, self.files)
        self.assertEqual(list(out), [self.files.master])
        self.assertEqual(out[self.files.master], self.files.master.read_text(encoding="utf-8"))   # unchanged

    def test_a_writer_that_overrides_a_field_cell_is_refused(self):
        mine = [dict(r, dcc="7") for r in D.load(self.files) if r["written_by"] == "build_device_map.py"]
        with self.assertRaisesRegex(D.DevicesError, "devices_field.csv holds '100'"):
            D.outputs_after_rows("build_device_map.py", mine, self.files)

    def test_a_writer_that_drops_a_key_the_field_file_names_is_refused(self):
        self.files.field.write_text(D.master_text([field(), blank(level="1", layer="mast", user_name="Mast 2L",
                                                                 notes="the owner's"), unplaced()]), encoding="utf-8")
        with self.assertRaisesRegex(D.DevicesError, r"Mast 2L \(level 1, mast\) has no row in .*rename the "
                                                    "field row"):
            D.outputs_after_rows("build_masts.py", [], self.files)

    def test_another_writers_rows_are_kept_as_written(self):
        mine = [dict(r, notes="moved") for r in D.load(self.files) if r["written_by"] == "build_masts.py"]
        text = D.outputs_after_rows("build_masts.py", mine, self.files)[self.files.master]
        self.assertIn(D.master_text([generated()]).splitlines()[1], text.splitlines())

    def test_write_field_and_write_generated_check_the_pair_first(self):
        with self.assertRaisesRegex(D.DevicesError, "has no row in"):
            D.write_field([field(), field("Switch 9", cp="Brick")], self.files)
        with self.assertRaisesRegex(D.DevicesError, "has no row in"):
            D.write_generated([mast()], self.files)
        D.write_field([field(notes="kept")], self.files)
        self.assertEqual(D.load(self.files)[0]["notes"], "kept")
        self.assertEqual(len(D.load(self.files)), 2)              # the Store row went with the rewrite

    def test_a_generated_path_with_no_field_file_beside_it_is_refused(self):
        self.files.field.unlink()
        with self.assertRaisesRegex(D.DevicesError, "devices_field.csv is missing beside it"):
            D.load(self.files.master)
        with self.assertRaisesRegex(D.DevicesError, "a one-file copy takes another name"):
            D.one_file_copy(self.files.master)

    def test_a_field_row_with_a_writer_is_refused_not_ranked(self):
        with self.assertRaisesRegex(D.DevicesError, "written_by 'other.py'; a field row has no writer"):
            D.check_field([field(), field("Switch 3", written_by="other.py")])

    def test_a_missing_field_file_is_an_error_once_it_is_named(self):
        self.files.field.unlink()
        with self.assertRaisesRegex(D.DevicesError, "cannot read it"):
            D.load(self.files)


if __name__ == "__main__":
    unittest.main()
