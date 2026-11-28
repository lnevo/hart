"""hartlib.track_names: the owner's track names, kept by block ID in devices_field.csv, reach the plugin's `name` and
`end` edits and `left_end` through the merged plan view; plan_overrides.json holds none (naming-layers step 3)."""
from __future__ import annotations

import csv
import io
import shutil
import sys
import tempfile
import unittest
import unittest.mock
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
        shutil.copy(T.SCHEMATIC.parent / "devices_generated.csv", root / "devices_generated.csv")
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


    def test_build_main_route_reads_the_plan_without_its_own_flags(self) -> None:
        """A stale name_main (a run the plan no longer has) stops every reader but the script that rewrites it."""
        L.write_generated({"staging": {L.NAME_MAIN: ["17C-31C"]}}, self.data)
        with self.assertRaisesRegex(L.LayerFileError, "run 17C-31C"):
            L.merged(self.data)
        self.assertTrue(any(e["op"] == "name" for e in L.merged(self.data, main=False)["staging"]["edits"]))

    def test_a_helix_rename_is_one_field_row(self) -> None:
        self.edit_field(lambda rows: self.by_name(rows, "Track Helix Outer").update(user_name="Track Helix Big"))
        whole = L.merged(self.data)
        self.assertEqual(whole["main_upper"]["helix"]["131A"], "Helix Big")
        ends = next(e for e in whole["staging"]["edits"] if e["op"] == "end")["ends"]
        self.assertIn("Helix Big", [e[2] for e in ends])

    def test_with_no_generated_file_the_plugin_still_gets_the_names(self) -> None:
        L.path(L.GENERATED, self.data).unlink()
        (self.data / "preferences_generated.json").unlink(missing_ok=True)
        with tempfile.TemporaryDirectory() as cache, unittest.mock.patch.dict("os.environ", {"HART_CACHE_DIR": cache}):
            folder = L.view(self.data)
            self.assertNotEqual(folder, self.data.resolve())
            got = L.parse((folder / "plan_overrides.json").read_text(encoding="utf-8"), "plan_overrides", "view")
        self.assertEqual(got["staging"]["left_end"], "W-1")

    def test_a_rename_reaches_the_preferences_with_no_edit_there(self) -> None:
        """preferences.json names tracks by block ID (step 5b): renaming Track S-1 and Track W-1 in the field file
        renames them in the merged preferences the plugin reads, and preferences.json is left as it is."""
        hand = L.path("preferences", self.data).read_bytes()
        self.edit_field(lambda rows: self.by_name(rows, "Track S-1").update(user_name="Track South 1"))
        self.edit_field(lambda rows: self.by_name(rows, "Track W-1").update(user_name="Track Brick 1"))
        got = L.merged(self.data, "preferences")["staging"]
        self.assertEqual(got["le_labels"]["name_columns"], [["S-R", "South 1", "S-2", "S-3", "S-4"]])
        self.assertEqual(got["le_labels"]["extra_follow"], [["Track Brick 1", "Track W-2"]])
        self.assertEqual(L.path("preferences", self.data).read_bytes(), hand)

    def test_a_name_put_back_in_preferences_stops(self) -> None:
        whole = L.read_file("preferences", self.data)
        whole["staging"]["turnbacks"] = ["Brick-Plane"]
        whole["main_upper"]["le_band_labels"]["Main"]["numbers_below"] = ["Track 101-103"]
        L.path("preferences", self.data).write_text(L.dumps(whole), encoding="utf-8")
        with self.assertRaisesRegex(L.LayerFileError, r"preferences.json\[staging\]: turnbacks\[0\] is 'Brick-Plane', "
                                                      r"not a block ID"):
            L.merged(self.data, "preferences")
        whole["staging"]["turnbacks"] = ["block:1C-5A#1+1C-5A#2"]
        L.path("preferences", self.data).write_text(L.dumps(whole), encoding="utf-8")
        with self.assertRaisesRegex(L.LayerFileError, r"preferences.json\[main_upper\]: le_band_labels.Main.numbers_below"
                                                      r"\[0\] names 'Track 101-103'"):
            L.merged(self.data, "preferences")

    def test_an_id_the_store_has_not_is_kept_until_the_device_master_check(self) -> None:
        # the generated names are device-map's output: the view keeps an unnamed ID, the check after it stops on it
        self.assertEqual(L.unnamed_preferences(self.data), [])
        whole = L.read_file("preferences", self.data)
        whole["main_upper"]["le_band_labels"]["Main"]["optional_block_contents"].append("block:199A-199B")
        L.path("preferences", self.data).write_text(L.dumps(whole), encoding="utf-8")
        got = L.merged(self.data, "preferences")["main_upper"]["le_band_labels"]["Main"]["optional_block_contents"]
        self.assertEqual(got[-1], "block:199A-199B")
        self.assertIn("Track 101-103", got)
        bad = L.unnamed_preferences(self.data)
        self.assertEqual(len(bad), 1)
        self.assertRegex(bad[0], r"preferences.json\[main_upper\].*block:199A-199B is no block on level 2/3")

    def test_a_staging_id_in_a_main_upper_track_key_is_no_block_there(self) -> None:
        whole = L.read_file("preferences", self.data)
        whole["main_upper"]["le_band_labels"]["Main"]["hidden_names"] = ["block:3B-end"]
        L.path("preferences", self.data).write_text(L.dumps(whole), encoding="utf-8")
        self.assertRegex(L.unnamed_preferences(self.data)[0], "block:3B-end is no block on level 2/3")


