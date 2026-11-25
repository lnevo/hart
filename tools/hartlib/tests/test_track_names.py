"""hartlib.track_names: the owner's track names, kept by block ID in devices_field.csv, reach the plugin's `name` and
`end` edits and `left_end` through the merged plan view; plan_overrides.json holds none (naming-layers step 3)."""
from __future__ import annotations

import csv
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import layer_files as L  # noqa: E402
from hartlib import track_names as T  # noqa: E402

# the owner's staging names as plan_overrides.json held them before step 3, by run (one name per plan track)
STAGING = {"1A-23A": "Main West", "23B-35B": "West Ext", "15B-23B": "S-R", "17C-29C": "S-1", "19C-27C": "S-2",
           "21B-25B": "S-4", "21C-25C": "S-3", "33A-35A": "East Lead", "1C-5A": "Brick-Plane",
           "37C-39C": ["K-2", "K-1"], "5B-7A": "East Ext", "7B-33C": "Main East", "5C-7B": "Scale", "7A-13C": "Barn"}
ENDS = {("3", "B"): "W-1", ("3", "C"): "W-2", ("11", "B"): "EH-1", ("9", "B"): "EH-2", ("9", "C"): "EH-3",
        ("39", "B"): "Helix Outer", ("37", "B"): "Helix Inner"}
MAIN = {"1A-23A", "1C-5A", "23B-35B", "33A-35A", "35A-39A", "35B-37A", "5B-7A", "7B-33C"}


def staging_view(data: Path = T.SCHEMATIC) -> dict:
    return L.merged(data)["staging"]


class Repo(unittest.TestCase):
    """The repo's view gives the plugin every name the hand file used to, by the plan's junctions."""

    def test_the_hand_file_holds_no_track_name(self) -> None:
        for sheet in T.PLAN_GRAPHS:
            self.assertEqual(T.hand_problems(L.read("plan_overrides", sheet)), [], sheet)

    def test_the_name_edit_names_each_owner_run_and_flags_the_main_lines(self) -> None:
        sec = staging_view()
        runs = T.plan_runs("staging", sec)
        at = {(lo[0], lo[1], hi[0]): run for run, hits in runs.items() for lo, hi in hits}
        tracks = next(e for e in sec["edits"] if e["op"] == "name")["tracks"]
        got = {at[(a, leg, b)]: (name, "main" in rest) for a, b, name, leg, *rest in tracks}
        self.assertEqual({r: n for r, (n, _m) in got.items() if n}, STAGING)
        self.assertEqual({r for r, (_n, m) in got.items() if m}, MAIN)
        self.assertEqual(set(got), set(STAGING) | MAIN)
        self.assertEqual([e["op"] for e in sec["edits"]], ["relabel", "name", "end"])

    def test_each_track_end_and_the_left_end_take_their_block_rows_names(self) -> None:
        sec = staging_view()
        ends = next(e for e in sec["edits"] if e["op"] == "end")["ends"]
        self.assertEqual({(r, p): n for r, p, n, _k, _t in ends}, ENDS)
        self.assertEqual(sec["left_end"], "W-1")

    def test_main_and_upper_have_no_owner_names_yet(self) -> None:
        self.assertFalse(any(e["op"] == "name" for e in L.merged()["main_upper"]["edits"]))


