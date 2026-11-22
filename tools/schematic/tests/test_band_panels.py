"""band_panels.py: the "Staging Level", "Main Level" and "Upper Level" panels, copies of the built "HART Railroad"
panel trimmed to one band each and joined by edge connectors. The real-build tests run the Layout Editor build over
the repo's committed files under repo_read_only; the error tests use a small panel made here."""
from __future__ import annotations

import collections
import contextlib
import copy
import functools
import io
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import band_panels as bp  # noqa: E402
import build_layout_le as ble  # noqa: E402
import publish_draft as pd  # noqa: E402
from hartlib import tables  # noqa: E402
from repo_read_only import repo_read_only  # noqa: E402


def plugin_here() -> bool:
    try:
        ble.plugin()
    except ble.BuildError:
        return False
    return True


@functools.lru_cache(maxsize=None)
def built():
    """(tables root before, tables root with the band panels, add()'s report) of the real build."""
    with repo_read_only(), pd.cache_on(), contextlib.redirect_stdout(io.StringIO()):
        data, P, _names, bands = ble.build(levels="all", as_live=True)
    before = tables.loads(data).root
    after = copy.deepcopy(before)
    report = bp.add(after, P, bands, ble.plugin()[1].CHROME)
    return before, after, report


def text(el: ET.Element) -> bytes:
    el = copy.deepcopy(el)
    el.tail = None
    ET.indent(el, space="  ")
    return ET.tostring(el, encoding="utf-8")


def panel(root, name):
    return next(p for p in tables.layout_editors(root) if p.get("name") == name)


def marker(el) -> bool:
    return el.tag == "positionablelabel" and el.get("text") == tables.GENERATED_PANEL_MARKER


@unittest.skipUnless(plugin_here(), "the schematic-maps plugin is not checked out")
class RealBuild(unittest.TestCase):
    def setUp(self) -> None:
        self.before, self.after, self.report = built()
        self.full = panel(self.after, bp.FULL_PANEL)
        self.bands = {r["name"]: panel(self.after, r["name"]) for r in self.report}

    def test_four_panels_full_first_then_the_bands(self) -> None:
        self.assertEqual([bp.FULL_PANEL, "Staging Level", "Main Level", "Upper Level"],
                         [p.get("name") for p in tables.layout_editors(self.after)])

    def test_the_full_panel_is_unchanged(self) -> None:
        self.assertEqual(text(panel(self.before, bp.FULL_PANEL)), text(self.full))

    def _restored(self, el, dy):
        """`el` of a band panel as its source element: moved back, an edge connector made the anchor again."""
        el = copy.deepcopy(el)
        bp.shift(el, -dy)
        return el

    def test_each_kept_element_is_its_source_and_every_band_element_is_kept_once(self) -> None:
        source = collections.Counter(text(el) for el in tables.elements(self.full)
                                     if el.tag not in bp.EVERY_PANEL and not marker(el))
        anchors = {el.get("ident"): el for el in self.full.findall("positionablepoint")}
        joins = {el.get("ident") for el in self.full.findall("tracksegment") if el.get("hidden") == "yes"
                 and {anchors.get(el.get("connect1name")) is not None, anchors.get(el.get("connect2name")) is not None}
                 == {True}}
        kept = collections.Counter()
        edges = 0
        for r in self.report:
            dy = r["translation"][1]
            for el in tables.elements(self.bands[r["name"]]):
                if el.tag in bp.EVERY_PANEL:
                    self.assertEqual(r["name"], el.get("name"))
                    src = self.full.find(el.tag)
                    self.assertEqual(text(src), text(copy.deepcopy(el)).replace(
                        f'name="{r["name"]}"'.encode(), f'name="{bp.FULL_PANEL}"'.encode()))
                    continue
                if marker(el):
                    continue
                el = self._restored(el, dy)
                if el.get("type") == bp.EDGE:
                    edges += 1
                    src = anchors[el.get("ident")]
                    join = next(c for c in (src.get("connect1name"), src.get("connect2name"))
                                if c != el.get("connect1name"))
                    self.assertIn(join, joins)
                    want = {k: v for k, v in src.attrib.items() if k not in ("type", "connect1name", "connect2name")}
                    got = {k: v for k, v in el.attrib.items()
                           if k not in ("type", "connect1name", "linkedpanel", "linkpointid")}
                    self.assertEqual(want, got)
                    kept[text(src)] += 1
                    continue
                kept[text(el)] += 1
        dropped = collections.Counter(text(el) for el in self.full.findall("tracksegment")
                                      if el.get("ident") in joins)
        self.assertEqual(4, len(joins))
        self.assertEqual(8, edges)
        self.assertEqual(source - dropped, kept)

    def test_every_edge_connector_links_both_ways(self) -> None:
        for name, p in self.bands.items():
            idents = [el.get("ident") for el in tables.elements(p) if el.get("ident")]
            self.assertEqual(len(idents), len(set(idents)), name)
            for el in p.findall("positionablepoint"):
                if el.get("type") != bp.EDGE:
                    continue
                self.assertNotIn("connect2name", el.attrib)
                self.assertIn(el.get("connect1name"), idents)
                other = self.bands[el.get("linkedpanel")]
                partner = next(e for e in other.findall("positionablepoint") if e.get("ident") == el.get("linkpointid"))
                self.assertEqual((bp.EDGE, name, el.get("ident")),
                                 (partner.get("type"), partner.get("linkedpanel"), partner.get("linkpointid")))

    def test_only_the_upper_level_moves_up_to_where_staging_stands(self) -> None:
        moves = {r["name"]: r["translation"] for r in self.report}
        self.assertEqual((0, 0), moves["Staging Level"])
        self.assertEqual((0, 0), moves["Main Level"])
        self.assertLess(moves["Upper Level"][1], 0)


