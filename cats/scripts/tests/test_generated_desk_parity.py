"""The generated three-level desks bind staging exactly as the hand-wired desks did, which they replaced at the CATS
cut-over (ADR-023). Geometry is ignored: the panels are drawn differently.

Compared for every binding of the last hand-wired cats/panels/HART_CTC.xml (git, hartlib.hand_drawn) against the
live, generated cats/panels/HART_CTC.xml, and of the hand-wired HART_ABS.xml against the live HART_ABS.xml:
  blocks   name, STATION, DISCIPLINE and the occupied and unoccupied IOSPECs
  switches each OS block's points: the block each route leads to, which route is NORMAL, and its IOSPECs
  masts    SECSIGNAL name, PHYSIGNAL template and SIGPANTYPE, and the block it protects
  header   the hand-wired desk's header elements (counters, signal templates, stores, colours, OPERATIONS, JMRI names,
           fonts) in its order, and its publication plate's words
and the generated desk binds nothing on staging the hand-wired desk did not. Main and upper (which the hand-wired desk
did not have) are left out of the comparison: their plants command only their internal turnouts (IT:HART:C3), their
masts are main_upper_masts.csv's, and their blocks are ABS on both twins with no detector yet.
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
from hartlib import hand_drawn, level_masts  # noqa: E402

LEVEL_MASTS = level_masts.names()                   # the main and upper masts, which the hand-wired desk did not have

# the last hand-wired desks (git), and the generated desks, which are the live files since the CATS cut-over
HAND_WIRED = hand_drawn.skip_unless_available("HART_CTC.xml")
GENERATED = ROOT / "cats/panels/HART_CTC.xml"
HAND_WIRED_ABS = hand_drawn.skip_unless_available("HART_ABS.xml")
GENERATED_ABS = ROOT / "cats/panels/HART_ABS.xml"
BINDINGS = ROOT / "cats/panels/HART_CTC.bindings.json"
HEADER_TAGS = ("LINE", "COUNTER", "SIGNALTEMPLATE", "TRAINSTORE", "JOBSTORE", "CREWSTORE", "COLORDEFINITION",
               "TRAINSTATLABEL", "OPERATIONS", "JMRINAME")
# The plugin writes the panel title font at 13 points and sizes its band titles by it; the hand-wired desk had 16.
FONT_SIZES = {"FONT_TITLE": "13"}

# Two hand-wired masts stood inside a block, on a lamp gap with the same block on both sides (mast_cells.csv): Mast 24L
# mid Track West Ext and Mast 2035 inside Track K-2, a cell east of the K-1/K-2 cut. The generated panel puts every
# mast on the block boundary it guards: 24L governs the move toward Switch 23, so it guards OS Switch 23a; 2035
# governs the move from K-2 toward Switch 39, so it guards Track K-1. Owner approved the boundary placement for both
# (2026-11-14): the cut-over carries it on purpose. Live block, generated block:
PROTECTS = {"Mast 24L": ("Track West Ext", "OS Switch 23a"), "Mast 2035": ("Track K-2", "Track K-1")}


def level_io(el: ET.Element) -> bool:
    """An IOSPEC on a main or upper internal turnout (the generated desk's main and upper plants)."""
    return el.get("JMRIPREFIX") == trace.LEVEL_PREFIX


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
            if sp is None or sp.find("ROUTEINFO/*/IOSPEC") is None or any(map(level_io, sp.iter("IOSPEC"))):
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
            placed |= {((c.tag,), ios(i)) for i in c.iter("IOSPEC") if not level_io(i)}
            found += len([i for i in c.iter("IOSPEC") if not level_io(i)])
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
        if s is None or (s.text or "").strip() in LEVEL_MASTS:
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
    HAND_WIRED, GENERATED, DISCIPLINE = HAND_WIRED, GENERATED, "CTC"

    @classmethod
    def setUpClass(cls) -> None:
        cls.hand, cls.gen = ET.parse(cls.HAND_WIRED).getroot(), ET.parse(cls.GENERATED).getroot()

    def test_every_hand_wired_block_is_bound_the_same(self) -> None:
        live, gen = blocks(self.hand), blocks(self.gen)
        self.assertTrue(live)
        for name, defs in sorted(live.items()):
            with self.subTest(block=name):
                self.assertEqual(len(defs), 1, defs)
                self.assertEqual(gen.get(name), defs)
        bound = {n for n, d in gen.items() if any(spec for *_, spec in d)}
        self.assertEqual(bound, {n for n, d in live.items() if any(spec for *_, spec in d)})
        self.assertEqual(empty_specs(self.hand), [])
        self.assertEqual(empty_specs(self.gen), [])

    def test_every_iospec_is_the_same_both_ways(self) -> None:
        (n_live, live), (n_gen, gen) = placed_ios(self.hand), placed_ios(self.gen)
        self.assertEqual(n_live, len(list(self.hand.iter("IOSPEC"))), "an IOSPEC outside a block spec or route")
        self.assertFalse(any(map(level_io, self.hand.iter("IOSPEC"))))
        self.assertEqual(n_gen, len([i for i in self.gen.iter("IOSPEC") if not level_io(i)]),
                         "an IOSPEC outside a block spec or route")
        self.assertEqual(gen - live, set())
        self.assertEqual(live - gen, set())

    def test_every_hand_wired_switch_is_bound_the_same(self) -> None:
        live, gen = plants(self.hand), plants(self.gen)
        self.assertTrue(live)
        self.assertEqual(gen, live)

    def test_every_hand_wired_mast_is_bound_the_same(self) -> None:
        live, gen = masts(self.hand), masts(self.gen)
        self.assertTrue(live)
        self.assertEqual(set(gen), set(live))
        for name, here in sorted(live.items()):
            with self.subTest(mast=name):
                self.assertEqual((len(here), len(gen[name])), (1, 1), "one SECSIGNAL per mast")
                (template, pantype, block), (g_template, g_pantype, g_block) = here[0], gen[name][0]
                self.assertEqual((g_template, g_pantype), (template, pantype))
                self.assertEqual((block, g_block), PROTECTS.get(name, (block, block)))

    def test_header_matches_the_hand_wired_desk(self) -> None:
        for tag in HEADER_TAGS:
            with self.subTest(tag=tag):
                self.assertTrue(self.hand.findall(tag))
                self.assertEqual([canon(e) for e in self.gen.findall(tag)],
                                 [canon(e) for e in self.hand.findall(tag)])
        self.assertEqual(self.gen.find("OPERATIONS").get("CONNECT"), "false")

    def test_fonts_are_the_hand_wired_desks(self) -> None:
        live = {e.get("FONTKEY"): dict(e.attrib) for e in self.hand.findall("FONTDEFINITION")}
        gen = {e.get("FONTKEY"): dict(e.attrib) for e in self.gen.findall("FONTDEFINITION")}
        for key, size in FONT_SIZES.items():
            live[key]["FONTSIZE"] = size
        self.assertEqual(gen, live)
        self.assertEqual([e.get("FONTKEY") for e in self.gen.findall("FONTDEFINITION")], list(live))

    def test_elements_are_in_the_hand_wired_desks_order(self) -> None:
        self.assertEqual([t for t in order(self.gen) if t != "ROWWRAPTAG"], order(self.hand))

    def test_the_plate_says_what_the_hand_wired_desk_says(self) -> None:
        self.assertEqual(len(plate(self.hand)), 5)
        self.assertLessEqual(plate(self.hand), plate(self.gen))

    def test_main_and_upper_bind_only_their_internal_turnouts_and_masts(self) -> None:
        level = [i for i in self.gen.iter("IOSPEC") if level_io(i)]
        self.assertTrue(level)
        on_routes = {id(i) for ri in self.gen.iter("ROUTEINFO") for c in ri for i in c.iter("IOSPEC")}
        for i in level:
            with self.subTest(turnout=i.get("USER_NAME")):
                self.assertRegex(i.get("DECADDR"), r"^:HART:C3:[0-9]+$")
                self.assertEqual(i.get("USER_NAME"), "Switch " + i.get("DECADDR").rpartition(":")[2])
                self.assertIn(id(i), on_routes, "an internal turnout outside a route")
        drawn = {(s.text or "").strip() for s in self.gen.iter("SECSIGNAL")}
        self.assertEqual(drawn & LEVEL_MASTS, LEVEL_MASTS)
        self.assertFalse(LEVEL_MASTS & set(masts(self.hand)))

    def test_main_and_upper_take_the_desk_discipline_with_no_detector_yet(self) -> None:
        # CTC on the CTC desk, as staging is: CATS holds their signals and releases them (owner, 2026-11-17);
        # ABS on the ABS twin
        bound = json.loads(BINDINGS.read_text(encoding="utf-8"))["blocks"]
        dark = {e.get("name", k) for k, e in bound.items() if "discipline" in e and "occupied" not in e}
        self.assertGreater(len(dark), 90)
        found = blocks(self.gen)
        for name in sorted(dark):
            with self.subTest(block=name):
                self.assertEqual({d[1] for d in found[name]}, {self.DISCIPLINE})
                self.assertEqual({d[2] for d in found[name]}, {()}, "no detector bound yet")
        self.assertEqual({d[1] for defs in found.values() for d in defs}, {self.DISCIPLINE})


class ParityABS(Parity):
    HAND_WIRED, GENERATED, DISCIPLINE = HAND_WIRED_ABS, GENERATED_ABS, "ABS"


if __name__ == "__main__":
    unittest.main()
