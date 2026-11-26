"""tools/ops/check_json.py: the repo's four build-input JSON files pass their schemas, and a missing required key or a
wrong type fails with the file and the key path named; the panel_items schema keeps panel_items.py's field lists."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("check_json", ROOT / "tools/ops/check_json.py")
J = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(J)

PLAN, PREFS, ITEMS = J.PLAN_OVERRIDES_FILE, J.PREFERENCES_FILE, J.PANEL_ITEMS_FILE
PUBLISHED = "www/scripts/published-files.json"


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


class RepoFiles(unittest.TestCase):
    def test_every_file_passes(self):
        for rel in J.SCHEMAS:
            with self.subTest(rel):
                self.assertEqual(J.check_file(rel), [])

    def test_main_checks_them_all(self):
        self.assertEqual(J.main([]), 0)


class Broken(unittest.TestCase):
    """A copy of a repo file with one edit, written under a temporary root, checked with the file's schema."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def broken(self, rel: str, edit) -> list[str]:
        data = copy.deepcopy(load(rel))
        edit(data)
        out = self.root / Path(rel).name
        out.write_text(json.dumps(data), encoding="utf-8")
        return J.check_file(rel, path=out)        # a published source is looked up in the repo

    def assertNamed(self, found: list[str], rel: str, path: str, words: str) -> None:
        hits = [p for p in found if p.startswith(f"{rel}: {path}: ") and words in p]
        self.assertTrue(hits, f"no problem '{rel}: {path}: ...{words}...' in {found}")

    # plan_overrides.json
    def test_plan_missing_required_key(self):
        found = self.broken(PLAN, lambda d: d["staging"].pop("scale_ratio"))
        self.assertNamed(found, PLAN, "staging.scale_ratio", "is required")

    def test_plan_wrong_type(self):
        found = self.broken(PLAN, lambda d: d["main_upper"]["levels"]["bands"][0].update(level="2"))
        self.assertNamed(found, PLAN, "main_upper.levels.bands[0].level", "must be a whole number, not text")

    def test_plan_sections_flag(self):
        found = self.broken(PLAN, lambda d: d.pop("_sections"))
        self.assertNamed(found, PLAN, "_sections", "is required")

    def test_plan_relabel_needs_a_map(self):
        def edit(d):
            next(e for e in d["staging"]["edits"] if e["op"] == "relabel").pop("map")
        self.assertNamed(self.broken(PLAN, edit), PLAN, "staging.edits[0]", "needs a map")

    # preferences.json
    def test_prefs_missing_required_key(self):
        found = self.broken(PREFS, lambda d: d["main_upper"].pop("revision"))
        self.assertNamed(found, PREFS, "main_upper.revision", "is required")

    def test_prefs_wrong_type(self):
        found = self.broken(PREFS, lambda d: d["main_upper"]["host_screen"].update(size=[1920, "1080"]))
        self.assertNamed(found, PREFS, "main_upper.host_screen.size[1]", "must be a whole number, not text")

    def test_prefs_revision_is_not_a_bool(self):
        found = self.broken(PREFS, lambda d: d["main_upper"].update(revision=True))
        self.assertNamed(found, PREFS, "main_upper.revision", "not true or false")

    def test_prefs_staging_detail_sheets_are_generated(self):
        found = self.broken(PREFS, lambda d: d["staging"].update(detail_sheets={}))
        self.assertNamed(found, PREFS, "staging.detail_sheets", "is generated")

    def test_prefs_window_keys_are_host_screens(self):
        found = self.broken(PREFS, lambda d: d["staging"].update(le_window=[1, 1]))
        self.assertNamed(found, PREFS, "staging", "le_window is set from host_screen")

    # panel_items.json
    def test_items_missing_required_key(self):
        found = self.broken(ITEMS, lambda d: d["items"][0].pop("anchor"))
        self.assertNamed(found, ITEMS, "items[0].anchor", "is required")

    def test_items_wrong_type(self):
        found = self.broken(ITEMS, lambda d: d["items"][0]["anchor"].update(dx="9"))
        self.assertNamed(found, ITEMS, "items[0].anchor.dx", "must be a number, not text")

    def test_items_unknown_field_and_duplicate_id(self):
        def edit(d):
            d["items"][0]["colour"] = "red"
            d["items"].append(copy.deepcopy(d["items"][1]))
        found = self.broken(ITEMS, edit)
        self.assertNamed(found, ITEMS, "items[0].colour", "is not a key here")
        self.assertNamed(found, ITEMS, f"items[{len(load(ITEMS)['items'])}].id", "is given twice")

    def test_items_build_attributes(self):
        found = self.broken(ITEMS, lambda d: d["attributes"].update(panelwidth="9"))
        self.assertNamed(found, ITEMS, "attributes", "panelwidth are the build's to set")

    # published-files.json
    def test_published_missing_source(self):
        found = self.broken(PUBLISHED, lambda d: d.update({"assets/x.png": "docs/no/such/file.png"}))
        self.assertNamed(found, PUBLISHED, '"assets/x.png"', "is not a file in the repo")

    def test_published_wrong_type(self):
        found = self.broken(PUBLISHED, lambda d: d.update({"assets/x.png": ["docs/ops"]}))
        self.assertNamed(found, PUBLISHED, '"assets/x.png"', "must be text, not an array")

    def test_published_site_path_outside_the_site(self):
        found = self.broken(PUBLISHED, lambda d: d.update({"../x.png": next(iter(d.values()))}))
        self.assertNamed(found, PUBLISHED, '"../x.png" (the key)', "not a path inside the site")


class Checker(unittest.TestCase):
    def test_missing_file_and_bad_json_name_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIn("x.json: cannot read it", J.check_file("x.json", root, J.PANEL_ITEMS)[0])
            (root / "x.json").write_text("{", encoding="utf-8")
            self.assertIn("x.json: not JSON", J.check_file("x.json", root, J.PANEL_ITEMS)[0])

    def test_notes_are_free_unless_closed(self):
        open_obj, shut = J.obj({"a": J.whole()}), J.obj({"a": J.whole()}, closed=True)
        self.assertEqual(J.problems({"a": 1, "_note": 3}, open_obj), [])
        self.assertEqual(J.problems({"a": 1, "_note": 3}, shut), ["_note: is not a key here (keys: a)"])

    def test_unknown_file_is_refused(self):
        self.assertEqual(J.main(["www/data/crew.json"]), 2)


class PanelItemsAgree(unittest.TestCase):
    """The schema's field lists are panel_items.py's, so the two cannot drift apart."""

    def test_field_lists(self):
        sys.path.insert(0, str(ROOT / "tools/schematic"))
        try:
            import panel_items as pi
        finally:
            sys.path.remove(str(ROOT / "tools/schematic"))
        self.assertEqual(set(J.ITEM["keys"]), pi.ITEM_FIELDS)
        self.assertEqual(set(J.MEMBER["keys"]), pi.MEMBER_FIELDS)
        self.assertEqual(set(J.ANCHOR["keys"]), pi.ANCHOR_FIELDS)
        self.assertEqual(set(J.PANEL_ITEMS["keys"]), pi.FILE_FIELDS)
        self.assertEqual(set(J.SET_BY_BUILD), pi.SET_BY_BUILD)
        self.assertEqual(J.POINTS, tuple(pi.POINTS))


if __name__ == "__main__":
    unittest.main()
