"""build_layout_le.py: the C3 trial panel of all three levels, drawn like the schematic, beside the live tables."""
from __future__ import annotations

import contextlib
import copy
import functools
import importlib.util
import io
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import paths, tables  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


B = _load("build_layout_le", ROOT / "tools/schematic/build_layout_le.py")
sys.path.insert(0, str(paths.LAYOUT_SCRIPTS))
AUDIT = _load("audit_panel_contracts", paths.LAYOUT_SCRIPTS / "audit_panel_contracts.py")
RENDER = _load("render_le_layout", paths.LAYOUT_SCRIPTS / "render_le_layout.py")
LIVE_PANEL = "HART Railroad"


def is_new(el) -> bool:
    if el.tag == "LayoutEditor":
        return el.get("name") == B.PANEL_NAME
    sysname = tables.system_name(el) if el.find("systemName") is not None else (el.get("systemName") or "")
    if el.tag == "turnout":
        return sysname.startswith(B.TURNOUT_SYS)
    if el.tag == "block":
        return sysname.startswith(B.BLOCK_SYS)
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
            if not (i + 1 < len(kids) and is_new(kids[i + 1])):
                if prev is not None:
                    prev.tail = el.tail
                else:
                    parent.text = el.tail
            parent.remove(el)
            removed += 1
    return removed


def used_blocks(le) -> set:
    out = {s.get("blockname") for s in le.findall("tracksegment")}
    for t in le.findall("layoutturnout"):
        out |= {t.get(a) for a in ("blockname", "blockbname", "blockcname", "blockdname") if t.get(a)}
    return out


def closed_block(le) -> dict:
    """{turnout name: block of the track on its closed route} for each plain turnout."""
    segs = {s.get("ident"): s for s in le.findall("tracksegment")}
    out = {}
    for t in le.findall("layoutturnout"):
        if "XOVER" not in t.get("type"):
            leg = "b" if t.get("continuing") == "2" else "c"
            out[t.get("turnoutname")] = segs[t.get(f"connect{leg}name")].get("blockname")
    return out


def crossover_legs(le) -> dict:
    """{turnout name: (type, sorted (leg block, block of the track on that leg))} for each crossover."""
    segs = {s.get("ident"): s for s in le.findall("tracksegment")}
    out = {}
    for t in le.findall("layoutturnout"):
        if "XOVER" in t.get("type") and t.get("type") != "DOUBLE_XOVER":
            pairs = sorted(((t.get("blockname") if leg == "a" else t.get(f"block{leg}name") or t.get("blockname")),
                            segs[t.get(f"connect{leg}name")].get("blockname")) for leg in "abcd")
            out[t.get("turnoutname")] = (t.get("type"), pairs)
    return out


@functools.lru_cache(maxsize=None)
def built():
    """(trial bytes, Panel, names, bands): built once for every test module that needs it."""
    with contextlib.redirect_stdout(io.StringIO()):
        return B.build()


