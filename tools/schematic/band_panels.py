"""The three band panels of tables.xml: "Staging Level", "Main Level" and "Upper Level".

build_tables.py calls add() after build_layout_le.build(): each band panel is a copy of the built "HART Railroad"
panel trimmed to one band, the way JMRI's own advice makes a panel from another (copy the panel's XML, keep what the
new panel shows). Nothing is drawn again and the "HART Railroad" panel is left as it is.

Which band an element is in comes from the build's own data (the plugin's Panel, P): turnouts, track segments,
points and shapes by their written ident (P.name), mast icons by their mast, block contents icons by block and spot,
and the drawn labels by text and spot, each carrying the band it was drawn on. The panel's own items (panel_items.json:
the title, the status cluster, the backdrop) and the level titles carry no band: each goes to the band whose area it
stands in. A band's area runs across the panel, from the bottom of the band above it (the top of the panel for the
first) to its own bottom: its box (P.band_boxes), and for the staging band also the panel items' bottom
(P.items["bottom"]), the bottom the build kept the main level clear of. The layoutTrackDrawingOptions element and the
generated-panel marker label are copied into every band panel, the options under the band panel's name. An element
in no band, in two bands, or of a kind this module does not know stops the build (BandPanelError).

The hidden track segments that join two bands (P.joins: the two helix tracks and the two halves of crossovers 127 and
131 on the main and upper levels) are left out of the band panels. Each of their end anchors becomes an edge
connector: a positionablepoint of type EDGE_CONNECTOR whose connect1name is the track segment it ends on that panel,
linkedpanel the other band panel's name and linkpointid the anchor at the far end (JMRI 5.16
PositionablePointViewXml; the link is made when the second panel loads). A join is inside one block, so the
connector is no block boundary and carries no mast.

Each band panel opens on its own band: the band is moved up by one translation, so that its
topmost element stands MARGIN px below the top of the panel, and the panel is as tall as its lowest element plus
MARGIN. The margin gives the level room above and below that the full panel, packed level under level, does not.
The move is in whole px; a band that would still not fit the window stops the build (BandPanelError). The band
panel's window is as tall as the panel and the frame Layout Editor draws round it (`chrome`), and keeps the full panel's
width (open at the size the level needs, at the common window width). A host that has opened a
panel keeps its own window size in its profile's user-interface.xml, over this one: every Pi and Windows deploy sets
the saved sizes to the installed tables' (tools/hosts/panel_window_sizes.py, hartlib.jmri_profile).
"""
from __future__ import annotations

import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from le_common import BuildError, band_levels  # noqa: E402  (and hartlib on the path)
from hartlib import tables  # noqa: E402

FULL_PANEL = "HART Railroad"
# The band panels by the level of their band (plan_overrides.json), in the order they follow the full panel
PANELS = tables.BAND_PANEL_NAMES
EDGE = "EDGE_CONNECTOR"
EVERY_PANEL = ("layoutTrackDrawingOptions",)           # and the generated-panel marker label
AREA_TAGS = ("positionablelabel", "sensoricon", "signalheadicon", "memoryicon", "MemoryIcon", "LocoIcon")
Y_ATTRS = ("y", "ycen", "ya", "yb", "yc", "yd")
MARGIN = 40          # px above and below a band in its panel (module text)
# where JMRI 5.16 writes linkedpanel and linkpointid on a positionablepoint: after the slots, before class
POINT_ORDER = ("ident", "type", "x", "y", "connect1name", "connect2name", "eastboundsignal", "westboundsignal",
               "eastboundsignalmast", "westboundsignalmast", "eastboundsensor", "westboundsensor", "linkedpanel",
               "linkpointid", "class")


class BandPanelError(BuildError):
    """A band panel cannot be made from the built panel (build_tables.py prints it and exits 2)."""


