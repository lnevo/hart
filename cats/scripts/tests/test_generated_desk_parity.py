"""The generated three-level panel binds staging exactly as the live desk does, so it can replace the desk at the
cut-over (ADR-023). Geometry is ignored: the two panels are drawn differently.

Compared for every binding of cats/panels/HART_CTC.xml against cats/panels/generated/HART_Generated.xml:
  blocks   name, STATION, DISCIPLINE and the occupied and unoccupied IOSPECs
  switches each OS block's points: the block each route leads to, which route is NORMAL, and its IOSPECs
  masts    SECSIGNAL name, PHYSIGNAL template and SIGPANTYPE, and the block it protects
and the generated panel binds nothing the live desk does not.
"""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

import digicon_trace as trace  # noqa: E402

LIVE = ROOT / "cats/panels/HART_CTC.xml"
GENERATED = ROOT / "cats/panels/generated/HART_Generated.xml"

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


class Parity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.live, cls.gen = ET.parse(LIVE).getroot(), ET.parse(GENERATED).getroot()

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
        for tag in ("SIGNALTEMPLATE", "JMRINAME"):
            with self.subTest(tag=tag):
                self.assertEqual([canon(e) for e in self.gen.findall(tag)],
                                 [canon(e) for e in self.live.findall(tag)])


if __name__ == "__main__":
    unittest.main()
