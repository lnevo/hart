"""The generated three-level desks bind staging exactly as the hand-wired desks did, which they replaced at the CATS
cut-over (ADR-023). Geometry is ignored: the panels are drawn differently.

Compared for every binding of the last hand-wired cats/panels/HART_CTC.xml (git, hartlib.hand_drawn) against the
live, generated cats/panels/HART_CTC.xml, and of the hand-wired HART_ABS.xml against the live HART_ABS.xml:
  blocks   name, STATION, DISCIPLINE and the occupied and unoccupied IOSPECs
  switches each OS block's points: the block each route leads to, which route is NORMAL, and its IOSPECs
  masts    SECSIGNAL name, PHYSIGNAL template and SIGPANTYPE, and the block it protects
  header   the live desk's header elements (counters, signal templates, stores, colours, OPERATIONS, JMRI names,
           fonts) in its order, and its publication plate's words
and the generated desk binds nothing the live desk does not. Main and upper blocks are DTC on both twins.
"""
from __future__ import annotations

import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

import digicon_trace as trace  # noqa: E402

sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import hand_drawn  # noqa: E402

# "LIVE" is the last hand-wired desk (git); the generated desks are the live files since the CATS cut-over
LIVE = hand_drawn.skip_unless_available("HART_CTC.xml")
GENERATED = ROOT / "cats/panels/HART_CTC.xml"
LIVE_ABS = hand_drawn.skip_unless_available("HART_ABS.xml")
GENERATED_ABS = ROOT / "cats/panels/HART_ABS.xml"
BINDINGS = ROOT / "cats/panels/HART_CTC.bindings.json"
HEADER_TAGS = ("LINE", "COUNTER", "SIGNALTEMPLATE", "TRAINSTORE", "JOBSTORE", "CREWSTORE", "COLORDEFINITION",
               "TRAINSTATLABEL", "OPERATIONS", "JMRINAME")
# The plugin writes the panel title font at 13 points and sizes its band titles by it; the live desk has 16.
FONT_SIZES = {"FONT_TITLE": "13"}

# Two live masts stand inside a block, on a lamp gap with the same block on both sides (mast_cells.csv): Mast 24L
# mid Track West Ext and Mast 2035 inside Track K-2, a cell east of the K-1/K-2 cut. The generated panel puts every
# mast on the block boundary it guards: 24L governs the move toward Switch 23, so it guards OS Switch 23a; 2035
# governs the move from K-2 toward Switch 39, so it guards Track K-1. Owner approved the boundary placement for both
# (2026-11-14): the cut-over carries it on purpose. Live block, generated block:
PROTECTS = {"Mast 24L": ("Track West Ext", "OS Switch 23a"), "Mast 2035": ("Track K-2", "Track K-1")}


def ios(el: ET.Element) -> tuple:
    return tuple(sorted(el.attrib.items())) + ((el.text or "").strip(),)


def canon(el: ET.Element) -> tuple:
    """An element as (tag, attributes, text, children), whitespace and attribute order ignored."""
    return el.tag, tuple(sorted(el.attrib.items())), (el.text or "").strip(), tuple(canon(c) for c in el)


def blocks(root: ET.Element) -> dict[str, set[tuple]]:
    """Block name -> every distinct definition of it (attributes and IOSPECs)."""
    out: dict[str, set[tuple]] = {}
    for b in root.iter("BLOCK"):
        if not b.get("NAME"):
            continue
        spec = tuple((tag, tuple(ios(i) for i in el.iter("IOSPEC")))
                     for tag in ("OCCUPIEDSPEC", "UNOCCUPIEDSPEC") for el in [b.find(tag)] if el is not None)
        out.setdefault(b.get("NAME"), set()).add((b.get("STATION"), b.get("DISCIPLINE"), spec))
    return out