def add(root: ET.Element, P, bands, chrome: tuple[int, int]) -> list[dict]:
    """Add the band panels (PANELS) to the tables `root` after the full panel, from the build's Panel `P` and its
    `bands` (build_layout_le.build). `chrome`: the frame Layout Editor draws round a panel (the plugin's le.CHROME).
    Returns one entry per band panel: name, band index, translation (dx, dy) and its edge connectors
    [(point, linked panel, link point)]. BandPanelError on anything that stops it (module text)."""
    full = _full_panel(root)
    names = panel_names(bands)
    areas = band_areas(P, full)
    of = membership(full, P, areas)
    joins = band_joins(full, P, of)
    out = []
    after = full
    for bi, name in names.items():
        dy, height = translation(full, of, bi, chrome)
        panel = band_panel(full, of, joins, names, bi, name, dy, height, chrome)
        check_links(panel)
        root.insert(list(root).index(after) + 1, panel)
        after = panel
        out.append({"name": name, "band": bi, "translation": (0, dy),
                    "edges": [(p.get("ident"), p.get("linkedpanel"), p.get("linkpointid"))
                              for p in panel.findall("positionablepoint") if p.get("type") == EDGE]})
    return out


def _full_panel(root: ET.Element) -> ET.Element:
    panels = [p for p in tables.layout_editors(root) if p.get("name") == FULL_PANEL]
    if len(panels) != 1:
        raise BandPanelError(f"the tables hold {len(panels)} {FULL_PANEL!r} panels, expected one to copy the band "
                             "panels from")
    taken = sorted({p.get("name") for p in tables.layout_editors(root)} & set(PANELS.values()))
    if taken:
        raise BandPanelError(f"the tables already hold a panel named {', '.join(taken)}")
    return panels[0]


def panel_names(bands) -> dict[int, str]:
    """{band index: band panel name}, by each band's level. BandPanelError when the bands' levels are not one band of
    each level PANELS names."""
    levels = band_levels(bands)
    if sorted(levels) != sorted(PANELS):
        raise BandPanelError(f"the band panels need one band at each level {', '.join(map(str, sorted(PANELS)))}; "
                             f"the bands are at {', '.join(map(str, levels))}")
    return {bi: PANELS[lv] for bi, lv in sorted(enumerate(levels), key=lambda x: x[1])}


def band_areas(P, full: ET.Element) -> list[tuple[float, float]]:
    """(top, bottom) of each band's area (module text), in band order. BandPanelError when the boxes do not stand
    one under the other."""
    boxes = list(P.band_boxes)
    if not boxes:
        raise BandPanelError("the build gives no band boxes")
    bottoms = [b[3] for b in boxes]
    bottoms[0] = max(bottoms[0], P.items["bottom"])
    bottoms[-1] = max(bottoms[-1], float(full.get("panelheight")))
    areas, top = [], 0.0
    for bi, bottom in enumerate(bottoms):
        if not top <= boxes[bi][1] < bottom:
            raise BandPanelError(f"band {bi}'s box {boxes[bi]} does not stand below the band above it (bottom {top:g})")
        areas.append((top, bottom))
        top = bottom
    return areas


def _area_of(y: float, areas) -> int | None:
    found = [bi for bi, (top, bottom) in enumerate(areas) if top <= y < bottom]
    return found[0] if found else None


def _key(el: ET.Element):
    """What ties a panel element to the build's objects (module text); None for an element with no such key."""
    tag = el.tag
    if tag in ("layoutturnout", "tracksegment", "positionablepoint", "layoutShape"):
        return ("ident", el.get("ident"))
    if tag == "signalmasticon":
        return ("mast", el.get("signalmast"))
    if tag == "BlockContentsIcon":
        return ("bci", el.get("blockcontents"), el.get("x"), el.get("y"))
    if tag == "positionablelabel" and el.get("text") is not None:
        return ("label", el.get("text"), el.get("x"), el.get("y"))
    return None


def _drawn(P) -> dict:
    """{key: set of band indexes (None for a join or an unbanded label)} of everything the build drew."""
    out: dict = {}

    def put(key, band):
        out.setdefault(key, set()).add(band)
    for o in P.turnouts + P.segments + P.shapes:
        put(("ident", P.name(o["ident"])), o["band"])
    for ident, p in P.points.items():
        put(("ident", P.name(ident)), p["band"])
    for m in P.masts:
        put(("mast", m["mast"]), m["band"])
    for b in P.bcis:
        put(("bci", b["block"], str(b["xy"][0]), str(b["xy"][1])), b["band"])
    for lb in P.labels:
        put(("label", lb["text"], str(round(lb["xy"][0])), str(round(lb["xy"][1]))), lb["band"])
    return out