class Copy(unittest.TestCase):
    """A copy of the layout data: a rename is one field row; a wrong row stops with its reason."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data = root / "schematic"
        shutil.copytree(T.SCHEMATIC, self.data, symlinks=True)
        shutil.copy(T.SCHEMATIC.parent / T.FIELD_FILE, root / T.FIELD_FILE)
        self.field = root / T.FIELD_FILE

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def edit_field(self, fn) -> None:
        rows = list(csv.DictReader(io.StringIO(self.field.read_text(encoding="utf-8"))))
        fn(rows)
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        self.field.write_text(out.getvalue(), encoding="utf-8")

    def by_name(self, rows, name):
        return next(r for r in rows if r["level"] == "1" and r["user_name"] == name)

    def test_a_rename_in_the_field_file_is_the_drawn_name(self) -> None:
        self.edit_field(lambda rows: self.by_name(rows, "Track S-1").update(user_name="Track Old Main"))
        tracks = next(e for e in staging_view(self.data)["edits"] if e["op"] == "name")["tracks"]
        self.assertIn("Old Main", [t[2] for t in tracks])
        self.assertNotIn("S-1", [t[2] for t in tracks])
        self.assertEqual(L.read_file("plan_overrides", self.data), L.read_file("plan_overrides"))

    def test_a_name_left_in_plan_overrides_stops(self) -> None:
        whole = L.read_file("plan_overrides", self.data)
        whole["staging"]["edits"].append({"op": "name", "tracks": [["17", "29", "S-1"]]})
        L.path("plan_overrides", self.data).write_text(L.dumps(whole), encoding="utf-8")
        with self.assertRaisesRegex(L.LayerFileError, r"plan_overrides.json\[staging\]: a `name` edit"):
            L.merged(self.data)

    def test_an_id_no_plan_track_has_stops(self) -> None:
        self.edit_field(lambda rows: self.by_name(rows, "Track S-1").update(id="block:17C-31C"))
        with self.assertRaisesRegex(L.LayerFileError, "run 17C-31C: no plan tracks run there"):
            L.merged(self.data)

    def test_a_track_end_with_no_named_row_stops(self) -> None:
        self.edit_field(lambda rows: self.by_name(rows, "Track W-1").update(id=""))
        with self.assertRaisesRegex(L.LayerFileError, r"no named block row block:3B-end"):
            L.merged(self.data)

    def test_old_index_flags_ask_for_build_main_route(self) -> None:
        L.write_generated({"staging": {L.NAME_MAIN: [0, 1]}}, self.data)
        with self.assertRaisesRegex(L.LayerFileError, "run python3 tools/schematic/build_main_route.py"):
            L.merged(self.data)


class Pieces(unittest.TestCase):
    """The pieces of one run: one name, a list in piece order, or a stop."""

    def names(self, owner):
        return T._names_of_runs(owner, {"1"})

    def test_pieces_with_one_name_are_one_name_and_different_names_a_list_from_the_lower_end(self) -> None:
        self.assertEqual(self.names({("1", "block:1C-5A#1+1C-5A#2"): "Brick-Plane"}), {"1C-5A": "Brick-Plane"})
        self.assertEqual(self.names({("1", "block:37C-39C#2"): "K-1", ("1", "block:37C-39C#1"): "K-2"}),
                         {"37C-39C": ["K-2", "K-1"]})

    def test_a_name_on_part_of_a_piece_or_a_missing_piece_stops(self) -> None:
        with self.assertRaisesRegex(T.TrackNameError, "a name on part of a piece"):
            self.names({("1", "block:1B-3A:1/2"): "x"})
        with self.assertRaisesRegex(T.TrackNameError, r"pieces \[1, 3\] are named"):
            self.names({("1", "block:2A-4A#1"): "x", ("1", "block:2A-4A#3"): "y"})

    def test_another_levels_names_are_not_this_sections(self) -> None:
        self.assertEqual(self.names({("2", "block:101B-103A"): "x"}), {})

    def test_a_run_is_its_ends_lower_first(self) -> None:
        self.assertEqual(T.run_of("39C", "37C"), "37C-39C")
        self.assertEqual(T.run_of("end", "3B"), "3B-end")
        self.assertEqual(T.run_of("103BA", "103AB"), "103AB-103BA")


class HandProblems(unittest.TestCase):
    def test_each_kind_of_name_in_a_hand_section_is_named(self) -> None:
        got = T.hand_problems({"edits": [{"op": "name", "tracks": []},
                                         {"op": "end", "ends": [["3", "B", "W-1", "bumper", ""]]}],
                               "left_end": "W-1"})
        self.assertEqual(len(got), 3)
        self.assertEqual(T.hand_problems({"edits": [{"op": "end", "ends": [["3", "B", "bumper", ""]]}],
                                          "left_end": "block:3B-end"}), [])


if __name__ == "__main__":
    unittest.main()