class PrefSection(unittest.TestCase):
    """The track keys of a preferences section and the form each takes (step 5b)."""

    NAMES = {"block:5C-7B": "Track Scale", "block:9B-end": "Track EH-2", "block:39B-helix": "Track Helix Outer",
             "block:1B-3A:1/2": "Track 1-3 at 1"}

    def test_each_key_takes_its_form(self) -> None:
        sec = {"min_cells": [["5", "7", 5, "block:5C-7B"], ["7", "13", 4]], "turnbacks": ["block:5C-7B"],
               "track_labels": {"block:39B-helix": "McKees Rocks"}, "title": ["Staging level"],
               "le_labels": {"extra_steps": [["block:9B-end"]], "name_steps": [["block:9B-end"]],
                             "optional_block_contents": ["block:1B-3A:1/2"]},
               "le_band_labels": {"Main": {"hidden_names": ["block:5C-7B"], "numbers_below": ["101"],
                                           "names_first": ["block:9B-end"]}}}
        got = T.pref_section("staging", sec, self.NAMES)
        self.assertEqual(got["min_cells"], [["5", "7", 5, "Scale"], ["7", "13", 4]])
        self.assertEqual(got["turnbacks"], ["Scale"])
        self.assertEqual(got["track_labels"], {"Helix Outer": "McKees Rocks"})
        self.assertEqual(got["le_labels"], {"extra_steps": [["Track EH-2"]], "name_steps": [["EH-2"]],
                                            "optional_block_contents": ["Track 1-3 at 1"]})
        self.assertEqual(got["le_band_labels"]["Main"], {"hidden_names": ["Scale"], "numbers_below": ["101"],
                                                         "names_first": ["EH-2"]})
        self.assertEqual(T.pref_ids(sec), set(self.NAMES))
        self.assertEqual(T.pref_problems(sec), [])
        self.assertEqual(sec["turnbacks"], ["block:5C-7B"])          # the section given is not changed

    def test_a_section_with_no_id_reads_no_store(self) -> None:
        sec = {"title": ["Main levels"], "min_cells": [["105", "103B", 6]]}
        self.assertIs(T.pref_section("main_upper", sec, data=Path("/nowhere")), sec)

    def test_names_by_id_prefers_the_owners_and_reads_the_generated_file_only_for_the_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "schematic").mkdir()
            (root / T.FIELD_FILE).write_text("level,layer,id,user_name\n1,block,block:3B-end,Track Brick 1\n",
                                             encoding="utf-8")
            self.assertEqual(T.names_by_id({"block:3B-end"}, root / "schematic"), {"block:3B-end": "Track Brick 1"})
            with self.assertRaisesRegex(T.TrackNameError, "devices_generated.csv is missing"):
                T.names_by_id({"block:3C-end"}, root / "schematic")
            (root / "devices_generated.csv").write_text(
                "level,layer,id,user_name\n1,block,block:3B-end,Track W-1\n1,block,block:3C-end,Track W-2\n",
                encoding="utf-8")
            self.assertEqual(T.names_by_id({"block:3B-end", "block:3C-end"}, root / "schematic", "here"),
                             {"block:3B-end": "Track Brick 1", "block:3C-end": "Track W-2"})

            with self.assertRaisesRegex(T.TrackNameError, "here: block:3D-end is no block"):
                T.names_by_id({"block:3D-end"}, root / "schematic", "here", missing=T.STOP)
            self.assertEqual(T.names_by_id({"block:3D-end"}, root / "schematic", missing=T.KEEP), {})

    def test_an_id_on_two_levels_is_a_clash_unless_the_levels_are_given(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "schematic").mkdir()
            (root / T.FIELD_FILE).write_text("level,layer,id,user_name\n", encoding="utf-8")
            (root / "devices_generated.csv").write_text(
                "level,layer,id,user_name\n2,block,block:1A-3B,Track 1-3\n3,block,block:1A-3B,Track Up 1-3\n",
                encoding="utf-8")
            with self.assertRaisesRegex(T.TrackNameError, "block:1A-3B is a block of levels 2 and 3"):
                T.names_by_id({"block:1A-3B"}, root / "schematic")
            self.assertEqual(T.names_by_id({"block:1A-3B"}, root / "schematic", levels={"3"}),
                             {"block:1A-3B": "Track Up 1-3"})

    def test_two_labels_for_one_track_stop(self) -> None:
        sec = {"track_labels": {"block:39B-helix": "A", "block:39X-helix": "B"}}
        with self.assertRaisesRegex(T.TrackNameError, "both 'Helix Outer'"):
            T.pref_section("main_upper", sec, {"block:39B-helix": "Track Helix Outer",
                                               "block:39X-helix": "Track Helix Outer"})

    def test_a_track_key_of_the_wrong_shape_is_a_problem(self) -> None:
        sec = {"le_labels": {"extra_follow": ["block:3B-end"], "hidden_names": "block:3B-end"},
               "track_labels": ["block:39B-helix"], "turnbacks": "S-1"}
        got = T.pref_problems(sec)
        self.assertIn("le_labels.extra_follow[0] is 'block:3B-end', not a list of tracks", got)
        self.assertIn("le_labels.hidden_names is 'block:3B-end', not a list of tracks", got)
        self.assertIn("turnbacks is 'S-1', not a list of tracks", got)
        self.assertTrue(any(p.startswith("track_labels is") for p in got), got)

    def test_problems_name_each_wrong_value_once_and_scan_the_keys_as_written(self) -> None:
        got = T.pref_problems({"turnbacks": ["Track S-1"], "track_labels": {"Helix Outer": "McKees Rocks"},
                               "other": {"Track X": 1}})
        self.assertEqual(len([p for p in got if "turnbacks[0]" in p]), 1)
        self.assertIn("track_labels key 'Helix Outer' is 'Helix Outer', not a block ID (block:...; the track's name "
                      "is its row's in devices_field.csv)", got)
        self.assertTrue(any("key 'Track X'" in p for p in got), got)