def _what(el: ET.Element) -> str:
    key = _key(el)
    if key:
        return f"{el.tag} {' '.join(map(str, key[1:]))}"
    return f"{el.tag} {el.get('ident')}" if el.get("ident") else f"{el.tag} at {el.get('x')},{el.get('y')}"


def membership(full: ET.Element, P, areas) -> dict:
    """{id(element): band index, or "every" (EVERY_PANEL and the marker) or "join" (a hidden join)} for every child
    of the full panel. BandPanelError on an element in no band or in two (module text)."""
    drawn = _drawn(P)
    joins = {P.name(j) for j in P.joins}
    of, lost, twice, astray = {}, [], [], []
    for el in tables.elements(full):
        if el.tag in EVERY_PANEL or (el.tag == "positionablelabel" and el.get("text") == tables.GENERATED_PANEL_MARKER):
            of[id(el)] = "every"
            continue
        key = _key(el)
        bands = drawn.get(key) if key else None
        if bands is not None and len(bands) > 1:
            twice.append(f"{_what(el)} (bands {', '.join(map(str, sorted(bands, key=str)))})")
            continue
        band = next(iter(bands)) if bands else None
        if band is None and key == ("ident", el.get("ident")) and el.tag == "tracksegment" and el.get("ident") in joins:
            of[id(el)] = "join"
            continue
        if band is None and el.tag in AREA_TAGS and (bands is not None or el.tag != "positionablelabel" or
                                                     el.get("level") != "4"):
            y = el.get("y")
            band = _area_of(float(y), areas) if y is not None else None
        if band is None:
            lost.append(_what(el))
            continue
        y = el.get("y", el.get("ycen"))
        if y is not None and _area_of(float(y), areas) != band:
            astray.append(f"{_what(el)} (band {band}, area {_area_of(float(y), areas)})")
        of[id(el)] = band
    if twice:
        raise BandPanelError(f"{len(twice)} element(s) of {FULL_PANEL!r} in two bands: {'; '.join(twice[:6])}")
    if lost:
        raise BandPanelError(f"{len(lost)} element(s) of {FULL_PANEL!r} in no band: {'; '.join(lost[:6])}")
    if astray:
        raise BandPanelError(f"{len(astray)} element(s) of {FULL_PANEL!r} stand outside their band's area: "
                             f"{'; '.join(astray[:6])}")
    return of


def band_joins(full: ET.Element, P, of) -> dict[str, tuple[ET.Element, ET.Element]]:
    """{join segment ident: (its two end points)}: each end an anchor of a different band, joined only by that
    segment and something on its own band. BandPanelError on a join with no partner or one inside a band."""
    points = {p.get("ident"): p for p in full.findall("positionablepoint")}
    out, bad = {}, []
    for seg in full.findall("tracksegment"):
        if of.get(id(seg)) != "join":
            continue
        ident = seg.get("ident")
        ends = [points.get(seg.get(f"connect{i}name")) for i in (1, 2)]
        if any(e is None for e in ends) or {seg.get("type1"), seg.get("type2")} != {"POS_POINT"}:
            bad.append(f"{ident}: an end is not a point of the panel (no partner)")
            continue
        sides = [of.get(id(e)) for e in ends]
        if sides[0] == sides[1] or not all(isinstance(s, int) for s in sides):
            bad.append(f"{ident}: ends {ends[0].get('ident')} and {ends[1].get('ident')} are not on two bands")
            continue
        for e in ends:
            conns = [e.get("connect1name"), e.get("connect2name")]
            if e.get("type") != "ANCHOR" or ident not in conns or None in conns:
                bad.append(f"{ident}: {e.get('ident')} is not an anchor between it and its band's track")
            if any(k.endswith(("boundsignalmast", "boundsignal", "boundsensor")) for k in e.attrib):
                bad.append(f"{ident}: {e.get('ident')} carries a mast, head or sensor slot")
        out[ident] = (ends[0], ends[1])
    if bad:
        raise BandPanelError("band joins: " + "; ".join(bad))
    return out


