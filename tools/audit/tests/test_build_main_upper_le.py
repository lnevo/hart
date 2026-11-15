"""build_main_upper_le.py: the C3 trial panel of the main and upper levels, built beside the live tables."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import paths, tables  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # dataclasses look their module up while the class is built
    spec.loader.exec_module(mod)
    return mod


B = _load("build_main_upper_le", ROOT / "tools/anyrail/build_main_upper_le.py")
sys.path.insert(0, str(paths.LAYOUT_SCRIPTS))
AUDIT = _load("audit_panel_contracts", paths.LAYOUT_SCRIPTS / "audit_panel_contracts.py")
RENDER = _load("render_le_layout", paths.LAYOUT_SCRIPTS / "render_le_layout.py")

NEW_TURNOUT, NEW_BLOCK = B.TURNOUT_SYS, B.BLOCK_SYS


def is_new(el) -> bool:
    if el.tag == "LayoutEditor":
        return el.get("name") == B.PANEL_NAME
    sysname = tables.system_name(el) if el.find("systemName") is not None else (el.get("systemName") or "")
    if el.tag == "turnout":
        return sysname.startswith(NEW_TURNOUT)
    if el.tag == "block":
        return sysname.startswith(NEW_BLOCK)
    if el.tag == "layoutblock":
        return sysname.startswith("ILB") and sysname[3:].isdigit() and int(sysname[3:]) >= B.LAYOUT_BLOCK_FIRST
    return False


def strip_new(root) -> int:
    """Take the generated elements out again, giving each run's tail back to the element before it."""
    removed = 0
    for parent in [root, *root.iter()]:
        kids = list(parent)
        for i, el in enumerate(kids):
            if not is_new(el):
                continue
            prev = next((k for k in reversed(kids[:i]) if not is_new(k)), None)
            nxt_new = i + 1 < len(kids) and is_new(kids[i + 1])
            if not nxt_new:
                if prev is not None:
                    prev.tail = el.tail
                else:
                    parent.text = el.tail
            parent.remove(el)
            removed += 1
    return removed


