"""The parts of the generated tables.xml that come from no drawing: the template, the fixed envelope and the
device master's beans (ADR-029). The other jobs of the tables build are modules of their own: the sections and the
Store's order (tables_sections), the panel rewrites a Store makes (tables_normal), the jmri_bean column (jmri_bean),
the startup LogixNG (startup_logixng), the discovered Signal Mast Logic and the Digicon boot rule (tables_sml) and
the PanelPro round trip (tables_roundtrip).

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
    jmri/layouts/hart/data/schematic/discovered_sml.xml   tables_sml.DISCOVERED: the Signal Mast Logic and the mast
                                                      properties (intermediateSignal) stock discovery wrote
    jmri/layouts/hart/data/wiring.csv                 the Digicon masts (its wired heads), whose logic boots disabled
                                                      (tables_sml.disable_digicon)

The envelope is fixed: PROLOG and EPILOG around the root, jmriversion as the template has it, and none of what a
Store writes each time (ENVELOPE_DROPS: the file history, the "Written by" comment, the clock's time, the memory
values). strip_envelope takes those out of a Store.

Order. Every section's beans, the template's and the master's together, stand in the
order a JMRI 5.16 Store writes them (tables_sections.jmri_sort: by system name, AlphanumComparator), so a load and
Store gives the same bytes after normalise_store. The discovered logic keeps the order discovery wrote.

Every failure is a TablesBuildError naming the file, section or row.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import NamedTuple

from . import block_lengths, devices, level_devices, paths, railroad, tables
from .jmri_bean import kept_beans
from .tables_normal import EPILOG, PROLOG, ROOT_ATTRS, envelope_items
from .startup_logixng import START_ACTIONS, start_action, start_logixng
from .tables_sections import (BLOCKS, HEADS, LAYOUT_BLOCKS, MASTER_SECTIONS, MASTS, SECTIONS, SENSOR_SECTIONS,
                              TURNOUT_SECTIONS, BeanKey, SectionKey, TablesBuildError, alphanum_key, bean_names, finish,
                              section_key, sub)

# Names of the modules split out of this one, still read here by callers that import them from tables_build
# (store_*.py, devices.py, build_tables.py, sync_signals.py and their tests, which other open work changes). New code
# imports them from their own module.
from .jmri_bean import bean_json as bean_json, row_beans as row_beans
from .tables_sections import (CONDITIONALNGS as CONDITIONALNGS, DIGITAL_ACTIONS as DIGITAL_ACTIONS,
                              INTERNAL_SENSORS as INTERNAL_SENSORS, INTERNAL_TURNOUTS as INTERNAL_TURNOUTS,
                              LCC_TURNOUTS as LCC_TURNOUTS, LOGIXNGS as LOGIXNGS, MQTT_SENSORS as MQTT_SENSORS,
                              MQTT_TURNOUTS as MQTT_TURNOUTS, jmri_order as jmri_order, jmri_sort as jmri_sort,
                              sort_group as sort_group)
from .tables_normal import (ENVELOPE_DROPS as ENVELOPE_DROPS, normalise_store as normalise_store,
                            strip_envelope as strip_envelope)
from .tables_roundtrip import roundtrip_differences as roundtrip_differences, roundtrip_report as roundtrip_report
from .tables_sml import (DISCOVERED as DISCOVERED, digicon_masts as digicon_masts, disable_digicon as disable_digicon,
                         discovered_from_store as discovered_from_store, enabled_digicon as enabled_digicon,
                         merge_discovered as merge_discovered, missing_logic as missing_logic,
                         read_discovered as read_discovered, read_discovered_root as read_discovered_root,
                         write_discovered as write_discovered)

TEMPLATE = paths.LAYOUT_DATA / "tables_template.xml"
BLOCK_LENGTHS = paths.LAYOUT_DATA / "block_lengths.csv"
MM_PER_INCH = 25.4

HEAD_CLASS = "jmri.implementation.configurexml.VirtualSignalHeadXml"
MAST_CLASS = "jmri.implementation.configurexml.SignalHeadSignalMastXml"
VIRTUAL_MAST_CLASS = "jmri.implementation.configurexml.VirtualSignalMastXml"
VIRTUAL_HEAD_NOTE = level_devices.VIRTUAL_NOTE  # a staging head on an internal name: no field head drives it
LAYOUT_BLOCK_ATTRS = (("occupiedsense", "2"), ("trackcolor", "gray"), ("occupiedcolor", "red"),
                      ("extracolor", "white"))
HELIX_LEVEL = railroad.STAGING_LEVEL   # the helix blocks' beans are staging's; a main or upper helix detector binds them


GENERATED_NOTE = ("tables.xml is generated (ADR-029): change the device master, the template (data/tables_template.xml) "
                  "or the other sources, then run python3 tools/schematic/build_tables.py")


def refuse_generated(target: Path | str, script: str) -> None:
    """Stop `script` (SystemExit) before it writes the repo's generated tables.xml, by path or through a link; a
    script that edited tables.xml by hand may still write another tables file it is pointed at."""
    if os.path.realpath(target) == os.path.realpath(paths.REPO_TABLES_XML):
        raise SystemExit(f"{script}: not writing {paths.rel(Path(target))}: {GENERATED_NOTE}")


# ---------------------------------------------------------------- the template

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
                               "fixed envelope (hartlib.tables_normal.PROLOG, EPILOG)")
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


# ---------------------------------------------------------------- the master's beans

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


def _route(name: str, table: Iterable[tuple[str, SectionKey]], what: str) -> SectionKey:
    for prefix, key in table:
        if name.startswith(prefix):
            return key
    raise TablesBuildError(f"the device master: {what} {name!r} has no manager section for its prefix "
                           f"({', '.join(p for p, _ in table)})")


def _named(tag: str, attrs: dict, system: str, user: str, comment: str) -> ET.Element:
    el = ET.Element(tag, attrs)
    sub(el, "systemName", system)
    sub(el, "userName", user)
    sub(el, "comment", comment)
    return el

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
    sub(names_only, "systemName", name)
    sub(names_only, "userName", user)
    full = _named("block", {"systemName": name, "length": f"{length * MM_PER_INCH:.1f}", "curve": "0"},
                  name, user, comment)
    sub(full, "permissive", "no")
    lb_attrs = {"systemName": r["layout_block"]}
    if sensor:
        sub(full, "occupancysensor", sensor)
        lb_attrs["occupancysensor"] = sensor
    lb = ET.Element("layoutblock", {**lb_attrs, **dict(LAYOUT_BLOCK_ATTRS)})
    sub(lb, "systemName", r["layout_block"])
    sub(lb, "userName", user)
    return names_only, full, lb


def mast_bean(name: str, user: str, comment: str) -> ET.Element | None:
    """A mast's bean by its system name: a SignalHeadSignalMast (IF$shsm:, unlit not allowed) or a VirtualSignalMast
    (IF$vsm:, unlit allowed); None for any other."""
    if name.startswith("IF$vsm:"):
        el = _named("virtualsignalmast", {"class": VIRTUAL_MAST_CLASS}, name, user, comment)
        sub(el, "unlit", allowed="yes")
    elif name.startswith("IF$shsm:"):
        el = _named("signalmast", {"class": MAST_CLASS}, name, user, comment)
        sub(el, "unlit", allowed="no")
    else:
        return None
    return el


def master_beans(rows: Iterable[Mapping[str, str]], lengths: Mapping[str, float],
                 levels: Iterable[str] | None = None) -> dict[BeanKey, list[ET.Element]]:
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
    where = _Where(by_id, mast_places(rows), _detectors(rows), lengths)
    out: dict[BeanKey, list[ET.Element]] = {}
    bad: list[str] = []
    for r in rows:
        try:
            for key, el in _layer_beans(r, where):
                out.setdefault(key, []).append(el)
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


class _Where(NamedTuple):
    """What master_beans knows of every row of the levels it builds, which a row's beans read (_layer_beans)."""
    by_id: Mapping[str, Mapping[str, Mapping[str, str]]]     # {level: {id: row}}, every row (assignment none too)
    places: Mapping[str, str]                                # mast_places
    detector: Mapping[tuple[str, str], list[str]]            # _detectors
    lengths: Mapping[str, float]                             # {block user name: operating length in inches}