def band_extent(full: ET.Element, of, bi: int) -> tuple[float, float]:
    """(top, bottom): the least and greatest y (Y_ATTRS) of band `bi`'s elements in the full panel. BandPanelError when
    the band has no element with a y."""
    ys = [float(e.get(a)) for el in tables.elements(full) if of[id(el)] == bi
          for e in el.iter() for a in Y_ATTRS if e.get(a) is not None]
    if not ys:
        raise BandPanelError(f"band {bi} has no element with a position")
    return min(ys), max(ys)


def translation(full: ET.Element, of, bi: int, chrome) -> tuple[int, int]:
    """(dy, panel height) for band `bi` (module text): the move that puts its topmost element MARGIN px from the top,
    and its lowest element plus MARGIN after that move. BandPanelError when the band does not fit the window."""
    top, bottom = band_extent(full, of, bi)
    dy = round(MARGIN - top)
    height = round(bottom + dy + MARGIN)
    room = int(full.get("windowheight")) - chrome[1]
    if height > room:
        raise BandPanelError(f"band {bi} needs a {height} px panel with its margins, more than the window's {room} px: "
                             "its window would not show the whole band")
    return dy, height


def _num(text: str, dy: int) -> str:
    if "." in text:
        places = len(text.split(".")[1])
        return f"{float(text) + dy:.{places}f}"
    return str(int(text) + dy)


def shift(el: ET.Element, dy: int) -> None:
    """Move `el` and everything under it `dy` px down (up when negative), keeping each value's form."""
    if not dy:
        return
    for e in el.iter():
        for a in Y_ATTRS:
            if e.get(a) is not None:
                e.set(a, _num(e.get(a), dy))


def edge_connector(point: ET.Element, join: str, linked: str, partner: str) -> ET.Element:
    """`point`, an anchor between the join segment `join` and its band's track, as an edge connector to `partner`
    on the panel `linked`."""
    unknown = sorted(set(point.attrib) - set(POINT_ORDER))
    if unknown or len(point):
        raise BandPanelError(f"anchor {point.get('ident')} has {', '.join(unknown) or 'child elements'}, which an "
                             "edge connector made from it would drop (POINT_ORDER)")
    keep = next(c for c in (point.get("connect1name"), point.get("connect2name")) if c != join)
    attrs = dict(point.attrib, type=EDGE, connect1name=keep, linkedpanel=linked, linkpointid=partner)
    attrs.pop("connect2name")
    el = ET.Element(point.tag, {k: attrs[k] for k in POINT_ORDER if k in attrs})
    el.tail = point.tail
    return el


def band_panel(full: ET.Element, of, joins, names, bi: int, name: str, dy: int, height: int,
               chrome: tuple[int, int]) -> ET.Element:
    """The band panel of band `bi` (module text)."""
    edges = {}
    for ident, (a, b) in joins.items():
        for mine, theirs in ((a, b), (b, a)):
            if of[id(mine)] == bi:
                edges[id(mine)] = (ident, names[of[id(theirs)]], theirs.get("ident"))
    panel = ET.Element(full.tag, dict(full.attrib))
    panel.text, panel.tail = full.text, full.tail
    for el in tables.elements(full):
        where = of[id(el)]
        if where not in (bi, "every"):
            continue
        new = edge_connector(el, *edges[id(el)]) if id(el) in edges else copy.deepcopy(el)
        if el.tag in EVERY_PANEL and new.get("name") is not None:
            new.set("name", name)
        if where == bi:
            shift(new, dy)
        panel.append(new)
    panel.set("name", name)
    panel.set("panelheight", str(height))
    # the window opens just tall enough for the panel and its frame, at the full panel's width (the page's le_window)
    panel.set("windowheight", str(height + chrome[1]))
    return panel


def check_links(panel: ET.Element) -> None:
    """Every connection a track object of `panel` names is an object of `panel`. BandPanelError otherwise."""
    idents = {el.get("ident") for el in tables.elements(panel) if el.get("ident")}
    dangling = sorted(f"{el.get('ident')}.{k}={v}" for el in tables.elements(panel) for k, v in el.attrib.items()
                      if k.startswith("connect") and k.endswith("name") and v not in idents)
    if dangling:
        raise BandPanelError(f"band panel {panel.get('name')!r} names track it does not hold: {', '.join(dangling[:6])}")