# ---------------------------------------------------------------- a small panel

def point(ident, kind, c1, c2=None):
    at = {"ident": ident, "type": kind, "x": "0.0", "y": "20.0", "connect1name": c1}
    if c2:
        at["connect2name"] = c2
    return ET.Element("positionablepoint", at)


def seg(ident, a, b, hidden="no"):
    return ET.Element("tracksegment", {"ident": ident, "blockname": "Track X", "connect1name": a, "type1": "POS_POINT",
                                       "connect2name": b, "type2": "POS_POINT", "hidden": hidden})


def small():
    """(root, P): two bands, each an end bumper, a track and an anchor, joined by hidden segment J."""
    full = ET.Element("LayoutEditor", {"name": bp.FULL_PANEL, "panelheight": "100", "windowheight": "1032"})
    full.append(ET.Element("layoutTrackDrawingOptions", {"name": bp.FULL_PANEL}))
    for b, y in ((1, "20.0"), (2, "70.0")):
        e = point(f"E{b}", "END_BUMPER", f"T{b}")
        a = point(f"A{b}", "ANCHOR", f"T{b}", "J")
        e.set("y", y)
        a.set("y", y)
        full.extend([e, seg(f"T{b}", f"E{b}", f"A{b}"), a])
    full.append(seg("J", "A1", "A2", hidden="yes"))
    root = ET.Element("layout-config")
    root.append(full)
    P = SimpleNamespace(
        turnouts=[], shapes=[], masts=[], bcis=[], labels=[],
        segments=[{"ident": "T1", "band": 0}, {"ident": "T2", "band": 1}, {"ident": "J", "band": None}],
        points={"E1": {"band": 0}, "A1": {"band": 0}, "E2": {"band": 1}, "A2": {"band": 1}},
        joins=["J"], band_boxes=[(0, 10, 100, 40), (0, 60, 100, 90)], items={"bottom": 45}, name=lambda i: i)
    return root, P


