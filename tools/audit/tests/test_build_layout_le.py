"""build_layout_le.py: the three-level build (levels all), drawn like the schematic, on the generator's
base (hartlib.tables_build.base: the template and every level's beans of devices.csv; ADR-029, naming-layers step 11). The all-levels viewing trial these tests once read
(tables_layout.xml) is retired; its behaviour checks read the candidate, which test_le_cutover.py
and test_le_mast_parity.py share."""
from __future__ import annotations

import contextlib
import copy
import functools
import importlib
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
from hartlib import device_ids, level_devices, paths, tables  # noqa: E402
from hartlib import railroad as T_railroad  # noqa: E402  the device map's columns

TABLES = paths.TABLES_XML       # the generated tables.xml (build_tables.py), which the build no longer reads


def staging_key(bands) -> str:
    """The plugin's key of the staging band, found by its level (build_layout_le.base_band), as build() keys its
    names."""
    return B.band_key(bands[B.base_band(bands)][0])


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


def _level_counts() -> tuple[int, int, int, int]:
    """(blocks, sensors, masts, heads) of the main and upper levels in the committed data: the blocks the build adds,
    the device map's block rows (the 107 Loop's halves, 225's corners and Track 227-241's halves among them) less the
    helix blocks, which are staging's beans (Track <plan name>, 2026-11-20/21), and the parts (links inside an OS block,
    each a block of its own, step 5 part 2); a virtual sensor for every block row, the helix blocks' too, which the
    parts share with their OS blocks; and masts.csv."""
    from hartlib import devices
    helix = {h["block"] for h in sys.modules["plan_bands"].read_helix_tracks().values()}
    rows = [r["user_name"] for _n, r in devices.device_map_lines(("2", "3"), B.DEVICE_MAP) if r["layer"] == "block"]
    parts = devices.part_lines(("2", "3"), B.DEVICE_MAP)
    masts = B.read_level_masts()
    return (len([r for r in rows if r not in helix]) + len(parts), len(rows), len(masts),
            sum(len(r["heads"]) for r in masts))


LEVEL_BLOCKS, LEVEL_SENSORS, LEVEL_MASTS, LEVEL_HEADS = _level_counts()
HELIX_BLOCKS = {"Track Helix Outer", "Track Helix Inner"}       # the helix tracks: staging's beans, bound by the build


@functools.lru_cache(maxsize=None)
def _stripped_bytes() -> bytes:
    return B.base_tables()


def stripped() -> ET.Element:
    """A fresh copy of the tables the build draws on: the generator's base (B.base_tables)."""
    return tables.loads(_stripped_bytes()).root


LEVEL_NAMES = B.level_bean_names()      # the system names of the beans the main and upper rows give