class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data, cls.plan, cls.panel = B.build()
        cls.root = tables.loads(cls.data).root
        cls.live = tables.read(paths.TABLES_XML)
        cls.le = tables.layout_editor(cls.root, B.PANEL_NAME)
        cls.items = {el.get("ident"): el for el in tables.elements(cls.le) if el.get("ident")}

    # ---- switches
    def test_every_plan_switch_is_one_layoutturnout(self) -> None:
        want = sorted(n["label"] for n in self.plan.nodes.values() if n["kind"] in ("switch", "dx"))
        got = sorted(t.get("turnoutname").removeprefix("Switch ") for t in self.le.findall("layoutturnout"))
        self.assertEqual(got, want)
        self.assertEqual(len(got), 51)
        self.assertIn("223", got)            # T300 moved, not dropped
        self.assertNotIn("T300", got)

    def test_turnout_types_follow_the_hands(self) -> None:
        hands = {r.split(",")[0]: r.split(",")[1] for r in B.HANDS.read_text().splitlines()[1:] if r}
        for t in self.le.findall("layoutturnout"):
            label = t.get("turnoutname").removeprefix("Switch ")
            if label == "225":
                self.assertEqual(t.get("type"), "DOUBLE_XOVER")
                self.assertEqual(t.get("ver"), "2")
                continue
            self.assertEqual(t.get("type"), {"R": "RH_TURNOUT", "L": "LH_TURNOUT"}[hands[label]], label)

    def test_check_hands_stops_on_a_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "hands.csv"
            text = B.HANDS.read_text().replace("223,R,", "223,L,")
            bad.write_text(text)
            with self.assertRaises(B.BuildError):
                B.check_hands(self.plan, bad)

    def test_turnout_legs_point_back(self) -> None:
        for t in self.le.findall("layoutturnout"):
            legs = "abcd" if t.get("type") == "DOUBLE_XOVER" else "abc"
            for leg in legs:
                seg = self.items[t.get(f"connect{leg}name")]
                self.assertEqual(seg.tag, "tracksegment")
                ends = {(seg.get("connect1name"), seg.get("type1")), (seg.get("connect2name"), seg.get("type2"))}
                self.assertIn((t.get("ident"), f"TURNOUT_{leg.upper()}"), ends)

    def test_turnouts_sit_where_the_plan_puts_them(self) -> None:
        # centre within 2.5 cm of the plan's switch, on its level (moved 223 and the dx aside); the parts sit
        # up to about 2 cm off the export after the least-squares fit
        for nid, n in self.plan.nodes.items():
            if n["kind"] != "switch" or n["label"] == "223":
                continue
            t = self.items[f"TO{B.TAG}-{n['label']}"]
            ox, oy = self.panel.offset[self.plan.level[nid]]
            cen = (float(t.get("xcen")) - ox, float(t.get("ycen")) - oy)
            self.assertLess(math.dist(cen, n["xy"]) / B.PX_PER_CM, 2.5, n["label"])

    # ---- track
    def test_no_dangling_connection_names(self) -> None:
        for el in tables.elements(self.le):
            for attr in ("connect1name", "connect2name", "connectaname", "connectbname", "connectcname",
                         "connectdname"):
                name = el.get(attr)
                if name:
                    self.assertIn(name, self.items, f"{el.get('ident')} {attr}")
        for p in self.le.findall("positionablepoint"):
            if p.get("type") == "ANCHOR":
                self.assertTrue(p.get("connect1name") and p.get("connect2name"), p.get("ident"))
            else:
                self.assertEqual(p.get("type"), "END_BUMPER")
                self.assertIsNone(p.get("connect2name"))
            for name in (p.get("connect1name"), p.get("connect2name")):
                if name:
                    seg = self.items[name]
                    self.assertIn(p.get("ident"), (seg.get("connect1name"), seg.get("connect2name")))

    def test_every_run_is_connected_track(self) -> None:
        ident = self.panel.ident

        def follow(name, typ):
            seg = self.items[self.panel.conn[(name, typ)]]
            here = (name, typ)
            for _ in range(200):
                ends = [(seg.get("connect1name"), seg.get("type1")), (seg.get("connect2name"), seg.get("type2"))]
                other = ends[1] if ends[0] == here else ends[0]
                el = self.items[other[0]]
                if el.tag != "positionablepoint" or el.get("type") != "ANCHOR":
                    return other
                nxt = el.get("connect2name") if el.get("connect1name") == seg.get("ident") else el.get("connect1name")
                here, seg = other, self.items[nxt]
            self.fail("run does not end")

        for e in self.plan.edges:
            start = (ident[e["u"]], self.panel._ctype(e["u"], e["up"]))
            end = (ident[e["v"]], self.panel._ctype(e["v"], e["vp"]))
            self.assertEqual(follow(*start), end, e["id"])

    def test_track_attributes(self) -> None:
        for s in self.le.findall("tracksegment"):
            self.assertEqual(s.get("mainline"), "yes")
            self.assertIn(s.get("dashed"), ("yes", "no"))
            self.assertIn(s.get("hidden"), ("yes", "no"))
            self.assertFalse(s.get("ident").startswith(("TO", "TUR", "TRV")))
            self.assertTrue(s.get("class"))
            if s.get("bezier") == "yes":
                self.assertEqual(len(s.findall("controlpoints/controlpoint")), 2)
        hidden = [s for s in self.le.findall("tracksegment") if s.get("hidden") == "yes"]
        cut = [e for e in self.plan.edges if self.plan.level[e["u"]] != self.plan.level[e["v"]]]
        self.assertEqual(len(hidden), len(cut))      # one hidden jump per run that changes level
        self.assertTrue(cut)

    def test_levels_side_by_side(self) -> None:
        xs = {0: [], 1: []}
        for t in self.le.findall("layoutturnout"):
            label = t.get("turnoutname").removeprefix("Switch ")
            xs[0 if label.startswith("1") else 1].append(float(t.get("xcen")))
        self.assertLess(max(xs[0]), min(xs[1]))       # main 101-135 left, upper 201-245 right

    def test_blocks_match_track(self) -> None:
        used = {s.get("blockname") for s in self.le.findall("tracksegment")}
        used |= {t.get(a) for t in self.le.findall("layoutturnout")
                 for a in ("blockname", "blockbname", "blockcname", "blockdname") if t.get(a)}
        new_lb = {tables.user_name(b) for b in tables.layout_blocks(self.root) if is_new(b)}
        new_b = {tables.user_name(b) for b in tables.blocks(self.root, full=False) if is_new(b)}
        full_b = {tables.user_name(b) for b in tables.blocks(self.root) if is_new(b)}
        self.assertEqual(used, new_lb)
        self.assertEqual(new_b, new_lb)
        self.assertEqual(full_b, new_lb)

    # ---- the live file
    def test_live_tables_unchanged_but_for_the_additions(self) -> None:
        doc = tables.loads(self.data)
        removed = strip_new(doc.root)
        self.assertEqual(removed, 1 + 51 + 3 * len(self.panel.blocks))
        self.assertEqual(doc.tobytes(), paths.TABLES_XML.read_bytes())

    def test_no_name_collisions(self) -> None:
        live_users = {tables.user_name(b) for b in tables.turnouts(self.live) + tables.blocks(self.live)
                      + tables.layout_blocks(self.live)}
        live_sys = {tables.system_name(b) for b in tables.turnouts(self.live) + tables.blocks(self.live)
                    + tables.layout_blocks(self.live)}
        new = [b for b in tables.turnouts(self.root) + tables.blocks(self.root, full=False)
               + tables.layout_blocks(self.root) if is_new(b)]
        self.assertFalse({tables.user_name(b) for b in new} & live_users)
        self.assertFalse({tables.system_name(b) for b in new} & live_sys)
        idents = [el.get("ident") for el in tables.elements(self.le) if el.get("ident")]
        self.assertEqual(len(idents), len(set(idents)))
        for t in tables.turnouts(self.root):
            if is_new(t):
                self.assertTrue(tables.system_name(t).startswith("IT:"))     # never field hardware
        self.assertEqual([le.get("name") for le in tables.layout_editors(self.root)],
                         [le.get("name") for le in tables.layout_editors(self.live)] + [B.PANEL_NAME])

    def test_no_masts_or_sensors(self) -> None:
        for el in self.le.iter():
            self.assertNotIn(el.tag, ("signalmasticon", "sensoricon", "signalAMast", "sensorA"))
            for a in ("eastboundsignalmast", "westboundsignalmast", "eastboundsensor", "westboundsensor"):
                self.assertIsNone(el.get(a))
        for b in tables.layout_blocks(self.root):
            if is_new(b):
                self.assertIsNone(b.get("occupancysensor"))

    def test_audit_passes_on_the_trial(self) -> None:
        boundaries = AUDIT.load_boundaries(AUDIT.BOUNDARIES)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables_main_upper.xml"
            path.write_bytes(self.data)
            audit = AUDIT.audit_source("trial", path, boundaries, {b.mast for b in boundaries})
        self.assertEqual(audit.errors, [])
        self.assertEqual(audit.facts["panel"], "HART Railroad")

    def test_check_mode_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "t.xml"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(B.main(["--out", str(out)]), 0)
                self.assertEqual(B.main(["--check", "--out", str(out)]), 0)
                out.write_bytes(out.read_bytes() + b" ")
                self.assertEqual(B.main(["--check", "--out", str(out)]), 1)

    def test_renderer_draws_the_panel_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.xml"
            path.write_bytes(self.data)
            _pp, _legs, turnouts, segs, *_ = RENDER.load_geometry(path, B.PANEL_NAME, curves=True)
            self.assertEqual(len(turnouts), 51)
            self.assertGreater(len(segs), len(self.le.findall("tracksegment")))   # Beziers drawn as pieces
            _pp, _legs, turnouts, chords, *_ = RENDER.load_geometry(path, B.PANEL_NAME)
            shown = [s for s in self.le.findall("tracksegment") if s.get("hidden") != "yes"]
            self.assertEqual(len(chords), len(shown))                # default: one chord a segment
            _pp, _legs, live_turnouts, *_ = RENDER.load_geometry(path)
            self.assertEqual(len(live_turnouts), 20)            # the default is still the live panel


