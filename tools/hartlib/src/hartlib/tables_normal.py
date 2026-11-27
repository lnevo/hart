"""What a PanelPro Store adds to or rewrites in a tables file without changing it, taken out so a Store and the
generated file compare as bytes (ADR-029): the fixed envelope (PROLOG, EPILOG, ROOT_ATTRS; ENVELOPE_DROPS, which
strip_envelope takes out), the block paths JMRI derives, and the rewrites of a Layout Editor panel (normalise_panel).
normalise_store applies all of them; the round trip (tables_roundtrip) and the Store pull use it on both sides.
"""
from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET

from . import tables
from .tables_sections import finish

PROLOG = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
          b'<?xml-stylesheet href="/xml/XSLT/panelfile-5-5-5.xsl" type="text/xsl"?>\n')
EPILOG = b"\n"
# the root's schema attribute as ElementTree reads it (it writes the xmlns:xsi declaration back from the name)
ROOT_ATTRS = {"{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation":
              "http://jmri.org/xml/schema/layout-5-5-5.xsd"}
# What a PanelPro Store writes on every run, which the generated file never holds (strip_envelope).
ENVELOPE_DROPS = ("filehistory", "the 'Written by' comment", "timebase@time", "memory@value")


# What a PanelPro Store rewrites in a Layout Editor panel without changing it (the owner's decision: compare past
# these rewrites, never make the generated panel Store-shaped). normalise_panel applies them to both sides:
# - PANEL_WINDOW_ATTRS: the window's place and state on the host that stored it (where it stood on that screen, its
#   size there, the scroll bars), which differ on every host and every Store;
# - attribute order: JMRI writes a panel's attributes in its own order (name first);
# - element order: JMRI writes the labels and icons first, then the track (turnouts, segments, points, shapes);
# - numbers: JMRI keeps panel coordinates and angles as Java floats and writes them back at that precision
#   (1761.2 as 1761.199951171875, 90 as 90.0), so every number is compared as a float32 (_float32);
# - PANEL_IGNORED_ATTRS: a block contents icon's editable flag, which a Store always writes false;
# - a layout turnout's derived points: JMRI keeps a (version 1) turnout as its centre and two displacements and
#   computes A and D from them (LayoutTurnoutView.getCoordsA, getCoordsD, JMRI 5.16), so a Store writes A and D
#   as it computes them, not as the file held them; both sides take them from the centre, B and C (_derived_points).
PANEL_WINDOW_ATTRS = ("x", "y", "sliders", "windowwidth", "windowheight")
PANEL_IGNORED_ATTRS = {"BlockContentsIcon": ("editable",)}
_NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _float32(text: str) -> str:
    """A number as the float32 JMRI holds it, written one way ("90" and "90.0" both "90.0"); other text unchanged."""
    if not _NUMBER.fullmatch(text):
        return text
    return repr(struct.unpack("f", struct.pack("f", float(text)))[0])


def _f32(text: str) -> float:
    return float(struct.unpack("f", struct.pack("f", float(text)))[0])


XOVER_TYPES = ("RH_XOVER", "LH_XOVER", "DOUBLE_XOVER")


def _derived_points(turnout: ET.Element) -> None:
    """Set a version 1 layout turnout's A and D points as JMRI computes them from its centre, B and C (read as Java
    floats, worked in doubles): A = centre - (C - centre) on a crossover, centre - (B - centre) otherwise; D =
    centre - (B - centre). A turnout without those coordinates, or of version 2 (its four points stored), is left
    as it is."""
    if turnout.get("ver", "1") != "1":
        return
    try:
        cx, cy = _f32(turnout.get("xcen", "")), _f32(turnout.get("ycen", ""))     # "": ValueError, left as it is
        bx, by = _f32(turnout.get("xb", "")), _f32(turnout.get("yb", ""))
        dx, dy = _f32(turnout.get("xc", "")), _f32(turnout.get("yc", ""))
    except (TypeError, ValueError):
        return
    disp_b, disp_a = (bx - cx, by - cy), (dx - cx, dy - cy)
    a = disp_a if turnout.get("type") in XOVER_TYPES else disp_b
    turnout.set("xa", repr(cx - a[0]))
    turnout.set("ya", repr(cy - a[1]))
    if "xd" in turnout.attrib:
        turnout.set("xd", repr(cx - disp_b[0]))
        turnout.set("yd", repr(cy - disp_b[1]))


def _panel_key(el: ET.Element) -> str:
    """A stable sort key for a panel child: its tag, then the whole element as normalised text."""
    return el.tag + "\0" + ET.tostring(el, encoding="unicode")


def normalise_panel(panel: ET.Element) -> None:
    """A Layout Editor panel with the rewrites a Store makes taken out (edited in place; the rules above)."""
    for name in PANEL_WINDOW_ATTRS:
        panel.attrib.pop(name, None)
    for turnout in panel.findall("layoutturnout"):
        _derived_points(turnout)
    for el in panel.iter():
        if not isinstance(el.tag, str):
            continue
        for name in PANEL_IGNORED_ATTRS.get(el.tag, ()):
            el.attrib.pop(name, None)
        items = sorted((k, _float32(v)) for k, v in el.attrib.items())
        el.attrib.clear()
        el.attrib.update(items)
        if el.text is not None and el.text.strip():
            el.text = _float32(el.text.strip())
        el.tail = None
        if el.text is not None and not el.text.strip():
            el.text = None
    kids = [c for c in panel if isinstance(c.tag, str)]
    for c in list(panel):
        panel.remove(c)
    panel.extend(sorted(kids, key=_panel_key))


def envelope_items(root: ET.Element) -> list[str]:
    """What of ENVELOPE_DROPS `root` holds."""
    out = []
    if root.find("filehistory") is not None:
        out.append("filehistory")
    if any(not isinstance(c.tag, str) for c in root):
        out.append("the 'Written by' comment")
    if any(t.get("time") is not None for t in root.findall("timebase")):
        out.append("timebase@time")
    if any(m.get("value") is not None for box in root.findall("memories") for m in box.findall("memory")):
        out.append("memory@value")
    return out


def strip_envelope(root: ET.Element) -> None:
    """Take ENVELOPE_DROPS out of a Store's `root` (edited in place)."""
    for el in [c for c in root if not isinstance(c.tag, str) or c.tag == "filehistory"]:
        tables.remove_child(root, el)
    for t in root.findall("timebase"):
        t.attrib.pop("time", None)
    for box in root.findall("memories"):
        for m in box.findall("memory"):
            m.attrib.pop("value", None)


def normalise_store(root: ET.Element) -> None:
    """Tables `root` as compared after a Store (edited in place; used on both sides of a round trip, and by the pull):
    the envelope out (strip_envelope), the block paths JMRI derives from the panel when it loads the file (ADR-029:
    a Store rebuilds them on every staging block), and each Layout Editor panel normalised
    (normalise_panel). Idempotent: a generated file normalises to the same bytes as a Store of it."""
    strip_envelope(root)
    for block in tables.blocks(root):
        for path in block.findall("path"):
            tables.remove_child(block, path)
    for panel in tables.layout_editors(root):
        normalise_panel(panel)
    finish(root)
