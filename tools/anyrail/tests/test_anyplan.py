"""The schematic-maps plugin's plan reader (`schematic anyplan`, its schematic.anyplan module) on the owner's plan
5.3c, where it is on this machine (never in CI: the .any files stay private): the committed parts list is what it
reads, the plan has the same runs as the graphs built from AnyRail's own export, and the checks the owner asked of
5.3c still hold. The reader's tests on made-up bytes and ends are the plugin's (plugins/schematic-maps/tests)."""
import collections
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools/schematic"))
import le_common  # noqa: E402  the pinned schematic-maps plugin

PLANS = Path.home() / "Documents/Layout"
PLAN_C = PLANS / "Lee Nevo Design Version 5.3c.any"
INPUTS = REPO / "jmri/layouts/hart/data/schematic/inputs"


def reader():
    """schematic.anyplan from the pinned plugin (read only once a test needs it, so CI never looks for the plan)."""
    return le_common.plugin_module("anyplan")


@unittest.skipUnless(PLAN_C.exists(), "the owner's plan 5.3c is not on this machine")
class Plan53cParts(unittest.TestCase):
    """inputs/parts.json is the plugin's parts list of 5.3c (`schematic anyplan PLAN --parts`), unchanged."""

    def test_the_committed_parts_list_is_the_plans(self):
        A = reader()
        self.assertEqual(json.loads((INPUTS / "parts.json").read_text()), A.parts_list(A.read(PLAN_C)))


@unittest.skipUnless(PLAN_C.exists(), "the owner's plan 5.3c is not on this machine")
class Plan53cGraphs(unittest.TestCase):
    """Read from the .any file, 5.3c has the same switch-to-switch runs as the graphs in inputs/, which the plugin
    built from AnyRail's JMRI export with the reader's parts list; each run through the helix is the two stubs
    up to the -5 cm cut (--cut -5 --stubs), and the export draws the three-way as two turnouts the parts cannot name."""

    def test_same_runs_as_the_export(self):
        A = reader()
        parts = A.read(PLAN_C)
        links, _ = A.joins(parts)
        threeway = next(f"T{p['index']}" for p in parts if p["kind"] == "threeway")
        cuts = {frozenset((f"T{c['low'][0]}", f"T{c['high'][0]}")) for c in A.level_cuts(parts, links, -5.0)}

        def label(graph, n):
            d = graph["nodes"][n]
            if d["kind"] == "end":
                return "CUT" if "cut" in d else "END"
            return d["label"] if d["label"].startswith("T") else threeway

        want, stubs = collections.Counter(), collections.Counter()
        for f in ("staging.json", "main.json"):
            g = json.loads((INPUTS / f).read_text())
            for e in g["edges"]:
                u, v = label(g, e["u"]), label(g, e["v"])
                if "CUT" in (u, v):
                    stubs[u if v == "CUT" else v] += 1
                elif u != v or u != threeway:
                    want[tuple(sorted((u, v)))] += 1
        got = collections.Counter()
        for a, _, b, _, _ in A.runs(parts, links):
            u, v = f"T{a}", (f"T{b}" if b is not None else "END")
            if frozenset((u, v)) not in cuts:
                got[tuple(sorted((u, v)))] += 1
        got = collections.Counter({k: (n if "END" in k else n // 2) for k, n in got.items()})
        self.assertEqual(+(want - got), collections.Counter(), "runs in the export graphs the .any file lacks")
        self.assertEqual(+(got - want), collections.Counter(), "runs in the .any file the export graphs lack")
        self.assertEqual(stubs, collections.Counter({t: 1 for c in cuts for t in c}))      # one stub each side


@unittest.skipUnless(PLAN_C.exists(), "the owner's plan 5.3c is not on this machine")
class Plan53c(unittest.TestCase):
    """What the owner fixed in 5.3c (2026-11-19) stays fixed: one connected railroad through the helix, every switch
    level, no track end that nearly meets another, and no flat track left between the main and upper levels."""

    @classmethod
    def setUpClass(cls):
        cls.A = A = reader()
        cls.parts = A.read(PLAN_C)
        cls.links, cls.free = A.joins(cls.parts)

    def test_one_connected_piece(self):
        self.assertEqual(len(self.A.components(self.parts, self.links)), 1)

    def test_every_switch_is_level(self):
        self.assertEqual([p["index"] for p in self.parts if len(p["ends"]) > 2
                          and max(e["z"] for e in p["ends"]) - min(e["z"] for e in p["ends"]) > self.A.LEVEL_CM], [])

    def test_no_free_end_nearly_meets_another(self):
        self.assertIn("none", self.A.report(self.parts)[-1])

    def test_no_flat_track_between_the_levels(self):
        flat = [p["index"] for p in self.parts if all(1.5 < e["z"] < 5 for e in p["ends"])
                and max(e["z"] for e in p["ends"]) - min(e["z"] for e in p["ends"]) <= self.A.LEVEL_CM]  # grades pass
        self.assertEqual(flat, [])


if __name__ == "__main__":
    unittest.main()
