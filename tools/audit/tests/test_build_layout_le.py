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
from collections import Counter
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


def is_new_name(name) -> bool:
    """A main or upper level turnout name (Switch 101 to 245)."""
    return bool(re.fullmatch(r"Switch [12]\d\d", name or ""))


def used_blocks(le) -> set:
    out = {s.get("blockname") for s in le.findall("tracksegment")}
    for t in le.findall("layoutturnout"):
        out |= {t.get(a) for a in ("blockname", "blockbname", "blockcname", "blockdname") if t.get(a)}
    return out


def closed_block(facts: dict) -> dict:
    """{turnout name: block of the track on its closed route} for each plain turnout (`facts`: turnout facts, from
    B.turnout_facts(panel) or the frozen le_inputs.Inputs.turnout_facts())."""
    out = {}
    for t in facts.values():
        if "XOVER" not in t["type"]:
            out[t["name"]] = t["legs"]["B" if t["continuing"] == "2" else "C"]
    return out


def crossover_legs(facts: dict) -> dict:
    """{turnout name: (type, sorted (leg block, block of the track on that leg))} for each crossover."""
    out = {}
    for t in facts.values():
        if "XOVER" in t["type"] and t["type"] != "DOUBLE_XOVER":
            own = t["blocks"][0]
            pairs = sorted(((own if i == 0 else t["blocks"][i] or own), t["legs"][leg]) for i, leg in enumerate("ABCD"))
            out[t["name"]] = (t["type"], pairs)
    return out