class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data, cls.P, cls.names, cls.bands = built()
        cls.root = tables.loads(cls.data).root
        cls.live = tables.read(paths.TABLES_XML)
        cls.le = tables.layout_editor(cls.root, B.PANEL_NAME)
        cls.live_le = tables.layout_editor(cls.live, LIVE_PANEL)
        cls.items = {el.get("ident"): el for el in tables.elements(cls.le) if el.get("ident")}

    # ---- staging is the live railroad
    def test_every_live_staging_turnout_and_block_is_on_the_new_panel(self) -> None:
        live_turnouts = {t.get("turnoutname") for t in self.live_le.findall("layoutturnout")}
        new_turnouts = {t.get("turnoutname") for t in self.le.findall("layoutturnout")}
        self.assertTrue(live_turnouts)
        self.assertLessEqual(live_turnouts, new_turnouts)
        self.assertLessEqual(used_blocks(self.live_le), used_blocks(self.le))

    def test_closed_routes_and_crossovers_match_the_live_panel(self) -> None:
        live, new = closed_block(self.live_le), closed_block(self.le)
        self.assertEqual(len(live), 17)
        for name, block in live.items():
            self.assertEqual(new[name], block, name)
        live_x, new_x = crossover_legs(self.live_le), crossover_legs(self.le)
        self.assertEqual(sorted(live_x), ["Switch 23", "Switch 35", "Switch 7"])
        for name, legs in live_x.items():
            self.assertEqual(new_x[name], legs, name)

    def test_no_staging_object_is_created(self) -> None:
        for t in tables.turnouts(self.root):
            if is_new(t):
                self.assertTrue(re.fullmatch(r"Switch [12]\d\d[AB]?", tables.user_name(t)), tables.user_name(t))
        live_lb = {tables.user_name(b) for b in tables.layout_blocks(self.live)}
        staging = set(self.names[B.STAGING]["os"].values()) | {
            b for v in self.names[B.STAGING]["blocks"].values() for b in v}
        self.assertLessEqual(staging, live_lb)

    # ---- main and upper placeholders, as C3 named them
    def test_main_and_upper_placeholders(self) -> None:
        new_t = [tables.user_name(t) for t in tables.turnouts(self.root) if is_new(t)]
        self.assertEqual(len(new_t), 51)
        self.assertIn("Switch 223", new_t)             # T300 moved, its mark dropped from the name
        self.assertIn("Switch 225", new_t)             # the double crossover
        new_lb = {tables.user_name(b) for b in tables.layout_blocks(self.root) if is_new(b)}
        self.assertEqual(len(new_lb), 121)
        self.assertIn("OS Switch 135", new_lb)         # connector A joins 135A and 135B: their OS block
        self.assertIn("Track e68+e81", new_lb)
        self.assertFalse({b for b in new_lb if re.search(r"e\d+[xy]$", b)})
        dx = [t for t in self.le.findall("layoutturnout") if t.get("type") == "DOUBLE_XOVER"]
        self.assertEqual([t.get("turnoutname") for t in dx], ["Switch 225"])

    def test_blocks_match_track(self) -> None:
        new_lb = {tables.user_name(b) for b in tables.layout_blocks(self.root) if is_new(b)}
        new_b = {tables.user_name(b) for b in tables.blocks(self.root, full=False) if is_new(b)}
        full_b = {tables.user_name(b) for b in tables.blocks(self.root) if is_new(b)}
        live_lb = {tables.user_name(b) for b in tables.layout_blocks(self.live)}
        self.assertEqual(new_b, new_lb)
        self.assertEqual(full_b, new_lb)
        self.assertEqual(used_blocks(self.le) - live_lb, new_lb)

    # ---- the panel
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

    def test_the_look(self) -> None:
        arcs = [s for s in self.le.findall("tracksegment") if s.get("arc") == "yes"]
        self.assertGreater(len(arcs), 30)
        self.assertTrue(all(s.get("circle") == "yes" and float(s.get("angle")) > 0 for s in arcs))
        self.assertEqual(sum(1 for s in self.le.findall("tracksegment") if s.get("hidden") == "yes"), 4)
        self.assertEqual({s.get("mainline") for s in self.le.findall("tracksegment")}, {"yes", "no"})
        texts = {lb.get("text") for lb in self.le.findall("positionablelabel")}
        self.assertTrue({"STAGING LEVEL", "MAIN LEVEL", "Main West", "39", "135A"} <= texts, texts)
        self.assertEqual(len(self.le.findall("layoutShape")), 8)     # four helix ends, four connector ends

    def test_no_sensors_and_masts_only_on_staging(self) -> None:
        for el in self.le.iter():
            self.assertNotIn(el.tag, ("sensoricon", "sensorA", "sensorB", "sensorC", "sensorD"))
            for a in ("eastboundsensor", "westboundsensor"):
                self.assertIsNone(el.get(a))
        staging = B.band_key(self.bands[0][0])
        self.assertEqual(staging, B.STAGING)
        self.assertTrue(self.P.masts)
        self.assertEqual({m["band"] for m in self.P.masts}, {0})       # main and upper have none

    # ---- size: the owner's 1900 x 1200 display at 100% zoom
    def test_panel_fits_the_display(self) -> None:
        w, h = int(self.le.get("panelwidth")), int(self.le.get("panelheight"))
        window = (int(self.le.get("windowwidth")), int(self.le.get("windowheight")))
        self.assertEqual(window, (w + 18, h + 60))                    # Layout Editor's frame allowance
        self.assertLessEqual(window[0], B.FIT[0])
        self.assertLessEqual(window[1], B.FIT[1])
        self.assertLessEqual(window[0], 1900)                         # the owner's display
        self.assertLessEqual(window[1], 1200 - 37)                    # below the macOS menu bar
        self.assertGreater(window[0], 0.98 * B.FIT[0])                # as large as fits, not smaller
        # everything drawn lies on the panel: track, turnout legs, labels (at the plugin's text width) and icons
        xs, ys = [], []
        for p in self.le.findall("positionablepoint"):
            xs.append(float(p.get("x")))
            ys.append(float(p.get("y")))
        for t in self.le.findall("layoutturnout"):
            for leg in "abcd":
                xs.append(float(t.get(f"x{leg}")))
                ys.append(float(t.get(f"y{leg}")))
        _sheet, le_mod, _core = B.plugin()
        for lb in self.le.findall("positionablelabel"):
            x, y, size = float(lb.get("x")), float(lb.get("y")), int(lb.get("size"))
            xs += [x, x + le_mod.text_width(lb.get("text"), size)]
            ys += [y, y + size]
        for m in self.P.masts:
            x, y, bw, bh = m["box"]
            xs += [x, x + bw]
            ys += [y, y + bh]
        self.assertGreaterEqual(min(xs), 0)
        self.assertGreaterEqual(min(ys), 0)
        self.assertLessEqual(max(xs), w)
        self.assertLessEqual(max(ys), h)

    def test_fitting_keeps_label_fonts(self) -> None:
        _sheet, le_mod, _core = B.plugin()
        sizes = {int(lb.get("size")) for lb in self.le.findall("positionablelabel")}
        unscaled = {le_mod.LABEL_SIZE, le_mod.LABEL_SIZE - 1, le_mod.LABEL_SIZE - 2, le_mod.NUMBER_SIZE,
                    le_mod.TITLE_SIZE}
        self.assertLessEqual(sizes, unscaled)
        self.assertIn(le_mod.TITLE_SIZE, sizes)
        kx, ky = self.P.scale
        self.assertLess(kx, 1.0)                  # the full-size grid is too wide for the display
        self.assertGreaterEqual(ky, kx)           # rows keep their room: only as short as the height needs

    # ---- the live file
    def test_live_tables_unchanged_but_for_the_additions(self) -> None:
        doc = tables.loads(self.data)
        removed = strip_new(doc.root)
        self.assertEqual(removed, 1 + 51 + 3 * 121)
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
        for t in tables.turnouts(self.root):
            if is_new(t):
                self.assertTrue(tables.system_name(t).startswith("IT:"))     # never field hardware
        idents = [el.get("ident") for el in tables.elements(self.le) if el.get("ident")]
        self.assertEqual(len(idents), len(set(idents)))
        self.assertEqual([le.get("name") for le in tables.layout_editors(self.root)],
                         [le.get("name") for le in tables.layout_editors(self.live)] + [B.PANEL_NAME])

    def test_audit_passes_on_the_trial(self) -> None:
        boundaries = AUDIT.load_boundaries(AUDIT.BOUNDARIES)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables_layout.xml"
            path.write_bytes(self.data)
            audit = AUDIT.audit_source("trial", path, boundaries, {b.mast for b in boundaries})
        self.assertEqual(audit.errors, [])
        self.assertEqual(audit.facts["panel"], LIVE_PANEL)

    def test_check_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
                B, "build", return_value=(self.data, self.P, self.names, self.bands)):
            out = Path(tmp) / "t.xml"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(B.main(["--out", str(out)]), 0)
                self.assertEqual(B.main(["--check", "--out", str(out)]), 0)
                out.write_bytes(out.read_bytes() + b" ")
                self.assertEqual(B.main(["--check", "--out", str(out)]), 1)

    def test_renderer_draws_arcs_and_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.xml"
            path.write_bytes(self.data)
            _pp, _legs, turnouts, segs, signals, _st = RENDER.load_geometry(path, B.PANEL_NAME, curves=True)
            self.assertEqual(len(turnouts), 71)
            self.assertEqual(len(signals), len(self.P.masts))
            self.assertEqual({s["hidden"] for s in signals}, {True, False})
            shown = [s for s in self.le.findall("tracksegment") if s.get("hidden") != "yes"]
            self.assertGreater(len(segs), len(shown))                # arcs drawn as pieces
            labels, shapes = RENDER.load_decor(path, B.PANEL_NAME)
            self.assertEqual(len(shapes), 8)
            self.assertIn("MAIN LEVEL", {lb[0] for lb in labels})


