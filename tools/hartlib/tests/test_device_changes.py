"""hartlib.device_changes: a write of the device master held to the last generated file by device ID (naming-layers
step 4): new and gone IDs listed, a gone ID with owner's cells stops (decision 3), a rename lists the Operations Pro
copies of the old name (decision 5) and a mast rename warns (decision 6)."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import device_changes as C, devices as D  # noqa: E402
from test_devices import OTHER, mast, setUpModule, tearDownModule  # noqa: E402,F401
from test_devices_pair import field, generated  # noqa: E402

LOCATIONS = """<?xml version="1.0" encoding="UTF-8"?>
<operations-config>
  <location id="1" name="South Yard" comment="Mast 2L guards the throat">
    <track id="1s1" name="S-1" trackType="Yard"/>
    <track id="1s2" name="S-10" trackType="Yard" comment="not Mast 2LA"/>
  </location>
  <car id="S-1" roadNumber="S-1" comment="a car number, not a track"/>
  <location id="2" name="East End" comment="DCC Switch 3 is the alias" switch="Switch 3"/>
</operations-config>
"""


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.ops = self.tmp / "operations"
        self.ops.mkdir()
        (self.ops / "OperationsLocationRoster.xml").write_text(LOCATIONS, encoding="utf-8")


class TheComparison(unittest.TestCase):
    def test_new_gone_and_renamed_are_by_id(self):
        old = [mast(id="mast:1"), mast("Mast 4R", id="mast:2")]
        new = [mast("Mast 2LX", id="mast:1"), mast("Mast 6L", id="mast:3")]
        got = C.compare(old, new)
        self.assertEqual([r["id"] for r in got.new], ["mast:3"])
        self.assertEqual([r["id"] for r in got.gone], ["mast:2"])
        self.assertEqual([(o["user_name"], n["user_name"]) for o, n in got.renamed], [("Mast 2L", "Mast 2LX")])

    def test_the_same_rows_are_no_change(self):
        self.assertFalse(C.compare([mast()], [mast()]))


class TheOperationsCopies(Temp):
    def test_a_name_is_found_as_a_whole_word(self):
        self.assertEqual(C.ops_copies("Mast 2L", self.ops), ["OperationsLocationRoster.xml:3"])

    def test_a_track_is_found_by_its_bare_name_as_operations_pro_names_it(self):
        self.assertEqual(C.ops_copies("Track S-1", self.ops), ["OperationsLocationRoster.xml:4"])

    def test_a_bare_track_name_counts_only_as_a_track_or_location_name(self):
        """A car's id or road number of the same text is no copy of the track (code review, 2026-11-25)."""
        self.assertNotIn("OperationsLocationRoster.xml:7", C.ops_copies("Track S-1", self.ops))

    def test_the_tail_of_a_longer_name_is_no_copy(self):
        """"Switch 3" inside "DCC Switch 3" is the alias's name, not a copy of the turnout's; the bare "Switch 3"
        on the same line, an attribute of its own, is one."""
        self.assertEqual(C._quoted("Switch 3").findall("DCC Switch 3 is the alias"), [])
        self.assertEqual(C.ops_copies("Switch 3", self.ops), ["OperationsLocationRoster.xml:8"])
        self.assertEqual(C._quoted("Switch 3").findall('comment="Switch 3 here"'), ["Switch 3"])

    def test_no_folder_is_no_copy(self):
        self.assertEqual(C.ops_copies("Mast 2L", self.tmp / "none"), [])


class TheLines(Temp):
    def test_a_new_id_is_listed(self):
        got = C.lines(OTHER, C.compare([mast(id="mast:1")], [mast(id="mast:1"), mast("Mast 4R", id="m:2")]),
                      self.ops)
        self.assertEqual(got, [f"{OTHER}: 1 new ID(s) on level 1, mast: m:2"])

    def test_a_gone_id_with_no_owner_cells_is_listed(self):
        got = C.lines(OTHER, C.compare([mast(id="mast:1"), mast("Mast 4R", id="m:2")], [mast(id="mast:1")]),
                      self.ops)
        self.assertEqual(got, [f"{OTHER}: 1 gone ID(s) on level 1, mast: m:2"])

    def test_a_rename_lists_the_operations_pro_copies(self):
        got = C.lines("build_device_map.py", C.compare([generated(user_name="Track S-1", id="block:1")],
                                                       [generated(user_name="Track S-9", id="block:1")]), self.ops)
        self.assertEqual(got, ["build_device_map.py: id 'block:1' (level 1, turnout) is renamed 'Track S-1' -> "
                               "'Track S-9'; the Operations Pro files hold the old name at "
                               "OperationsLocationRoster.xml:4 (nothing rewrites them)"])

    def test_a_rename_with_no_copy_says_so(self):
        got = C.lines("build_device_map.py", C.compare([generated(id="switch:1")],
                                                       [generated(user_name="Switch One", id="switch:1")]), self.ops)
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0].endswith("no Operations Pro file holds the old name"), got[0])

    def test_a_mast_rename_warns_of_sml_discovery_and_approval(self):
        got = C.lines(OTHER, C.compare([mast(id="mast:1")], [mast("Mast 2LA", id="mast:1")]), self.ops)
        self.assertEqual(len(got), 2)
        self.assertIn("OperationsLocationRoster.xml:3", got[0])
        self.assertEqual(got[1], f"warning: {OTHER}: mast 'Mast 2L' is now 'Mast 2LA': JMRI keys Signal Mast "
                                 f"Logic by mast user name, so this needs a new SML discovery ({C.SML_DISCOVERY}) and "
                                 "the owner's panel approval")