def is_new(el) -> bool:
    """A main or upper bean (a bean a main or upper row of the device master gives: le_tables.level_bean_names), which
    the base holds since naming-layers step 11; the generated panel is never one."""
    return el.tag != "LayoutEditor" and B.is_level_bean(el, LEVEL_NAMES)


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
    B.turnout_facts(panel))."""
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


@functools.lru_cache(maxsize=None)
def built():
    """(tables bytes, Panel, names, bands) of the three-level build (levels all, as build_tables.py builds it; the
    approval fingerprint is its own test, test_le_cutover.py): built once for every test module that needs it."""
    with mock.patch.object(B.sdm, "load", wraps=B.sdm.load) as load, contextlib.redirect_stdout(io.StringIO()):
        out = B.build(levels="all", as_live=True)
    STAGING_MAP_LOADS.append(load.call_count)
    return out


STAGING_MAP_LOADS: list = []     # sdm.load calls in the one cached build above


@functools.lru_cache(maxsize=None)
def staging_alone():
    """(tables bytes, Panel, names, bands) of staging drawn alone (levels staging), whose grid the three-level build
    is drawn at: built once for every test module that needs it."""
    with contextlib.redirect_stdout(io.StringIO()):
        return B.build(levels="staging", as_live=True)


@functools.lru_cache(maxsize=None)
def le_window() -> tuple:
    """(width, height): the window the panels open in, the page's le_window (derived from preferences.json[main_upper]
    host_screen by publish_draft.solved_sheet), read by the plugin as the build reads it."""
    return B.plugin()[1].window(B.schematic()[1])


class PagePreferences(unittest.TestCase):
    """The window and staging's rows are the page's preferences (le_window, le_row): without them, or with a bad
    one, the build stops naming it, before drawing."""

    def test_a_missing_or_bad_window_or_row_stops(self) -> None:
        page = dict(B.schematic()[1])
        for prefs, why in (({"le_row": None}, "hold no le_row"), ({"le_window": None}, "hold no le_window"),
                           ({"le_window": [1900]}, "le_window must be"), ({"le_row": 0}, "le_row must be")):
            bad = {k: v for k, v in dict(page, **prefs).items() if v is not None}
            with self.subTest(prefs=prefs), self.assertRaisesRegex(B.BuildError, why):
                B.build(as_live=True, page=bad)


class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data, cls.P, cls.names, cls.bands = built()
        cls.root = tables.loads(cls.data).root
        cls.live = stripped()                                           # the tables the build draws on
        cls.le = tables.layout_editor(cls.root, LIVE_PANEL)              # the generated panel, under the live name
        cls.live_le = tables.layout_editor(tables.read(paths.REPO_TABLES_XML), LIVE_PANEL)  # the live generated one
        cls.items = {el.get("ident"): el for el in tables.elements(cls.le) if el.get("ident")}

    def test_the_staging_device_map_is_read_once_for_the_two_candidates(self) -> None:
        """The three-level build draws the staging candidate first and reuses the map it read, a copy of it."""
        self.assertEqual(STAGING_MAP_LOADS, [1])

    # ---- staging is the live railroad
    def test_every_staging_switch_and_block_is_on_the_new_panel(self) -> None:
        staging = B.staging_switches()
        new_idents = {t.get("ident") for t in self.le.findall("layoutturnout")}
        self.assertEqual(len(staging), 20)
        self.assertLessEqual({sw.le_ident for sw in staging.values()}, new_idents)
        blocks = set(self.names[staging_key(self.bands)]["os"].values()) | {
            b for v in self.names[staging_key(self.bands)]["blocks"].values() for b in v}
        self.assertLessEqual(blocks, used_blocks(self.le))

    def test_closed_routes_and_crossovers_match_the_live_panel(self) -> None:
        # staging's turnouts as the live generated panel in tables.xml has them (switches.csv decides the closed
        # leg when the build draws them: staging_device_map.normal_legs)
        facts, live_facts = B.turnout_facts(self.le), B.turnout_facts(self.live_le)
        live = {n: b for n, b in closed_block(live_facts).items() if not is_new_name(n)}
        self.assertEqual(len(live), 17)
        new = closed_block(facts)
        for name, block in live.items():
            self.assertEqual(new[name], block, name)
        live_x = {n: v for n, v in crossover_legs(live_facts).items() if not is_new_name(n)}
        new_x = crossover_legs(facts)
        self.assertEqual(sorted(live_x), ["Switch 23", "Switch 35", "Switch 7"])
        for name, legs in live_x.items():
            self.assertEqual(new_x[name], legs, name)

    def test_no_staging_object_is_created(self) -> None:
        for t in tables.turnouts(self.root):
            if is_new(t):
                self.assertTrue(re.fullmatch(r"Switch [12]\d\d", tables.user_name(t)), tables.user_name(t))
        live_lb = {tables.user_name(b) for b in tables.layout_blocks(self.live)}
        staging = set(self.names[staging_key(self.bands)]["os"].values()) | {
            b for v in self.names[staging_key(self.bands)]["blocks"].values() for b in v}
        self.assertLessEqual(staging, live_lb)

    # ---- main and upper: the device map's names (the main and upper rows of devices.csv)
    def test_main_and_upper_device_map_names(self) -> None:
        device = B.device_names()
        new_t = [tables.user_name(t) for t in tables.turnouts(self.root) if is_new(t)]
        self.assertEqual(len(new_t), 39)                # one turnout per crossover (101A and 101B are Switch 101)
        self.assertEqual(set(new_t), {v for k, v in device.items() if k.startswith("Switch ")})
        self.assertIn("Switch 223", new_t)              # its trial name's mark dropped
        self.assertIn("Switch 225", new_t)              # the double crossover
        new_lb = {tables.user_name(b) for b in tables.layout_blocks(self.root) if is_new(b)}
        self.assertEqual(len(new_lb), LEVEL_BLOCKS)      # the 107 Loop's two halves and 225's four corners
        self.assertEqual(new_lb, {v for k, v in device.items() if not k.startswith("Switch ")} - HELIX_BLOCKS)
        self.assertIn("OS Switch 131", new_lb)          # connector A joins 131A and 131B: their OS block
        self.assertNotIn("Track Helix Inner", new_lb)   # the placeholder Track 131BB-helix: staging's block, not a new one
        self.assertFalse({b for b in new_lb if re.search(r"\be\d+", b)})
        dx = [t for t in self.le.findall("layoutturnout") if t.get("type") == "DOUBLE_XOVER"]
        self.assertEqual([t.get("turnoutname") for t in dx], ["Switch 225"])
        # a crossover's halves on one level are one single crossover; the helix-top 127 and 131 stand on two
        # levels, so each is two Layout Editor turnouts on one turnout, 101 and 103 (one three-way part in the
        # plan, drawn tight and split by the plugin's rule) are each two plain turnouts on one turnout, and so are
        # 121 and 125, whose halves the plan joins leg C to leg B (2026-11-19)
        xo = Counter(t.get("turnoutname") for t in self.le.findall("layoutturnout")
                     if t.get("type") in ("RH_XOVER", "LH_XOVER") and is_new_name(t.get("turnoutname")))
        self.assertEqual(set(xo), {f"Switch {n}" for n in (119, 211, 217, 221, 243, 245)})
        twice = Counter(t.get("turnoutname") for t in self.le.findall("layoutturnout"))
        self.assertEqual({n for n, c in twice.items() if c > 1},
                         {"Switch 101", "Switch 103", "Switch 121", "Switch 125", "Switch 127", "Switch 131"})
        # 121 and 125: the half the plan joins by its leg B is closed on its leg C, so the one turnout closed puts
        # both halves on their through tracks and thrown on the diagonal between them
        for name in ("Switch 121", "Switch 125"):
            with self.subTest(turnout=name):
                halves = [t for t in self.le.findall("layoutturnout") if t.get("turnoutname") == name]
                self.assertEqual(len(halves), 2)
                legs = [{t.get(f"connect{p}name"): p for p in "bc"} for t in halves]
                diagonal = set(legs[0]) & set(legs[1])
                self.assertEqual(len(diagonal), 1)
                for t, by_track in zip(halves, legs):
                    thrown = "c" if t.get("continuing") == "2" else "b"
                    self.assertEqual(by_track[next(iter(diagonal))], thrown, t.get("ident"))

    def test_every_main_and_upper_block_reports_its_virtual_sensor(self) -> None:
        """Each main and upper block, and its layout block, is bound by user name to its virtual occupancy sensor
        IS:HART:C3:B:<block key> (the device map's jmri_name), stored in the internal sensor section as staging's
        internal sensors are."""
        internal = next(s for s in self.root.findall("sensors") if "InternalSensorManager" in s.get("class"))
        sensors = {tables.user_name(s): tables.system_name(s) for s in internal.findall("sensor") if is_new(s)}
        self.assertEqual(len(sensors), LEVEL_SENSORS)                # the helix blocks' sensors too
        self.assertFalse([s for s in tables.sensors(self.root) if is_new(s) and s not in list(internal)])
        bd = level_devices
        from hartlib import devices
        part_of = {r["user_name"]: r["part_of"] for _n, r in devices.part_lines(("2", "3"), B.DEVICE_MAP)}
        self.assertEqual(len(part_of), 25)          # the links: blocks of their own on their OS block's sensor
        for b in [b for b in tables.blocks(self.root) if is_new(b)]:
            name = part_of.get(tables.user_name(b), tables.user_name(b))
            with self.subTest(block=tables.user_name(b)):
                self.assertEqual(b.findtext("occupancysensor"), bd.occupancy_user(name))
                self.assertEqual(sensors[bd.occupancy_user(name)], bd.block_sensor(name))
                kids = [c.tag for c in b]
                self.assertEqual(kids[kids.index("permissive") + 1], "occupancysensor")
        for lb in [b for b in tables.layout_blocks(self.root) if is_new(b)]:
            name = part_of.get(tables.user_name(lb), tables.user_name(lb))
            self.assertEqual(lb.get("occupancysensor"), bd.occupancy_user(name))
            self.assertEqual(list(lb.attrib)[:2], ["systemName", "occupancysensor"])     # as staging's
        self.assertEqual(sensors["BS Switch 225b"], "IS:HART:C3:B:OS225b")
        self.assertEqual(sensors["BS 107 Loop 2"], "IS:HART:C3:B:107_Loop_2")
        self.assertNotIn("BS Switch 225", sensors)          # the middle of 225's X is a CATS desk block only

    def test_the_virtual_sensors_start_clear_and_only_they(self) -> None:
        """A LogixNG in the tables sets every main and upper virtual block sensor INACTIVE when they load, and no
        other sensor: in the candidate and in the released tables."""
        for label, root in (("candidate", self.root), ("released", tables.read(paths.TABLES_XML))):
            with self.subTest(tables=label):
                level = sorted(tables.system_name(s) for s in tables.sensors(root) if is_new(s))
                self.assertEqual(len(level), LEVEL_SENSORS)
                self.assertEqual(sorted(level_devices.clear_sensors(root)), level)
                acts = {e.findtext("systemName"): e for e in root.find("LogixNGDigitalActions")}
                for name in level_devices.clear_sensors(root):
                    a = acts[level_devices.clear_action(name)]
                    self.assertEqual((a.tag, a.findtext("state/enum")), ("ActionSensor", "Inactive"))
                lx = next(e for e in root.find("LogixNGs") if e.findtext("systemName") == level_devices.CLEAR_LOGIXNG)
                self.assertEqual(lx.get("enabled"), "yes")
                self.assertEqual(lx.findtext("ConditionalNGs/systemName"), level_devices.CLEAR_CONDITIONAL)
                cn = next(e for e in root.find("LogixNGConditionalNGs")
                          if e.findtext("systemName") == level_devices.CLEAR_CONDITIONAL)
                self.assertEqual((cn.get("enabled"), cn.get("executeAtStartup")), ("yes", None))    # runs at load
                self.assertEqual(cn.findtext("Socket/systemName"), level_devices.CLEAR_MANY)
                internal = next(s for s in root.findall("sensors") if "InternalSensorManager" in s.get("class"))
                self.assertEqual(internal.findtext("defaultInitialState"), "unknown")   # the other lamps unchanged

    def test_the_clear_logixng_reader_names_a_broken_action(self) -> None:
        root = tables.read(paths.TABLES_XML)
        acts = root.find("LogixNGDigitalActions")
        first = level_devices.clear_action(level_devices.clear_sensors(root)[0])
        acts.remove(next(e for e in acts if e.findtext("systemName") == first))
        with self.assertRaisesRegex(ValueError, f"socket A1 names {re.escape(first)}, which is not an ActionSensor"):
            level_devices.clear_sensors(root)

    def test_blocks_match_track(self) -> None:
        new_lb = {tables.user_name(b) for b in tables.layout_blocks(self.root) if is_new(b)}
        new_b = {tables.user_name(b) for b in tables.blocks(self.root, full=False) if is_new(b)}
        full_b = {tables.user_name(b) for b in tables.blocks(self.root) if is_new(b)}
        staging_lb = {tables.user_name(b) for b in tables.layout_blocks(self.live) if not is_new(b)}
        self.assertEqual(new_b, new_lb)
        self.assertEqual(full_b, new_lb)
        self.assertEqual(used_blocks(self.le) - staging_lb, new_lb)

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
        # the two main-upper connector joins (Switches 127 and 131); and the two helix joins
        self.assertEqual(sum(1 for s in self.le.findall("tracksegment") if s.get("hidden") == "yes"),
                         4)
        self.assertEqual({s.get("mainline") for s in self.le.findall("tracksegment")}, {"yes", "no"})
        texts = {lb.get("text") for lb in self.le.findall("positionablelabel")}
        prefix = B.schematic()[1]["le_labels"]["switch_prefix"]     # the page's: as the label layer writes them
        self.assertTrue({"STAGING LEVEL", "MAIN LEVEL", "Main West", prefix + "39", prefix + "131A"} <= texts, texts)
        self.assertEqual(len(self.le.findall("layoutShape")), 8)     # four helix ends, four connector ends

    def test_no_track_sensors_and_every_mast_placed(self) -> None:
        # no Entry/Exit sensor (parked) and no track sensor icon: the only sensor icons are the status cluster's
        # (panel_items.json)
        for el in self.le.iter():
            self.assertNotIn(el.tag, ("sensorA", "sensorB", "sensorC", "sensorD"))
            for a in ("eastboundsensor", "westboundsensor"):
                self.assertIsNone(el.get(a))
        items = B.panel_items.load(B.PANEL_ITEMS)["items"]
        status = {ET.fromstring(m["xml"]).get("sensor") for it in items for m in (it.get("members") or [it])
                  if ET.fromstring(m["xml"]).tag == "sensoricon"}
        self.assertTrue(status)
        self.assertEqual({el.get("sensor") for el in self.le.iter("sensoricon")}, status)
        self.assertEqual(B.base_band(self.bands), 0)            # staging, found by its level, is drawn first
        self.assertTrue(self.P.masts)
        # main and upper: their control-point masts (masts.csv), every one placed
        level = {m["mast"] for m in self.P.masts if m["band"] != 0}
        self.assertEqual(level, {r["mast"] for r in B.read_level_masts()})
        self.assertEqual(len(level), LEVEL_MASTS)

    # ---- size: the panel holds what it draws (the window: test_le_cutover.py, the panel scrolls)
    def test_everything_drawn_lies_on_the_panel(self) -> None:
        w, h = int(self.le.get("panelwidth")), int(self.le.get("panelheight"))
        self.assertEqual(le_window(), (1920, 1032))   # host_screen: the layout hosts' 1920 x 1080 less the taskbar
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
        jt = importlib.import_module("schematic.jmri_text")
        for lb in self.le.findall("positionablelabel"):
            if lb.get("text") is None:                # an icon label (the backdrop): its corner on the panel
                xs.append(float(lb.get("x")))
                ys.append(float(lb.get("y")))
                continue
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

    def test_the_grid_scale_keeps_label_fonts(self) -> None:
        _sheet, le_mod, _core = B.plugin()
        # the labels the plugin draws (the panel items, panel_items.json, carry their own sizes), as the panel has them
        sizes = {lb["size"] for lb in self.P.labels}
        drawn = {(lb.get("text"), int(lb.get("size"))) for lb in self.le.findall("positionablelabel")
                 if lb.get("text") is not None}
        self.assertLessEqual({(lb["text"], lb["size"]) for lb in self.P.labels}, drawn)
        # station names at the page's station_size (14, owner 2026-11-21), the rest at the drawing's own sizes
        station = B.schematic()[1]["le_labels"]["station_size"]
        number = B.schematic()[1]["le_labels"]["switch_size"]     # switch numbers at the page's size (C1: 12)
        unscaled = {le_mod.LABEL_SIZE, le_mod.LABEL_SIZE - 1, le_mod.LABEL_SIZE - 2, le_mod.NUMBER_SIZE,
                    le_mod.TITLE_SIZE, station, number}
        self.assertLessEqual(sizes, unscaled)
        self.assertEqual({lb["size"] for lb in self.P.labels if lb["kind"] == "station"}, {station})
        self.assertIn(le_mod.TITLE_SIZE, sizes)
        self.assertNotEqual(self.P.scale, (1.0, 1.0))         # the grid is scaled (staging's fit, stretched)

    # ---- the live file
    def test_the_build_adds_no_bean(self) -> None:
        """Every level's beans are the base's (naming-layers step 11): the three-level candidate is the staging
        candidate, parked and its yard ladder retired as the build does, but for the panel (the staging guard compares
        the panels: test_le_cutover.py)."""
        def no_panel(doc):
            """The tables without the panel, layout whitespace dropped (what is taken out leaves its own)."""
            doc.root.remove(tables.layout_editor(doc.root, LIVE_PANEL))
            for el in doc.root.iter():
                el.text = None if el.text is not None and not el.text.strip() else el.text
                el.tail = None if el.tail is not None and not el.tail.strip() else el.tail
            return ET.tostring(doc.root)
        doc = tables.loads(self.data)
        # turnouts, blocks (2 passes) and layout blocks, their sensors, the startup LogixNG (LogixNG, ConditionalNG,
        # DigitalMany, an ActionSensor per block, an ActionTurnout per turnout), heads and masts
        objects = 39 + 3 * LEVEL_BLOCKS + LEVEL_SENSORS + 3 + LEVEL_SENSORS + 39 + LEVEL_HEADS + LEVEL_MASTS
        self.assertEqual(objects, sum(1 for sec in tables.elements(doc.root) for el in tables.elements(sec)
                                      if is_new(el)))
        base = tables.loads(staging_alone()[0])
        B.parked.split(base.root, B.PARKED)
        B.retire_yard_ladder(base.root)
        self.assertEqual(no_panel(doc), no_panel(base))

    def test_no_name_collisions(self) -> None:
        beans = tables.turnouts(self.root) + tables.blocks(self.root, full=False) + tables.layout_blocks(self.root)
        live_users = {tables.user_name(b) for b in beans if not is_new(b)}
        live_sys = {tables.system_name(b) for b in beans if not is_new(b)}
        new = [b for b in beans if is_new(b)]
        self.assertFalse({tables.user_name(b) for b in new} & live_users)
        self.assertFalse({tables.system_name(b) for b in new} & live_sys)
        for t in tables.turnouts(self.root):
            if is_new(t):
                self.assertTrue(tables.system_name(t).startswith("IT:"))     # never field hardware
        idents = [el.get("ident") for el in tables.elements(self.le) if el.get("ident")]
        self.assertEqual(len(idents), len(set(idents)))
        # the generated panel replaces the live one in place, under its name: no panel beside it
        names = [le.get("name") for le in tables.layout_editors(self.root)]
        self.assertEqual(names.count(LIVE_PANEL), 1)
        self.assertNotIn("Layout (generated)", names)        # the retired viewing trials' panel

    def test_audit_passes_on_the_cut_over_candidate(self) -> None:
        # the audit reads the candidate, whose "HART Railroad" panel is the generated one
        staging = AUDIT.load_staging_masts()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables_cutover.xml"
            path.write_bytes(self.data)
            audit = AUDIT.audit_source("candidate", path, staging, generated=True)
        self.assertEqual(audit.errors, [])
        self.assertEqual(audit.facts["panel"], LIVE_PANEL)

    def test_renderer_draws_arcs_and_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.xml"
            path.write_bytes(self.data)
            _pp, _legs, turnouts, segs, signals, _st = RENDER.load_geometry(path, LIVE_PANEL, curves=True)
            self.assertEqual(len(turnouts), 65)             # 101 and 103 drawn as two plain turnouts each
            self.assertEqual(len(signals), len(self.P.masts))
            self.assertEqual({s["hidden"] for s in signals}, {True, False})
            shown = [s for s in self.le.findall("tracksegment") if s.get("hidden") != "yes"]
            self.assertGreater(len(segs), len(shown))                # arcs drawn as pieces
            labels, shapes = RENDER.load_decor(path, LIVE_PANEL)
            self.assertEqual(len(shapes), 8)
            self.assertIn("MAIN LEVEL", {lb[0] for lb in labels})


class FactsReaders(unittest.TestCase):
    """The build reads switches.csv and the main and upper device map through hartlib.railroad (le_common): the same
    facts, and a file it cannot read stops the build with a BuildError naming the file and row, not a traceback."""

    def setUp(self) -> None:
        self.lc = sys.modules["le_common"]
        self.lc.staging_switches.cache_clear()
        self.addCleanup(self.lc.staging_switches.cache_clear)

    def test_staging_switches_are_hartlibs(self) -> None:
        from hartlib import railroad
        self.assertEqual(B.staging_switches(), railroad.Railroad(upto="inputs").switches)
        self.assertIs(B.staging_switches(), B.staging_switches())          # read once per run

    def test_a_bad_switches_file_stops_with_a_build_error(self) -> None:
        rr = self.lc.railroad
        real = rr.Railroad
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "switches.csv"
            text = (paths.LAYOUT_DATA / "switches.csv").read_text(encoding="utf-8")
            bad.write_text(text + text.splitlines()[-1] + "\n", encoding="utf-8")      # the last switch twice
            def patched(sources=None, upto=rr.LAYERS[-1]):
                return real((sources or rr.Sources.under()).but(switches=bad), upto=upto)
            with mock.patch.object(rr, "Railroad", patched):
                with self.assertRaisesRegex(B.BuildError, r"^staging switches: switches.csv lines \d+ and \d+: both are"):
                    self.lc.switch_idents()

    def test_a_bad_device_map_stops_with_a_build_error(self) -> None:
        from hartlib import devices
        with tempfile.TemporaryDirectory() as tmp:
            rows = list(devices.load(B.DEVICE_MAP))
            block = next(r for r in rows if r["level"] == "2" and r["layer"] == "block")
            bad = devices.write_one_file(rows + [block], Path(tmp) / devices.ONE_FILE)     # a block row twice
            for read in (B.device_names,):
                with self.subTest(read=read.__name__), \
                        self.assertRaisesRegex(B.BuildError, r"^the device map: devices.csv: .*the same level, layer"):
                    read(bad)


class DeviceNames(unittest.TestCase):
    """The main and upper rows' trial_name of devices.csv maps each drawn placeholder to a device-map name; anything
    else stops."""
    HEAD = ",".join(T_railroad.DEVICE_COLUMNS) + "\n"    # the fact columns (DEVICE_FACTS) left empty in each row

    LAYER_ROLES = {"turnout": "turnout", "fb": "fb", "block": "track"}

    def read(self, rows: str, roles: dict | None = None, reader=None) -> dict:
        """device_names of a master made of these device-map rows (old form, the fact columns left out), each with the
        role its writer gives it: `roles` ({user name: role}), else its layer's in LAYER_ROLES; `reader` (default
        device_names) reads the master's path."""
        import csv
        import io
        from hartlib import devices
        text = self.HEAD + rows.replace("\n", "," * len(T_railroad.DEVICE_FACTS) + "\n")
        old = list(csv.DictReader(io.StringIO(text)))
        # each with an id, which check_rows wants on every row with a level: a turnout's names its switch
        # (switch:<n>, dcc:<n>: check_rows holds it to that), any other row's is a test id
        def ident(r):
            if r["layer"] != "turnout":
                return f"test:{r['layer']}:{r['user_name']}"
            n = r["user_name"].split()[-1]
            return device_ids.dcc_id(n) if r["user_name"].startswith("DCC ") else device_ids.switch_id(n)
        mine = [devices.master_row(dict(r, role=(roles or {}).get(r["user_name"]) or self.LAYER_ROLES[r["layer"]],
                                        id=ident(r)), "build_device_map.py")
                for r in old]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / devices.ONE_FILE
            path.write_text(devices.master_text(devices.replace_rows([], "build_device_map.py", mine)), encoding="utf-8")
            return (reader or B.device_names)(path)

    def test_block_roles_are_the_given_maps_main_and_upper_blocks(self) -> None:
        """named_bands' roles come from the map the names were made from: block_roles(path) reads that file's main
        and upper block rows (not the committed master's), with the role each row gives."""
        got = self.read('2,,block,Track 1-2,,,,,,Track 1A-2B,\n2,,block,OS Switch 1,,,,,,Switch 1,\n'
                        '1,,block,Track Barn,,,,,,,\n', roles={"OS Switch 1": "os"},
                        reader=sys.modules["le_names"].block_roles)
        self.assertEqual(got, {"Track 1-2": "track", "OS Switch 1": "os"})        # staging's Track Barn left out
        self.assertNotIn("Track 101-103", got)

    def test_an_owners_name_is_free_of_the_generated_form(self) -> None:
        """Naming-layers step 13: a main turnout the owner names "Switch Coal" in the field file reaches the drawing
        by its id; the name form holds only generated names, as hartlib.railroad.check_virtual_names does."""
        import csv
        import shutil
        from hartlib import devices
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            here = devices.Files.here()
            for src in (here.master, here.dictionary, here.field):
                shutil.copy(src, data / src.name)
            field = devices.field_path(data)
            rows = list(csv.DictReader(io.StringIO(field.read_text(encoding="utf-8"))))
            row = dict.fromkeys(rows[0], "")
            row.update(level="2", layer="turnout", id="switch:101", user_name="Switch Coal")
            field.write_text(devices.master_text(rows + [row]), encoding="utf-8")
            got = B.device_names(devices.master_path(data))
        self.assertEqual((got["Switch 101A"], got["Switch 101B"]), ("Switch Coal", "Switch Coal"))

    def test_the_committed_map(self) -> None:
        got = B.device_names()
        self.assertEqual(got["Switch 101A"], "Switch 101")
        self.assertEqual(got["Switch 101B"], "Switch 101")
        self.assertEqual(got["Switch 223"], "Switch 223")
        self.assertEqual(got["Track 131BB-helix"], "Track Helix Inner")    # one block with staging's Helix Inner track
        self.assertEqual(got["Track 115A-117C"], "Track 115-117")       # a part: a block of its own (step 5 part 2)
        self.assertEqual(len(got), 51 + LEVEL_SENSORS + 26)          # the 25 parts: 26 trial names (201-219 has two pieces)

    def test_rows_read_and_bad_rows_stop(self) -> None:
        got = self.read('2,,turnout,DCC Switch 101,MTT120,,34,120,,,\n'
                        '2,,turnout,Switch 101,M2T1,,34,120,,"Switch 101A, Switch 101B",\n'
                        '2,,fb,FB Switch 101 N,M2S1,,34,,,,\n'
                        '2,,block,Track 1-2,,,,,,Track 1A-2B,\n', roles={"DCC Switch 101": "lcc_alias"})
        self.assertEqual(got, {"Switch 101A": "Switch 101", "Switch 101B": "Switch 101", "Track 1A-2B": "Track 1-2"})
        for rows, why in (('2,,block,Track 1-2,,,,,,,\n', "has no trial_name"),
                          ('2,,block,Track 1-2,,,,,,Track 1A-2B,\n2,,block,Track 3-4,,,,,,Track 1A-2B,\n',
                           r"trial_name Track 1A-2B is given to Track 1-2 \(level 2, block\) and Track 3-4"),
                          ('2,,turnout,Turnout 5,,,,,,Switch 5,\n', "is not named"),
                          ('2,,block,Siding,,,,,,Track 1A-2B,\n', "is not named"),
                          ('2,,fb,FB 1,,,,,,,\n', "no turnout or block rows")):
            with self.subTest(why=why), self.assertRaisesRegex(B.BuildError, why):
                self.read(rows)
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(B.BuildError, "cannot read"):
            B.device_names(Path(tmp) / "none.csv")

    def test_an_unpaired_connector_stops_the_placeholders(self) -> None:
        """A track's placeholder is its switch-and-leg key, so a run to a connector the plugin's partners do not pair
        (nothing beyond it to key it by) stops the build, where it once took an empty label."""
        _sheet, le_mod, _core = B.plugin()
        bands = B.schematic()[0]
        unpaired = mock.Mock(wraps=le_mod)
        unpaired.partners = lambda _bands: {}
        unpaired.SchematicError = le_mod.SchematicError
        with self.assertRaisesRegex(B.BuildError, "Main level: connector .* is joined to no other band"):
            B.placeholder_names(bands, unpaired)

    def test_a_placeholder_with_no_name_or_a_name_with_no_placeholder_stops(self) -> None:
        _sheet, le_mod, _core = B.plugin()
        bands = B.schematic()[0]
        device = B.device_names()
        with self.assertRaisesRegex(B.BuildError, "names nowhere: \\['Track 101BA-111C'\\]"):
            B.level_names(bands, le_mod, {k: v for k, v in device.items() if k != "Track 101BA-111C"})
        with self.assertRaisesRegex(B.BuildError, "does not have: \\['Track 998A-999B'\\]"):
            B.level_names(bands, le_mod, dict(device, **{"Track 998A-999B": "Track 9-9"}))
        names, lengths = B.placeholder_names(bands, le_mod)         # a length with no device-map row: named, no KeyError
        with mock.patch.object(sys.modules["le_names"], "placeholder_names", return_value=(names, dict(lengths, **{"Track 777A-778B": 1.0}))):
            with self.assertRaisesRegex(B.BuildError, "names nowhere: \\['Track 777A-778B'\\]"):
                B.level_names(bands, le_mod, device)

    def test_hidden_names_keeps_the_label_off_track_101_103_on_main_only(self) -> None:
        # Main's le_band_labels hidden_names ["101-103"] (the real preferences) marks that track so the plugin draws
        # no Layout Editor name for it; the fast form of the cut-over test's check, with no built tables needed
        _sheet, le_mod, _core = B.plugin()
        bands, page = B.schematic()
        names, _lengths = B.level_names(bands, le_mod)
        drawn = B.named_bands(bands, names)
        main_opts = next(o for t, _b, o in drawn if B.band_key(t) == "Main")     # hide_names reads the band's own
        self.assertEqual(main_opts["le_band_labels"]["Main"]["hidden_names"], ["101-103"])

        def hidden(marked) -> dict:
            return {B.band_key(t): sorted(s["name"] for s in b["strands"].values() if s.get(le_mod.le_labels.HIDDEN))
                    for t, b, _o in marked}

        self.assertEqual(hidden(le_mod.le_labels.hide_names(drawn, page)),
                         {"Staging": [], "Main": ["101-103"], "Upper": []})

    def test_named_bands_join_a_crossovers_halves_and_name_one_track_per_block(self) -> None:
        _sheet, le_mod, _core = B.plugin()
        bands = B.schematic()[0]
        names, _lengths = B.level_names(bands, le_mod)
        B.shared_turnouts(names, B.base_keys(bands))
        # the helix-top crossovers stand on two levels; 121 and 125 (joined B to C) are the plugin's own crossovers
        self.assertEqual(names["Main"]["shared_turnouts"], ["Switch 127", "Switch 131"])
        self.assertEqual(names["Upper"]["shared_turnouts"], ["Switch 127", "Switch 131"])
        self.assertNotIn("normal", names["Main"])                       # the plugin closes each half on its through leg
        drawn = B.named_bands(bands, names)
        self.assertIs(drawn[0][1], bands[0][1])                 # staging as it is
        main = drawn[1][1]
        labels = {d.get("label") for d in main["nodes"].values()}
        self.assertIn("101", labels)
        self.assertNotIn("101A", labels)
        self.assertIn("127A", labels)                           # its B half is on the upper level
        self.assertLessEqual({"121A", "121B", "125A", "125B"}, labels)  # joined C to B: the plugin pairs them by letter
        for (_t, _b, o), (_t2, _b2, given) in zip(drawn, bands):
            self.assertIs(o, given)                             # the preferences reach the plugin as they are
        named = [s["name"] for s in main["strands"].values() if s["name"]]
        self.assertEqual(len(named), len(set(named)))           # one track per block
        self.assertIn("Helix Outer", named)                     # the helix track keeps its plan name
        self.assertIn("101-103", named)                         # named here; the plugin leaves it off (hidden_names)
        # a part (a link inside an OS block, step 5 part 2) keeps its track name as a label, so no track moves
        self.assertLessEqual({"109-111", "115-117", "125-129"}, set(named))
        bad = copy.deepcopy(names)
        n = next(k for k, d in bands[1][1]["nodes"].items() if d.get("label") == "101B")
        bad["Main"]["turnouts"][n] = "Switch 999"
        with self.assertRaisesRegex(B.BuildError, "joined as a crossover but the device map gives them two"):
            B.named_bands(bands, bad)