def frozen_blocks(inputs) -> set:
    out = {b for c in inputs.chains for b in c["blocks"]}
    for t in inputs.turnouts:
        out |= {t[a] for a in ("blockname", "blockbname", "blockcname", "blockdname") if t.get(a)}
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
        cls.inputs = B.le_inputs.load()          # the staging facts frozen from the hand-drawn panel
        cls.items = {el.get("ident"): el for el in tables.elements(cls.le) if el.get("ident")}

    # ---- staging is the live railroad
    def test_every_live_staging_turnout_and_block_is_on_the_new_panel(self) -> None:
        live_turnouts = {t["turnoutname"] for t in self.inputs.turnouts}
        new_turnouts = {t.get("turnoutname") for t in self.le.findall("layoutturnout")}
        self.assertTrue(live_turnouts)
        self.assertLessEqual(live_turnouts, new_turnouts)
        self.assertLessEqual(frozen_blocks(self.inputs), used_blocks(self.le))

    def test_closed_routes_and_crossovers_match_the_live_panel(self) -> None:
        live, new = closed_block(self.inputs.turnout_facts()), closed_block(B.turnout_facts(self.le))
        self.assertEqual(len(live), 17)
        for name, block in live.items():
            self.assertEqual(new[name], block, name)
        live_x, new_x = crossover_legs(self.inputs.turnout_facts()), crossover_legs(B.turnout_facts(self.le))
        self.assertEqual(sorted(live_x), ["Switch 23", "Switch 35", "Switch 7"])
        for name, legs in live_x.items():
            self.assertEqual(new_x[name], legs, name)

    def test_no_staging_object_is_created(self) -> None:
        for t in tables.turnouts(self.root):
            if is_new(t):
                self.assertTrue(re.fullmatch(r"Switch [12]\d\d", tables.user_name(t)), tables.user_name(t))
        live_lb = {tables.user_name(b) for b in tables.layout_blocks(self.live)}
        staging = set(self.names[B.STAGING]["os"].values()) | {
            b for v in self.names[B.STAGING]["blocks"].values() for b in v}
        self.assertLessEqual(staging, live_lb)

    # ---- main and upper: the device map's names (device_map_main_upper.csv)
    def test_main_and_upper_device_map_names(self) -> None:
        device = B.device_names()
        new_t = [tables.user_name(t) for t in tables.turnouts(self.root) if is_new(t)]
        self.assertEqual(len(new_t), 41)                # one turnout per crossover (101A and 101B are Switch 101)
        self.assertEqual(set(new_t), {v for k, v in device.items() if k.startswith("Switch ")})
        self.assertIn("Switch 223", new_t)              # its trial name's mark dropped
        self.assertIn("Switch 225", new_t)              # the double crossover
        new_lb = {tables.user_name(b) for b in tables.layout_blocks(self.root) if is_new(b)}
        self.assertEqual(len(new_lb), 121)
        self.assertEqual(new_lb, {v for k, v in device.items() if not k.startswith("Switch ")})
        self.assertIn("OS Switch 135", new_lb)          # connector A joins 135A and 135B: their OS block
        self.assertIn("Track 135-H2", new_lb)           # the placeholder Track e68+e81
        self.assertFalse({b for b in new_lb if re.search(r"\be\d+", b)})
        dx = [t for t in self.le.findall("layoutturnout") if t.get("type") == "DOUBLE_XOVER"]
        self.assertEqual([t.get("turnoutname") for t in dx], ["Switch 225"])
        # a crossover's halves on one level are one single crossover; the helix-top 129 and 135 stand on two
        # levels, so each is two Layout Editor turnouts on one turnout
        xo = Counter(t.get("turnoutname") for t in self.le.findall("layoutturnout")
                     if t.get("type") in ("RH_XOVER", "LH_XOVER") and is_new_name(t.get("turnoutname")))
        self.assertEqual(set(xo), {f"Switch {n}" for n in (101, 103, 119, 213, 217, 221, 241, 245)})
        twice = Counter(t.get("turnoutname") for t in self.le.findall("layoutturnout"))
        self.assertEqual({n for n, c in twice.items() if c > 1}, {"Switch 129", "Switch 135"})

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
        prefix = B.TRIAL_LE_LABELS["switch_prefix"]          # switch numbers as the plugin's label layer writes them
        self.assertTrue({"STAGING LEVEL", "MAIN LEVEL", "Main West", prefix + "39", prefix + "135A"} <= texts, texts)
        self.assertEqual(self.le.findall("BlockContentsIcon"), [])     # none in the all-levels trial
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
        # everything drawn lies on the panel: track, turnout legs, labels (at the width JMRI draws) and icons
        xs, ys = [], []
        for p in self.le.findall("positionablepoint"):
            xs.append(float(p.get("x")))
            ys.append(float(p.get("y")))
        for t in self.le.findall("layoutturnout"):
            for leg in "abcd":
                xs.append(float(t.get(f"x{leg}")))
                ys.append(float(t.get(f"y{leg}")))
        B.plugin()
        jt = B.importlib.import_module("schematic.jmri_text")
        for lb in self.le.findall("positionablelabel"):
            x, y, size, bold = float(lb.get("x")), float(lb.get("y")), int(lb.get("size")), lb.get("style") == "1"
            xs += [x, x + jt.width(lb.get("text"), size, bold)]
            ys += [y, y + jt.height(size, bold)]
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
        self.assertEqual(removed, 1 + 41 + 3 * 121)
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
            self.assertEqual(len(turnouts), 63)
            self.assertEqual(len(signals), len(self.P.masts))
            self.assertEqual({s["hidden"] for s in signals}, {True, False})
            shown = [s for s in self.le.findall("tracksegment") if s.get("hidden") != "yes"]
            self.assertGreater(len(segs), len(shown))                # arcs drawn as pieces
            labels, shapes = RENDER.load_decor(path, B.PANEL_NAME)
            self.assertEqual(len(shapes), 8)
            self.assertIn("MAIN LEVEL", {lb[0] for lb in labels})


