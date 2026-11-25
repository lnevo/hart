"""tools/pipeline/map_lane.py: the pipeline map's manifest lane (ADR-037 stage 3), what it draws from the steps, where
it puts new boxes and links, what it refuses, and the map build failing on a stale or hand-edited lane."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
MAP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MAP)
LANE = MAP.MANIFEST_LANE
M = LANE.MANIFEST

DOMAINS = [{"id": "a", "label": "A", "color": "#000"}]


def step(name: str, script: str, inputs=(), outputs=(), label: str = "", desc: str = "Checks.") -> object:
    return M.Step(name=name, runner="check", cmd=("python3", script), domain="a", label=label or Path(script).name,
                  desc=desc, script=script, inputs=tuple(M.Edge(*i) for i in inputs),
                  outputs=tuple(M.Edge(*o) for o in outputs))


def box(nid: str, **extra) -> dict:
    return {"id": nid, "label": nid, "kind": "structured", "status": "live", "domain": "a", "desc": "", "path": nid,
            **extra}


def graph(nodes=(), edges=()) -> dict:
    return {"domains": DOMAINS, "nodes": [box("tools/check.sh", kind="generator", runner=True), box("data/x.csv"),
                                          box("out/y.json"), *nodes], "edges": list(edges)}


STEPS = (step("one", "tools/one.py", inputs=[("data/x.csv", "reads", "")], outputs=[("out/y.json", "writes")]),
         step("two", "tools/two.py", inputs=[("data/x.csv", "check", "check")]))


def ids(data: dict) -> list[str]:
    return [n["id"] for n in data["nodes"]]


def keys(data: dict) -> list[tuple[str, str]]:
    return [(e["from"], e["to"]) for e in data["edges"]]


class Fixture(unittest.TestCase):
    """Tests on stand-in steps: the repo's HAND_KEPT_STEPS name steps these do not have."""

    def setUp(self) -> None:
        patcher = mock.patch.dict(LANE.HAND_KEPT_STEPS, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)


class DrawTest(Fixture):
    def test_a_box_per_step_with_its_inputs_outputs_and_check_link(self) -> None:
        out = LANE.regenerate(graph(), STEPS)
        one = next(n for n in out["nodes"] if n["id"] == "tools/one.py")
        self.assertEqual(one, {"id": "tools/one.py", "label": "one.py", "kind": "generator", "status": "live",
                               "domain": "a", "desc": "Checks.", "path": "tools/one.py", "gen": "manifest"})
        self.assertEqual([e for e in out["edges"] if "tools/one.py" in (e["from"], e["to"])], [
            {"from": "data/x.csv", "to": "tools/one.py", "label": "reads", "gen": "manifest"},
            {"from": "tools/one.py", "to": "out/y.json", "label": "writes", "gen": "manifest"},
            {"from": "tools/one.py", "to": "tools/check.sh", "label": "check one", "side": "check", "gen": "manifest"},
        ])
        two_in = next(e for e in out["edges"] if e["to"] == "tools/two.py")
        self.assertEqual(two_in, {"from": "data/x.csv", "to": "tools/two.py", "label": "check", "side": "check",
                                  "gen": "manifest"})
        MAP.validate(out, tracked=False)

    def test_an_unlabelled_input_has_no_label_key(self) -> None:
        out = LANE.regenerate(graph(), (step("one", "tools/one.py", inputs=[("data/x.csv", "", "")]),))
        self.assertIn({"from": "data/x.csv", "to": "tools/one.py", "gen": "manifest"}, out["edges"])

    def test_regenerating_is_stable_and_keeps_every_other_entry(self) -> None:
        hand = graph([box("tools/code.py", kind="generator")], [{"from": "tools/code.py", "to": "data/x.csv"}])
        once = LANE.regenerate(hand, STEPS)
        self.assertEqual(LANE.regenerate(once, STEPS), once)
        self.assertEqual([n for n in once["nodes"] if not n.get("gen")], hand["nodes"])
        self.assertEqual([e for e in once["edges"] if not e.get("gen")], hand["edges"])

    def test_boxes_and_links_stay_where_the_file_has_them(self) -> None:
        once = LANE.regenerate(graph(), STEPS)
        moved = dict(once, nodes=once["nodes"][::-1], edges=once["edges"][::-1])
        again = LANE.regenerate(moved, STEPS)
        self.assertEqual(ids(again), ids(moved))
        self.assertEqual(keys(again), keys(moved))

    def test_a_new_box_follows_the_previous_steps_box_and_a_new_link_its_scripts_last_link(self) -> None:
        once = LANE.regenerate(graph([box("z")], [{"from": "z", "to": "data/x.csv"}]), STEPS)
        three = step("three", "tools/three.py", inputs=[("out/y.json", "joins", "")])
        steps = (STEPS[0], three, STEPS[1])
        out = LANE.regenerate(once, steps)
        self.assertEqual(ids(out)[ids(out).index("tools/one.py") + 1], "tools/three.py")
        grown = (step("one", "tools/one.py", inputs=[("data/x.csv", "reads", ""), ("z", "also", "")],
                      outputs=[("out/y.json", "writes")]), STEPS[1])
        out = LANE.regenerate(once, grown)
        k = keys(out)
        self.assertEqual(k.index(("z", "tools/one.py")), k.index(("tools/one.py", "tools/check.sh")) + 1)

    def test_a_new_entry_is_never_placed_after_another_lanes_entry(self) -> None:
        """The agent-doc lane puts its entries last on every run, so a place after one would move each time."""
        g = graph([box("doc.md", gen="agent-docs")], [{"from": "doc.md", "to": "tools/check.sh", "gen": "agent-docs"}])
        out = LANE.regenerate(g, STEPS)
        self.assertEqual(ids(out)[-1], "doc.md")
        self.assertEqual(keys(out)[-1], ("doc.md", "tools/check.sh"))

    def test_a_step_gone_from_the_manifest_takes_its_box_and_links(self) -> None:
        once = LANE.regenerate(graph(), STEPS)
        out = LANE.regenerate(once, STEPS[:1])
        self.assertNotIn("tools/two.py", ids(out))
        self.assertFalse([k for k in keys(out) if "tools/two.py" in k])

    def test_hand_kept_steps_are_left_alone(self) -> None:
        LANE.HAND_KEPT_STEPS["panels"] = "a runner box"
        steps = STEPS + (step("panels", "tools/panels.sh"),)
        hand = graph([box("tools/panels.sh", kind="generator")], [{"from": "tools/panels.sh", "to": "tools/check.sh",
                                                                   "label": "check panels (all)"}])
        out = LANE.regenerate(hand, steps)
        self.assertIn(box("tools/panels.sh", kind="generator"), out["nodes"])
        self.assertIn({"from": "tools/panels.sh", "to": "tools/check.sh", "label": "check panels (all)"}, out["edges"])
        with self.assertRaisesRegex(LANE.MapLaneError, "no hand-kept box for tools/panels.sh"):
            LANE.regenerate(graph(), steps)

    def test_a_link_another_lane_draws_is_left_to_it_when_they_agree(self) -> None:
        other = {"from": "data/x.csv", "to": "tools/two.py", "label": "check", "side": "check", "gen": "agent-docs"}
        out = LANE.regenerate(graph([], [other]), STEPS)
        self.assertEqual([e for e in out["edges"] if (e["from"], e["to"]) == ("data/x.csv", "tools/two.py")], [other])
        with self.assertRaisesRegex(LANE.MapLaneError, r"drawn by the agent-docs lane as 'checks' \(check\) and "
                                                       r"listed in tools/pipeline/checks.toml as 'check' \(check\)"):
            LANE.regenerate(graph([], [dict(other, label="checks")]), STEPS)