def plants(root: ET.Element) -> dict[str, dict[str, tuple]]:
    """OS block -> {block the route leads to: (NORMAL, IOSPECs)} for every bound SWITCHPOINTS."""
    cells = trace.track_cells(root.find("TRACKPLAN"))
    out: dict[str, dict[str, tuple]] = {}
    for xy, sec in cells.items():
        for se in sec.findall("SEC_EDGE"):
            sp = se.find("SWITCHPOINTS")
            if sp is None or sp.find("ROUTEINFO/*/IOSPEC") is None:
                continue
            os_name = trace.plant_os(cells, xy)
            routes = {}
            for ri in sp.findall("ROUTEINFO"):
                dest = trace.trace_leg(cells, xy, ri.get("ROUTEID"), own=os_name)
                routes[dest] = (ri.get("NORMAL") == "true",
                                tuple(sorted((c.tag,) + ios(i) for c in ri for i in c.iter("IOSPEC"))))
            if os_name in out:
                raise AssertionError(f"two bound plants in {os_name}")
            out[os_name] = routes
    return out


def placed_ios(root: ET.Element) -> tuple[int, set[tuple]]:
    """(IOSPECs anywhere in the panel, {(where, IOSPEC)} of those in a block spec or a route): where is
    (block name, spec) or (route tag,); a count above the set's coverage means an IOSPEC somewhere else."""
    found, placed = 0, set()
    for b in root.iter("BLOCK"):
        for tag in ("OCCUPIEDSPEC", "UNOCCUPIEDSPEC"):
            for el in b.findall(tag):
                placed |= {((b.get("NAME"), tag), ios(i)) for i in el.iter("IOSPEC")}
                found += len(list(el.iter("IOSPEC")))
    for ri in root.iter("ROUTEINFO"):
        for c in ri:
            placed |= {((c.tag,), ios(i)) for i in c.iter("IOSPEC")}
            found += len(list(c.iter("IOSPEC")))
    return found, placed


def empty_specs(root: ET.Element) -> list[str]:
    """Blocks with an OCCUPIEDSPEC or UNOCCUPIEDSPEC that holds no IOSPEC."""
    return sorted({b.get("NAME") or "?" for b in root.iter("BLOCK") for tag in ("OCCUPIEDSPEC", "UNOCCUPIEDSPEC")
                   for el in b.findall(tag) if el.find("IOSPEC") is None})


def masts(root: ET.Element) -> dict[str, list[tuple]]:
    """Mast user name -> [(PHYSIGNAL, SIGPANTYPE, block on its edge)] for each SECSIGNAL of that name."""
    out: dict[str, list[tuple]] = {}
    for se in root.iter("SEC_EDGE"):
        s = se.find("SECSIGNAL")
        if s is None:
            continue
        pan = s.find("PANELSIGNAL")
        blk = se.find("BLOCK")
        out.setdefault((s.text or "").strip(), []).append((
            (s.findtext("PHYSIGNAL") or "").strip(), pan.get("SIGPANTYPE") if pan is not None else None,
            blk.get("NAME") if blk is not None else None))
    return out


def plate(root: ET.Element) -> set[tuple]:
    """(text, font, place) of every label on the top row of the track plan (the publication plate)."""
    return {(n.get("NAME"), n.get("FONT_NAME"), n.get("LOC_NAME")) for sec in root.find("TRACKPLAN")
            if sec.get("Y") == "1" for n in sec.findall("SEC_NAME")}


def order(root: ET.Element) -> list[str]:
    out = []
    for el in root:
        if not out or out[-1] != el.tag:
            out.append(el.tag)
    return out


