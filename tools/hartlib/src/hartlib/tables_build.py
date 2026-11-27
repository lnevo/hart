"""The parts of the generated tables.xml that come from no drawing: the template, the device master's staging beans,
the discovered Signal Mast Logic, the Digicon boot rule and the fixed envelope (ADR-029).

tables.xml is an output. tools/schematic/build_tables.py writes it from:

    jmri/layouts/hart/data/tables_template.xml        TEMPLATE: what PanelPro owns and the build does not generate, in
                                                      JMRI's own format: every manager section in SECTIONS order with
                                                      its settings (turnout operations and default speeds, the
                                                      internal sensors' default state, the blocks' default speed,
                                                      blockrouting, logicDelay, the timebase), the memories, the clock
                                                      sensor, and the "Hide windows on start" LogixNG with its thread,
                                                      initialisation table and clipboard
    The device master                every level's rows: turnouts, sensors,
                                                      heads, masts, blocks and layout blocks, and the startup LogixNG
                                                      that sets each virtual detector and turnout when the tables load
                                                      (base); the Layout Editor build adds only the panels on top
    jmri/layouts/hart/data/block_lengths.csv          each block's operating length (block_lengths.operating_lengths)
    jmri/layouts/hart/data/schematic/discovered_sml.xml   DISCOVERED: the Signal Mast Logic and the mast properties
                                                      (intermediateSignal) stock discovery wrote, taken from a
                                                      discovery Store by build_tables.py --discovered-from, the only
                                                      writer (run_sml_discover.sh)
    jmri/layouts/hart/data/wiring.csv                 the Digicon masts (its wired heads), whose logic boots disabled
                                                      (disable_digicon)

The envelope is fixed: PROLOG and EPILOG around the root, jmriversion as the template has it, and none of what a
Store writes each time (ENVELOPE_DROPS: the file history, the "Written by" comment, the clock's time, the memory
values). strip_envelope takes those out of a Store.

Order. Every section's beans, the template's and the master's together, stand in the
order a JMRI 5.16 Store writes them (jmri_sort: by system name, AlphanumComparator), so a load and Store gives the
same bytes after normalise_store. The discovered logic keeps the order discovery wrote.

Every failure is a TablesBuildError naming the file, section or row.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import functools
import json
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from collections.abc import Iterable, Mapping

from . import block_lengths, devices, level_devices, paths, railroad, tables
from .errors import HartlibError

TEMPLATE = paths.LAYOUT_DATA / "tables_template.xml"
DISCOVERED = paths.LAYOUT_DATA / "schematic" / "discovered_sml.xml"
BLOCK_LENGTHS = paths.LAYOUT_DATA / "block_lengths.csv"
MM_PER_INCH = 25.4

PROLOG = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
          b'<?xml-stylesheet href="/xml/XSLT/panelfile-5-5-5.xsl" type="text/xsl"?>\n')
EPILOG = b"\n"
# the root's schema attribute as ElementTree reads it (it writes the xmlns:xsi declaration back from the name)
ROOT_ATTRS = {"{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation":
              "http://jmri.org/xml/schema/layout-5-5-5.xsd"}
# What a PanelPro Store writes on every run, which the generated file never holds (strip_envelope).
ENVELOPE_DROPS = ("filehistory", "the 'Written by' comment", "timebase@time", "memory@value")

# The sections of the generated file, in order: (tag, class). The template holds exactly these; the Layout Editor
# build appends the panel after the last.
MQTT_SENSORS = ("sensors", "jmri.jmrix.mqtt.configurexml.MqttSensorManagerXml")
INTERNAL_SENSORS = ("sensors", "jmri.jmrix.internal.configurexml.InternalSensorManagerXml")
LCC_TURNOUTS = ("turnouts", "jmri.jmrix.openlcb.configurexml.OlcbTurnoutManagerXml")
INTERNAL_TURNOUTS = ("turnouts", "jmri.jmrix.internal.configurexml.InternalTurnoutManagerXml")
MQTT_TURNOUTS = ("turnouts", "jmri.jmrix.mqtt.configurexml.MqttTurnoutManagerXml")
MEMORIES = ("memories", "jmri.managers.configurexml.DefaultMemoryManagerXml")
HEADS = ("signalheads", "jmri.managers.configurexml.AbstractSignalHeadManagerXml")
MASTS = ("signalmasts", "jmri.managers.configurexml.DefaultSignalMastManagerXml")
BLOCKS = ("blocks", "jmri.configurexml.BlockManagerXml")
LAYOUT_BLOCKS = ("layoutblocks", "jmri.jmrit.display.layoutEditor.configurexml.LayoutBlockManagerXml")
LOGICS = ("signalmastlogics", "jmri.managers.configurexml.DefaultSignalMastLogicManagerXml")
TIMEBASE = ("timebase", "jmri.jmrit.simpleclock.configurexml.SimpleTimebaseXml")
LOGIXNGS = ("LogixNGs", "jmri.jmrit.logixng.implementation.configurexml.DefaultLogixNGManagerXml")
CONDITIONALNGS = ("LogixNGConditionalNGs", "jmri.jmrit.logixng.implementation.configurexml.DefaultConditionalNGManagerXml")
DIGITAL_ACTIONS = ("LogixNGDigitalActions", "jmri.jmrit.logixng.implementation.configurexml.DefaultDigitalActionManagerXml")
SECTIONS = (("jmriversion", None), MQTT_SENSORS, INTERNAL_SENSORS, LCC_TURNOUTS, INTERNAL_TURNOUTS, MQTT_TURNOUTS,
            MEMORIES, HEADS, MASTS, BLOCKS, LAYOUT_BLOCKS, LOGICS, TIMEBASE, LOGIXNGS, CONDITIONALNGS, DIGITAL_ACTIONS)
# The sections whose beans come from the master only: the template holds their settings and no bean (read_template),
# so a block or mast never has two sources.
MASTER_SECTIONS = (MQTT_SENSORS, LCC_TURNOUTS, INTERNAL_TURNOUTS, MQTT_TURNOUTS, HEADS, MASTS, BLOCKS, LAYOUT_BLOCKS)
# The manager section of a sensor or turnout, by the system name's prefix (the connection's).
SENSOR_SECTIONS = (("M2S", MQTT_SENSORS), ("IS", INTERNAL_SENSORS))
TURNOUT_SECTIONS = (("M2T", MQTT_TURNOUTS), ("MTT", LCC_TURNOUTS), ("IT", INTERNAL_TURNOUTS))

HEAD_CLASS = "jmri.implementation.configurexml.VirtualSignalHeadXml"
MAST_CLASS = "jmri.implementation.configurexml.SignalHeadSignalMastXml"
VIRTUAL_MAST_CLASS = "jmri.implementation.configurexml.VirtualSignalMastXml"
VIRTUAL_HEAD_NOTE = level_devices.VIRTUAL_NOTE  # a staging head on an internal name: no field head drives it
LAYOUT_BLOCK_ATTRS = (("occupiedsense", "2"), ("trackcolor", "gray"), ("occupiedcolor", "red"),
                      ("extracolor", "white"))
HELIX_LEVEL = railroad.STAGING_LEVEL   # the helix blocks' beans are staging's; a main or upper helix detector binds them
_LCOS_HEAD = re.compile(r"\(IH\d+\)")


class TablesBuildError(HartlibError, ValueError):
    """The template, the master rows, the discovered logic or the result cannot make a tables file."""


GENERATED_NOTE = ("tables.xml is generated (ADR-029): change the device master, the template (data/tables_template.xml) "
                  "or the other sources, then run python3 tools/schematic/build_tables.py")


def refuse_generated(target: Path | str, script: str) -> None:
    """Stop `script` (SystemExit) before it writes the repo's generated tables.xml, by path or through a link; a
    script that edited tables.xml by hand may still write another tables file it is pointed at."""
    if os.path.realpath(target) == os.path.realpath(paths.REPO_TABLES_XML):
        raise SystemExit(f"{script}: not writing {paths.rel(Path(target))}: {GENERATED_NOTE}")


# ---------------------------------------------------------------- order

def _chunks(s: str) -> list[str]:
    return re.findall(r"\d+|\D+", s)


def _alphanum(a: str, b: str) -> int:
    """jmri.util.AlphanumComparator: digit runs compare as numbers, everything else as text, a prefix first."""
    for x, y in zip(_chunks(a), _chunks(b)):
        if x.isdigit() and y.isdigit():
            d = int(x) - int(y)
        else:
            d = (x > y) - (x < y)
        if d:
            return d
    return len(a) - len(b)


def jmri_order(names: Iterable[str]) -> list[str]:
    """`names` in the order a JMRI manager keeps system names (AlphanumComparator)."""
    return sorted(names, key=functools.cmp_to_key(_alphanum))


# ---------------------------------------------------------------- the template

def section_key(el: ET.Element) -> tuple[str, str | None]:
    return el.tag, el.get("class")


def read_template(path: Path = TEMPLATE) -> tables.Tables:
    """The template, checked: the fixed envelope (PROLOG, EPILOG, ROOT_ATTRS), exactly the SECTIONS in their order,
    and none of what a Store writes each time (ENVELOPE_DROPS), no panel and no Signal Mast Logic."""
    try:
        doc = tables.load(path)
    except OSError as exc:
        raise TablesBuildError(f"{paths.rel(path)}: cannot read it ({exc.strerror})") from exc
    except ET.ParseError as exc:
        raise TablesBuildError(f"{paths.rel(path)}: not XML ({exc})") from exc
    where = paths.rel(path)
    if doc.prolog != PROLOG or doc.epilog != EPILOG:
        raise TablesBuildError(f"{where}: the declaration and stylesheet lines, or the final newline, are not the "
                               "fixed envelope (hartlib.tables_build.PROLOG, EPILOG)")
    if doc.root.tag != "layout-config" or dict(doc.root.attrib) != ROOT_ATTRS:
        raise TablesBuildError(f"{where}: the root is not <layout-config> with the schema attributes")
    got = [section_key(el) for el in tables.elements(doc.root)]
    missing = [f"<{t} class={c}>" if c else f"<{t}>" for t, c in SECTIONS if (t, c) not in got]
    if missing:
        raise TablesBuildError(f"{where}: no {', '.join(missing)} section")
    known = [k for k in got if k in SECTIONS]
    if known != list(SECTIONS):
        raise TablesBuildError(f"{where}: the sections are not exactly {', '.join(t for t, _ in SECTIONS)} in that "
                               f"order (got {', '.join(t for t, _ in got)})")
    # A section outside SECTIONS is one the owner made in PanelPro (a Route table, say) that a Store split kept
    # (hartlib.store_split); it stays where the Store had it. Never a second copy of a known one, a panel or the
    # file history.
    extra = [k for k in got if k not in SECTIONS]
    bad = sorted({t for t, _ in extra if t in {s for s, _ in SECTIONS} | {"filehistory"} or t.lower().endswith("editor")})
    if bad or len(set(extra)) != len(extra):
        raise TablesBuildError(f"{where}: holds {', '.join(bad) or 'a section'} twice or out of place")
    held = envelope_items(doc.root)
    if held:
        raise TablesBuildError(f"{where}: holds what a Store writes each time ({', '.join(held)}); the envelope is "
                               "fixed (strip_envelope)")
    if tables.mast_logics(doc.root) or doc.root.find("LayoutEditor") is not None:
        raise TablesBuildError(f"{where}: holds Signal Mast Logic or a panel; those are generated")
    owned = [f"{el.tag} {tables.system_name(el)}" for sec in tables.elements(doc.root)
             if section_key(sec) in MASTER_SECTIONS for el in tables.elements(sec) if tables.system_name(el)]
    if owned:
        raise TablesBuildError(f"{where}: holds {', '.join(owned[:6])}, but turnouts, MQTT sensors, heads, masts, "
                               "blocks and layout blocks come from the device master")
    return doc


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


def sort_group(el: ET.Element) -> str:
    """The run of beans a JMRI manager writes and sorts on its own: a block's names-only pass apart from its full pass
    (BlockManagerXml writes every block twice), one group for every other bean of a section."""
    if el.tag == "block":
        return "block-names" if {c.tag for c in tables.elements(el)} <= {"systemName", "userName"} else "block"
    return "bean"


def jmri_sort(root: ET.Element) -> None:
    """Put every section's beans in the order a JMRI 5.16 Store writes them (edited in place): each manager keeps its
    beans in a set ordered by system name (NamedBean.compareTo, AlphanumComparator: jmri_order), so within each
    group of a section (sort_group) the beans take the group's places in that order; settings and other children
    (Thread, InitializationTable, Clipboard, defaultspeed ...) keep their places. Checked against a PanelPro Store of
    the generated file. Signal Mast Logic carries no system name and keeps discovery's order."""
    key = functools.cmp_to_key(_alphanum)
    for sec in tables.elements(root):
        kids = list(sec)
        groups: dict[str, list[int]] = {}
        for i, el in enumerate(kids):
            if isinstance(el.tag, str) and tables.system_name(el):
                groups.setdefault(sort_group(el), []).append(i)
        if not groups:
            continue
        for slots in groups.values():
            ordered = sorted((kids[i] for i in slots), key=lambda e: key(tables.system_name(e)))
            for i, el in zip(slots, ordered):
                kids[i] = el
        for el in list(sec):
            sec.remove(el)
        sec.extend(kids)