class Pieces(unittest.TestCase):
    def test_live_chains_follow_anchors_to_the_next_turnout(self) -> None:
        xml = ('<LayoutEditor name="P">'
               '<layoutturnout ident="TO1" type="RH_TURNOUT" connectaname="T1" connectbname="T2" connectcname="T3"/>'
               '<positionablepoint ident="A1" type="ANCHOR" connect1name="T1" connect2name="T4"/>'
               '<positionablepoint ident="EB1" type="END_BUMPER" connect1name="T4"/>'
               '<positionablepoint ident="EB2" type="END_BUMPER" connect1name="T2"/>'
               '<positionablepoint ident="EB3" type="END_BUMPER" connect1name="T3"/>'
               '<tracksegment ident="T1" blockname="X West" connect1name="TO1" type1="TURNOUT_A" '
               'connect2name="A1" type2="POS_POINT"/>'
               '<tracksegment ident="T4" blockname="X" connect1name="A1" type1="POS_POINT" '
               'connect2name="EB1" type2="POS_POINT"/>'
               '<tracksegment ident="T2" blockname="Y" connect1name="TO1" type1="TURNOUT_B" '
               'connect2name="EB2" type2="POS_POINT"/>'
               '<tracksegment ident="T3" blockname="Z" connect1name="EB3" type1="POS_POINT" '
               'connect2name="TO1" type2="TURNOUT_C"/></LayoutEditor>')
        chains = B.live_chains(ET.fromstring(xml))
        got = {c["ends"][0][1]: c["blocks"] for c in chains}
        self.assertEqual(got, {"A": ["X West", "X"], "B": ["Y"], "C": ["Z"]})

    def test_runs_join_tracks_through_a_turnback(self) -> None:
        band = {"nodes": {"S": {"kind": "switch"}, "T": {"kind": "switch"}, "turn": {"kind": "turnL"}},
                "strands": {"a": {"src": ("turn", 0), "dst": ("S", "A")},
                            "b": {"src": ("turn", 1), "dst": ("T", "C")}}}
        (start, chain, end), = B.runs(band)
        self.assertEqual({start[0], end[0]}, {"S", "T"})
        self.assertEqual([sid for sid, _ in chain], ["a", "b"] if start[0] == "S" else ["b", "a"])
        self.assertEqual(dict(chain), {"a": start[0] == "S", "b": start[0] != "S"})