class Parity(unittest.TestCase):
    LIVE, GENERATED, DISCIPLINE = LIVE, GENERATED, "CTC"

    @classmethod
    def setUpClass(cls) -> None:
        cls.live, cls.gen = ET.parse(cls.LIVE).getroot(), ET.parse(cls.GENERATED).getroot()

    def test_every_live_block_is_bound_the_same(self) -> None:
        live, gen = blocks(self.live), blocks(self.gen)
        self.assertTrue(live)
        for name, defs in sorted(live.items()):
            with self.subTest(block=name):
                self.assertEqual(len(defs), 1, defs)
                self.assertEqual(gen.get(name), defs)
        bound = {n for n, d in gen.items() if any(spec for *_, spec in d)}
        self.assertEqual(bound, {n for n, d in live.items() if any(spec for *_, spec in d)})
        self.assertEqual(empty_specs(self.live), [])
        self.assertEqual(empty_specs(self.gen), [])

    def test_every_iospec_is_the_same_both_ways(self) -> None:
        (n_live, live), (n_gen, gen) = placed_ios(self.live), placed_ios(self.gen)
        self.assertEqual(n_live, len(list(self.live.iter("IOSPEC"))), "an IOSPEC outside a block spec or route")
        self.assertEqual(n_gen, len(list(self.gen.iter("IOSPEC"))), "an IOSPEC outside a block spec or route")
        self.assertEqual(gen - live, set())
        self.assertEqual(live - gen, set())

    def test_every_live_switch_is_bound_the_same(self) -> None:
        live, gen = plants(self.live), plants(self.gen)
        self.assertTrue(live)
        self.assertEqual(gen, live)

    def test_every_live_mast_is_bound_the_same(self) -> None:
        live, gen = masts(self.live), masts(self.gen)
        self.assertTrue(live)
        self.assertEqual(set(gen), set(live))
        for name, here in sorted(live.items()):
            with self.subTest(mast=name):
                self.assertEqual((len(here), len(gen[name])), (1, 1), "one SECSIGNAL per mast")
                (template, pantype, block), (g_template, g_pantype, g_block) = here[0], gen[name][0]
                self.assertEqual((g_template, g_pantype), (template, pantype))
                self.assertEqual((block, g_block), PROTECTS.get(name, (block, block)))

    def test_header_matches_the_live_desk(self) -> None:
        for tag in HEADER_TAGS:
            with self.subTest(tag=tag):
                self.assertTrue(self.live.findall(tag))
                self.assertEqual([canon(e) for e in self.gen.findall(tag)],
                                 [canon(e) for e in self.live.findall(tag)])
        self.assertEqual(self.gen.find("OPERATIONS").get("CONNECT"), "false")

    def test_fonts_are_the_live_desks(self) -> None:
        live = {e.get("FONTKEY"): dict(e.attrib) for e in self.live.findall("FONTDEFINITION")}
        gen = {e.get("FONTKEY"): dict(e.attrib) for e in self.gen.findall("FONTDEFINITION")}
        for key, size in FONT_SIZES.items():
            live[key]["FONTSIZE"] = size
        self.assertEqual(gen, live)
        self.assertEqual([e.get("FONTKEY") for e in self.gen.findall("FONTDEFINITION")], list(live))

    def test_elements_are_in_the_live_desks_order(self) -> None:
        self.assertEqual([t for t in order(self.gen) if t != "ROWWRAPTAG"], order(self.live))

    def test_the_plate_says_what_the_live_desk_says(self) -> None:
        self.assertEqual(len(plate(self.live)), 5)
        self.assertLessEqual(plate(self.live), plate(self.gen))

    def test_main_and_upper_are_dark_territory(self) -> None:
        bound = json.loads(BINDINGS.read_text(encoding="utf-8"))["blocks"]
        dark = {e.get("name", k) for k, e in bound.items() if e.get("discipline") == "DTC"}
        self.assertTrue(dark)
        found = blocks(self.gen)
        for name in sorted(dark):
            with self.subTest(block=name):
                self.assertEqual({d[1] for d in found[name]}, {"DTC"})
                self.assertEqual({d[2] for d in found[name]}, {()}, "no detector bound yet")
        others = {d[1] for name, defs in found.items() if name not in dark for d in defs}
        self.assertEqual(others, {self.DISCIPLINE})


class ParityABS(Parity):
    LIVE, GENERATED, DISCIPLINE = LIVE_ABS, GENERATED_ABS, "ABS"


if __name__ == "__main__":
    unittest.main()
