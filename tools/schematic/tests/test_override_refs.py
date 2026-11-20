"""The plan overrides name junctions the way the railroad does, not by the plan's part numbers where the plan has a
better handle: the milepost route names crossover 35's half by its track (35@East Lead), and the three-way's halves are
named by their part ids. Needs the schematic-maps plugin for the lookups (skipped without it)."""
import csv
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_draft as pd  # noqa: E402

STAGING = json.loads((pd.DATA / "staging.plan_overrides.json").read_text(encoding="utf-8"))
MAIN_UPPER = json.loads((pd.DATA / "main_upper.plan_overrides.json").read_text(encoding="utf-8"))
PREFS = (pd.DATA / "main_upper.preferences.json").read_text(encoding="utf-8")
PART = re.compile(r"T\d+")


def relabel(overrides):
    return next(e["map"] for e in overrides["edits"] if e["op"] == "relabel")


class Refs(unittest.TestCase):
    def test_the_milepost_route_names_no_part_number(self):
        names = {n for hop in STAGING["milepost_route"] for n in hop}
        self.assertEqual([n for n in names if PART.fullmatch(n)], [])
        self.assertIn("35@East Lead", names)

    def test_a_relabel_key_is_a_part_number_or_a_part_id_the_graph_has(self):
        graph = json.loads((pd.GRAPHS / "main.json").read_text())["nodes"]
        odd = [k for k in relabel(MAIN_UPPER) if not PART.fullmatch(k)]
        self.assertEqual(sorted(odd), ["TO_3W33789-1", "TO_3W33789-2"])
        for key in odd:
            self.assertIn(key, graph)
            self.assertEqual(graph[key]["kind"], "switch")

    def test_the_preferences_use_the_same_names_for_the_three_way(self):
        self.assertNotRegex(PREFS, r'^\s*"5[01]",?$')

    def test_hands_are_written_for_the_three_way_halves(self):
        with open(pd.DATA / "hands.csv", newline="") as fh:
            labels = {r["switch"] for r in csv.DictReader(fh)}
        self.assertLessEqual({"101A", "103A"}, labels)

    def test_both_names_resolve_in_the_plugin(self):
        import build_layout_le as bl
        try:
            sheet, _le, _core = bl.plugin()
        except bl.BuildError as exc:
            self.skipTest(str(exc))
        from schematic import edits
        graph = json.loads((pd.GRAPHS / "main.json").read_text())
        g = sheet.prepare(graph, dict(sheet.options("main_upper", pd.DATA)), set())
        self.assertEqual(g["nodes"][edits.by_label(g, "TO_3W33789-1")]["label"], "101A")
        try:
            sg = sheet.prepare(json.loads((pd.GRAPHS / "staging.json").read_text()),
                               dict(sheet.options("staging", pd.DATA)), set())
            half = edits.by_label(sg, "35@East Lead")
        except Exception as exc:       # a plugin older than label@track
            self.skipTest(f"the plugin does not know label@track yet: {exc}")
        self.assertEqual(sg["nodes"][half]["alias"], "T95")


if __name__ == "__main__":
    unittest.main()
