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
PART_REF = re.compile(r"T\d+|TO_\w+-\d")      # a plan part number or a three-way's part id
# The name edit's first track at each half of the shared numbers 23, 35 and 7 reaches its half as number@neighbour (no
# track leaving it has a name yet); these are the halves the plan part numbers named before.
NEIGHBOUR_REFS = {"23@1": "T57", "35@23": "T54", "23@15": "T126", "35@33": "T95", "7@33": "T33", "7@13": "T139"}


def strings(node):
    """Every string in a parsed JSON value, keys and values alike, comment entries (keys starting with _) left out."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for item in node:
            yield from strings(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            if not key.startswith("_"):
                yield key
                yield from strings(value)


def outside_relabel(overrides):
    """The overrides without the relabel edit, the one place that keys by plan part number."""
    return [e for e in overrides["edits"] if e["op"] != "relabel"] + [v for k, v in overrides.items() if k != "edits"]


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

    def test_only_the_relabel_edit_keys_by_part_number(self):
        found = {s for doc in (outside_relabel(STAGING), outside_relabel(MAIN_UPPER)) for s in strings(doc)
                 if PART_REF.fullmatch(s)}
        self.assertEqual(found, set())
        for name in ("staging.preferences", "main_upper.preferences"):
            prefs = json.loads((pd.DATA / f"{name}.json").read_text(encoding="utf-8"))
            self.assertEqual([s for s in strings(prefs) if PART_REF.fullmatch(s)], [], name)

    def test_the_neighbour_refs_stand_in_the_name_edit(self):
        name = next(e for e in STAGING["edits"] if e["op"] == "name")
        refs = {r for t in name["tracks"] for r in t[:2]}
        self.assertLessEqual(set(NEIGHBOUR_REFS), refs)

    def test_each_neighbour_ref_finds_the_half_its_part_number_did(self):
        import build_layout_le as bl
        try:
            sheet, _le, _core = bl.plugin()
        except bl.BuildError as exc:
            self.skipTest(str(exc))
        from schematic import edits
        # The final graph: the plugin stops on a ref whose track-name and neighbour readings disagree, so a ref
        # that resolves here to its old half resolved to it when the name edit ran too.
        sg = sheet.prepare(json.loads((pd.GRAPHS / "staging.json").read_text()),
                           dict(sheet.options("staging", pd.DATA)), set())
        for ref, part in NEIGHBOUR_REFS.items():
            self.assertEqual(sg["nodes"][edits.by_label(sg, ref)]["alias"], part, ref)

    def test_the_main_upper_refs_resolve_by_label(self):
        import build_layout_le as bl
        try:
            sheet, _le, _core = bl.plugin()
        except bl.BuildError as exc:
            self.skipTest(str(exc))
        from schematic import edits
        graph = json.loads((pd.GRAPHS / "main.json").read_text())
        opts = dict(sheet.options("main_upper", pd.DATA))
        g = sheet.prepare(graph, opts, set())
        refs = list(opts["level_leg"]) + list(opts["levels"]["assign"]) + list(opts["helix"])
        refs += [r for e in opts["edits"] if e["op"] == "flip" for r in e["switches"]]
        refs += [r for h in opts["min_cells"] + opts["shorten"] for r in h[:2]]
        self.assertTrue(refs)
        for ref in refs:
            self.assertEqual(g["nodes"][edits.by_label(g, ref)]["label"], ref)

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
