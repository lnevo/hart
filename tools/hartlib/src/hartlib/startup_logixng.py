"""The startup LogixNG of the generated tables: the LogixNG that sets each virtual detector and turnout when the
tables load (start_logixng), and its actions as PanelPro 5.16 stores them (start_action). The rows that give the
actions are chosen by tables_build.start_actions.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from . import level_devices, tables
from .tables_sections import CONDITIONALNGS, DIGITAL_ACTIONS, LOGIXNGS, TablesBuildError, section_key, sub

START_ACTIONS = ("start-actions",) + DIGITAL_ACTIONS     # master_beans' key for the startup actions (start_actions)
ACTION_CLASS = {"occupancy": ("ActionSensor", "jmri.jmrit.logixng.actions.configurexml.ActionSensorXml"),
                "turnout": ("ActionTurnout", "jmri.jmrit.logixng.actions.configurexml.ActionTurnoutXml")}
MALE_DEBUGGER = "jmri.jmrit.logixng.tools.debugger.configurexml.DebuggerMaleDigitalActionSocketXml"
MALE_ACTION = "jmri.jmrit.logixng.implementation.configurexml.DefaultMaleDigitalActionSocketXml"


def male_socket(el: ET.Element) -> None:
    """The <MaleSocket> PanelPro 5.16 stores under a digital action (as on IQDA:AUTO:0001 in tables.xml)."""
    m = sub(el, "MaleSocket")
    sub(m, "AbstractDebuggerMaleSocket", **{"class": MALE_DEBUGGER})
    a = sub(m, "AbstractMaleSocket", enabled="yes", locked="no", system="no", catchAbortExecution="no",
            **{"class": MALE_ACTION})
    sub(a, "errorHandling", "Default")


def start_action(layer: str, name: str, bean: str, state: str) -> ET.Element:
    """The startup LogixNG's action `name` that sets `bean` (a sensor for layer occupancy, a turnout for layer
    turnout) to `state` (Inactive, Closed or Thrown: hartlib.level_devices.START_ENUM), as PanelPro 5.16 stores it."""
    tag, cls = ACTION_CLASS[layer]
    a = ET.Element(tag, {"class": cls})
    sub(a, "systemName", name)
    nb = sub(a, "namedBean")
    for t, text in (("addressing", "Direct"), ("name", bean), ("listenToMemory", "no")):
        sub(nb, t, text)
    st = sub(a, "state")
    for t, text in (("addressing", "Direct"), ("enum", state), ("listenToMemory", "no")):
        sub(st, t, text)
    male_socket(a)
    return a


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
    sub(lx, "systemName", level_devices.CLEAR_LOGIXNG)
    sub(lx, "userName", level_devices.CLEAR_USER)
    sub(sub(lx, "ConditionalNGs"), "systemName", level_devices.CLEAR_CONDITIONAL)
    last = [e for e in logixngs if e.tag == "LogixNG"]
    _insert(logixngs, [lx], last[-1] if last else None)
    cn = ET.Element("ConditionalNG", {"enabled": "yes"})
    sub(cn, "systemName", level_devices.CLEAR_CONDITIONAL)
    sub(cn, "userName", level_devices.CLEAR_USER)
    sub(cn, "thread", "0")
    sock = sub(cn, "Socket")
    sub(sock, "socketName", "A")
    sub(sock, "systemName", level_devices.CLEAR_MANY)
    _insert(conditionals, [cn])
    many = ET.Element("DigitalMany", {"class": "jmri.jmrit.logixng.actions.configurexml.DigitalManyXml"})
    sub(many, "systemName", level_devices.CLEAR_MANY)
    acts = sub(many, "Actions")
    for i, a in enumerate(actions, 1):
        s = sub(acts, "Socket")
        sub(s, "socketName", f"A{i}")
        sub(s, "systemName", tables.system_name(a))
    male_socket(many)
    _insert(digital, [many] + list(actions))
