"""hartlib.layer_files: one file per layer kind, a section per sheet, read and written in one format."""
import json
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import layer_files as L  # noqa: E402

SHEETS = ["staging", "main_upper"]       # publish_draft.INPUTS' layer stems


class RepoFiles(unittest.TestCase):
    def test_every_kind_is_one_file_with_both_sheets_and_no_per_sheet_file(self) -> None:
        for kind in L.KINDS:
            self.assertEqual(L.sheets(kind), SHEETS, kind)
            self.assertEqual(L.path(kind).read_text(encoding="utf-8"), L.dumps(L.read_file(kind)), kind)
        self.assertEqual(sorted(L.SCHEMATIC.glob("*.*.json")), [])

    def test_a_section_is_what_the_old_file_held(self) -> None:
        self.assertEqual(L.read("plan_overrides", "staging")["level"], 1)
        self.assertTrue(L.read("preferences", "main_upper")["revision"])
        self.assertIsInstance(L.read("signals", "staging")["signals"], list)

    def test_plugin_reads_the_same_sections(self) -> None:
        plugin = L.paths.REPO_ROOT / "external/model-railroad-skills/plugins/schematic-maps"
        if not (plugin / "schematic/layers.py").exists():
            self.skipTest("plugin submodule not checked out")
        sys.path.insert(0, str(plugin))
        try:
            from schematic import layers
        finally:
            sys.path.remove(str(plugin))
        if not hasattr(layers, "read_layer"):
            self.skipTest("plugin older than 0.1.49")
        for kind in L.KINDS:
            for sheet in SHEETS:
                self.assertEqual(layers.read_layer(sheet, kind, L.SCHEMATIC), L.read(kind, sheet), (kind, sheet))


class Temp(unittest.TestCase):
    def setUp(self) -> None:
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data)
        self.put("plan_overrides", {"_sections": True, "_note": "n", "staging": {"a": 1}, "main_upper": {"b": [2]}})

    def put(self, kind: str, whole) -> Path:
        p = self.data / f"{kind}.json"
        p.write_text(json.dumps(whole) if not isinstance(whole, str) else whole, encoding="utf-8")
        return p

    def fails(self, call, pattern: str) -> None:
        with self.assertRaisesRegex(L.LayerFileError, pattern):
            call()

    def test_read_and_sheets(self) -> None:
        self.assertEqual(L.read("plan_overrides", "main_upper", self.data), {"b": [2]})
        self.assertEqual(L.sheets("plan_overrides", self.data), SHEETS)
        self.assertEqual(L.Section("plan_overrides", "staging", self.data).read(), {"a": 1})
        self.assertEqual(L.Section("plan_overrides", "staging", self.data).name, "plan_overrides.json[staging]")

    def test_texts_replace_one_section_and_keep_the_rest(self) -> None:
        got = L.texts({("plan_overrides", "staging"): {"a": 3}}, self.data)
        p = self.data / "plan_overrides.json"
        self.assertEqual(list(got), [p])
        self.assertEqual(got[p], L.dumps({"_sections": True, "_note": "n", "staging": {"a": 3}, "main_upper": {"b": [2]}}))
        self.assertEqual(got[p], '{\n "_sections": true,\n "_note": "n",\n "staging": {\n  "a": 3\n },\n'
                                 ' "main_upper": {\n  "b": [\n   2\n  ]\n }\n}\n')

    def test_write_two_sections_at_once_and_only_when_changed(self) -> None:
        p = self.data / "plan_overrides.json"
        self.assertEqual(L.write({("plan_overrides", "staging"): {"a": 4}, ("plan_overrides", "main_upper"): {"é": 5}},
                                 self.data), [p])
        self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["main_upper"], {"é": 5})
        self.assertIn("é", p.read_text(encoding="utf-8"))           # written as UTF-8, not escaped
        before = p.stat().st_mtime_ns
        self.assertEqual(L.write({("plan_overrides", "staging"): {"a": 4}}, self.data), [])
        self.assertEqual(p.stat().st_mtime_ns, before)
        self.assertFalse(L.Section("plan_overrides", "staging", self.data).write({"a": 4}))
        self.assertTrue(L.Section("plan_overrides", "staging", self.data).write({"a": 5}))

    def test_section_of_text(self) -> None:
        s = L.Section("plan_overrides", "main_upper", self.data)
        self.assertEqual(s.of(L.dumps({"_sections": True, "main_upper": {"r": 7}}), "x@main"), {"r": 7})
        self.fails(lambda: s.of('{"revision": 7}', "x@main"), r"x@main: not a layer file of sections")
        self.assertIn('"x": 1', s.text_with({"x": 1}))

    def test_unknown_kind(self) -> None:
        self.fails(lambda: L.path("hints", self.data), "layer kind 'hints': the layer files are plan_overrides")
        self.fails(lambda: L.read("overrides", "staging", self.data), "layer kind 'overrides'")

    def test_missing_file(self) -> None:
        self.fails(lambda: L.read("preferences", "staging", self.data), r"preferences.json: cannot be read")

    def test_bad_json_and_not_sections(self) -> None:
        self.put("plan_overrides", "{")
        self.fails(lambda: L.read("plan_overrides", "staging", self.data), "plan_overrides.json: not JSON")
        self.put("plan_overrides", {"staging": {}})
        self.fails(lambda: L.read("plan_overrides", "staging", self.data), '"_sections": true')
        self.put("plan_overrides", {"_sections": "yes", "staging": {}})
        self.fails(lambda: L.read("plan_overrides", "staging", self.data), '"_sections": true')
        self.put("plan_overrides", [1])
        self.fails(lambda: L.read("plan_overrides", "staging", self.data), "not a layer file of sections")

    def test_a_section_that_is_not_an_object(self) -> None:
        self.put("plan_overrides", {"_sections": True, "staging": [], "main_upper": {}, "_n": "notes may be text"})
        self.fails(lambda: L.read("plan_overrides", "main_upper", self.data), r"section\(s\) staging are not objects")

    def test_missing_section_is_an_error_not_empty(self) -> None:
        self.fails(lambda: L.read("plan_overrides", "upper", self.data), "no section 'upper' .it has staging, main_upper")
        self.fails(lambda: L.texts({("plan_overrides", "upper"): {}}, self.data), "no section 'upper'")

    def test_a_note_key_is_no_sheet(self) -> None:
        self.fails(lambda: L.read("plan_overrides", "_note", self.data), "'_note' is no sheet name")
        self.fails(lambda: L.texts({("plan_overrides", "_note"): {}}, self.data), "is no sheet name")

    def test_a_new_section_must_be_an_object(self) -> None:
        self.fails(lambda: L.texts({("plan_overrides", "staging"): [1]}, self.data),
                   "section 'staging': must be an object, not list")

    def test_an_old_per_sheet_file_beside_it_stops(self) -> None:
        (self.data / "staging.plan_overrides.json").write_text("{}", encoding="utf-8")
        self.fails(lambda: L.read("plan_overrides", "main_upper", self.data),
                   "staging.plan_overrides.json beside plan_overrides.json: move each into its section")
        self.fails(lambda: L.write({("plan_overrides", "main_upper"): {}}, self.data), "beside plan_overrides.json")