class RefuseTest(Fixture):
    def assertRefused(self, data: dict, steps, pattern: str) -> None:
        with self.assertRaisesRegex(LANE.MapLaneError, pattern):
            LANE.regenerate(data, steps)

    def test_a_hand_kept_box_or_link_the_lane_generates(self) -> None:
        self.assertRefused(graph([box("tools/one.py")]), STEPS,
                           r"tools/one.py is a hand-kept box, but step 'one' of tools/pipeline/checks.toml generates "
                           r"it: remove the hand-kept box")
        self.assertRefused(graph([], [{"from": "tools/one.py", "to": "tools/check.sh", "label": "check"}]), STEPS,
                           r"hand-kept link tools/one.py -> tools/check.sh: the manifest lane generates it; remove it")

    def test_an_input_or_output_that_is_no_box(self) -> None:
        self.assertRefused(graph(), (step("one", "tools/one.py", inputs=[("data/gone.csv", "", "")]),),
                           r"step 'one': input data/gone.csv is no box of the map; add a hand-kept box")
        self.assertRefused(graph(), (step("one", "tools/one.py", outputs=[("out/gone", "")]),),
                           r"step 'one': output out/gone is no box of the map")
        self.assertRefused(graph(), (step("one", "tools/one.py", inputs=[("tools/one.py", "", "")]),),
                           r"input tools/one.py is the step's own script")

    def test_two_steps_of_one_script_and_a_link_listed_twice(self) -> None:
        self.assertRefused(graph(), (step("one", "tools/one.py"), step("again", "tools/one.py")),
                           r"steps 'one' and 'again' both run tools/one.py; the map draws one box per script")
        self.assertRefused(graph(), (step("one", "tools/one.py", inputs=[("data/x.csv", "", ""), ("data/x.csv", "b", "")]),),
                           r"data/x.csv -> tools/one.py comes from two entries of the manifest")

    def test_no_runner_box_and_a_stale_hand_kept_step(self) -> None:
        g = graph()
        g["nodes"] = g["nodes"][1:]
        self.assertRefused(g, STEPS, r"no hand-kept box for tools/check.sh")
        with mock.patch.dict(LANE.HAND_KEPT_STEPS, {"gone": "why"}):
            self.assertRefused(graph(), STEPS, r"HAND_KEPT_STEPS in tools/pipeline/map_lane.py names .*gone, no step")

    def test_a_manifest_that_does_not_load(self) -> None:
        with mock.patch.object(M, "load", side_effect=M.ManifestError("t.toml: step 'x': cmd: broken")):
            self.assertRefused(graph(), None, r"t.toml: step 'x': cmd: broken")
        with mock.patch.object(M, "tracked_files", side_effect=M.ManifestError("git ls-files failed in /r: boom")):
            self.assertRefused(graph(), None, r"git ls-files failed in /r: boom")
        err = io.StringIO()
        with mock.patch.object(M, "load", side_effect=M.ManifestError("t.toml: broken")), \
                contextlib.redirect_stderr(err):
            self.assertEqual(LANE.main(), 1)
        self.assertIn("manifest map lane: t.toml: broken", err.getvalue())