class SmallPanel(unittest.TestCase):
    def membership(self, root, P):
        full = root.find("LayoutEditor")
        return full, bp.membership(full, P, bp.band_areas(P, full))

    def test_two_bands_become_two_panels_joined_by_edge_connectors(self) -> None:
        root, P = small()
        with mock.patch.object(bp, "PANELS", {1: "One", 2: "Two"}), \
                mock.patch.object(bp, "band_levels", return_value=[1, 2]):
            report = bp.add(root, P, bands=None, chrome=(18, 60))
        self.assertEqual([("A1", "Two", "A2")], report[0]["edges"])
        self.assertEqual([("A2", "One", "A1")], report[1]["edges"])
        one = panel(root, "One")
        self.assertEqual(["layoutTrackDrawingOptions", "positionablepoint", "tracksegment", "positionablepoint"],
                         [el.tag for el in one])
        self.assertEqual("One", one.find("layoutTrackDrawingOptions").get("name"))
        self.assertEqual({"ident": "A1", "type": "EDGE_CONNECTOR", "x": "0.0", "y": "20.0", "connect1name": "T1",
                          "linkedpanel": "Two", "linkpointid": "A2"}, one[3].attrib)

    def test_an_element_in_no_band_stops(self) -> None:
        root, P = small()
        root.find("LayoutEditor").append(ET.Element("layoutturnout", {"ident": "TO9", "ycen": "20.0"}))
        with self.assertRaisesRegex(bp.BandPanelError, "in no band: layoutturnout TO9"):
            self.membership(root, P)

    def test_an_unknown_kind_of_element_stops(self) -> None:
        root, P = small()
        root.find("LayoutEditor").append(ET.Element("levelxing", {"ident": "X1"}))
        with self.assertRaisesRegex(bp.BandPanelError, "in no band: levelxing X1"):
            self.membership(root, P)

    def test_an_element_in_two_bands_stops(self) -> None:
        root, P = small()
        P.segments.append({"ident": "T1", "band": 1})
        with self.assertRaisesRegex(bp.BandPanelError, "in two bands: tracksegment T1"):
            self.membership(root, P)

    def test_a_join_with_no_partner_stops(self) -> None:
        root, P = small()
        full = root.find("LayoutEditor")
        full.find("tracksegment[@ident='J']").set("connect2name", "A9")
        full_, of = self.membership(root, P)
        with self.assertRaisesRegex(bp.BandPanelError, "J: an end is not a point of the panel"):
            bp.band_joins(full_, P, of)

    def test_a_join_inside_one_band_stops(self) -> None:
        root, P = small()
        P.points["A2"]["band"] = 0
        P.points["E2"]["band"] = 0
        P.segments[1]["band"] = 0
        root.find("LayoutEditor").find("positionablepoint[@ident='A2']").set("y", "20.0")
        root.find("LayoutEditor").find("positionablepoint[@ident='E2']").set("y", "20.0")
        full, of = self.membership(root, P)
        with self.assertRaisesRegex(bp.BandPanelError, "J: ends A1 and A2 are not on two bands"):
            bp.band_joins(full, P, of)

    def test_an_element_outside_its_bands_area_stops(self) -> None:
        root, P = small()
        root.find("LayoutEditor").find("positionablepoint[@ident='E2']").set("y", "20.0")
        with self.assertRaisesRegex(bp.BandPanelError, "outside their band's area: positionablepoint E2"):
            self.membership(root, P)


class SmokeTestNames(unittest.TestCase):
    def test_the_panelpro_smoke_test_checks_the_same_band_panels(self):
        """The Jython smoke test cannot import hartlib, so it keeps its own list; this holds the two equal."""
        import ast
        src = (Path(__file__).resolve().parents[3] / "jmri/layouts/hart/scripts/panelpro_smoke_test.py").read_text()
        node = next(n for n in ast.parse(src).body if isinstance(n, ast.Assign)
                    and getattr(n.targets[0], "id", "") == "BAND_PANELS")
        self.assertEqual(tuple(ast.literal_eval(node.value)), tuple(bp.tables.BAND_PANEL_NAMES.values()))


if __name__ == "__main__":
    unittest.main()