class ReviewFixes(unittest.TestCase):
    def test_split_connector_track_counts_both_pieces(self) -> None:
        _sheet, le_mod, _core = B.plugin()
        _names, lengths = B.placeholder_names(Built.bands, le_mod)
        cm = {k: s["cm"] for _, b, _ in Built.bands for k, s in b["strands"].items()}
        self.assertGreater(cm["e36x"], 0)
        # e36 (19.7 cm) is cut at connector A into a piece on each level: both count (the plugin rounds each piece)
        self.assertAlmostEqual(lengths["OS Switch 135"], (cm["e36x"] + cm["e36y"]) * 10)
        self.assertAlmostEqual(lengths["OS Switch 129"], (cm["e37x"] + cm["e37y"]) * 10)
        self.assertGreater(lengths["OS Switch 135"], 190)
        self.assertAlmostEqual(lengths["Track e33"], next(s["cm"] for _, b, _ in Built.bands
                                                          for k, s in b["strands"].items() if k == "e33.0") * 10)

    def test_east_and_west_blocks_go_with_their_track(self) -> None:
        strands = {"a": {"name": "K-1"}, "b": {"name": "K-2"}, "c": {"name": "Main East"}}
        got = B.share_blocks(["Track K-1", "Track K-2 West", "Track K-2"], [("a", False), ("b", True)], strands)
        self.assertEqual(got, {"a": ["Track K-1"], "b": ["Track K-2", "Track K-2 West"]})
        got = B.share_blocks(["Track Main East"], [("c", False)], strands)   # a track really named ... East
        self.assertEqual(got, {"c": ["Track Main East"]})

    def test_a_track_with_one_label_at_both_ends_needs_a_symmetric_block_order(self) -> None:
        chain = dict(labels=["7", "7"], blocks=["Track X", "Track Y"], ends=[("TO1", "B"), ("TO1", "C")])
        with self.assertRaises(B.BuildError):
            B.orient(chain, "7", "x")
        chain["blocks"] = ["Track X"]
        self.assertEqual(B.orient(chain, "7", "x")[0], ["Track X"])
        chain = dict(labels=["1", "3"], blocks=["A", "B"], ends=[("TO1", "B"), ("TO3", "A")])
        self.assertEqual(B.orient(chain, "3", "x"), (["B", "A"], [("TO3", "A"), ("TO1", "B")]))

    def test_runs_stop_on_a_broken_or_closed_turnback(self) -> None:
        lone = {"nodes": {"S": {"kind": "switch"}, "turn": {"kind": "turnL"}},
                "strands": {"a": {"src": ("turn", 0), "dst": ("S", "A")}}}
        with self.assertRaises(B.BuildError):
            B.runs(lone)
        ring = {"nodes": {"t1": {"kind": "turnL"}, "t2": {"kind": "turnR"}},
                "strands": {"a": {"src": ("t1", 0), "dst": ("t2", 0)}, "b": {"src": ("t2", 1), "dst": ("t1", 1)}}}
        with self.assertRaises(B.BuildError):
            B.runs(ring)

    def test_live_chains_stop_at_what_they_cannot_follow(self) -> None:
        for far in ('<positionablepoint ident="EC1" type="EDGE_CONNECTOR" connect1name="T1"/>',
                    '<levelxing ident="X1" connectaname="T1"/>'):
            typ = "POS_POINT" if "EC1" in far else "LEVEL_XING_A"
            name = "EC1" if "EC1" in far else "X1"
            xml = ('<LayoutEditor name="P"><layoutturnout ident="TO1" type="RH_TURNOUT" connectaname="T1"/>' + far +
                   f'<tracksegment ident="T1" blockname="X" connect1name="TO1" type1="TURNOUT_A" '
                   f'connect2name="{name}" type2="{typ}"/></LayoutEditor>')
            with self.assertRaisesRegex(B.BuildError, "does not follow"):
                B.live_chains(ET.fromstring(xml))

    def test_tables_with_no_names_only_block_pass_stop(self) -> None:
        doc = tables.load(paths.TABLES_XML)
        blocks_el = doc.root.find("blocks")
        for b in tables.blocks(doc.root, full=False):
            blocks_el.remove(b)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            path.write_bytes(doc.tobytes())
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(B.BuildError, "names-only"):
                B.build(path, bands=Built.bands)