def inputs():
    return (json.loads(B.GRAPH.read_text()), json.loads(B.PARTS.read_text()), json.loads(B.OVERRIDES.read_text()))


def bare_plan(parts):
    """A Plan with only the part tables filled, for the walk and port code; parts in export px already."""
    P = B.Plan.__new__(B.Plan)
    P.parts, P.notes = parts, []
    P.sx = P.sy = 1 / B.PX_PER_CM
    P.ox = P.oy = 0.0
    P._joints()
    return P


class ReviewFixes(unittest.TestCase):
    def test_moved_switch_stays_on_its_run(self) -> None:
        graph, parts, ov = inputs()
        move = next(ed for ed in ov["edits"] if ed["op"] == "move")
        move["cm_from_first"] = 1           # the plugin clamps to 5 cm; half the switch is longer than that
        plan = B.Plan(graph, parts, ov)
        x = plan.by_label("223")
        run_a = next(e for e in plan.edges if e["id"].endswith("a") and x in (e["u"], e["v"]))
        start = run_a["pts"][0] if run_a["v"] == x else run_a["pts"][-1]
        self.assertLess(math.dist(plan.port_pt[(x, "B")], start[:2]), 1.0)

    def test_a_part_on_another_level_is_not_claimed(self) -> None:
        base = B.Plan(*inputs())

        def to_cm(xy):
            return ((xy[0] / B.PX_PER_CM - base.ox) / base.sx, (xy[1] / B.PX_PER_CM - base.oy) / base.sy)

        # switch 119B's part, copied onto the upper level and centred exactly on the plan's switch
        graph, parts, ov = inputs()
        node = graph["nodes"]["TOR33649"]
        tx, ty = to_cm(node["xy"])
        cx = sum(q["x"] for q in parts[0]["eps"]) / len(parts[0]["eps"])
        cy = sum(q["y"] for q in parts[0]["eps"]) / len(parts[0]["eps"])
        twin = {"name": "SL-8351", "eps": [{"x": q["x"] + tx - cx, "y": q["y"] + ty - cy, "z": 10.795}
                                           for q in parts[0]["eps"]]}
        parts.append(twin)
        self.assertEqual(B.Plan(graph, parts, ov).part_of["TOR33649"], 0)

        # a dead end on the upper level, nearer the track end's plan point than the real one, is not that end
        graph, parts, ov = inputs()
        real = base.nodes["END:EB398"]["xy"]            # the walk put it on the real dead end
        ex, ey = to_cm(real)
        parts.append({"name": "SL-8300", "eps": [{"x": ex + 0.5, "y": ey, "z": 10.795},
                                                 {"x": ex + 0.5, "y": ey + 40, "z": 10.795}]})
        plan = B.Plan(graph, parts, ov)
        plan.nodes["END:EB398"]["xy"] = [real[0] + 0.5 * B.PX_PER_CM * base.sx, real[1]]
        self.assertAlmostEqual(plan.joint_point(plan._end_start("END:EB398"))[2], 0.0)

    def test_walk_stops_at_a_part_with_more_than_two_ends(self) -> None:
        flex = {"name": "SL-8300", "eps": [{"x": 0, "y": 0, "z": 0}, {"x": 10, "y": 0, "z": 0}]}
        diamond = {"name": "SL-8387", "eps": [{"x": 10, "y": 0, "z": 0}, {"x": 20, "y": 0, "z": 0},
                                               {"x": 15, "y": -5, "z": 0}, {"x": 15, "y": 5, "z": 0}]}
        P = bare_plan([flex, diamond])
        P.switch_parts = set()
        with self.assertRaises(B.BuildError):
            P._walk(P.joint[(0, 0)], None)

    def test_misread_part_with_too_many_ends_stops(self) -> None:
        part = {"name": "SL-8351", "eps": [{"x": i, "y": 0, "z": 0} for i in range(4)]}
        P = bare_plan([part])
        P.nodes = {"N": {"kind": "switch", "label": "X", "xy": [0, 0], "hand": 1,
                         "dirs": {"A": [-1, 0], "B": [1, 0], "C": [1, 0.1]}}}
        P.part_of, P.shared_parts = {"N": 0}, set()
        with self.assertRaises(B.BuildError):
            P._ports()

    def test_override_keys_the_panel_does_not_draw_stop_it(self) -> None:
        for change in (lambda ov: ov.update(new_thing=1),
                       lambda ov: ov["levels"].update(squash=1),
                       lambda ov: ov["edits"].append({"op": "remove", "switches": ["T6"]}),
                       lambda ov: ov["edits"][1].update(points_toward="T237")):
            graph, parts, ov = inputs()
            change(ov)
            with self.assertRaises(B.BuildError):
                B.Plan(graph, parts, ov)

    def test_levels_come_from_the_plugin(self) -> None:
        graph, parts, ov = inputs()
        ov["levels"]["assign"] = {"T262": 0}      # the plugin's per-switch pin, which _levels never read
        plan = B.Plan(graph, parts, ov)
        self.assertEqual(plan.level[plan.by_label("221B")], 0)
        self.assertEqual(plan.level[plan.by_label("221A")], 1)

    def test_level_cut_uses_treat(self) -> None:
        spec = json.loads(B.OVERRIDES.read_text())["levels"]
        self.assertEqual(B.z_level(0.8, spec), 0)
        self.assertEqual(B.z_level(2.5, spec), 1)        # treated as 10.8: upper
        self.assertEqual(B.z_level(4.9, spec), 1)
        _data, plan, panel = B.build()
        e75 = next(e for e in plan.edges if e["id"] == "e75")
        lu, lv = plan.level[e75["u"]], plan.level[e75["v"]]
        cut = panel.cuts["e75"]
        self.assertNotEqual(lu, lv)
        self.assertEqual(plan.point_level(e75["pts"][cut][2], lu), lv)
        for q in e75["pts"][1:cut]:
            self.assertEqual(plan.point_level(q[2], lu), lu)

    def test_part_geometry_must_agree_with_the_plan_hand(self) -> None:
        graph, parts, ov = inputs()
        graph["nodes"]["TOL30431"]["hand"] *= -1       # switch 121 (plan T15)
        with self.assertRaisesRegex(B.BuildError, "part 15"):
            B.Plan(graph, parts, ov)

    def test_renderer_reads_control_points_by_index_and_labels_a_curve_once(self) -> None:
        xml = ('<layout-config><LayoutEditor name="P">'
               '<positionablepoint ident="A1" type="ANCHOR" x="0" y="0"/>'
               '<positionablepoint ident="A2" type="ANCHOR" x="100" y="0"/>'
               '<tracksegment ident="T1" blockname="Blk" connect1name="A1" type1="POS_POINT" connect2name="A2" '
               'type2="POS_POINT" mainline="yes" hidden="no" bezier="yes"><controlpoints>'
               '<controlpoint index="1" x="70" y="50"/><controlpoint index="0" x="30" y="0"/>'
               '</controlpoints></tracksegment></LayoutEditor></layout-config>')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.xml"
            path.write_text(xml)
            segs = RENDER.load_geometry(path, "P", curves=True)[3]
        want = RENDER.bezier_points((0.0, 0.0), [(30.0, 0.0), (70.0, 50.0)], (100.0, 0.0))
        self.assertEqual([s[0] for s in segs] + [segs[-1][1]], want)
        self.assertEqual(sum(1 for s in segs if s[3] == "Blk"), 1)


class Geometry(unittest.TestCase):
    def test_arc_tangents_on_a_quarter_circle(self) -> None:
        r = 100.0
        pts = [(r * math.cos(t), r * math.sin(t)) for t in (0, math.pi / 6, math.pi / 3, math.pi / 2)]
        ang = B.arc_tangents(pts, (0.0, 1.0), (-1.0, 0.0))
        for a, t in zip(ang, (0, math.pi / 6, math.pi / 3, math.pi / 2)):
            self.assertAlmostEqual(a, t + math.pi / 2, places=2)

    def test_arc_tangents_straight_line(self) -> None:
        ang = B.arc_tangents([(0, 0), (10, 0), (30, 0)], None, None)
        for a in ang:
            self.assertAlmostEqual(a, 0.0, places=6)

    def test_bezier_points_end_on_the_ends(self) -> None:
        pts = RENDER.bezier_points((0, 0), [(10, 0), (20, 10)], (20, 20))
        self.assertEqual(pts[0], (0, 0))
        self.assertAlmostEqual(pts[-1][0], 20)
        self.assertAlmostEqual(pts[-1][1], 20)


if __name__ == "__main__":
    unittest.main()