class DeviceNames(unittest.TestCase):
    """device_map_main_upper.csv's trial_name maps each drawn placeholder to a device-map name; anything else stops."""
    HEAD = "level,cp,layer,user_name,system_name,node,dcc,comment,trial_name,notes\n"

    def read(self, rows: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "map.csv"
            path.write_text(self.HEAD + rows, encoding="utf-8")
            return B.device_names(path)

    def test_the_committed_map(self) -> None:
        got = B.device_names()
        self.assertEqual(got["Switch 101A"], "Switch 101")
        self.assertEqual(got["Switch 101B"], "Switch 101")
        self.assertEqual(got["Switch 223"], "Switch 223")          # "Switch 223*" in the file
        self.assertEqual(got["Track e68+e81"], "Track 135-H2")
        self.assertEqual(len(got), 51 + 121)

    def test_rows_read_and_bad_rows_stop(self) -> None:
        got = self.read('2,,turnout,DCC Switch 101,MTT120,34,120,,,\n'
                        '2,,turnout,Switch 101,M2T1,34,120,,"Switch 101A, Switch 101B",\n'
                        '2,,fb,FB Switch 101 N,M2S1,34,,,,\n'
                        '2,,block,Track 1-2,,,,,Track e1,\n')
        self.assertEqual(got, {"Switch 101A": "Switch 101", "Switch 101B": "Switch 101", "Track e1": "Track 1-2"})
        for rows, why in (('2,,block,Track 1-2,,,,,,\n', "has no trial_name"),
                          ('2,,block,Track 1-2,,,,,Track e1,\n2,,block,Track 3-4,,,,,Track e1,\n',
                           "trial_name Track e1 is given to Track 1-2 and Track 3-4"),
                          ('2,,turnout,Turnout 5,,,,,Switch 5,\n', "is not named"),
                          ('2,,block,Siding,,,,,Track e1,\n', "is not named"),
                          ('2,,fb,FB 1,,,,,,\n', "no turnout or block rows")):
            with self.subTest(why=why), self.assertRaisesRegex(B.BuildError, why):
                self.read(rows)
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(B.BuildError, "cannot read"):
            B.device_names(Path(tmp) / "none.csv")

    def test_a_placeholder_with_no_name_or_a_name_with_no_placeholder_stops(self) -> None:
        _sheet, le_mod, _core = B.plugin()
        bands = B.schematic()[0]
        device = B.device_names()
        with self.assertRaisesRegex(B.BuildError, "names nowhere: \\['Track e1'\\]"):
            B.level_names(bands, le_mod, {k: v for k, v in device.items() if k != "Track e1"})
        with self.assertRaisesRegex(B.BuildError, "does not have: \\['Track e999'\\]"):
            B.level_names(bands, le_mod, dict(device, **{"Track e999": "Track 9-9"}))
        names, lengths = B.placeholder_names(bands, le_mod)         # a length with no device-map row: named, no KeyError
        with mock.patch.object(B, "placeholder_names", return_value=(names, dict(lengths, **{"Track e777": 1.0}))):
            with self.assertRaisesRegex(B.BuildError, "names nowhere: \\['Track e777'\\]"):
                B.level_names(bands, le_mod, device)

    def test_named_bands_join_a_crossovers_halves_and_name_one_track_per_block(self) -> None:
        _sheet, le_mod, _core = B.plugin()
        bands = B.schematic()[0]
        names, _lengths = B.level_names(bands, le_mod)
        B.shared_turnouts(names)
        self.assertEqual(names["Main"]["shared_turnouts"], ["Switch 129", "Switch 135"])
        self.assertEqual(names["Upper"]["shared_turnouts"], ["Switch 129", "Switch 135"])
        drawn = B.named_bands(bands, names)
        self.assertIs(drawn[0][1], bands[0][1])                 # staging as it is
        main = drawn[1][1]
        labels = {d.get("label") for d in main["nodes"].values()}
        self.assertIn("101", labels)
        self.assertNotIn("101A", labels)
        self.assertIn("129A", labels)                           # its B half is on the upper level
        self.assertEqual(drawn[1][2]["le_labels"], dict(B.LEVEL_LE_LABELS, numbers_below=B.NUMBERS_BELOW["Main"]))
        self.assertEqual(drawn[2][2]["le_labels"], dict(B.LEVEL_LE_LABELS, numbers_below=[]))
        named = [s["name"] for s in main["strands"].values() if s["name"]]
        self.assertEqual(len(named), len(set(named)))           # one track per block
        self.assertIn("McKees Rocks", named)                    # the helix track keeps its plan name
        bad = copy.deepcopy(names)
        n = next(k for k, d in bands[1][1]["nodes"].items() if d.get("label") == "101B")
        bad["Main"]["turnouts"][n] = "Switch 999"
        with self.assertRaisesRegex(B.BuildError, "joined as a crossover but the device map gives them two"):
            B.named_bands(bands, bad)
        prefs = [(t, b, dict(o, le_labels={})) for t, b, o in bands]
        with self.assertRaisesRegex(B.BuildError, "already hold le_labels"):
            B.named_bands(prefs, names)


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
        chains = B.le_inputs.live_chains(ET.fromstring(xml))
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
            with self.assertRaisesRegex(B.le_inputs.InputsError, "does not follow"):
                B.le_inputs.live_chains(ET.fromstring(xml))

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
        P.name = lambda i: i            # Mock's own name= argument is not an attribute: set it after
        P.moved = []
        le_mod = mock.Mock(to_xml=lambda *_a: el)
        return P, el, le_mod

    def test_a_mast_two_slots_would_fit_stops_the_build(self) -> None:
        want = [{"mast": "M", "kind": "anchor", "ident": "A1", "slot": "east"}]
        P, el, le_mod = self.fake(1)
        B.check_slots(P, want, le_mod)                                      # one W|E boundary: certain
        P, el, le_mod = self.fake(2)
        with self.assertRaisesRegex(B.BuildError, "fits 2 slots"):
            B.check_slots(P, want, le_mod)
        P, el, le_mod = self.fake(1)
        with self.assertRaisesRegex(B.BuildError, "M was not asked for"):
            B.check_slots(P, [], le_mod)
        for ident, slot in (("A2", "east"), ("A1", "west")):         # masts.csv edited by hand: it must take effect
            with self.subTest(ident=ident, slot=slot), self.assertRaisesRegex(
                    B.BuildError, f"M stands at A1 east, masts.csv says {ident} {slot}"):
                B.check_slots(P, [dict(want[0], ident=ident, slot=slot)], le_mod)
        P.moved = [("t", "M", "at a helix join")]                    # the all-levels trial's helix-join masts
        B.check_slots(P, [dict(want[0], ident="EB9", slot="west")], le_mod)

    def test_slots_naming_a_mast_by_system_name_resolve(self) -> None:
        root = tables.read(paths.TABLES_XML)
        live = copy.deepcopy(tables.layout_editor(root, LIVE_PANEL))
        system = tables.mast_system_names(root)
        point = next(p for p in live.findall("positionablepoint") if p.get("eastboundsignalmast") == "Mast 16R")
        point.set("eastboundsignalmast", system["Mast 16R"])
        with contextlib.redirect_stdout(io.StringIO()):
            got = {m["mast"]: m for m in B.le_inputs.staging_masts(root, live, B.slots_module())}
        self.assertIn(system["Mast 16R"], got)
        self.assertEqual(got[system["Mast 16R"]]["icon"], list(tables.MAST_ICON_DWARF))     # one-low virtual
        self.assertTrue(got[system["Mast 16R"]]["hidden"])

    def test_hidden_only_when_every_live_icon_is(self) -> None:
        live = ET.fromstring('<LayoutEditor><signalmasticon signalmast="M" hidden="yes"/>'
                             '<signalmasticon signalmast="M" hidden="no"/>'
                             '<signalmasticon signalmast="N" hidden="yes"/></LayoutEditor>')
        self.assertEqual(B.le_inputs.live_icons_hidden(live, {}), {"M": False, "N": True})

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


class Throats(unittest.TestCase):
    """The short throat blocks of a staging track (S-1 West / S-1 East, East Lead East, K-1 West) are drawn at their
    own ends of the track, in block order, at their real share (wiki/DISPATCHER_LAYOUT_HOOPS.md: mid-block anchors
    vs throat blocks), not cut into equal thirds."""

    @classmethod
    def setUpClass(cls) -> None:
        _data, cls.P, cls.names, cls.bands = built()
        _sheet, cls.le_mod, _core = B.plugin()
        cls.turnouts = {t["ident"]: t for t in cls.P.turnouts}
        cls.segs = {s["ident"]: s for s in cls.P.segments}

    def xy(self, end):
        ident, typ = end
        return tuple(self.P.points[ident]["xy"]) if typ == "POS_POINT" else tuple(self.turnouts[ident]["pts"][typ[-1]])

    def drawn(self, sid, bent=False):
        """[(block, px)] along a staging track from its first end, runs of one block folded; with `bent`, only the
        px of its arcs and slopes."""
        out = []
        for ident in self.P.strand_segments[(0, sid)]:
            s = self.segs[ident]
            a, b = (self.xy(e) for e in s["ends"])
            L = self.le_mod.piece_len(dict(kind="arc", a=a, b=b, angle=s["arc"]["angle"])) if s["arc"] else \
                self.le_mod.math.dist(a, b)
            if bent and not s["arc"] and abs(a[1] - b[1]) < 0.5:
                L = 0.0
            if out and out[-1][0] == s["block"]:
                out[-1] = (s["block"], out[-1][1] + L)
            else:
                out.append((s["block"], L))
        return out

    def measured(self):
        lengths = self.names[B.STAGING]["lengths"]
        return {sid: bl for sid, bl in self.names[B.STAGING]["blocks"].items()
                if len(bl) > 1 and all(b in lengths for b in bl)}

    def test_the_throat_tracks_are_measured(self) -> None:
        tracks = {self.bands[0][1]["strands"][sid]["name"] for sid in self.measured()}
        self.assertEqual(tracks, {"S-R", "S-1", "S-2", "S-3", "S-4", "East Lead", "K-1"})

    def test_throats_sit_at_their_own_ends_in_block_order(self) -> None:
        lengths = self.names[B.STAGING]["lengths"]
        moved = {}
        for _mast, ident, px in self.P.anchors_moved:
            moved[ident] = max(moved.get(ident, 0.0), px)
        for sid, blocks in sorted(self.measured().items()):
            on_track = {e[0] for i in self.P.strand_segments[(0, sid)] for e in self.segs[i]["ends"]}
            stretch = max([0.0] + [px for ident, px in moved.items() if ident in on_track])
            with self.subTest(track=self.bands[0][1]["strands"][sid]["name"]):
                got = self.drawn(sid)
                bent = dict(self.drawn(sid, bent=True))
                self.assertEqual([b for b, _ in got], blocks)                  # the order along the run
                total, real = sum(L for _, L in got), sum(lengths[b] for b in blocks)
                for b, L in got:
                    if lengths[b] * 4 < real:                                   # a throat: at an end, short
                        self.assertIn(b, (blocks[0], blocks[-1]))
                        share = total * lengths[b] / real
                        self.assertGreaterEqual(L, min(self.le_mod.MIN_BLOCK, share) - 0.5)
                        # its share, or the floor, or the room for the icon of a mast facing it (a high mast needs
                        # more), plus what the gantry moved its boundary and the arcs and slopes it takes in (a
                        # boundary stands on straight track)
                        room = [8 + m["icon"][1] for m in self.names[B.STAGING]["masts"] if m["facing"] == b]
                        least = max([self.le_mod.MIN_BLOCK] + room)
                        self.assertLessEqual(L, max(share, least) + stretch + bent[b] + 0.5)
                        self.assertLess(L, total / 2)

    def test_the_south_yard_masts_stand_in_a_column_by_each_ladder(self) -> None:
        cols = {}
        for g in self.P.gantries:
            names = {m["mast"] for m in g}
            xs = {round(self.P.points[m["ident"]]["xy"][0], 1) for m in g if m["kind"] == "anchor"}
            if not xs:                      # a gantry of turnout-leg masts only: no anchor column
                continue
            self.assertEqual(len(xs), 1, names)
            x = xs.pop()
            for n in names:
                cols[n] = x
        west = [cols[f"Mast {n}L"] for n in (16, 18, 20) if f"Mast {n}L" in cols]
        east = [cols[f"Mast {n}R"] for n in (16, 18, 20) if f"Mast {n}R" in cols]
        self.assertTrue(west and east)
        for sid in self.measured():
            if self.bands[0][1]["strands"][sid]["name"].startswith("S-"):
                pts = [self.xy(self.segs[i]["ends"][0]) for i in self.P.strand_segments[(0, sid)]]
                lo, hi = min(p[0] for p in pts), max(p[0] for p in pts)
                self.assertLess(max(west), lo + (hi - lo) / 2)                  # the west column on the west half
                self.assertGreater(min(east), lo + (hi - lo) / 2)               # the east column on the east half


if __name__ == "__main__":
    unittest.main()


class FinalReview(unittest.TestCase):
    """The 2026-11-16 code review's findings on the cut-over build."""

    def test_legs_swapped_and_generated_slot_agree(self) -> None:
        B.check_swapped_slots()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.csv"
            text = B.BOUNDARIES.read_text(encoding="utf-8")
            path.write_text(text.replace("(owner, 2026-11-16)\",C", "(owner, 2026-11-16)\","), encoding="utf-8")
            with self.assertRaisesRegex(B.BuildError, "TO1 B .*generated_slot empty, LEGS_SWAPPED gives C"):
                B.check_swapped_slots(path)
            path.write_text(text + "turnout,TO99,B,Mast X,,C\n", encoding="utf-8")
            with self.assertRaisesRegex(B.BuildError, "TO99 B .*generated_slot C, LEGS_SWAPPED gives empty"):
                B.check_swapped_slots(path)

    def test_station_steps_on_one_row_stop(self) -> None:
        boxes = mock.Mock(extras=[{"id": "A", "box": (100, 0, 10, 10)}, {"id": "B", "box": (90, 0, 10, 10)},
                                  {"id": "W", "box": (50, 0, 10, 10)}, {"id": "V", "box": (70, 48, 10, 10)}])
        with self.assertRaisesRegex(B.BuildError, "stand on one row"):
            B.cluster_steps(boxes, [["A", "B"]], [("W", "V")])

    def test_west_shift_stops_on_a_reversed_track(self) -> None:
        raw = B.schematic()[0]
        B.west_shifted(raw)
        with mock.patch.dict(B.WEST_SHIFT, {"columns": 9}), \
                self.assertRaisesRegex(B.BuildError, "overlapped or reversed .*Brick-Plane"):
            B.west_shifted(raw)

    def test_half_lamps_are_for_os_blocks_with_sensors(self) -> None:
        ov = B.overlay_mod()
        panel = ET.fromstring(
            '<LayoutEditor><layoutturnout type="RH_XOVER" turnoutname="Switch 7" blockname="OS Switch 7" '
            'blockcname="OS Switch 7b"/><sensoricon sensor="BS Switch 7"/></LayoutEditor>')
        sensors = {"OS Switch 7": "BS Switch 7", "OS Switch 7b": "BS Switch 7b"}
        with self.assertRaisesRegex(ov.OverlayError, "lamps for .* but none for \\['OS Switch 7b'\\]"):
            ov.check_half_lamps(panel, sensors)
        with self.assertRaisesRegex(ov.OverlayError, "OS Switch 7b has no occupancy sensor"):
            ov.check_half_lamps(panel, {"OS Switch 7": "BS Switch 7"})
        ov.check_half_lamps(panel, {})                          # no lamp shown: nothing to match
        track = ET.fromstring('<LayoutEditor><layoutturnout type="RH_XOVER" turnoutname="Switch 9" '
                              'blockname="OS Switch 9" blockcname="Track X"/><sensoricon sensor="BS 9"/>'
                              '</LayoutEditor>')
        ov.check_half_lamps(track, {"OS Switch 9": "BS 9", "Track X": "BS X"})      # a track block needs none
        gen = mock.Mock(turnouts={"T": track.find("layoutturnout")})
        lamp = mock.Mock(anchor=("turnout", "T", "OS Switch 9", (0, 0)), lamp=True, index=1)
        with mock.patch.object(ov, "in_circle", lambda its: True):
            self.assertEqual(ov.half_lamps([lamp], gen, {"Track X": "BS X"}), [])

    def test_one_track_word_rule(self) -> None:
        ov = B.overlay_mod()
        stations = _load("reconcile_dispatcher_stations", paths.LAYOUT_SCRIPTS / "reconcile_dispatcher_stations.py")
        for name in ("Track EH-1", "Track Power", "EH-1", "Tracks", "Track "):
            el = ET.fromstring(f'<sensoricon text="{name}"/>')
            ov.drop_track_word(el)
            self.assertEqual(el.get("text"), stations.station_display(name, generated=True), name)