class TheReport(Temp):
    def test_a_gone_id_with_owner_cells_stops_and_names_the_new_ids(self):
        old = [generated(id="switch:1")]
        new = [generated(id="switch:2", user_name="Switch 2")]
        with self.assertRaisesRegex(D.DevicesError, r"id 'switch:1' \(Switch 1 \(level 1, turnout\)\) is gone from "
                                                    r"the plan, and its field row holds user_name 'Switch 1', role "
                                                    r"'turnout', assignment 'field', dcc '100': move them "
                                                    r"to the device's new id \(new on level 1, turnout: switch:2\), "
                                                    r"or remove the row"):
            C.report("build_device_map.py", old, new, [field(id="switch:1")], lambda line: None, self.ops)

    def test_the_lines_go_to_warn(self):
        said = []
        C.report(OTHER, [mast(id="mast:1")], [mast("Mast 2LA", id="mast:1")], [], said.append, self.ops)
        self.assertEqual(len(said), 2)


class ThroughTheWriter(unittest.TestCase):
    """devices.outputs_after_rows reports every write against the last generated file."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        shutil.copyfile(D.Files.here().dictionary, self.tmp / "devices.columns.csv")
        self.files = D.Files.under(self.tmp)
        self.files.master.write_text(D.master_text([generated(), mast()]), encoding="utf-8")
        self.files.field.write_text(D.master_text([field()]), encoding="utf-8")

    def test_an_unchanged_write_says_nothing(self):
        said = []
        mine = [r.cells() for r in D.load(self.files) if r.written_by == OTHER]
        D.outputs_after_rows(OTHER, mine, self.files, said.append)
        self.assertEqual(said, [])

    def test_a_new_id_and_a_mast_rename_are_said(self):
        said = []
        mine = [dict(mast(), user_name="Mast 2LB"),
                mast("Mast 4R", id="mast:new", system_name="IF$vsm:basic:one-low($2)",
                     jmri_name="IF$vsm:basic:one-low($2)")]
        D.outputs_after_rows(OTHER, mine, self.files, said.append)
        self.assertEqual(said[0], f"{OTHER}: 1 new ID(s) on level 1, mast: mast:new")
        self.assertIn("is renamed 'Mast 2L' -> 'Mast 2LB'", said[1])
        self.assertTrue(said[2].startswith(f"warning: {OTHER}: mast 'Mast 2L' is now 'Mast 2LB'"), said[2])

    NEW = staticmethod(lambda **c: mast("Mast 4R", id="mast:new", **{"system_name": "IF$vsm:basic:one-low($2)",
                                                                    "jmri_name": "IF$vsm:basic:one-low($2)", **c}))

    def test_a_check_run_marks_its_lines_check_only(self):
        said = []
        D.outputs_after_rows(OTHER, [mast(), self.NEW()], self.files, said.append, check=True)
        self.assertEqual(said, [C.CHECK_ONLY + f"{OTHER}: 1 new ID(s) on level 1, mast: mast:new"])

    def test_a_write_that_does_not_merge_says_nothing(self):
        """Code review (2026-11-25): the changes are said once the write has merged back, never before a stop."""
        said = []
        clash = self.NEW(system_name=mast()["system_name"], jmri_name=mast()["jmri_name"])     # Mast 2L's name
        with self.assertRaisesRegex(D.DevicesError, "jmri_name .* as well"):
            D.outputs_after_rows(OTHER, [mast(), clash], self.files, said.append)
        self.assertEqual(said, [])

    def test_outputs_after_says_each_change_once(self):
        said = []
        rows = [dict(D.device_map_row(r), role=r["role"], id=r["id"]) for r in [mast(), self.NEW()]]
        D.outputs_after(OTHER, rows, self.files, warn=said.append)
        self.assertEqual(said, [f"{OTHER}: 1 new ID(s) on level 1, mast: mast:new"])

    def test_an_owner_rename_reaches_the_merged_view_and_is_said_when_the_builder_gives_it(self):
        """A staging device: the owner renames it in its field row (keyed by id), the builder takes the name from
        there, and the write says so."""
        self.files.field.write_text(D.master_text([field(user_name="Switch One", id="switch:1")]), encoding="utf-8")
        self.assertEqual(D.load(self.files)[0].user_name, "Switch One")
        said = []
        mine = [D.load(self.files)[0].cells()]
        out = D.outputs_after_rows("build_device_map.py", mine, self.files, said.append)
        self.assertIn(",Switch One,", out[self.files.master])           # the generated file names the row too
        self.assertEqual(len(said), 1)
        self.assertIn("is renamed 'Switch 1' -> 'Switch One'", said[0])


if __name__ == "__main__":
    unittest.main()