class BuildTest(unittest.TestCase):
    """The map build with both lanes, on the committed graph."""

    def run_check(self, data: dict) -> tuple[int, str, dict]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "g.json")
            path.write_text(json.dumps(data))
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = MAP.main(["--graph", str(path), "--check"])
            return rc, err.getvalue(), json.loads(path.read_text())

    def test_the_committed_graph_holds_the_lane_for_every_step(self) -> None:
        data = MAP.read(MAP.GRAPH)
        self.assertEqual(MAP.graph_text(MAP.validate(MAP.regenerate(data))), MAP.GRAPH.read_text())
        drawn = {n["id"] for n in data["nodes"] if n.get("gen") == LANE.GEN}
        steps = M.load()
        self.assertEqual(drawn, {s.script for s in steps if s.name not in LANE.HAND_KEPT_STEPS})
        checks = {(e["from"], e.get("label")) for e in data["edges"] if e["to"] == LANE.RUNNER}
        for s in steps:
            if s.name not in LANE.HAND_KEPT_STEPS:
                self.assertIn((s.script, f"check {s.name}"), checks)

    def test_a_hand_edit_to_a_generated_entry_fails_check_naming_it(self) -> None:
        data = MAP.read(MAP.GRAPH)
        box_ = next(n for n in data["nodes"] if n.get("gen") == LANE.GEN)
        box_["desc"] = "edited by hand"
        link = next(e for e in data["edges"] if e.get("gen") == LANE.GEN)
        link["label"] = "edited"
        rc, err, kept = self.run_check(data)
        self.assertEqual(rc, 1)
        self.assertIn(f"node {box_['id']!r} (manifest lane): desc differ from what is generated", err)
        self.assertIn(f"edge {link['from']} -> {link['to']} (manifest lane): label differ", err)
        self.assertIn("A hand edit to a generated entry is overwritten: change its source instead", err)
        self.assertEqual(kept, data)                         # --check writes nothing

    def test_a_dropped_or_extra_generated_entry_fails_check(self) -> None:
        data = MAP.read(MAP.GRAPH)
        gone = next(e for e in data["edges"] if e.get("gen") == LANE.GEN and e["to"] == LANE.RUNNER)
        data["edges"].remove(gone)
        data["edges"].append({"from": gone["from"], "to": "tools/ops/build_pipeline_map.py", "gen": LANE.GEN})
        rc, err, _ = self.run_check(data)
        self.assertEqual(rc, 1)
        self.assertIn(f"edge {gone['from']} -> {gone['to']} (manifest lane): missing from the file", err)
        self.assertIn(f"edge {gone['from']} -> tools/ops/build_pipeline_map.py (manifest lane): in the file, but no "
                      f"lane generates it", err)

    def test_a_reordered_file_or_other_format_is_named(self) -> None:
        data = MAP.read(MAP.GRAPH)
        fresh = MAP.regenerate(data)
        self.assertEqual(MAP.differences(data, fresh), [])
        swapped = dict(data, edges=[data["edges"][1], data["edges"][0], *data["edges"][2:]])
        self.assertEqual(MAP.differences(swapped, data), ["the order of the edges differs from what is generated"])
        self.assertEqual(MAP.differences(dict(data, updated="x"), data), ["a top-level key differs from what is "
                                                                          "generated"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "g.json")
            path.write_text(json.dumps(fresh))          # no indent: same data, not the file's own format
            _, stale = MAP.current(path)
        self.assertIn("the file is not in the graph's own format", stale)

    def test_a_broken_manifest_is_a_graph_error(self) -> None:
        with mock.patch.object(M, "load", side_effect=M.ManifestError("checks.toml: step 'x': cmd: broken")):
            with self.assertRaisesRegex(MAP.GraphError, "manifest lane: checks.toml: step 'x': cmd: broken"):
                MAP.regenerate(MAP.read(MAP.GRAPH))


if __name__ == "__main__":
    unittest.main()
