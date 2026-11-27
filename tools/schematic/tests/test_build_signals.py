"""build_signals.py on small hand-written inputs: the plan graph checks (check_runs), the main and upper rows' error
paths (home_row, apb_row, virtual_row, signal_row) and main()'s exits. The run over the committed plan is tested in
tools/audit/tests/test_publish_draft.py (SignalsCheck)."""
from __future__ import annotations

import contextlib
import io
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_signals as bs  # noqa: E402

GRAPH = {"nodes": {"S1": {"kind": "switch", "label": "1*"}, "S3": {"kind": "switch", "label": "3"},
                   "E": {"kind": "end", "label": "end"}},
         "edges": [{"id": "e1", "u": "S1", "up": "A", "v": "S3", "vp": "B", "names": ["Main"]},
                   {"id": "e2", "u": "S3", "up": "C", "v": "E", "vp": "x", "names": []}]}


def row(**more):
    r = dict(mast="2L", toward="1", run=["1", "3"], names=["Main"], _edge="e1", _toward_node="S1")
    r.update(more)
    return r


class CheckRuns(unittest.TestCase):
    def test_a_row_that_fits_has_no_problem(self):
        self.assertEqual(bs.check_runs(GRAPH, [row()]), [])
        self.assertEqual(bs.check_runs(GRAPH, [row(toward="3", run=["3", ""], names=[], _edge="e2",
                                                   _toward_node="S3")]), [])

    def test_each_misfit_is_named(self):
        for more, why in ((dict(_edge="e9"), "schematic edge e9 is not in the plan graph"),
                          (dict(_toward_node="E"), "node E is not an end of edge e1"),
                          (dict(toward="3"), "toward '3', but node S1 is switch '1'"),
                          (dict(run=["1", "5"]), "runs 1 to 3, masts.csv says ['1', '5']"),
                          (dict(names=["Other"]), "carries ['Main'], masts.csv says ['Other']")):
            with self.subTest(more=more):
                (got,) = bs.check_runs(GRAPH, [row(**more)])
                self.assertIn(why, got)

    def test_a_turnback_of_its_own_edge_is_not_checked_as_a_node(self):
        self.assertEqual(bs.check_runs(GRAPH, [row(_toward_node="turn:e1")]), [])

    def test_node_labels_drop_the_star_and_name_no_end(self):
        self.assertEqual([bs.node_label(GRAPH["nodes"], n) for n in ("S1", "S3", "E")], ["1", "3", ""])


def plan(**more) -> bs.MainUpperPlan:
    band = {"nodes": {"n1": {"kind": "switch", "ins": {"A": "s1"}, "outs": {"B": "s2"}},
                      "t": {"kind": "turnback"}},
            "strands": {"s1": {"edge": "e1.0", "src": ["n1", "A"], "dst": ["t", "x"]},
                        "s2": {"edge": "e2x", "src": ["n1", "B"], "dst": ["t", "y"]}}}
    fields = dict(bands=[("Main level", band, {})], by_name={}, placed={}, destinations={}, levels=(2,))
    fields.update(more)
    return bs.MainUpperPlan(**fields)


class MainUpperRows(unittest.TestCase):
    R = dict(mast="Mast 2L", switch="1", facing="Track 1-3", dir="west", heads=["h1", "h2"], protects="OS 1")

    def test_a_mast_the_rule_no_longer_places_stops(self):
        with self.assertRaisesRegex(bs.SignalsError, "names a home mast the rule no longer places"):
            bs.home_row(plan(), self.R, "2L")
        with self.assertRaisesRegex(bs.SignalsError, "names a virtual mast the rule no longer places"):
            bs.virtual_row(plan(), self.R, "2L")

    def test_a_track_the_plan_does_not_have_stops(self):
        placed = {"2L": dict(band=0, node="n1", leg="A", strand="s1", track="Track 1-3 1")}
        with self.assertRaisesRegex(bs.SignalsError, "faces 'Track 1-3 1', which is no whole track"):
            bs.home_row(plan(placed=placed), self.R, "2L")
        with self.assertRaisesRegex(bs.SignalsError, "no half of a track of the plan"):
            bs.apb_row(plan(), dict(self.R, switch=""), "67")

    def test_a_home_mast_is_measured_from_its_switch(self):
        t = dict(name="Track 1-3", legs=[("n1", "A"), ("n3", "A")], ends=[("sw", "1"), ("sw", "3")], cm=120.0,
                 loop=False)
        placed = {"2L": dict(band=0, node="n1", leg="A", strand="s1", track="Track 1-3 1")}
        got = bs.home_row(plan(placed=placed, by_name={"Track 1-3": t}), self.R, "2L")
        self.assertEqual(got, bs.Placed("2L", "1", ["1", "3"], "e1", "n1", 120.0, 0.0, "west", 2, None))
        lost = dict(placed["2L"], leg="C")
        with self.assertRaisesRegex(bs.SignalsError, "has no end at leg C of Switch 1"):
            bs.home_row(plan(placed={"2L": lost}, by_name={"Track 1-3": t}), self.R, "2L")

    def test_a_loop_apb_west_mast_needs_a_turnback(self):
        t = dict(name="Track 1 Loop", legs=[("n1", "B"), ("n1", "C")], ends=[("sw", "1"), ("sw", "1")], cm=300.0,
                 loop=True, band=0, strands=["s1"])
        r = dict(self.R, mast="Mast 83", switch="", facing="Track 1 Loop 2", protects="Track 1 Loop 1")
        got = bs.apb_row(plan(by_name={"Track 1 Loop": t}), r, "83")
        self.assertEqual((got.toward, got.node, got.cm_from_toward, got.leg), ("", "t", bs.TURNBACK_CM, "C"))
        bare = plan(by_name={"Track 1 Loop": dict(t, strands=["s2"])})
        bare.bands[0][1]["nodes"]["t"]["kind"] = "end"
        with self.assertRaisesRegex(bs.SignalsError, "has no turnback to measure from"):
            bs.apb_row(bare, r, "83")

    def test_a_row_names_its_leg_only_on_a_loop(self):
        x = bs.Placed("2L", "1", ["1", "3"], "e1", "n1", 120.0, 0.0, "west", 2, None)
        self.assertNotIn("leg", bs.signal_row(x))
        self.assertEqual(bs.signal_row(x._replace(leg="B"))["leg"], "B")
        self.assertEqual(list(bs.signal_row(x)), ["mast", "toward", "run", "names", "edge_cm", "cm_from_toward",
                                                   "dir", "kind", "heads", "source", "_edge", "_toward_node"])


class Main(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = bs.main(argv)
        return status, out.getvalue(), err.getvalue()

    def test_a_write_without_the_plugin_exits_1_naming_it(self):
        with unittest.mock.patch.object(bs.pd, "plugin", side_effect=bs.pd.PluginMissing("no plugin here")), \
                unittest.mock.patch.object(bs.pd.paths, "exit_if_overridden"):
            self.assertEqual(self.run_main([]), (1, "", "no plugin here\n"))

    def test_a_mast_that_does_not_fit_exits_1_naming_it(self):
        with unittest.mock.patch.object(bs.pd, "plugin", return_value=Path("plugin")), \
                unittest.mock.patch.object(bs, "generate", side_effect=bs.SignalsError("staging: 1 masts do not fit")):
            self.assertEqual(self.run_main(["--check"]), (1, "", "staging: 1 masts do not fit\n"))


if __name__ == "__main__":
    unittest.main()