# what the three builders write (T6b): the keys that moved out of plan_overrides.json into plan_generated.json
MOVED = {"staging": ["stations", "control_points", "station_tracks", "_control_points", "milepost_route", "_main_lines"],
         "main_upper": ["control_points", "stations", "_control_points", "main_route"]}


def split_one_file(whole: dict) -> tuple[dict, dict]:
    """The one-file plan_overrides of before T6b as (hand, generated), the way the migration cut it."""
    hand, gen = json.loads(json.dumps(whole)), {"_sections": True, "staging": {}, "main_upper": {}}
    for sheet, keys in MOVED.items():
        for k in keys:
            gen[sheet][k] = hand[sheet].pop(k)
    named = [e for e in hand["staging"]["edits"] if e["op"] == "name"]
    gen["staging"][L.NAME_MAIN] = []
    for i, t in enumerate(named[0]["tracks"]):
        if "main" in t[3:]:
            gen["staging"][L.NAME_MAIN].append(i)
            t[:] = [x for j, x in enumerate(t) if j < 3 or x != "main"]
    return hand, gen


class PlanGenerated(unittest.TestCase):
    ONE_FILE = Path(__file__).resolve().parent / "fixtures" / "plan_overrides_one_file.json"

    def test_the_merged_view_is_the_one_file_it_was_cut_from(self) -> None:
        whole = json.loads(self.ONE_FILE.read_text(encoding="utf-8"))
        hand, gen = split_one_file(whole)
        self.assertFalse(set(gen["staging"]) & set(hand["staging"]))
        self.assertEqual(L.merge(hand, gen), whole)

    def test_a_hand_value_wins_and_a_generated_key_is_never_taken_from_the_hand_file(self) -> None:
        merged = L.merge({"_sections": True, "staging": {"a": 1, "edits": []}},
                         {"_sections": True, "staging": {"a": 2, "b": 3}})
        self.assertEqual(merged["staging"], {"a": 1, "edits": [], "b": 3})

    def test_a_hand_main_flag_is_dropped_and_only_the_generated_ones_stand(self) -> None:
        hand = {"_sections": True, "staging": {"edits": [{"op": "name", "tracks": [["1", "2", "x", "main"], ["2", "3", "y", "A"]]}]}}
        merged = L.merge(hand, {"_sections": True, "staging": {L.NAME_MAIN: [1]}})
        self.assertEqual(merged["staging"]["edits"][0]["tracks"], [["1", "2", "x"], ["2", "3", "y", "A", "main"]])
        self.assertIn("main", hand["staging"]["edits"][0]["tracks"][0])        # the hand data is not changed
        self.assertNotIn(L.NAME_MAIN, merged["staging"])

    def test_a_generated_section_with_no_hand_section_or_edits_is_a_layer_error(self) -> None:
        self.assertEqual(L.merge({"_sections": True}, {"_sections": True, "main_upper": {"a": 1}})["main_upper"], {"a": 1})
        with self.assertRaisesRegex(L.LayerFileError, "needs one `name` edit"):
            L.merge({"_sections": True}, {"_sections": True, "staging": {L.NAME_MAIN: [0]}})

    def test_a_flag_past_the_name_edit_stops(self) -> None:
        hand = {"_sections": True, "staging": {"edits": [{"op": "name", "tracks": [["1", "2", "x"]]}]}}
        with self.assertRaisesRegex(L.LayerFileError, "track 4 is past the 1"):
            L.merge(hand, {"_sections": True, "staging": {L.NAME_MAIN: [4]}})

    def test_the_repo_files_merge_to_a_whole_view_and_the_hand_file_has_no_generated_key(self) -> None:
        hand = L.read_file("plan_overrides")
        for sheet, keys in MOVED.items():
            self.assertEqual([k for k in keys if k in hand[sheet]], [], sheet)
        merged = L.merged()
        self.assertEqual(L.merged_section("staging"), merged["staging"])
        self.assertIn("main_route", merged["main_upper"])
        self.assertIn("milepost_route", merged["staging"])

    def test_a_generated_write_replaces_its_keys_only_and_never_touches_the_hand_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            hand, gen = split_one_file(json.loads(self.ONE_FILE.read_text(encoding="utf-8")))
            (data / "plan_overrides.json").write_text(L.dumps(hand), encoding="utf-8")
            (data / "plan_generated.json").write_text(L.dumps(gen), encoding="utf-8")
            before = (data / "plan_overrides.json").read_bytes()
            changed = L.write_generated({"main_upper": {"main_route": [["a", "b", "direct"]]}}, data)
            self.assertEqual([p.name for p in changed], ["plan_generated.json"])
            self.assertEqual((data / "plan_overrides.json").read_bytes(), before)
            now = L.read("plan_generated", "main_upper", data)
            self.assertEqual(now["main_route"], [["a", "b", "direct"]])
            self.assertEqual(now["control_points"], gen["main_upper"]["control_points"])
            self.assertEqual(L.read("plan_generated", "staging", data), gen["staging"])
            with self.assertRaisesRegex(L.LayerFileError, "written key by key"):
                L.texts({("plan_generated", "staging"): {}}, data)

    def test_a_folder_without_a_generated_file_has_nothing_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            whole = {"_sections": True, "staging": {"a": 1}}
            (Path(tmp) / "plan_overrides.json").write_text(L.dumps(whole), encoding="utf-8")
            self.assertEqual(L.merged(Path(tmp)), whole)
            self.assertEqual(L.view(Path(tmp)), Path(tmp).resolve())

    def test_the_plugin_folder_holds_the_merged_file_and_is_left_alone_when_nothing_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as cache:
            data = Path(tmp)
            hand, gen = split_one_file(json.loads(self.ONE_FILE.read_text(encoding="utf-8")))
            (data / "plan_overrides.json").write_text(L.dumps(hand), encoding="utf-8")
            (data / "plan_generated.json").write_text(L.dumps(gen), encoding="utf-8")
            (data / "preferences.json").write_text("{}", encoding="utf-8")
            with unittest.mock.patch.dict("os.environ", {"HART_CACHE_DIR": cache}):
                folder = L.view(data)
                self.assertEqual(json.loads((folder / "plan_overrides.json").read_text(encoding="utf-8")),
                                 L.merged(data))
                self.assertTrue((folder / "preferences.json").is_symlink())
                self.assertFalse((folder / "plan_generated.json").exists())
                stamp = (folder / "plan_overrides.json").stat().st_mtime_ns
                self.assertEqual(L.view(data), folder)
                self.assertEqual((folder / "plan_overrides.json").stat().st_mtime_ns, stamp)


if __name__ == "__main__":
    unittest.main()