def _detectors(rows: Iterable[Mapping[str, str]]) -> dict[tuple[str, str], list[str]]:
    """{(level, block user name): [detector user name, ...]} of the occupancy rows' blocks columns. A helix detector
    binds staging's helix block, the one block that climbs through the levels (HELIX_LEVEL)."""
    out: dict[tuple[str, str], list[str]] = {}
    for r in rows:
        if r["layer"] == "occupancy":
            level = HELIX_LEVEL if r["role"] == "helix" else r["level"]
            for b in filter(None, (x.strip() for x in r["blocks"].split(";"))):
                out.setdefault((level, b), []).append(r["user_name"])
    return out


def _layer_beans(r: Mapping[str, str], where: _Where) -> list[tuple[BeanKey, ET.Element]]:
    """[(key, bean)] of row `r` (assignment not none) by its layer (LAYER_BEANS): none for an LCC alias that names
    its turnout's bean, a block's names-only pass under ("blocks-names",) + BLOCKS. TablesBuildError naming the row
    on a layer with no bean, a mast name of neither kind, or a block with no length, no layout block or two
    detectors."""
    layer, user, name = r["layer"], r["user_name"], bean_name(r)
    at = f"{layer} {user!r}"
    if layer == "turnout":
        ids = where.by_id.get(r["level"], {})
        if r["role"] == "lcc_alias" and alias_is_turnout(r, ids, at):
            return []
        attrs = turnout_feedback(r, ids, at)
        return [(_route(name, TURNOUT_SECTIONS, at), _named("turnout", attrs, name, user, row_comment(r)))]
    if layer in ("fb", "occupancy", "sensor"):
        return [(_route(name, SENSOR_SECTIONS, at), _named("sensor", {"inverted": "false"}, name, user,
                                                           row_comment(r)))]
    if layer == "head":
        return [(HEADS, _named("signalhead", {"class": HEAD_CLASS}, name, user, row_comment(r, where.places)))]
    if layer == "mast":
        el = mast_bean(name, user, row_comment(r))
        if el is None:
            raise TablesBuildError(f"the device master: {at}: bean name {name!r} is neither a head mast (IF$shsm:) "
                                   "nor a virtual one (IF$vsm:)")
        return [(MASTS, el)]
    if layer != "block":
        raise TablesBuildError(f"the device master: {at}: no bean for layer {layer!r}")
    length = where.lengths.get(user)
    if length is None:
        raise TablesBuildError(f"the device master: {at}: no row in block_lengths.csv")
    if not r["layout_block"]:
        raise TablesBuildError(f"the device master: {at}: no layout_block")
    sensors = where.detector.get((r["level"], r["part_of"] or user), [])       # a part: its block's sensor
    if len(sensors) > 1:
        raise TablesBuildError(f"the device master: {at}: detected by {len(sensors)} occupancy rows "
                               f"({', '.join(sensors)})")
    names_only, full, lb = block_beans(r, name, length, sensors[0] if sensors else None, row_comment(r))
    return [(("blocks-names",) + BLOCKS, names_only), (BLOCKS, full), (LAYOUT_BLOCKS, lb)]


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
    sections: dict[BeanKey, ET.Element] = {section_key(el): el for el in tables.elements(doc.root)}
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


def _fill(sec: ET.Element, beans: list[ET.Element], full_pass: list[ET.Element] | None) -> None:
    """Put `beans` into `sec` after its settings and with its own beans, all in JMRI order; for the blocks, the
    names-only pass of every block, then the full pass (`full_pass`), as JMRI writes them."""
    own = [el for el in tables.elements(sec) if tables.system_name(el)]
    settings = [el for el in tables.elements(sec) if not tables.system_name(el)]
    first = sorted(own + beans, key=lambda e: alphanum_key(tables.system_name(e)))
    second = sorted(full_pass or [], key=lambda e: alphanum_key(tables.system_name(e)))
    for el in list(sec):
        sec.remove(el)
    for el in settings + first + second:
        sec.append(el)


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