class LabelTrackKeys(unittest.TestCase):
    """label_track_keys.csv: the label options that list tracks, read and checked."""

    def write(self, text: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "label_track_keys.csv"
        path.write_text(text, encoding="utf-8")
        return path

    def test_the_repo_file_reads_and_holds_names_first(self) -> None:
        got = T.label_track_keys()
        self.assertEqual(got["names_first"], (1, T.BARE))
        self.assertEqual(got["extra_steps"], (2, T.WHOLE))

    def test_rows_read_as_depth_and_form(self) -> None:
        path = self.write("key,depth,form,notes\nhidden_names,1,bare,x\nname_steps,2,bare,\n")
        self.assertEqual(T.label_track_keys(path), {"hidden_names": (1, "bare"), "name_steps": (2, "bare")})

    def test_a_bad_file_stops_naming_the_line(self) -> None:
        cases = [("key,depth\nx,1\n", "form"),
                 ("key,depth,form,notes\nx,3,bare,\n", "line 2: x: depth must be 1 or 2"),
                 ("key,depth,form,notes\nx,1,short,\n", "line 2: x: depth must be 1 or 2 and form"),
                 ("key,depth,form,notes\nx,1,bare,\nx,2,bare,\n", "line 3: key 'x' is empty or given twice")]
        for text, msg in cases:
            with self.subTest(msg=msg), self.assertRaisesRegex(T.TrackNameError, msg):
                T.label_track_keys(self.write(text))


class EarlyReturn(unittest.TestCase):
    def test_an_end_edit_is_filled_or_stops_even_with_no_other_names(self) -> None:
        sec = {"level": 2, "edits": [{"op": "end", "ends": [["209", "B", "bumper", ""]]}]}
        with self.assertRaisesRegex(T.TrackNameError, "no named block row block:209B-end"):
            T.plugin_section("main_upper", sec, owner={})


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


class ByPiece(unittest.TestCase):
    """piece_names: what the readers by ID (block_layer, cats_panel, build_masts) take a drawn strand's name from."""

    OWNER = {("1", "block:17C-29C"): "S-1", ("1", "block:1C-5A#1+1C-5A#2"): "Brick-Plane",
             ("1", "block:37C-39C#2"): "K-1", ("1", "block:37C-39C#1"): "K-2", ("1", "block:39B-helix"): "Helix Outer"}

    def test_each_piece_takes_its_runs_name_or_its_own(self) -> None:
        got = T.piece_names({"level": 1}, ["17C-29C", "1C-5A #1", "1C-5A #2", "37C-39C #1", "37C-39C #2",
                                           "39B-helix", "19C-27C"], owner=self.OWNER)
        self.assertEqual(got, {"17C-29C": "S-1", "1C-5A #1": "Brick-Plane", "1C-5A #2": "Brick-Plane",
                               "37C-39C #1": "K-2", "37C-39C #2": "K-1", "39B-helix": "Helix Outer"})

    def test_a_helix_track_on_another_level_takes_its_staging_blocks_name(self) -> None:
        sec = {"level": 2, "edits": [{"op": "relabel", "map": {"T131A": "131A"}}], "helix": {"T131A": "block:39B-helix"}}
        self.assertEqual(T.piece_names(sec, ["131AA-helix", "131BB-helix", "101B-103A"], owner=self.OWNER),
                         {"131AA-helix": "Helix Outer"})
        with self.assertRaisesRegex(T.TrackNameError, "helix T131A: block:37B-helix has no named block row"):
            T.piece_names({**sec, "helix": {"T131A": "block:37B-helix"}}, [], owner=self.OWNER)

    def test_a_piece_its_run_is_not_named_by_stops(self) -> None:
        with self.assertRaisesRegex(T.TrackNameError, "piece 37C-39C: its run is named by piece"):
            T.piece_names({"level": 1}, ["37C-39C"], owner=self.OWNER)

    def test_a_name_is_never_spread_to_a_piece_the_owner_did_not_name(self) -> None:
        with self.assertRaisesRegex(T.TrackNameError, r"pieces \[2\] are named, not every piece from #1"):
            T.piece_names({"level": 1}, ["37C-39C #1", "37C-39C #2"], owner={("1", "block:37C-39C#2"): "K-1"})
        with self.assertRaisesRegex(T.TrackNameError, r"piece 37C-39C #2: its run is named by piece \(#1 K-2\)"):
            T.piece_names({"level": 1}, ["37C-39C #1", "37C-39C #2"], owner={("1", "block:37C-39C#1"): "K-2"})
        self.assertEqual(T.piece_names({"level": 1}, ["37C-39C #1", "37C-39C #2"],
                                       owner={("1", "block:37C-39C#1"): "K", ("1", "block:37C-39C#2"): "K"}),
                         {"37C-39C #1": "K", "37C-39C #2": "K"})

    def test_two_tracks_up_the_helix_from_one_switch_stop(self) -> None:
        sec = {"level": 2, "helix": {"131A": "block:39B-helix"}}
        with self.assertRaisesRegex(T.TrackNameError, "helix track from switch 131A: 2 drawn tracks"):
            T.piece_names(sec, ["131AA-helix", "131AB-helix"], owner=self.OWNER)


class EndKeys(unittest.TestCase):
    def test_one_end_key_for_the_plan_and_the_main_lines(self) -> None:
        nodes = {"a": {"kind": "switch", "label": "23*"}, "b": {"kind": "end", "sub": "helix"},
                 "c": {"kind": "end"}, "d": {"kind": "switch"}}
        self.assertEqual(T.end_key(nodes["a"], "B", "a"), "23B")
        self.assertEqual(T.end_key(nodes["d"], "A", "d"), "dA")
        self.assertEqual(T.end_key(nodes["b"], "", "b"), "helix")
        self.assertEqual(T.end_key(nodes["b"], "", "b", helix=False), "end")
        self.assertEqual(T.edge_run(nodes, {"u": "b", "up": "", "v": "a", "vp": "B"}), "23B-helix")
        self.assertEqual(T.edge_run(nodes, {"u": "c", "up": "", "v": "a", "vp": "C"}, helix_ends={"c"}), "23C-helix")

    def test_end_order_pins_stagings_run_flip_order(self) -> None:
        """staging_device_map flips a run so its ends read in end_order: by switch number, then half letter, then
        leg, and a switch leg before any other end."""
        self.assertLess(T.end_order("101BA"), T.end_order("111C"))
        self.assertLess(T.end_order("121AC"), T.end_order("121BA"))
        self.assertLess(T.end_order("103AB"), T.end_order("103BA"))
        self.assertLess(T.end_order("229A"), T.end_order("helix"))


class Inputs(unittest.TestCase):
    """The store reads only the folder it is given; a test opts in to the repo's plan graphs and owner rows."""

    def test_a_missing_field_file_or_plan_graph_stops_and_repo_inputs_opts_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "schematic"
            data.mkdir()
            with self.assertRaisesRegex(T.TrackNameError, "the owner's rows .*devices_field.csv is missing"):
                T.owner_names(data)
            with self.assertRaisesRegex(T.TrackNameError, "the plan graph .*staging.json is missing"):
                T.plan_runs("staging", {}, data)
            self.assertEqual(T.repo_inputs(data), data)
            self.assertEqual(T.owner_names(data), T.owner_names())
            self.assertEqual(T.plan_runs("staging", {}, data), T.plan_runs("staging", {}))

    def test_a_section_that_draws_no_level_and_names_nothing_needs_no_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(T.plugin_section("staging", {"a": 1}, data=Path(tmp)), {"a": 1})


class HandProblems(unittest.TestCase):
    def test_each_kind_of_name_in_a_hand_section_is_named(self) -> None:
        got = T.hand_problems({"edits": [{"op": "name", "tracks": []},
                                         {"op": "end", "ends": [["3", "B", "W-1", "bumper", ""]]}],
                               "left_end": "W-1"})
        self.assertEqual(len(got), 3)
        self.assertEqual(T.hand_problems({"edits": [{"op": "end", "ends": [["3", "B", "bumper", ""]]}],
                                          "left_end": "block:3B-end"}), [])


class PlanSwitches(unittest.TestCase):
    """plan_switches: the switches of a plan graph by number, labelled by the relabel edit (naming-layers step 7)."""

    def test_the_staging_plan_has_its_twenty_switches(self) -> None:
        got = T.plan_switches("staging", L.read("plan_overrides", "staging", T.SCHEMATIC))
        self.assertEqual(list(got), [str(n) for n in range(1, 40, 2)])
        self.assertEqual((got["7"], got["35"], got["1"]), (["7", "7"], ["35", "35"], ["1"]))   # a crossover's halves

    def test_a_switch_the_relabel_edit_leaves_unnumbered_stops(self) -> None:
        section = {"edits": []}                     # no relabel edit: the plan's own labels (T33) are no numbers
        with self.assertRaisesRegex(T.TrackNameError, r"has label 'T\d+', no switch number"):
            T.plan_switches("staging", section)


if __name__ == "__main__":
    unittest.main()