def bean_names(root: ET.Element) -> set[str]:
    """Every system and user name of a bean in `root`."""
    return {n for sec in tables.elements(root) for el in tables.elements(sec)
            for n in (tables.system_name(el), tables.user_name(el)) if n}


# ---------------------------------------------------------------- the master's beans

def _sub(el: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    child = ET.SubElement(el, tag, attrs)
    if text is not None:
        child.text = text
    return child


DIRECTION_WORD = {"east": "East", "west": "West"}
_OCCUPANCY = re.compile(r"(?:^|; )occupancy (Block \d+-\d+ / M2S\d+(?: \([^()]*\))?)(?=;|$)")
_HEADS_OF_MAST = re.compile(r"\(([^()]+)\)")


def with_direction(comment: str, direction: str) -> str:
    """A mast's comment (its place) with the way it faces ("East" or "West", from the dir column) after it: "Brick |
    Switch 1 | West". A main or upper mast's planned device follows (device_map_rows.bean_cells)."""
    word = DIRECTION_WORD.get(direction)
    if not word:
        return comment
    parts = comment.split(" | ") if comment else []
    if word in parts:                       # a comment that names it already
        return comment
    return " | ".join(parts + [word])


def occupancy_first(comment: str) -> str:
    """A block's comment with its detector first, without the word occupancy:
    "Princess balloon, Track K-1; occupancy Block 1-1 / M2S100; stop" -> "Block 1-1 / M2S100; Princess balloon,
    Track K-1; stop". A comment with no detector text is as it was."""
    m = _OCCUPANCY.search(comment)
    if not m:
        return comment
    rest = (comment[: m.start()] + comment[m.end():]).strip("; ")
    return "; ".join(x for x in (m.group(1), rest) if x)


_DETECTOR_FIRST = re.compile(r"(Block \d+-\d+ / M2S\d+(?: \([^()]*\))?)(?:; (.*))?", re.S)


def occupancy_back(comment: str) -> str | None:
    """The master's form of a built block comment (occupancy_first undone): "Block 1-1 / M2S100; Princess balloon;
    stop" -> "Princess balloon; occupancy Block 1-1 / M2S100; stop". None when it does not start with a detector."""
    m = _DETECTOR_FIRST.fullmatch(comment)
    if not m or "occupancy Block" in (m.group(2) or ""):
        return None
    det, rest = f"occupancy {m.group(1)}", m.group(2) or ""
    if rest == "stop" or rest.endswith("; stop"):
        head = rest[: -len("stop")].rstrip("; ")
        return "; ".join(x for x in (head, det, "stop") if x)
    return "; ".join(x for x in (rest, det) if x)


def mast_places(rows: Iterable[Mapping[str, str]]) -> dict[str, str]:
    """{head jmri_name: the comment of the head mast it lights}, so a wired head reads its place first."""
    out: dict[str, str] = {}
    for r in rows:
        if r["layer"] == "mast" and r["jmri_name"].startswith("IF$shsm:") and r["jmri_comment"]:
            for h in _HEADS_OF_MAST.findall(r["jmri_name"]):
                out.setdefault(h, r["jmri_comment"])
    return out


def bean_comment(r: Mapping[str, str], places: Mapping[str, str] | None = None) -> str:
    """The JMRI comment of a master row, from its wiring columns: the device-map comment (jmri_comment, else the
    wiring text with a field turnout's DCC group, hartlib.devices.device_map_row), and for a staging head on an
    internal name VIRTUAL_HEAD_NOTE after it. A wired head reads its mast's place first ("Plane | Switch 5 | Node:
    4 ..."; `places`, mast_places), a mast its direction after its place (with_direction), a block its detector
    first (occupancy_first). TablesBuildError when the row gives no comment."""
    comment = devices.device_map_row(r)["comment"]
    if not comment:
        raise TablesBuildError(f"the device master: {r['layer']} {r['user_name']!r} has neither wiring nor jmri_comment, "
                               "so it gives no JMRI comment")
    layer = r["layer"]
    if layer == "head" and r["role"] == "head" and r["assignment"] == "virtual":
        comment = f"{comment} | {VIRTUAL_HEAD_NOTE}"
    elif layer == "head" and not r["jmri_comment"] and places and r["jmri_name"] in places:
        comment = f"{places[r['jmri_name']]} | {comment}"
    elif layer == "mast":
        comment = with_direction(comment, r["dir"])
    elif layer == "block":
        comment = occupancy_first(comment)
    return comment


def _route(name: str, table: Iterable[tuple[str, tuple[str, str]]], what: str) -> tuple[str, str]:
    for prefix, key in table:
        if name.startswith(prefix):
            return key
    raise TablesBuildError(f"the device master: {what} {name!r} has no manager section for its prefix "
                           f"({', '.join(p for p, _ in table)})")


def _named(tag: str, attrs: dict, system: str, user: str, comment: str) -> ET.Element:
    el = ET.Element(tag, attrs)
    _sub(el, "systemName", system)
    _sub(el, "userName", user)
    _sub(el, "comment", comment)
    return el


# ---------------------------------------------------------------- a device not on the layout yet (jmri_bean)
#
# A device the owner adds in PanelPro (a test turnout, a DCC accessory) has a device-master row with no level, cp or role
# until its details are known, and the beans exactly as the Store wrote them in its jmri_bean
# column, as compact JSON:
#     {"beans": [{"section": [tag, class], "element": NODE}, ...]}
#     NODE = {"tag": ..., "attrs": {...}, "text": ... (only when not blank), "children": [NODE, ...]}
# A child <userName> or <comment> whose text is the row's user_name or jmri_comment is {"tag": ..., "column": ...}
# instead, so a rename or a new comment changes one cell, not the JSON too.

BEAN_COLUMNS = {"userName": "user_name", "comment": "jmri_comment"}


def _node(el: ET.Element, row: Mapping[str, str] | None) -> dict:
    out: dict = {"tag": el.tag, "attrs": dict(el.attrib)}
    if el.text is not None and el.text.strip():
        out["text"] = el.text
    kids = []
    for c in tables.elements(el):
        col = BEAN_COLUMNS.get(c.tag)
        if row is not None and col and not len(c) and not c.attrib and (c.text or "") == row[col] and row[col]:
            kids.append({"tag": c.tag, "column": col})
        else:
            kids.append(_node(c, None))
    if kids:
        out["children"] = kids
    return out


def _element(node: Mapping, row: Mapping[str, str], where: str) -> ET.Element:
    if not isinstance(node, Mapping) or not isinstance(node.get("tag"), str):
        raise TablesBuildError(f"{where}: an element of jmri_bean has no tag")
    if "column" in node:
        if node["column"] not in BEAN_COLUMNS.values():
            raise TablesBuildError(f"{where}: jmri_bean names column {node['column']!r}, not "
                                   f"{' or '.join(BEAN_COLUMNS.values())}")
        el = ET.Element(node["tag"])
        el.text = row[node["column"]]
        return el
    attrs = node.get("attrs", {})
    if not isinstance(attrs, Mapping) or not all(isinstance(v, str) for v in attrs.values()):
        raise TablesBuildError(f"{where}: <{node['tag']}> attrs in jmri_bean are not text")
    el = ET.Element(node["tag"], dict(attrs))
    if "text" in node:
        el.text = node["text"]
    for c in node.get("children", []):
        el.append(_element(c, row, where))
    return el


def bean_json(beans: Iterable[tuple[tuple[str, str | None], ET.Element]], row: Mapping[str, str]) -> str:
    """The jmri_bean text of `row` for `beans` ((section key, element) as the Store holds them)."""
    return json.dumps({"beans": [{"section": list(k), "element": _node(el, row)} for k, el in beans]},
                      separators=(",", ":"), ensure_ascii=False)


def row_beans(row: Mapping[str, str]) -> list[tuple[tuple[str, str | None], ET.Element]]:
    """[(section key, element)] of a row's jmri_bean (bean_json); TablesBuildError when the text is not that shape, a
    section is not one the master gives (MASTER_SECTIONS), or a bean names no system name."""
    where = f"the device master: {row['layer']} {row['user_name']!r}"
    try:
        doc = json.loads(row["jmri_bean"])
    except json.JSONDecodeError as exc:
        raise TablesBuildError(f"{where}: jmri_bean is not JSON ({exc.msg})") from exc
    beans = doc.get("beans") if isinstance(doc, dict) else None
    if not isinstance(beans, list) or not beans:
        raise TablesBuildError(f"{where}: jmri_bean is not {{\"beans\": [...]}} with at least one bean")
    out: list[tuple[tuple[str, str | None], ET.Element]] = []
    for b in beans:
        given = tuple(b.get("section") or ()) if isinstance(b, dict) else ()
        sec = next((k for k in MASTER_SECTIONS if k == given), None)
        if sec is None:
            raise TablesBuildError(f"{where}: jmri_bean section {list(given)} is not one a device master row gives")
        el = _element(b.get("element"), row, where)
        if not tables.system_name(el):
            raise TablesBuildError(f"{where}: a <{el.tag}> in jmri_bean has no system name")
        out.append((sec, el))
    return out


def kept_beans(rows: Iterable[Mapping[str, str]]) -> dict[tuple, list[ET.Element]]:
    """{section: [bean, ...]} of the rows with a jmri_bean, as master_beans gives them (a block's names-only pass
    under ("blocks-names", ...))."""
    out: dict[tuple, list[ET.Element]] = {}
    bad = []
    for r in rows:
        if not r["jmri_bean"]:
            continue
        try:
            for sec, el in row_beans(r):
                key = ("blocks-names",) + BLOCKS if sec == BLOCKS and sort_group(el) == "block-names" else sec
                out.setdefault(key, []).append(el)
        except TablesBuildError as exc:
            bad.append(str(exc).removeprefix("the device master: "))
    if bad:
        raise TablesBuildError("the device master: " + "; ".join(bad))
    return out


# ---------------------------------------------------------------- a bean's shape, by its row's columns
#
# master_beans makes every level's beans from their rows' columns alone: the bean's name (bean_name), its comment
# (row_comment), a turnout's feedback (turnout_feedback), whether an LCC alias is a bean of its own
# (alias_is_turnout), and the state a virtual bean is set to when the tables load (start_actions). Which beans a row
# gives is its layer's (LAYER_BEANS). The startup LogixNG around the actions is start_logixng's.

LAYER_BEANS = {"turnout": "one turnout (an LCC alias none when it names its turnout's bean)",
               "fb": "one sensor", "occupancy": "one sensor", "sensor": "one sensor", "head": "one signal head",
               "mast": "one head mast (IF$shsm:) or virtual mast (IF$vsm:)",
               "block": "a names-only block, a full block and a layout block"}
START_ACTIONS = ("start-actions",) + DIGITAL_ACTIONS     # master_beans' key for the startup actions (start_actions)
ACTION_CLASS = {"occupancy": ("ActionSensor", "jmri.jmrit.logixng.actions.configurexml.ActionSensorXml"),
                "turnout": ("ActionTurnout", "jmri.jmrit.logixng.actions.configurexml.ActionTurnoutXml")}
MALE_DEBUGGER = "jmri.jmrit.logixng.tools.debugger.configurexml.DebuggerMaleDigitalActionSocketXml"
MALE_ACTION = "jmri.jmrit.logixng.implementation.configurexml.DefaultMaleDigitalActionSocketXml"


def bean_name(r: Mapping[str, str]) -> str:
    """The system name of a row's bean: a field turnout's system_name (its jmri_name may be its user name, bound by
    name, Q13), every other row's jmri_name. jmri_name is the device tables.xml uses and system_name a main or upper
    row's planned draft (ADR-028), so a swap is a jmri_name edit."""
    return r["system_name"] if r["assignment"] == "field" and r["layer"] == "turnout" else r["jmri_name"]


def level_turnouts(rows: Iterable[Mapping[str, str]]) -> dict[str, str]:
    """{user name: bean name} of the main and upper turnouts (level_devices.LEVELS, layer turnout, role turnout, a
    bean): by the rows, so a turnout swapped to a physical name (ADR-028) is still one. The CATS desk checks and the
    desk build pick the main and upper plants by it."""
    return {r["user_name"]: bean_name(r) for r in rows if r["level"] in level_devices.LEVELS
            and r["layer"] == "turnout" and r["role"] == "turnout" and r["assignment"] != "none"}


def row_comment(r: Mapping[str, str], places: Mapping[str, str] | None = None) -> str:
    """A bean's comment: its row's bean_comment (the main and upper rows' cell), else its wiring's (bean_comment)."""
    return r["bean_comment"] or bean_comment(r, places)


def _switch_number(r: Mapping[str, str], at: str) -> str:
    kind, _, number = r["id"].partition(":")
    if kind not in ("switch", "dcc") or not number:
        raise TablesBuildError(f"the device master: {at}: id {r['id']!r} is not switch:<n> or dcc:<n>")
    return number


def _gives_bean(row: Mapping[str, str] | None) -> bool:
    return row is not None and row["assignment"] != "none"


def turnout_feedback(r: Mapping[str, str], by_id: Mapping[str, Mapping[str, str]], at: str) -> dict[str, str]:
    """A turnout's (or its LCC alias's) feedback attributes: TWOSENSOR on its two feedback rows (fb:<n>:R as sensor1,
    fb:<n>:N as sensor2, by user name) when both give beans (`by_id`: every row of its level, by id); DIRECT when
    neither does and the turnout is not a field row (a virtual stand-in). TablesBuildError when only one does, or a
    field turnout has none (staging's are wired with both)."""
    number = _switch_number(r, at)
    ids = [f"fb:{number}:{pos}" for pos in ("R", "N")]
    fb = [by_id.get(i) for i in ids]
    lost = [i for i, f in zip(ids, fb) if not _gives_bean(f)]
    if len(lost) == 2 and r["assignment"] != "field":
        return {"feedback": "DIRECT", "inverted": "false", "automate": "Off"}
    if lost:
        raise TablesBuildError(f"the device master: {at}: no feedback bean {', '.join(lost)}; a field turnout has "
                               "two, a virtual one two or none")
    sensor1, sensor2 = (f["user_name"] for f in fb if f is not None)        # neither is lost
    return {"feedback": "TWOSENSOR", "sensor1": sensor1, "sensor2": sensor2,
            "inverted": "false", "automate": "Off"}


def alias_is_turnout(r: Mapping[str, str], by_id: Mapping[str, Mapping[str, str]], at: str) -> bool:
    """Whether LCC alias row `r` names its turnout's bean (a virtual turnout's alias, main and upper today): it then
    gives no bean of its own. `by_id`: as turnout_feedback's. TablesBuildError when its level has no switch:<n> row,
    or that row gives no bean while the alias names it."""
    tid = f"switch:{_switch_number(r, at)}"
    turnout = by_id.get(tid)
    if turnout is None:
        raise TablesBuildError(f"the device master: {at}: no turnout row {tid} on level {r['level']}")
    if bean_name(turnout) != bean_name(r):
        return False
    if not _gives_bean(turnout):
        raise TablesBuildError(f"the device master: {at}: names the bean of {tid}, whose assignment is none")
    return True


def male_socket(el: ET.Element) -> None:
    """The <MaleSocket> PanelPro 5.16 stores under a digital action (as on IQDA:AUTO:0001 in tables.xml)."""
    m = _sub(el, "MaleSocket")
    _sub(m, "AbstractDebuggerMaleSocket", **{"class": MALE_DEBUGGER})
    a = _sub(m, "AbstractMaleSocket", enabled="yes", locked="no", system="no", catchAbortExecution="no",
             **{"class": MALE_ACTION})
    _sub(a, "errorHandling", "Default")


def start_action(layer: str, name: str, bean: str, state: str) -> ET.Element:
    """The startup LogixNG's action `name` that sets `bean` (a sensor for layer occupancy, a turnout for layer
    turnout) to `state` (Inactive, Closed or Thrown: hartlib.level_devices.START_ENUM), as PanelPro 5.16 stores it."""
    tag, cls = ACTION_CLASS[layer]
    a = ET.Element(tag, {"class": cls})
    _sub(a, "systemName", name)
    nb = _sub(a, "namedBean")
    for t, text in (("addressing", "Direct"), ("name", bean), ("listenToMemory", "no")):
        _sub(nb, t, text)
    st = _sub(a, "state")
    for t, text in (("addressing", "Direct"), ("enum", state), ("listenToMemory", "no")):
        _sub(st, t, text)
    male_socket(a)
    return a


def start_actions(rows: Iterable[Mapping[str, str]]) -> list[ET.Element]:
    """The startup actions of the rows with a start (hartlib.devices.START): one ActionSensor per detector, then one
    ActionTurnout per turnout, each group in name order, as the main and upper LogixNG holds them. Only a virtual
    bean is set: a field device reports its own state. TablesBuildError on a start on a row that is not a virtual
    detector or turnout, or on a bean the startup LogixNG has no action name for (hartlib.level_devices.clear_action,
    turnout_action)."""
    groups: dict[str, list[tuple[str, str, str]]] = {"occupancy": [], "turnout": []}
    bad = []
    for r in rows:
        if not r["start"]:
            continue
        at = f"{r['layer']} {r['user_name']!r}"
        if r["assignment"] != "virtual" or r["layer"] not in groups:
            bad.append(f"{at}: start {r['start']!r} on a {r['assignment']} {r['layer']} row; only a virtual detector "
                       "or turnout is set when the tables load")
            continue
        name = bean_name(r)
        action = level_devices.clear_action if r["layer"] == "occupancy" else level_devices.turnout_action
        try:
            groups[r["layer"]].append((name, action(name), level_devices.START_ENUM[r["start"]]))
        except (ValueError, KeyError) as exc:
            bad.append(f"{at}: {exc}")
    if bad:
        raise TablesBuildError("the device master: " + "; ".join(bad))
    return [start_action(layer, action, bean, state)
            for layer, group in groups.items() for bean, action, state in sorted(group)]


def block_beans(r: Mapping[str, str], name: str, length: float, sensor: str | None,
                comment: str) -> tuple[ET.Element, ET.Element, ET.Element]:
    """A block row's names-only block, full block (`length`: its operating length in inches) and layout block, the last two on `sensor` (a
    detector's user name) when it has one."""
    user = r["user_name"]
    names_only = ET.Element("block", {"systemName": name})
    _sub(names_only, "systemName", name)
    _sub(names_only, "userName", user)
    full = _named("block", {"systemName": name, "length": f"{length * MM_PER_INCH:.1f}", "curve": "0"},
                  name, user, comment)
    _sub(full, "permissive", "no")
    lb_attrs = {"systemName": r["layout_block"]}
    if sensor:
        _sub(full, "occupancysensor", sensor)
        lb_attrs["occupancysensor"] = sensor
    lb = ET.Element("layoutblock", {**lb_attrs, **dict(LAYOUT_BLOCK_ATTRS)})
    _sub(lb, "systemName", r["layout_block"])
    _sub(lb, "userName", user)
    return names_only, full, lb


def mast_bean(name: str, user: str, comment: str) -> ET.Element | None:
    """A mast's bean by its system name: a SignalHeadSignalMast (IF$shsm:, unlit not allowed) or a VirtualSignalMast
    (IF$vsm:, unlit allowed); None for any other."""
    if name.startswith("IF$vsm:"):
        el = _named("virtualsignalmast", {"class": VIRTUAL_MAST_CLASS}, name, user, comment)
        _sub(el, "unlit", allowed="yes")
    elif name.startswith("IF$shsm:"):
        el = _named("signalmast", {"class": MAST_CLASS}, name, user, comment)
        _sub(el, "unlit", allowed="no")
    else:
        return None
    return el


def master_beans(rows: Iterable[Mapping[str, str]], lengths: Mapping[str, float],
                 levels: Iterable[str] | None = None) -> dict[tuple, list[ET.Element]]:
    """{section: [bean, ...]} of the master rows of `levels` (default every level a row has: what build_tables.py
    writes; a level-less row's beans are its jmri_bean's, kept_beans), a block's names-only pass first under
    ("blocks-names", ...) and the startup actions under START_ACTIONS (start_actions; staging has none, main and
    upper one per virtual detector and turnout). A row with assignment none gives no bean; every other row gives
    its layer's beans (LAYER_BEANS), shaped by its columns: bean_name, row_comment, turnout_feedback and
    alias_is_turnout. A block takes the sensor of the detector whose blocks column names it, on any of `levels` (a
    helix block: the main or upper detector's); a part (part_of) its block's. TablesBuildError on a row the module has
    no bean for, a turnout with one feedback row, a block with no length, no layout block or two detectors, or a
    start the startup LogixNG cannot set."""
    rows = list(rows)
    levels = tuple({r["level"] for r in rows if r["level"]} if levels is None else levels)
    every = [r for r in rows if r["level"] and r["level"] in levels]
    rows = [r for r in every if r["assignment"] != "none"]
    by_id: dict[str, dict[str, Mapping[str, str]]] = {}
    for r in every:
        if r["id"]:
            by_id.setdefault(r["level"], {})[r["id"]] = r
    places = mast_places(rows)
    detector: dict[tuple[str, str], list[str]] = {}       # {(level, block): detectors}
    for r in rows:
        if r["layer"] == "occupancy":
            # a helix detector binds staging's helix block, the one block that climbs through the levels
            level = HELIX_LEVEL if r["role"] == "helix" else r["level"]
            for b in filter(None, (x.strip() for x in r["blocks"].split(";"))):
                detector.setdefault((level, b), []).append(r["user_name"])
    out: dict[tuple, list[ET.Element]] = {}
    bad: list[str] = []

    def add(key: tuple[str, ...], el: ET.Element) -> None:     # a section key, or ("blocks-names",) + BLOCKS
        out.setdefault(key, []).append(el)

    for r in rows:
        layer, user, name = r["layer"], r["user_name"], bean_name(r)
        at = f"{layer} {user!r}"
        try:
            if layer == "turnout":
                ids = by_id.get(r["level"], {})
                if r["role"] == "lcc_alias" and alias_is_turnout(r, ids, at):
                    continue
                attrs = turnout_feedback(r, ids, at)
                add(_route(name, TURNOUT_SECTIONS, at), _named("turnout", attrs, name, user, row_comment(r)))
            elif layer in ("fb", "occupancy", "sensor"):
                add(_route(name, SENSOR_SECTIONS, at), _named("sensor", {"inverted": "false"}, name, user,
                                                               row_comment(r)))
            elif layer == "head":
                add(HEADS, _named("signalhead", {"class": HEAD_CLASS}, name, user, row_comment(r, places)))
            elif layer == "mast":
                el = mast_bean(name, user, row_comment(r))
                if el is None:
                    bad.append(f"{at}: bean name {name!r} is neither a head mast (IF$shsm:) nor a virtual one (IF$vsm:)")
                    continue
                add(MASTS, el)
            elif layer == "block":
                length = lengths.get(user)
                if length is None:
                    bad.append(f"{at}: no row in block_lengths.csv")
                    continue
                if not r["layout_block"]:
                    bad.append(f"{at}: no layout_block")
                    continue
                sensors = detector.get((r["level"], r["part_of"] or user), [])       # a part: its block's sensor
                if len(sensors) > 1:
                    bad.append(f"{at}: detected by {len(sensors)} occupancy rows ({', '.join(sensors)})")
                    continue
                names_only, full, lb = block_beans(r, name, length, sensors[0] if sensors else None, row_comment(r))
                add(("blocks-names",) + BLOCKS, names_only)
                add(BLOCKS, full)
                add(LAYOUT_BLOCKS, lb)
            else:
                bad.append(f"{at}: no bean for layer {layer!r}")
        except TablesBuildError as exc:
            bad.append(str(exc).removeprefix("the device master: "))
    try:
        actions = start_actions(rows)
    except TablesBuildError as exc:
        bad.append(str(exc).removeprefix("the device master: "))
        actions = []
    if bad:
        raise TablesBuildError("the device master: " + "; ".join(bad))
    if actions:
        out[START_ACTIONS] = actions
    return out


def base(rows: Iterable[Mapping[str, str]] | None = None, template: Path = TEMPLATE,
         lengths: Mapping[str, float] | None = None) -> tables.Tables:
    """The template with every level's master beans in it (master_beans) and the startup
    LogixNG around their startup actions (start_logixng), each section's beans in JMRI order: what the Layout Editor
    build draws its panels on, adding no bean, from `rows` of the master's text (default its cells). TablesBuildError
    when a master bean's system or user name is the template's too, or two beans of one kind share a name."""
    doc = read_template(template)
    rows = [r.cells() for r in devices.load()] if rows is None else list(rows)
    try:
        lengths = block_lengths.operating_lengths(BLOCK_LENGTHS) if lengths is None else lengths     # ADR-039 L8
    except railroad.FactsError as exc:
        raise TablesBuildError(str(exc)) from exc
    beans = master_beans(rows, lengths)
    actions = beans.pop(START_ACTIONS, [])
    made = {n for els in beans.values() for el in els for n in (tables.system_name(el), tables.user_name(el)) if n}
    kept = kept_beans(rows)
    twice = sorted({tables.system_name(el) for key, els in kept.items() if key[0] != "blocks-names" for el in els
                    if tables.system_name(el) in made})
    if twice:
        raise TablesBuildError(f"the device master: a level-less device's jmri_bean names a bean a level row makes too "
                               f"({', '.join(twice[:8])}); a bean has one source")
    for key, els in kept.items():
        beans.setdefault(key, []).extend(els)
    if ("blocks-names",) + BLOCKS in beans:
        beans.setdefault(BLOCKS, [])
    held = bean_names(doc.root)
    clash = sorted({n for els in beans.values() for el in els for n in (tables.system_name(el), tables.user_name(el))
                    if n in held})
    if clash:
        raise TablesBuildError(f"{paths.rel(template)}: holds beans the master gives too ({', '.join(clash[:8])}); "
                               "a bean has one source")
    sections = {section_key(el): el for el in tables.elements(doc.root)}
    for key, els in beans.items():
        sec = sections[key[1:] if key[0] == "blocks-names" else key]
        if key == BLOCKS:
            continue                # with the names-only pass below
        _fill(sec, els, beans.get(BLOCKS, []) if key[0] == "blocks-names" else None)
    if actions:
        start_logixng(doc.root, actions)
    finish(doc.root)
    check_names(doc.root)
    return doc


def _insert(parent: ET.Element, new: list[ET.Element], after: ET.Element | None = None) -> None:
    """Put `new` into `parent` after `after` (default: at the end); finish indents them."""
    at = list(parent).index(after) + 1 if after is not None else len(parent)
    for k, el in enumerate(new):
        parent.insert(at + k, el)


def start_logixng(root: ET.Element, actions: list[ET.Element]) -> None:
    """The LogixNG that runs `actions` (start_actions: an ActionSensor per virtual detector, an ActionTurnout per
    virtual turnout) once when the tables load, into tables `root` (edited in place), as PanelPro 5.16 stores it
    (hartlib.level_devices: LogixNG CLEAR_LOGIXNG after the template's LogixNGs, its ConditionalNG CLEAR_CONDITIONAL
    with one socket naming the DigitalMany CLEAR_MANY, whose sockets A1, A2, ... name the actions in their order, the
    DigitalMany and the actions after the template's digital actions). A ConditionalNG executes at startup unless told
    not to (DefaultLogixNG.execute), so the masts are not held at Stop by UNKNOWN blocks.
    TablesBuildError when the template lacks a LogixNG section or holds these names."""
    secs = {key: next((s for s in tables.elements(root) if section_key(s) == key), None)
            for key in (LOGIXNGS, CONDITIONALNGS, DIGITAL_ACTIONS)}
    found = {k: v for k, v in secs.items() if v is not None}
    gone = [k[0] for k in secs if k not in found]
    if gone:
        raise TablesBuildError(f"the template has no {', '.join(gone)} section for the startup LogixNG")
    if any(level_devices.CLEAR_PREFIX.match(tables.system_name(e) or "") for v in found.values()
           for e in tables.elements(v)):
        raise TablesBuildError("the template holds the startup LogixNG's names (hartlib.level_devices CLEAR_*); "
                               "the device master's start column makes it")
    logixngs, conditionals, digital = found[LOGIXNGS], found[CONDITIONALNGS], found[DIGITAL_ACTIONS]
    lx = ET.Element("LogixNG", {"enabled": "yes", "inline": "no"})
    _sub(lx, "systemName", level_devices.CLEAR_LOGIXNG)
    _sub(lx, "userName", level_devices.CLEAR_USER)
    _sub(_sub(lx, "ConditionalNGs"), "systemName", level_devices.CLEAR_CONDITIONAL)
    last = [e for e in logixngs if e.tag == "LogixNG"]
    _insert(logixngs, [lx], last[-1] if last else None)
    cn = ET.Element("ConditionalNG", {"enabled": "yes"})
    _sub(cn, "systemName", level_devices.CLEAR_CONDITIONAL)
    _sub(cn, "userName", level_devices.CLEAR_USER)
    _sub(cn, "thread", "0")
    sock = _sub(cn, "Socket")
    _sub(sock, "socketName", "A")
    _sub(sock, "systemName", level_devices.CLEAR_MANY)
    _insert(conditionals, [cn])
    many = ET.Element("DigitalMany", {"class": "jmri.jmrit.logixng.actions.configurexml.DigitalManyXml"})
    _sub(many, "systemName", level_devices.CLEAR_MANY)
    acts = _sub(many, "Actions")
    for i, a in enumerate(actions, 1):
        s = _sub(acts, "Socket")
        _sub(s, "socketName", f"A{i}")
        _sub(s, "systemName", tables.system_name(a))
    male_socket(many)
    _insert(digital, [many] + list(actions))


def _fill(sec: ET.Element, beans: list[ET.Element], full_pass: list[ET.Element] | None) -> None:
    """Put `beans` into `sec` after its settings and with its own beans, all in JMRI order; for the blocks, the
    names-only pass of every block, then the full pass (`full_pass`), as JMRI writes them."""
    own = [el for el in tables.elements(sec) if tables.system_name(el)]
    settings = [el for el in tables.elements(sec) if not tables.system_name(el)]
    order = functools.cmp_to_key(_alphanum)
    first = sorted(own + beans, key=lambda e: order(tables.system_name(e)))
    second = sorted(full_pass or [], key=lambda e: order(tables.system_name(e)))
    for el in list(sec):
        sec.remove(el)
    for el in settings + first + second:
        sec.append(el)


def finish(root: ET.Element) -> None:
    """Indent `root` as JMRI (JDOM) writes it: two spaces a level, one element a line."""
    ET.indent(root, space="  ")


def check_names(root: ET.Element) -> None:
    """TablesBuildError when two beans of one kind (turnouts, sensors, heads, masts, blocks' full pass, layout
    blocks, memories) share a system or user name: JMRI would load only one of them."""
    kinds = {"turnout": tables.turnouts(root), "sensor": tables.sensors(root), "head": tables.signal_heads(root),
             "mast": tables.masts(root), "block": tables.blocks(root), "layout block": tables.layout_blocks(root),
             "memory": tables.section(root, "memories", "memory")}
    bad = []
    for kind, els in kinds.items():
        for getter in (tables.system_name, tables.user_name):
            seen: dict[str, int] = {}
            for el in els:
                n = getter(el)
                if n:
                    seen[n] = seen.get(n, 0) + 1
            bad += [f"{kind} {n!r} x{k}" for n, k in seen.items() if k > 1]
    if bad:
        raise TablesBuildError("names given twice: " + ", ".join(sorted(bad)[:10]))


# ---------------------------------------------------------------- discovered Signal Mast Logic

DISCOVERED_ROOT = "discovered-sml"
DISCOVERED_PROLOG = b'<?xml version="1.0" encoding="UTF-8"?>\n'


def discovered_from_store(store: ET.Element) -> ET.Element:
    """The discovered document of a discovery Store's root: its <signalmastlogic> elements in the order stored, and a
    <mastproperties mast="user name"> holding each mast's <properties> (discovery sets intermediateSignal).
    TablesBuildError when the Store holds no Signal Mast Logic or a logic with no source."""
    logics = tables.mast_logics(store)
    if not logics:
        raise TablesBuildError("the Store holds no Signal Mast Logic: discovery found nothing, or this is not its Store")
    out = ET.Element(DISCOVERED_ROOT)
    for m in tables.masts(store):
        props = m.find("properties")
        if props is not None:
            box = _sub(out, "mastproperties", mast=tables.user_name(m) or tables.system_name(m))
            box.append(copy.deepcopy(props))
    for logic in logics:
        if not logic.get("source"):
            raise TablesBuildError("a stored <signalmastlogic> has no source attribute")
        out.append(copy.deepcopy(logic))
    ET.indent(out, space="  ")
    return out


def write_discovered(doc: ET.Element, path: Path = DISCOVERED) -> bool:
    """Write the discovered document (read_discovered reads it back); True when the bytes changed."""
    read_discovered_root(doc, paths.rel(path))       # never write what cannot be read back
    return tables.Tables(root=doc, path=path, prolog=DISCOVERED_PROLOG, epilog=b"\n").save(path)


def read_discovered(path: Path = DISCOVERED) -> tuple[list[ET.Element], dict[str, ET.Element]]:
    """([<signalmastlogic>, ...], {mast user name: <properties>}) of the discovered file."""
    try:
        root = tables.read(path)
    except OSError as exc:
        raise TablesBuildError(f"{paths.rel(path)}: cannot read it ({exc.strerror}); run "
                               "jmri/layouts/hart/scripts/run_sml_discover.sh") from exc
    except ET.ParseError as exc:
        raise TablesBuildError(f"{paths.rel(path)}: not XML ({exc})") from exc
    return read_discovered_root(root, paths.rel(path))


def read_discovered_root(root: ET.Element, where: str) -> tuple[list[ET.Element], dict[str, ET.Element]]:
    if root.tag != DISCOVERED_ROOT:
        raise TablesBuildError(f"{where}: the root is <{root.tag}>, not <{DISCOVERED_ROOT}>")
    logics, props, bad = [], {}, []
    sources = set()
    for el in tables.elements(root):
        if el.tag == "signalmastlogic":
            src = el.get("source") or ""
            if not src or src in sources:
                bad.append(f"a logic with source {src!r} (empty or given twice)")
            sources.add(src)
            logics.append(el)
        elif el.tag == "mastproperties":
            kids = list(tables.elements(el))
            mast = el.get("mast") or ""
            if not mast or mast in props or len(kids) != 1 or kids[0].tag != "properties":
                bad.append(f"mastproperties {mast!r}: needs a mast, given once, and exactly one <properties>")
                continue
            props[mast] = kids[0]
        else:
            bad.append(f"<{el.tag}> is neither signalmastlogic nor mastproperties")
    if bad:
        raise TablesBuildError(f"{where}: " + "; ".join(bad))
    return logics, props


def merge_discovered(root: ET.Element, logics: list[ET.Element], props: Mapping[str, ET.Element]) -> None:
    """Put the discovered logic into `root`'s <signalmastlogics> after its settings, and each mast's properties into
    that mast before <unlit>. TablesBuildError when a logic or a property names a mast the tables do not hold (the
    masts changed since discovery ran: run it again), or the tables hold logic already."""
    box = root.find("signalmastlogics")
    if box is None or tables.mast_logics(root):
        raise TablesBuildError("the tables have no <signalmastlogics>, or hold logic already")
    masts = {n: m for m in tables.masts(root) for n in (tables.user_name(m), tables.system_name(m)) if n}
    named = sorted({logic.get("source") or "" for logic in logics} |
                   {d.get("destination") or "" for logic in logics for d in logic.findall("destinationMast")})
    gone = [n for n in named if n not in masts] + [m for m in props if m not in masts]
    if gone:
        raise TablesBuildError(f"{paths.rel(DISCOVERED)} names masts the tables do not hold ({', '.join(gone[:8])}): "
                               "run jmri/layouts/hart/scripts/run_sml_discover.sh again")
    for logic in logics:
        box.append(copy.deepcopy(logic))
    for mast, p in props.items():
        el = masts[mast]
        if el.find("properties") is not None:
            raise TablesBuildError(f"mast {mast!r} has properties already")
        unlit = el.find("unlit")
        el.insert(list(el).index(unlit) if unlit is not None else len(el), copy.deepcopy(p))


def missing_logic(root: ET.Element) -> list[str]:
    """The masts of `root` without the discovered logic the rule expects: a head mast (<signalmast>) that is no
    logic's source, or a virtual mast (a buffer-stop destination) that no logic names. Stock discovery gives every
    one of them logic (data/schematic/discovered_sml.xml), so a gap means a mast added or renamed since
    discovery ran."""
    sources = {logic.get("source") for logic in tables.mast_logics(root)}
    named = sources | {d.get("destination") for logic in tables.mast_logics(root)
                       for d in logic.findall("destinationMast")}
    out = []
    for m in tables.masts(root):
        user = tables.user_name(m) or tables.system_name(m)
        if (m.tag == "signalmast" and user not in sources) or (m.tag != "signalmast" and user not in named):
            out.append(user)
    return out


# ---------------------------------------------------------------- Digicon boot rule

def digicon_masts(root: ET.Element, wiring: Path = paths.WIRING) -> set[str]:
    """The masts signal_coordinator.py takes over: with a wired head in wiring.csv (hartlib.wiring.digicon_rows) and
    standing on wired LCOS heads (IH and digits) in `root`. A mast wiring.csv names that is on internal heads is never
    taken over."""
    from . import wiring as wiring_source     # here, not at the top: wiring imports railroad_facts
    from .railroad_facts import FactsError
    try:
        planned = {r["mast_user_name"] for r in wiring_source.digicon_rows(wiring)}
    except FactsError as exc:
        raise TablesBuildError(str(exc)) from exc
    wired = {tables.user_name(m) for m in tables.masts(root) if _LCOS_HEAD.search(tables.system_name(m))}
    return planned & wired


def disable_digicon(root: ET.Element, masts: set[str]) -> tuple[int, int]:
    """Set <enabled>no</enabled> on every destination of the logic whose source is one of `masts`, so they boot
    disabled until signal_coordinator.py takes control. (flipped, already disabled)."""
    flipped = already = 0
    for logic in tables.mast_logics(root):
        if logic.get("source") not in masts:
            continue
        for dest in logic.findall("destinationMast"):
            en = dest.find("enabled")
            if en is None:
                raise TablesBuildError(f"logic {logic.get('source')} -> {dest.get('destination')} has no <enabled>")
            if en.text == "no":
                already += 1
            else:
                en.text = "no"
                flipped += 1
    return flipped, already


def enabled_digicon(root: ET.Element, masts: set[str]) -> list[tuple[str, str]]:
    """(source, destination) of each Digicon destination still enabled."""
    return [(logic.get("source") or "", d.get("destination") or "") for logic in tables.mast_logics(root)
            if logic.get("source") in masts for d in logic.findall("destinationMast")
            if (d.findtext("enabled") or "") != "no"]


# ---------------------------------------------------------------- the PanelPro round trip

def roundtrip_differences(store: bytes, generated: bytes, context: int = 40) -> list[str]:
    """[] when a PanelPro Store of the generated tables and the generated tables are the same bytes once both are
    normalised (normalise_store); else the first `context` lines of a unified diff (generated against Store).
    ADR-029 gate 2."""
    sides = []
    for data in (generated, store):
        doc = tables.loads(data)
        normalise_store(doc.root)
        sides.append(doc.tobytes())
    want, got = sides
    if got == want:
        return []
    diff = difflib.unified_diff(want.decode("utf-8").splitlines(), got.decode("utf-8").splitlines(),
                                "generated", "store (normalised)", lineterm="", n=1)
    return [line for _i, line in zip(range(context), diff)]


def without_panels(data: bytes) -> bytes:
    """Tables bytes with every Layout Editor panel taken out: the round trip reports the beans and the panel apart."""
    doc = tables.loads(data)
    for le in tables.layout_editors(doc.root):
        tables.remove_child(doc.root, le)
    finish(doc.root)
    return doc.tobytes()


def read_path_counts(path: Path) -> dict[str, tuple[str, int]]:
    """{block system name: (user name, path count)} of the round trip's block path file."""
    out = {}
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3 or not parts[2].isdigit():
                raise TablesBuildError(f"{path}: line {n} is not system name, user name, path count")
            out[parts[0]] = (parts[1], int(parts[2]))
    return out


def roundtrip_report(store: Path, counts: Path, generated: Path) -> tuple[bool, list[str]]:
    """(passed, lines) of a PanelPro round trip: the normalised Store against the generated file, and the block
    paths JMRI derived for the blocks of the device master (every staging block must have at least one)."""
    lines, ok = [], True
    try:
        diff = roundtrip_differences(store.read_bytes(), generated.read_bytes())
        paths_of = read_path_counts(counts)
    except OSError as exc:
        return False, [f"cannot read {exc.filename}: {exc.strerror}"]
    staging = [r.jmri_name for r in devices.load()
               if r.level_cell == railroad.STAGING_LEVEL and r.layer == "block" and r.assignment != "none"
               and not r.part_of]
    none = [b for b in staging if paths_of.get(b, ("", 0))[1] == 0]
    total = sum(n for _u, n in paths_of.values())
    lines.append(f"block paths JMRI derived: {total} on {len(paths_of)} blocks "
                 f"({sum(paths_of.get(b, ('', 0))[1] for b in staging)} on the {len(staging)} staging blocks)")
    if none:
        ok = False
        lines.append(f"FAIL: staging blocks with no derived path: {', '.join(none)}")
    if diff:
        ok = False
        lines.append("FAIL: the normalised Store differs from the generated tables.xml:")
        rest = roundtrip_differences(without_panels(store.read_bytes()), without_panels(generated.read_bytes()))
        lines.append("  without the Layout Editor panels: " + ("identical" if not rest else "they differ too"))
        lines += [f"  {line}" for line in diff]
    else:
        lines.append("ok: the Store and the generated tables.xml are the same bytes once both are normalised "
                     "(normalise_store)")
    lines.append("PASS: the PanelPro round trip gives the generated tables.xml back" if ok
                 else "FAIL: the PanelPro round trip does not give the generated tables.xml back")
    return ok, lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hartlib.tables_build",
                                 description="Compare a PanelPro round trip's Store with the generated tables.xml.")
    ap.add_argument("action", choices=("roundtrip",))
    ap.add_argument("--store", type=Path, required=True, help="the Store PanelPro wrote")
    ap.add_argument("--paths", type=Path, required=True, help="the block path counts the round trip wrote")
    ap.add_argument("--generated", type=Path, default=paths.REPO_TABLES_XML)
    args = ap.parse_args(argv)
    try:
        ok, lines = roundtrip_report(args.store, args.paths, args.generated)
    except (TablesBuildError, devices.DevicesError, ET.ParseError) as exc:
        print(f"tables_build: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
