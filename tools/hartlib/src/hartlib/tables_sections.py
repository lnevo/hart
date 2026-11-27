"""The sections of the generated tables.xml and the order a JMRI 5.16 Store writes their beans in (ADR-029).

SECTIONS lists the manager sections in file order, MASTER_SECTIONS the ones whose beans come from the device master.
jmri_sort puts every section's beans in the order a Store writes them (AlphanumComparator by system name, within each
sort_group), so a load and Store gives the same bytes. TablesBuildError is the error of every tables build module
(tables_build, jmri_bean, startup_logixng, tables_sml, tables_roundtrip).
"""
from __future__ import annotations

import functools
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from typing import Any

from . import tables
from .errors import HartlibError


class TablesBuildError(HartlibError, ValueError):
    """The template, the master rows, the discovered logic or the result cannot make a tables file."""


SectionKey = tuple[str, "str | None"]       # a section's (tag, class): section_key
# master_beans' key: a SectionKey, ("blocks-names",) + BLOCKS (a names-only pass) or START_ACTIONS
BeanKey = tuple["str | None", ...]

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


alphanum_key: Callable[[str], Any] = functools.cmp_to_key(_alphanum)     # a sort key: AlphanumComparator


def jmri_order(names: Iterable[str]) -> list[str]:
    """`names` in the order a JMRI manager keeps system names (AlphanumComparator)."""
    return sorted(names, key=alphanum_key)


def section_key(el: ET.Element) -> SectionKey:
    """A section's (tag, class), as SECTIONS lists them."""
    return el.tag, el.get("class")


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
    for sec in tables.elements(root):
        kids = list(sec)
        groups: dict[str, list[int]] = {}
        for i, el in enumerate(kids):
            if isinstance(el.tag, str) and tables.system_name(el):
                groups.setdefault(sort_group(el), []).append(i)
        if not groups:
            continue
        for slots in groups.values():
            ordered = sorted((kids[i] for i in slots), key=lambda e: alphanum_key(tables.system_name(e)))
            for i, el in zip(slots, ordered):
                kids[i] = el
        for el in list(sec):
            sec.remove(el)
        sec.extend(kids)


def bean_names(root: ET.Element) -> set[str]:
    """Every system and user name of a bean in `root`."""
    return {n for sec in tables.elements(root) for el in tables.elements(sec)
            for n in (tables.system_name(el), tables.user_name(el)) if n}


def sub(el: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    """A child `tag` of `el` with `attrs` and, when given, `text`."""
    child = ET.SubElement(el, tag, attrs)
    if text is not None:
        child.text = text
    return child


def finish(root: ET.Element) -> None:
    """Indent `root` as JMRI (JDOM) writes it: two spaces a level, one element a line."""
    ET.indent(root, space="  ")