def anchor_panel(*anchors) -> str:
    """A panel of separate W|E boundaries, one anchor each (A1, A2, ...), the anchor's east slot holding `anchors`."""
    parts = []
    for i, mast in enumerate(anchors, 1):
        y = 100 * i
        east = f' eastboundsignalmast="{mast}"' if mast else ""
        parts += [f'<positionablepoint ident="EB{i}a" type="END_BUMPER" x="0" y="{y}" connect1name="T{i}a"/>',
                  f'<positionablepoint ident="A{i}" type="ANCHOR" x="100" y="{y}" connect1name="T{i}a" '
                  f'connect2name="T{i}b"{east}/>',
                  f'<positionablepoint ident="EB{i}b" type="END_BUMPER" x="200" y="{y}" connect1name="T{i}b"/>',
                  f'<tracksegment ident="T{i}a" blockname="W" connect1name="EB{i}a" type1="POS_POINT" '
                  f'connect2name="A{i}" type2="POS_POINT"/>',
                  f'<tracksegment ident="T{i}b" blockname="E" connect1name="A{i}" type1="POS_POINT" '
                  f'connect2name="EB{i}b" type2="POS_POINT"/>']
    return "<LayoutEditor>" + "".join(parts) + "</LayoutEditor>"


class SecondReview(unittest.TestCase):
    def fake(self, n_anchors):
        el = ET.fromstring(anchor_panel(*["M"] + [""] * (n_anchors - 1)))
        P = mock.Mock(turnouts=[], points={p.get("ident"): {"band": 0} for p in el.findall("positionablepoint")},
                      masts=[dict(mast="M", kind="anchor", ident="A1", slot="east")])
        le_mod = mock.Mock(to_xml=lambda *_a: el)
        return P, el, le_mod

    def test_a_mast_two_slots_would_fit_stops_the_build(self) -> None:
        P, el, le_mod = self.fake(1)
        B.check_slots(P, [{"mast": "M"}], el, le_mod)                       # one W|E boundary: certain
        P, el, le_mod = self.fake(2)
        with self.assertRaisesRegex(B.BuildError, "fits 2 slots"):
            B.check_slots(P, [{"mast": "M"}], el, le_mod)

    def test_slots_naming_a_mast_by_system_name_resolve(self) -> None:
        root = tables.read(paths.TABLES_XML)
        live = copy.deepcopy(tables.layout_editor(root, LIVE_PANEL))
        system = tables.mast_system_names(root)
        point = next(p for p in live.findall("positionablepoint") if p.get("eastboundsignalmast") == "Mast 16R")
        point.set("eastboundsignalmast", system["Mast 16R"])
        with contextlib.redirect_stdout(io.StringIO()):
            got = {m["mast"]: m for m in B.staging_masts(root, live)}
        self.assertIn(system["Mast 16R"], got)
        self.assertEqual(got[system["Mast 16R"]]["icon"], list(tables.MAST_ICON_DWARF))     # one-low virtual
        self.assertTrue(got[system["Mast 16R"]]["hidden"])

    def test_hidden_only_when_every_live_icon_is(self) -> None:
        live = ET.fromstring('<LayoutEditor><signalmasticon signalmast="M" hidden="yes"/>'
                             '<signalmasticon signalmast="M" hidden="no"/>'
                             '<signalmasticon signalmast="N" hidden="yes"/></LayoutEditor>')
        self.assertEqual(B.live_icons_hidden(live, {}), {"M": False, "N": True})

    def test_the_trial_is_never_written_over_the_live_tables(self) -> None:
        self.assertTrue(B.live_target(paths.TABLES_XML))
        self.assertTrue(B.live_target(paths.JMRI_USER_FILES / "tables.xml"))
        self.assertFalse(B.live_target(B.TRIAL))
        with mock.patch.object(B, "build") as built_, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(B.main(["--out", str(paths.TABLES_XML)]), 1)
            self.assertEqual(B.main(["--out", str(paths.JMRI_USER_FILES / "x.xml")]), 1)
        built_.assert_not_called()
        self.assertIn("viewing only", out.getvalue())
        self.assertIn("for looking at only", B.__doc__)

    def test_renderer_sizes_icons_by_mast_type(self) -> None:
        data = built()[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.xml"
            path.write_bytes(data)
            signals = RENDER.load_geometry(path, B.PANEL_NAME, curves=True)[4]
        sizes = {s["name"]: s["size"] for s in signals}
        self.assertEqual(sizes["Mast 2L"], tables.MAST_ICON_HIGH)        # two-searchlight
        self.assertEqual(sizes["Mast 2R"], tables.MAST_ICON_DWARF)       # one-low virtual
        bw, bh = RENDER.icon_box({"size": tables.MAST_ICON_HIGH, "degrees": 90})
        self.assertAlmostEqual(bw, 40)
        self.assertAlmostEqual(bh, 12)
        for bad in ("0", "-1", "x", "inf"):
            with self.subTest(bad=bad), self.assertRaises(Exception):
                RENDER.positive(bad)
        self.assertEqual(RENDER.positive("1"), 1.0)


if __name__ == "__main__":
    unittest.main()