class Pieces(unittest.TestCase):
    def test_runs_join_tracks_through_a_turnback(self) -> None:
        band = {"nodes": {"S": {"kind": "switch"}, "T": {"kind": "switch"}, "turn": {"kind": "turnL"}},
                "strands": {"a": {"src": ("turn", 0), "dst": ("S", "A")},
                            "b": {"src": ("turn", 1), "dst": ("T", "C")}}}
        (start, chain, end), = B.runs(band)
        self.assertEqual({start[0], end[0]}, {"S", "T"})
        self.assertEqual([sid for sid, _ in chain], ["a", "b"] if start[0] == "S" else ["b", "a"])
        self.assertEqual(dict(chain), {"a": start[0] == "S", "b": start[0] != "S"})


class ReviewFixes(unittest.TestCase):
    def test_a_split_row_on_a_moved_edge_stops_the_loop_halves(self) -> None:
        bands = built()[3]
        bdm = sys.modules.get("build_device_map") or _load("build_device_map", ROOT / "tools/schematic/build_device_map.py")
        upper = next(b for t, b, _ in bands if t.startswith("Upper"))
        halves = bdm.loop_halves(upper, B.runs, {"e63": "Track 227-241"})
        self.assertEqual(sorted(halves.values()), [1, 2])
        with self.assertRaisesRegex(bdm.MapError, "Track 227-241"):    # e64 is 241's spur since 5.3c
            bdm.loop_halves(upper, B.runs, {"e64": "Track 227-241"})

    def test_split_connector_track_counts_both_pieces(self) -> None:
        bands = built()[3]
        _sheet, le_mod, _core = B.plugin()
        _names, lengths = B.placeholder_names(bands, le_mod)
        cm = {k: s["cm"] for _, b, _ in bands for k, s in b["strands"].items()}
        self.assertGreater(cm["e35x"], 0)
        # e35 (19.7 cm) is cut at connector A into a piece on each level: both count (the plugin rounds each piece)
        self.assertAlmostEqual(lengths["OS Switch 131"], (cm["e35x"] + cm["e35y"]) * 10)
        self.assertAlmostEqual(lengths["OS Switch 127"], (cm["e36x"] + cm["e36y"]) * 10)
        self.assertGreater(lengths["OS Switch 131"], 190)
        # the balloon loop's turnback tracks each carry the whole edge: each half block takes half of it once
        half = next(s["cm"] for _, b, _ in bands for k, s in b["strands"].items() if k == "e33.0") * 10 / 2
        self.assertAlmostEqual(lengths["Track 107B-107C #1"], half)
        self.assertAlmostEqual(lengths["Track 107B-107C #2"], half)

    def test_runs_stop_on_a_broken_or_closed_turnback(self) -> None:
        lone = {"nodes": {"S": {"kind": "switch"}, "turn": {"kind": "turnL"}},
                "strands": {"a": {"src": ("turn", 0), "dst": ("S", "A")}}}
        with self.assertRaises(B.BuildError):
            B.runs(lone)
        ring = {"nodes": {"t1": {"kind": "turnL"}, "t2": {"kind": "turnR"}},
                "strands": {"a": {"src": ("t1", 0), "dst": ("t2", 0)}, "b": {"src": ("t2", 1), "dst": ("t1", 1)}}}
        with self.assertRaises(B.BuildError):
            B.runs(ring)


class BaseNames(unittest.TestCase):
    """The staging candidate binds staging's turnouts, blocks and masts to the base's beans and adds none: one the
    base lacks stops the build, naming it."""

    def build_without(self, section: str, name: str):
        doc = tables.loads(B.base_tables())
        sec = next(s for s in doc.root.findall(section)
                   if any(name in (tables.system_name(e), tables.user_name(e)) for e in tables.elements(s)))
        sec.remove(next(e for e in tables.elements(sec) if name in (tables.system_name(e), tables.user_name(e))))
        with contextlib.redirect_stdout(io.StringIO()), B.pd.cache_on():
            return B.build(levels="staging", as_live=True, base_data=doc.tobytes())

    def test_a_staging_turnout_block_or_mast_the_base_lacks_stops(self) -> None:
        _data, _P, all_names, bands = built()
        names = all_names[staging_key(bands)]
        turnout = sorted(names["turnouts"].values())[0]
        block = sorted(names["os"].values())[0]
        mast = sorted(m["mast"] for m in names["masts"])[0]
        for section, name in (("turnouts", turnout), ("layoutblocks", block), ("signalmasts", mast)):
            with self.subTest(name=name), self.assertRaisesRegex(B.BuildError, re.escape(repr(name))):
                self.build_without(section, name)

    def test_the_staging_candidate_adds_no_bean(self) -> None:
        base = tables.loads(B.base_tables()).root
        with contextlib.redirect_stdout(io.StringIO()), B.pd.cache_on():
            data = B.build(levels="staging", as_live=True)[0]
        root = tables.loads(data).root
        for section in ("turnouts", "sensors", "blocks", "layoutblocks", "signalheads", "signalmasts"):
            with self.subTest(section=section):
                self.assertEqual(sorted(tables.system_name(e) for s in root.findall(section) for e in tables.elements(s)),
                                 sorted(tables.system_name(e) for s in base.findall(section) for e in tables.elements(s)))


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
                      masts=[dict(mast="M", kind="anchor", ident="A1", slot="east", band=0)])
        P.name = lambda i: i            # Mock's own name= argument is not an attribute: set it after
        P.moved = []
        le_mod = mock.Mock(to_xml=lambda *_a: el)
        return P, el, le_mod

    def test_a_mast_two_slots_would_fit_stops_the_build(self) -> None:
        P, el, le_mod = self.fake(1)
        f, pr = B.slots_module().Index(el).blocks("anchor", "A1", "east")
        want = {"Staging": [{"mast": "M", "kind": "anchor", "facing": f, "protects": pr}]}
        B.check_masts(P, want, le_mod, {})                                  # one W|E boundary: certain
        P, el, le_mod = self.fake(2)
        with self.assertRaisesRegex(B.BuildError, "fits 2 slots"):
            B.check_masts(P, want, le_mod, {})
        P, el, le_mod = self.fake(1)
        with self.assertRaisesRegex(B.BuildError, "N \\(Staging\\) is not on the panel"):
            B.check_masts(P, {"Staging": [dict(want["Staging"][0], mast="N")]}, le_mod, {})
        with self.assertRaisesRegex(B.BuildError, "M was not asked for"):      # a mast no band lists
            B.check_masts(P, {"Staging": []}, le_mod, {})

    def test_renderer_sizes_icons_by_mast_type(self) -> None:
        data = built()[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.xml"
            path.write_bytes(data)
            signals = RENDER.load_geometry(path, LIVE_PANEL, curves=True)[4]
        sizes = {s["name"]: s["size"] for s in signals}
        self.assertEqual(sizes["Mast 2L"], tables.MAST_ICON_HIGH)        # two-searchlight
        self.assertEqual(sizes["Mast 2R"], tables.MAST_ICON_HIGH)        # one-searchlight (visible, 2026-11-19)
        self.assertEqual(sizes["Mast 32R"], tables.MAST_ICON_DWARF)      # one-low
        bw, bh = RENDER.icon_box({"size": tables.MAST_ICON_HIGH, "degrees": 90})
        self.assertAlmostEqual(bw, 40)
        self.assertAlmostEqual(bh, 12)
        for bad in ("0", "-1", "x", "inf"):
            with self.subTest(bad=bad), self.assertRaises(Exception):
                RENDER.positive(bad)
        self.assertEqual(RENDER.positive("1"), 1.0)


class Throats(unittest.TestCase):
    """A staging track of several blocks is drawn in block order at their plan shares, a short block (OS Switch 7 on
    Scale) at its own end, not cut into equal parts. The hidden yard throats are gone."""

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
        lengths = self.names[staging_key(self.bands)]["lengths"]
        return {sid: bl for sid, bl in self.names[staging_key(self.bands)]["blocks"].items()
                if len(bl) > 1 and all(b in lengths for b in bl)}

    def test_the_tracks_of_several_blocks_are_measured(self) -> None:
        tracks = {self.bands[0][1]["strands"][sid]["name"] for sid in self.measured()}
        # every drawn block has its plan length; a track of several blocks is cut at their plan
        # shares: the Switch 1-3 and 35-39 links of OS blocks only (Scale is one block since step 5 part 2,
        # 2026-11-20). Each yard track is one block since its throats went.
        self.assertEqual(tracks, {""})

    def test_staging_lengths_are_the_plan_lengths_of_every_drawn_block(self) -> None:
        from le_names import staging_lengths
        names = {"blocks": {"a": ["Track Scale", "OS Switch 7"], "b": ["OS Switch 3", "OS Switch 1"]}}
        plan = {"Track Scale": 158.0, "OS Switch 7": 9.2, "OS Switch 3": 9.2, "OS Switch 1": 9.2, "Track X": 5.0}
        self.assertEqual(staging_lengths(names, plan), {"Track Scale": 158.0, "OS Switch 7": 9.2,
                                                        "OS Switch 3": 9.2, "OS Switch 1": 9.2})
        del plan["OS Switch 1"]
        with self.assertRaisesRegex(B.BuildError, r"no plan length for drawn staging blocks \['OS Switch 1'\]"):
            staging_lengths(names, plan)

    def test_throats_sit_at_their_own_ends_in_block_order(self) -> None:
        lengths = self.names[staging_key(self.bands)]["lengths"]
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
                        room = [8 + m["icon"][1] for m in self.names[staging_key(self.bands)]["masts"] if m["facing"] == b]
                        least = max([self.le_mod.MIN_BLOCK] + room)
                        self.assertLessEqual(L, max(share, least) + stretch + bent[b] + 0.5)
                        self.assertLess(L, total / 2)

if __name__ == "__main__":
    unittest.main()


class FinalReview(unittest.TestCase):
    """The 2026-11-16 code review's findings on the cut-over build."""

    def test_staging_le_labels_from_its_preferences(self) -> None:
        own = B.schematic()[0][0][2]["le_labels"]       # preferences.json[staging]: buttons that step, yard columns
        self.assertEqual(own["extra_steps"], [["Track EH-1", "Track EH-2", "Track EH-3"]])
        self.assertEqual(own["extra_follow"], [["Track W-1", "Track W-2"]])
        south = [["S-R", "S-1", "S-2", "S-3", "S-4"]]
        self.assertEqual(own["name_columns"], south)
        self.assertNotIn("lamp_columns", own)          # the lamps are parked and off every panel (2026-11-21)

    def test_level_le_labels_from_main_upper_preferences(self) -> None:
        # preferences.json[main_upper] sets the page and both levels: its flat le_labels reach every band (staging
        # through the page), and each level's own keys are band-keyed (le_band_labels), as the plugin combines them
        bands, page = B.schematic()
        _sheet, le_mod, _core = B.plugin()
        self.assertEqual(page["le_labels"], {"switch_prefix": "SW-", "switch_size": 12, "station_size": 14,
                                             "station_gap": 10})
        # a copy of the page, as the build passes it (dict(page, band_align=...)): a band-only key in the flat
        # le_labels would stop there
        opts = dict(zip((B.band_key(t) for t, _b, _o in bands), le_mod.le_labels.options(bands, dict(page))))
        for key in ("Staging", "Main", "Upper"):
            self.assertEqual((opts[key]["switch_prefix"], opts[key]["switch_size"]), ("SW-", 12), key)
            # station and CP names at 14, 10 px apart
            self.assertEqual((opts[key]["station_size"], opts[key]["station_gap"]), (14, 10), key)
        self.assertEqual((opts["Staging"]["names_last"], opts["Staging"]["block_contents_size"]), (False, 11))
        for key in ("Main", "Upper"):
            self.assertEqual((opts[key]["names_last"], opts[key]["block_contents_size"]), (True, 11), key)
        self.assertEqual((opts["Main"]["numbers_below"], opts["Upper"]["numbers_below"]), (["101"], []))
        self.assertEqual((opts["Main"]["hidden_names"], opts["Upper"]["hidden_names"]), (["101-103"], []))
        # every part's icon is optional on every level: the level's parts in devices.csv
        self.assertIn("Track 227-231", opts["Upper"]["optional_block_contents"])
        self.assertIn("Track 115-117", opts["Main"]["optional_block_contents"])
        self.assertIn("Track 11-13", opts["Staging"]["optional_block_contents"])

class LoopAndCrossover(unittest.TestCase):
    """The 107 Loop as two blocks and double crossover 225 as four, on appended numbers."""

    def test_appended_blocks_number_after_the_rest_and_shift_nothing(self) -> None:
        before = ["OS Switch 107", "OS Switch 225", "Track 105-109", "Track 107 Loop", "Track 107-109",
                  "Track 227-241", "Track 9-9"]
        after = [b for b in before if b not in ("Track 107 Loop", "OS Switch 225", "Track 227-241")] + \
            ["Track 107 Loop 1", "Track 107 Loop 2", "OS Switch 225a", "OS Switch 225b", "OS Switch 225c",
             "OS Switch 225d", "Track 227-241 1", "Track 227-241 2"]                 # split 2026-11-19
        old = B.numbered_blocks(before)
        new = B.numbered_blocks(after)
        renamed = {"Track 107 Loop": "Track 107 Loop 1", "OS Switch 225": "OS Switch 225a",
                   "Track 227-241": "Track 227-241 1"}
        self.assertEqual(new[:len(old)], [renamed.get(b, b) for b in old])      # every old number kept
        self.assertEqual(new[len(old):], list(B.APPENDED_BLOCKS))

    def test_the_numbering_is_read_from_its_csv(self) -> None:
        self.assertEqual(B.BLOCK_NUMBERED_AS, {"Track 107 Loop 1": "Track 107 Loop", "OS Switch 225a": "OS Switch 225",
                                               "Track 227-241 1": "Track 227-241"})
        self.assertEqual(B.APPENDED_BLOCKS, ("Track 107 Loop 2", "OS Switch 225b", "OS Switch 225c",
                                             "OS Switch 225d", "Track 227-241 2"))
        self.assertEqual(B.RETIRED_BLOCKS, ("Track 131-H1", "Track 131-H2"))

    def test_a_bad_numbering_file_stops_with_its_line(self) -> None:
        # a live block by its id (naming-layers step 5), named by the name store; a retired one by its old name
        head = "id,numbered_as,append_order,retired,notes\n"
        names = {("2", "block:a"): "A", ("3", "block:b"): "B"}
        cases = {
            "block:a,,,,\n": "line 2 (A): give exactly one of numbered_as, append_order",
            "block:a,B,1,,\n": "line 2 (A): give exactly one of numbered_as, append_order",
            "block:a,B,,Old,\n": "line 2: give a block's id, or a retired block's old name in retired",
            ",,,,\n": "line 2: give a block's id, or a retired block's old name in retired",
            ",,1,Old,\n": "line 2 (Old): a retired block holds its number",
            "block:a,,x,,\n": "append_order 'x' is not a whole number",
            "block:a,,2,,\n": "must count 1, 2, 3",
            "block:a,,1,,\nblock:a,,2,,\n": "line 3: block 'A' is listed twice",
            "block:a,B,,,\nblock:b,,1,,\n": "B is both a block and the name another is numbered as",
            "block:zz,,1,,\n": "line 2: block:zz is no main or upper device of the device master",
        }
        for body, why in cases.items():
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "block_numbering.csv"
                path.write_text(head + body)
                with self.assertRaisesRegex(B.BuildError, re.escape(why), msg=body):
                    B.load_numbering(path, names)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "block_numbering.csv"
            path.write_text("block,numbered_as,append_order,retired,notes\nA,B,,,\n")
            with self.assertRaisesRegex(B.BuildError, "expected the columns"):
                B.load_numbering(path, names)

    def test_the_build_stops_on_a_row_for_a_block_that_is_gone(self) -> None:
        have = ["OS Switch 107", "Track 107 Loop 1", "Track 107 Loop 2", "OS Switch 225a", "OS Switch 225b",
                "OS Switch 225c", "OS Switch 225d", "Track 227-241 1", *B.RETIRED_BLOCKS]   # no Track 227-241 2
        with self.assertRaisesRegex(B.BuildError, "Track 227-241 2, which the main and upper levels no longer have"):
            B.numbered_blocks(have, require_listed=True)
        self.assertEqual(B.numbered_blocks(have)[-4:], ["Track 107 Loop 2", "OS Switch 225b", "OS Switch 225c",
                                                        "OS Switch 225d"])

    def test_the_loop_is_two_blocks_and_225_a_block_per_corner(self) -> None:
        _sheet, le_mod, _core = B.plugin()
        bands, page = B.schematic()
        names, lengths = B.level_names(bands, le_mod, page=page)
        loop = sorted(b for bl in names["Main"]["blocks"].values() for b in bl if "107 Loop" in b)
        self.assertEqual(loop, ["Track 107 Loop 1", "Track 107 Loop 2"])      # one strand each
        # each half its block_lengths.csv plan length (154.5 in, step 5 part 2: the plan, not the drawing)
        self.assertAlmostEqual(lengths["Track 107 Loop 1"], 154.5 * 25.4)
        self.assertAlmostEqual(lengths["Track 107 Loop 2"], 154.5 * 25.4)
        (n, corners), = names["Upper"]["xover_blocks"].items()
        band = next(b for t, b, _ in bands if t.startswith("Upper"))
        to_corner = le_mod.double_corners(band, n)
        by_corner = {to_corner[leg]: block for leg, block in corners.items()}
        self.assertEqual(by_corner, {c: f"OS Switch 225{c.lower()}" for c in "ABCD"})
        # JMRI 5.16: with A and D (or B and C) in one block LayoutBlock.addThroughPath records a through path from
        # one track to the other on that side; every corner its own block stops it
        self.assertEqual(len(set(by_corner.values())), 4)
        self.assertNotIn(n, names["Upper"]["os"])


class LevelMasts(unittest.TestCase):
    """masts.csv's main and upper rows (build_masts.py; tools/schematic/tests/test_masts_file.py holds the file to the
    device map) and how the build takes them."""

    def test_the_rows_the_build_adds(self) -> None:
        rows = B.read_level_masts()
        self.assertEqual((LEVEL_BLOCKS, len(rows), sum(len(r["heads"]) for r in rows)), (120, 68, 76))
        r = next(r for r in rows if r["mast"] == "Mast 108LB")
        self.assertEqual((r["facing"], r["protects"]), ("Track 107 Loop 2", "OS Switch 107"))
        self.assertEqual(r["system_name"], "IF$shsm:basic:two-searchlight(IH:HART:C3:108LB_Top)(IH:HART:C3:108LB_Bottom)")
        self.assertEqual(r["device_system_name"], "IF$shsm:basic:two-searchlight(IH3334)(IH3335)")
        self.assertEqual(r["heads"], [("IH:HART:C3:108LB_Top", "Head 108LB Top"),
                                      ("IH:HART:C3:108LB_Bottom", "Head 108LB Bottom")])
        # the APB intermediates: no switch, one head each, not on a board yet
        inter = {x["mast"]: (x["facing"], x["protects"], x["device_system_name"]) for x in rows if not x["switch"]
                 and x["protects"]}                       # the virtual destination masts protect nothing
        self.assertEqual(inter, {"Mast A83": ("Track 107 Loop 2", "Track 107 Loop 1", ""),
                                 "Mast A84": ("Track 107 Loop 1", "Track 107 Loop 2", ""),
                                 "Mast B92": ("Track 227-241 2", "Track 227-241 1", ""),
                                 "Mast B93": ("Track 227-241 1", "Track 227-241 2", "")})
        self.assertEqual({x["mast"]: x["leg"] for x in rows if x["leg"]}, {})     # the loop's halves tell them apart

    def test_no_two_masts_share_a_facing_and_protected_block(self) -> None:
        """JMRI keys a mast by its facing and protected blocks: LayoutBlockManager.getFacingBean (5.16) returns
        one mast per pair, and LayoutBlockConnectivityTools.generateBlocksWithBeans lists one per pair, so a second
        mast on the pair is never discovered, gets no Signal Mast Logic and so no aspect (its icon stays JMRI's red
        X: SignalMastIcon.displayState draws nothing for a null aspect). Mast 108LB was that mast before the 107
        Loop was split."""
        pairs = Counter((r["facing"], r["protects"]) for r in B.read_level_masts())
        self.assertEqual([p for p, n in pairs.items() if n > 1], [])

    def test_an_lcos_name_stops_the_build(self) -> None:
        text = B.MASTS.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "masts.csv"
            path.write_text(text.replace("IH:HART:C3:108LA_Top", "IH:HART:C3:108LB_Top"), encoding="utf-8")
            with self.assertRaisesRegex(B.BuildError, r"^masts\.csv line \d+: mast Mast 108LA: head Head 108LA Top is "
                                                      r"'IH:HART:C3:108LB_Top', neither its internal name"):
                B.read_level_masts(path)                # a virtual name not from its user name: the file's own rule
            path.write_text(text.replace("IH:HART:C3:108LA_Top", "IH4240"), encoding="utf-8")
            with self.assertRaisesRegex(B.BuildError, r"head Head 108LA Top is the wired LCOS head 'IH4240', but a "
                                                      r"level 2 head is internal"):
                B.read_level_masts(path)                # a field (LCOS) name that is not its planned head: the
            # file's reader refuses it before the coordinator's own test below would
            path.write_text(text.replace("IH:HART:C3:108LA_Top", "IH3332"), encoding="utf-8")
            [m] = [r for r in B.read_level_masts(path) if r["mast"] == "Mast 108LA"]   # its planned head: a swap
            self.assertEqual(m["heads"][0], ("IH3332", "Head 108LA Top"))
        # and the coordinator's own test, which read_level_masts runs as well: no virtual name is an LCOS head
        self.assertEqual(B.lcos_named(["IH3332", "IF$shsm:basic:one-low(IH3332)", "IH:HART:C3:108LA",
                                       "IF$shsm:basic:one-low(IH:HART:C3:108LA)"]),
                         ["IF$shsm:basic:one-low(IH3332)", "IH3332"])
        rows = B.read_level_masts()
        self.assertEqual(B.lcos_named([r["system_name"] for r in rows] + [h for r in rows for h, _u in r["heads"]]),
                         [])
        from hartlib import level_masts
        for bad in ("Mast 108LA", "Head 108LA Middle"):
            with self.subTest(head=bad):
                self.assertIn("is not named Head", level_masts.head_problem("IH:HART:C3:108LA", bad, 2, False))
        self.assertIn("neither its internal name IH:HART:C3:108LA",
                      level_masts.head_problem("IH:HART:C3:108LB", "Head 108LA", 2, False))
        self.assertIsNone(level_masts.head_problem("IH:HART:C3:108R_Top", "Head 108R Top", 2, False))
        self.assertIn("until it is a field head", level_masts.head_problem("IH3332", "Head 108LA", 2, False))
        self.assertIsNone(level_masts.head_problem("IH3332", "Head 108LA", 2, True))

    def test_a_mast_no_band_draws_stops(self) -> None:
        rows = [dict(r, facing="Track Nowhere") if r["mast"] == "Mast 110L" else r for r in B.read_level_masts()]
        names = {"Staging": {}, "Main": {"blocks": {"e": ["Track 105-109"]}, "os": {"n": "OS Switch 109"}},
                 "Upper": {"blocks": {}, "os": {}}}
        with self.assertRaisesRegex(B.BuildError, "Mast 110L \\(Track Nowhere into OS Switch 109\\): drawn on no band"):
            B.level_masts(names, rows, {"Staging"})

    def test_a_level_mast_where_jmri_resolves_it(self) -> None:
        el = ET.fromstring(anchor_panel("M"))
        P = mock.Mock()
        le_mod = mock.Mock(to_xml=lambda *_a: el)
        f, pr = B.slots_module().Index(el).blocks("anchor", "A1", "east")
        m = dict(mast="M", kind="anchor", facing=f, protects=pr)
        B.check_masts(P, {"Main": [m]}, le_mod, {})                         # where JMRI resolves it: fine
        with self.assertRaisesRegex(B.BuildError, "M \\(Main\\) at A1 east faces"):
            B.check_masts(P, {"Main": [dict(m, facing="Elsewhere")]}, le_mod, {})
        with self.assertRaisesRegex(B.BuildError, "N \\(Main\\) is not on the panel"):
            B.check_masts(P, {"Main": [m, dict(m, mast="N")]}, le_mod, {})

    def test_audit_masts_on_a_panel_that_draws_the_levels(self) -> None:
        def run(masts, levels):
            root = ET.fromstring(f"<layout-config><signalmasts>{masts}</signalmasts></layout-config>")
            audit = AUDIT.Audit("t", Path("t"))
            AUDIT.audit_masts(root, set(), audit, levels=levels)
            return [e for e in audit.errors if "main and upper" in e]
        self.assertEqual(run("", False), [])                                    # the hand-drawn panel: none wanted
        missing = run("", True)                                                 # three levels, none present
        self.assertEqual(len(missing), 1)
        self.assertIn("Mast 108LA", missing[0])
        rows = B.read_level_masts()
        every = "".join(f'<signalmast><systemName>{r["system_name"]}</systemName><userName>{r["mast"]}</userName>'
                        f'</signalmast>' for r in rows)
        self.assertEqual(run(every, True), [])
        self.assertIn("missing=['Mast 108LA']", run(every.replace("<userName>Mast 108LA<", "<userName>X<"), True)[0])

    def test_audit_reports_two_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            root = tables.read(paths.TABLES_XML)
            le = tables.layout_editor(root)
            le.append(copy.deepcopy(tables.generated_marker_label()))
            le.append(copy.deepcopy(tables.generated_marker_label()))
            path.write_bytes(ET.tostring(root))
            audit = AUDIT.audit_source("t", path, AUDIT.load_staging_masts())
        self.assertTrue(any("generated-panel markers" in e for e in audit.errors), audit.errors)
