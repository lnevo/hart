#!/usr/bin/env python3
"""Read-only audit of the HART panel contracts across stored XML sources."""

from __future__ import annotations

import argparse
import importlib
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import (devices, level_devices, level_masts, occupancy_bindings, parked, paths,  # noqa: E402
                     levels, railroad_facts, tables, tables_build)

REPO_ROOT = paths.REPO_ROOT
DEFAULT_SOURCES = (("deployment", paths.TABLES_XML),)
MASTS = level_masts.PATH      # masts.csv, every level's masts (build_masts.py)
# the staging level (its field masts), and the main and upper levels (on virtual heads)
STAGING_LEVELS = (int(railroad_facts.STAGING_LEVEL),)
ADDED_LEVELS = tuple(lv for lv in level_masts.LEVELS if lv not in STAGING_LEVELS)
TRAININFO = paths.LAYOUT_DIR / "dispatcher" / "traininfo"
DISPATCHER_START_SCRIPT = "program:jython/DispatcherSystem/Startup.py"
PANEL_NAMES = {"HART", "HART Railroad"}
# Packed MQTT 467–469 are not JMRI beans. Do not create them in tables.xml.
FORBIDDEN_MQTT_SENSORS = ("M2S467", "M2S468", "M2S469")
MQTT_SENSOR_SYSNAME = re.compile(r"^M2S\d+$")
sys.path.insert(0, str(paths.LAYOUT_SCRIPTS))
from lcc_turnout_contract import contract_violations
from nx_contract import EXPECTED_NX_PAIRS, ISNX_SYSTEM, LAYOUT_PANEL, NXTYPE_SML


def station_comments(rows: Iterable[railroad_facts.MasterRow] | None = None) -> dict[str, str]:
    """{block: its JMRI comment} of the Dispatcher stations: the device master's staging block rows marked `stop` (the
    Dispatcher stations are parked with the stations topic since 2026-11-22, so the master marks none and the audit
    holds tables.xml to no block comment marking a stop; the 12 former stations are in docs/parked/UNPARK.md). The master is the one copy of the station list and the comments (the parked scripts' own copies are listed in
    docs/parked/UNPARK.md)."""
    out: dict[str, str] = {}
    for row in devices.load() if rows is None else rows:
        if row.level != levels.STAGING or row.layer != "block" or row.stop != "yes":
            continue
        name, comment = row.user_name, row.jmri_comment
        if not (comment == "stop" or comment.endswith("; stop")):
            raise devices.DevicesError(f"station {name!r} is marked stop in the device master but its comment "
                                       f"{comment!r} does not end in 'stop'")
        comment = tables_build.occupancy_first(comment)       # as the tables build writes it: detector first
        if out.setdefault(name, comment) != comment:
            raise devices.DevicesError(f"station {name!r} has two comments in the device master: "
                                       f"{out[name]!r} and {comment!r}")
    return out


def text(element: ET.Element | None, child: str) -> str:
    if element is None:
        return ""
    value = element.findtext(child)
    return value.strip() if value else ""


def attr_or_child(element: ET.Element, name: str) -> str:
    return (element.get(name) or text(element, name)).strip()


def sensor_key(block_name: str) -> str:
    return block_name.replace(" ", "_")


def occupancy_binding_map() -> dict[str, str]:
    """{block name: occupancy sensor} of the blocks the CATS desks bind (hartlib.occupancy_bindings: the block rows of
    the device master with a cats_discipline)."""
    return {r["block_user_name"]: r["occupancy_sensor_user_name"] for r in occupancy_bindings.rows()}


@dataclass
class Audit:
    label: str
    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    facts: dict[str, object] = field(default_factory=dict)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


class SetupError(Exception):
    """The audit cannot run (a tool it needs is missing): main() reports it as one line and exits 1."""


def load_staging_masts(path: Path | None = None) -> list[railroad_facts.Mast]:
    """The masts of the base levels (masts.csv's staging rows) the mast rule writes: the audit's expected set."""
    # stops on a file that breaks its rules (hartlib.level_masts.read)
    return railroad_facts.read_masts(MASTS if path is None else path, levels=STAGING_LEVELS)


def slots_index(panel: ET.Element):
    """The plugin's slot index of a Layout Editor panel (the rule the LE build places masts by). SetupError when the
    plugin is missing: the deploy audit needs it, so it fails and does not skip."""
    folder = Path(os.environ.get("SCHEMATIC_PLUGIN")
                  or REPO_ROOT / "external/model-railroad-skills/plugins/schematic-maps")
    if not (folder / "schematic" / "slots.py").is_file():
        raise SetupError(f"schematic-maps plugin not found at {folder}: run git submodule update --init "
                         "external/model-railroad-skills")
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    return importlib.import_module("schematic.slots").Index(panel)


def select_panel(root: ET.Element, audit: Audit) -> ET.Element | None:
    candidates = [
        panel
        for panel in root.iter("LayoutEditor")
        if (panel.get("name") or "").strip() in PANEL_NAMES
    ]
    if len(candidates) != 1:
        names = [(panel.get("name") or "<unnamed>") for panel in root.iter("LayoutEditor")]
        audit.error(
            "expected exactly one LayoutEditor named HART or HART Railroad; "
            f"found {len(candidates)} (all panels: {names or ['<none>']})"
        )
        return None
    audit.facts["panel"] = candidates[0].get("name", "")
    return candidates[0]


def audit_forbidden_mqtt_sensors(root: ET.Element, audit: Audit) -> None:
    found: list[str] = []
    garbage: list[str] = []
    for sensors in root.findall("sensors"):
        cls = sensors.get("class") or ""
        if "MqttSensor" not in cls:
            continue
        for sensor in sensors.findall("sensor"):
            sysn = text(sensor, "systemName") or (sensor.get("systemName") or "").strip()
            if not sysn:
                continue
            if sysn in FORBIDDEN_MQTT_SENSORS:
                found.append(sysn)
            elif not MQTT_SENSOR_SYSNAME.fullmatch(sysn):
                garbage.append(sysn)
    if found:
        audit.error(
            "do not add MQTT sensors "
            + ", ".join(FORBIDDEN_MQTT_SENSORS)
            + f"; found {sorted(set(found))}"
        )
    if garbage:
        audit.error(
            "MQTT sensor systemNames must be M2S plus digits "
            "(not M2SBlock 1-1); "
            f"found {sorted(set(garbage))}"
        )


def dispatcher_virtuals(expected: set[str], devices_csv: Path = devices.MASTER) -> set[str]:
    """The expected masts that are hidden virtual masts for Dispatcher Stage 1, not field
    masts: staging's hidden masts in the device master (role hidden, a virtual signal mast IF$vsm:...($10nn))."""
    virtual = {
        row.user_name for row in devices.load(devices_csv)
        if row.level == levels.STAGING and row.layer == "mast" and row.role == "hidden"
    }
    return expected & virtual


# The main and upper levels' masts, on virtual heads named from their user names (IH:HART:C3:108R_Top)
# (hartlib.level_masts; tools/schematic/build_masts.py): counted apart from the staging field masts.


def split_protects(value: str) -> list[str]:
    """The protected blocks of a mast file's `protects` column (";" separated, as read_masts reads it)."""
    return [b for b in (value or "").split(";") if b]


def draws_levels(panel: ET.Element | None) -> bool:
    """Whether a panel draws the main and upper levels: a turnout of it holds an OS block a main or upper mast
    protects (masts.csv's main and upper rows)."""
    if panel is None:
        return False
    protects = {b for r in level_masts.read(levels=ADDED_LEVELS) for b in split_protects(r["protects"])}   # a hidden mast protects none
    return any(t.get(a) in protects for t in panel.iter("layoutturnout")
               for a in ("blockname", "blockbname", "blockcname", "blockdname"))


def audit_masts(root: ET.Element, staging: list[railroad_facts.Mast], audit: Audit, *,
                levels: bool = False, devices_csv: Path = devices.MASTER) -> None:
    """The signal mast table: the staging field masts exactly (masts.csv's staging rows, those not virtual), the Dispatcher virtuals, no CATS runtime virtuals;
    and the main and upper masts on virtual heads, every main and upper row of masts.csv when the panel draws those
    levels (`levels`), else none but its own."""
    masts = root.find("signalmasts")
    names: set[str] = set()
    level: set[str] = set()
    virtual_names: set[str] = set()
    cats_virtual: list[str] = []
    if masts is not None:
        for mast in list(masts):
            name = text(mast, "userName")
            system_name = text(mast, "systemName")
            normalized = (system_name + " " + name).upper()
            if "IF$VSM:CATS" in normalized or "CATS1" in normalized or "CATS2" in normalized:
                cats_virtual.append(f"{name or '<unnamed>'} [{system_name or '<no system name>'}]")
            if level_masts.is_level_virtual(system_name):
                level.add(name)             # a main or upper virtual destination mast
                continue
            if mast.tag == "virtualsignalmast" or (system_name or "").startswith(
                "IF$vsm:"
            ):
                if name:
                    virtual_names.add(name)
                continue
            if level_masts.is_level_mast(system_name):
                level.add(name)             # a main or upper mast on virtual heads
                continue
            if name:
                names.add(name)
    if level or levels:
        want = level_masts.names(levels=ADDED_LEVELS)
        if level != want:
            audit.error(f"main and upper masts on virtual heads differ from {level_masts.PATH.name}: missing="
                        f"{sorted(want - level) or 'none'}, extra={sorted(level - want) or 'none'}")
    audit.facts["level_masts"] = len(level)
    expected = {m.mast for m in staging}
    virtuals = {m.mast for m in staging if m.system_name.startswith("IF$vsm:")}     # masts.csv's own word
    in_devices = dispatcher_virtuals(expected, devices_csv)
    if in_devices != virtuals:
        audit.error(f"virtual staging masts differ between {MASTS.name} and the device master: only in "
                    f"{MASTS.name}={sorted(virtuals - in_devices) or 'none'}, only in "
                    f"the device master={sorted(in_devices - virtuals) or 'none'}")
    field_expected = expected - virtuals
    missing = sorted(field_expected - names)
    extra = sorted(names - field_expected)
    if missing or extra or len(names) != len(field_expected):
        audit.error(
            f"signal mast names are not the exact expected {len(field_expected)}; "
            f"missing={missing or 'none'}, extra={extra or 'none'}, count={len(names)}"
        )
    missing_virtuals = sorted(virtuals - virtual_names)
    if missing_virtuals:
        audit.error(f"missing dispatcher virtual masts: {missing_virtuals}")
    if cats_virtual:
        audit.error(f"CATS runtime virtual masts stored in file: {cats_virtual}")
    audit.facts["masts"] = tuple(sorted(names))
    audit.facts["cats_virtual"] = tuple(sorted(cats_virtual))


def audit_bindings(panel: ET.Element | None, staging: list[railroad_facts.Mast], audit: Audit, *,
                   levels: bool = False) -> None:
    """Every staging mast (masts.csv), and every main and upper mast (the file's other rows) when the panel
    draws those levels, is bound in exactly one slot, and that slot resolves (the plugin's slot index, the rule the LE
    build places masts by) to the mast's facing block and protected blocks. A mast bound twice, or in a slot facing
    another block, is an error; so is a bound mast no file names, or a turnout or anchor ident used twice (the
    index would keep only one of them). `levels`: the panel draws the main and upper levels."""
    if panel is None:
        audit.facts["bindings"] = ()
        return
    want = {m.mast: (m.facing, sorted(m.protects)) for m in staging}
    if levels:
        want |= {r["mast"]: (r["facing"], split_protects(r["protects"])) for r in level_masts.read(levels=ADDED_LEVELS)}
    idents = Counter((el.tag, el.get("ident")) for tag in ("layoutturnout", "positionablepoint")
                     for el in panel.iter(tag))
    for (tag, ident), n in sorted(idents.items(), key=str):
        if n > 1:
            audit.error(f"{tag} ident {ident} is used {n} times in the selected panel: its masts cannot be "
                        "told apart")
    placed: dict[str, list[dict]] = {}
    for m in slots_index(panel).masts():
        placed.setdefault(m["mast"], []).append(m)
    for name, (facing, protects) in sorted(want.items()):
        found = placed.get(name, [])
        if len(found) != 1:
            audit.error(f"mast {name} expected bound once in the selected panel, found {len(found)}")
            continue
        m = found[0]
        if (m["facing"], sorted(m["protects"])) != (facing, protects):
            audit.error(f"mast {name} in {m['kind']} {m['ident']} slot {m['slot']} faces {m['facing']} and protects "
                        f"{sorted(m['protects'])}, not {facing} into {protects}")
    unnamed = sorted(set(placed) - set(want))
    if unnamed:
        audit.error(f"masts bound in the selected panel that no mast file names: {unnamed}")
    audit.facts["bindings"] = tuple(sorted((m["kind"], m["ident"], m["slot"], m["mast"])
                                           for ms in placed.values() for m in ms))


# What apply_le_sml_facing.py (retired 2026-11-20, a no-op on the generated panel) used to ensure: Layout Editor
# continuingSense is the JMRI constant (CLOSED=2, THROWN=4, UNKNOWN=1), and "1" draws both legs and ignores the
# table's Closed/Thrown. Closed is the continuing (through) leg for the Princess turnouts 114/115 and for the
# crossovers 111/113/117 (MQTT CLOSED = through mains).
CONTINUING_CLOSED = ("TOL29", "TOR36", "TO111", "TO113", "TO117")      # 115, 114, 111, 113, 117
AAR_2_HEAD = "IF$shsm:AAR-1946:SL-2-high-abs"
AAR_2_HEAD_DISABLED = ("Clear Alt", "Advance Approach Medium", "Approach Medium", "Advance Approach", "Medium Clear",
                       "Medium Approach", "Restricting")


def audit_generated_settings(root: ET.Element, audit: Audit) -> None:
    """The settings the facing script used to write and nothing now guards: continuing="2" on the Princess turnouts,
    Layout Block advanced routing on (SML Discover needs it), and the disabled aspects of AAR 2-head masts."""
    for turnout in root.iter("layoutturnout"):
        if turnout.get("ident") in CONTINUING_CLOSED and turnout.get("continuing") != "2":
            audit.error(f"layoutturnout {turnout.get('ident')} has continuing={turnout.get('continuing')!r}, not "
                        "'2' (CLOSED = through; '1' is UNKNOWN and draws both legs)")
    blocks = next(root.iter("layoutblocks"), None)
    if blocks is None:
        audit.error("no layoutblocks element (SML Discover needs advanced routing on)")
    elif blocks.get("blockrouting") != "yes":
        audit.error(f'layoutblocks blockrouting is {blocks.get("blockrouting")!r}, not "yes" (SML Discover needs '
                    "advanced routing)")
    for mast in root.iter("signalmast"):
        name = text(mast, "systemName")
        if name.startswith(AAR_2_HEAD):
            off = {a.text for a in mast.iter("disabledAspect")}
            if missing := [a for a in AAR_2_HEAD_DISABLED if a not in off]:
                audit.error(f"AAR 2-head mast {name} does not disable aspects {missing}")


def audit_parked_nx(root: ET.Element, problem) -> None:
    """Entry/Exit parked (hartlib.parked.PARKED): no NX sensor, pair or slot binding in the tables (the parked file
    holds them; parked.check)."""
    sensors = sorted(text(s, "systemName") for s in root.iter("sensor") if text(s, "systemName").startswith("ISNX:"))
    pairs = root.findall("./entryexitpairs")
    slots = [f"{el.get('ident')} {tag}" for el in root.iter() for tag in parked.SLOT_TAGS
             if text(el, tag).startswith("NX ")]
    slots += [f"{el.get('ident')} {a}" for el in root.iter() for a in parked.SLOT_ATTRS
              if (el.get(a) or "").startswith("NX ")]
    if sensors or pairs or slots:
        problem(f"Entry/Exit is parked, but the tables hold ISNX sensors {sensors[:4]}, {len(pairs)} entryexitpairs "
                f"and NX slot bindings {slots[:4]}")


def audit_nx(root: ET.Element, audit: Audit, *, required: bool) -> None:
    problem = audit.error if required else audit.warn
    if "nx" in parked.parked_in(root):
        audit_parked_nx(root, problem)
        audit.facts["nx_pairs"] = ()
        audit.facts["isnx"] = ()
        return
    sensors: dict[str, str] = {}
    for sensor in root.iter("sensor"):
        system_name = text(sensor, "systemName")
        if system_name.startswith("ISNX:"):
            sensors[system_name] = text(sensor, "userName")
    expected_user = {sysn: f"NX {mast}" for mast, sysn in ISNX_SYSTEM.items()}
    if set(sensors) != set(expected_user):
        missing = sorted(set(expected_user) - set(sensors))
        extra = sorted(set(sensors) - set(expected_user))
        problem(
            f"ISNX sensors expected {len(expected_user)} frozen CTC ids; "
            f"missing={missing[:8]} extra={extra[:8]}"
        )
    for sysn, user in expected_user.items():
        actual = sensors.get(sysn)
        if actual and actual != user:
            problem(f"{sysn} userName expected {user!r}, found {actual!r}")
    panel_names: list[str] = []
    pairs: list[tuple[str, str, str]] = []
    for block in root.findall("./entryexitpairs"):
        for panel in block.findall("layoutPanel"):
            panel_names.append(panel.get("name") or "")
            for source in panel.findall("source"):
                src = source.get("item") or ""
                for dest in source.findall("destination"):
                    pairs.append(
                        (src, dest.get("item") or "", dest.get("nxType") or "")
                    )
    if LAYOUT_PANEL not in panel_names:
        problem(f"Entry/Exit layoutPanel expected {LAYOUT_PANEL!r}, found {panel_names}")
    if len(pairs) != EXPECTED_NX_PAIRS:
        problem(f"NX pairs expected {EXPECTED_NX_PAIRS}, found {len(pairs)}")
    bad_type = [p for p in pairs if p[2] != NXTYPE_SML]
    if bad_type:
        problem(
            f"NX pairs expected nxType={NXTYPE_SML}; "
            f"found {sorted({p[2] for p in bad_type})}"
        )
    audit_nx_slots(root, problem)
    audit.facts["nx_pairs"] = tuple(sorted(pairs))
    audit.facts["isnx"] = tuple(sorted(sensors.items()))


def audit_nx_slots(root: ET.Element, problem) -> None:
    """Each NX sensor sits in the slot of its own mast. A sensor left behind when its mast moves is not at a
    block boundary, and Discover walks past the mast into false pairs (NX Mast 8RA on TO117 A, 2026-11-15)."""
    def check(where: str, sensor: str | None, mast: str | None) -> None:
        if sensor and sensor.startswith("NX ") and sensor != f"NX {mast}":
            problem(f"{sensor} is on {where}, whose mast is {mast or 'none'}; bind it in the slot of {sensor[3:]}")
    for panel in root.iter("LayoutEditor"):
        if panel.get("name") != LAYOUT_PANEL:
            continue
        for turnout in panel.iter("layoutturnout"):
            for leg in "ABCD":
                check(f"{turnout.get('ident')} {leg}", text(turnout, f"sensor{leg}") or None,
                      text(turnout, f"signal{leg}Mast") or None)
        for point in panel.iter("positionablepoint"):
            for bound in ("east", "west"):
                check(f"{point.get('ident')} {bound}bound", point.get(f"{bound}boundsensor"),
                      point.get(f"{bound}boundsignalmast"))


# What stock Discover and Dispatcher System Stage 1 store, per panel. The hand-drawn panel: staging only. The generated
# three-level panel (build_layout_le.build, written by build_tables.py): unjoined (2026-11-16 cut-over) staging kept its NX and transits but
# lost the 8 head-on pairs 10RA/10RB/12R/14R -> 22L/26L, and the main and upper control points added 71 SML destinations
# and 98 sections of their own (163 SML, 197 sections). Joined at the helix (the helix-join release, owner 2026-11-17),
# stock SML discovery in a sandbox stored 171: staging gains 10RA/10RB/12R/14R -> 16L and loses 36RB -> 40RB
# (accepted), the 107 Loop and Switch 225 splits give 108LB -> 110LA and drop the false 226RA/226RB -> 224LB/224LA,
# and the helix adds 130LA/130LB -> 38LA/40LA, 38RA -> 136RB and 40RA -> 136RA. Staging from its device map (the
# device-map switch-over, owner 2026-11-17): stock discovery in a sandbox stored 180, every earlier pair kept and 9
# gained, the head-on 10RA/10RB/12R/14R -> 22L/26L and 36RB -> 40RB. The Dispatcher graph is parked
# (hartlib.parked): no section or transit while it is.
EXPECTED_SML = {False: 100, True: 177}    # True: stock discovery from an empty list on the 2026-11-20 one-mast-process candidate (virtual masts only as destinations on every level: staging 5, main 10, upper 14; Scale running track)
# A generated panel before stock discovery (the three-level build as built, build_layout_le.build) carries the
# Signal Mast Logic of the live tables.xml it was built on (owner, 2026-11-18), less every logic and destination that
# names a main or upper object: exactly the live tables' destinations between staging masts
# (carried_destinations), allowed with a warning that discovery is still to run. Since the device-map switch-over
# that is 104 of the 180 then, but the audit reads it from the live tables, so a later discovery moves it too. A
# generated panel before its Stage 1 with the Dispatcher System unparked still carries the hand-drawn panel's graph
# (EXPECTED_GRAPH[False]): allowed, with the same kind of warning.
EXPECTED_GRAPH = {False: (107, 187), True: (197, 187)}
EXPECTED_TRAININFO = 374


def sml_destinations(root: ET.Element) -> list[tuple[str, str, str, ET.Element]]:
    """(source, destination, useLayoutEditor, <destinationMast>) for every stored SML destination of `root`."""
    out = []
    for logic in root.findall("./signalmastlogics/signalmastlogic"):
        source = attr_or_child(logic, "sourceSignalMast") or logic.get("source", "")
        for destination in logic.findall("destinationMast"):
            target = attr_or_child(destination, "destinationSignalMast") or destination.get("destination", "")
            out.append((source, target, text(destination, "useLayoutEditor").lower(), destination))
    return out


def carried_destinations(destinations: list) -> list[tuple[str, str, str]]:
    """The destinations (sml_destinations) a cut-over build keeps: from a staging mast, naming no main or upper
    object (hartlib.level_devices.is_level_name, by the fields JMRI keeps bean references in)."""
    return [(s, t, u) for s, t, u, el in destinations
            if not level_devices.is_level_name(s) and not tables.names_any(el, (), level_devices.is_level_name)]


def audit_sml(root: ET.Element, audit: Audit, *, required: bool, generated: bool = False,
              live: ET.Element | None = None) -> None:
    """The stored SML destinations against EXPECTED_SML, or, on a generated panel that holds no main or upper one
    yet, against the live tables' carried_destinations (`live`: their root; default this checkout's tables.xml)."""
    found = sml_destinations(root)
    destinations = [(s, t, u) for s, t, u, _el in found]
    auto = sum(use_le == "yes" for _, _, use_le in destinations)
    manual = sum(use_le == "no" for _, _, use_le in destinations)
    unknown = len(destinations) - auto - manual
    # Every destination comes from Discover: the two manual Princess pairs were retired on 2026-11-15.
    want = EXPECTED_SML[generated]
    before = generated and len(carried_destinations(found)) == len(found)       # nothing on main or upper yet
    carried = carried_destinations(sml_destinations(live if live is not None else tables.read(paths.TABLES_XML))) \
        if before else []
    if generated and not found:
        # a cut-over candidate since R9c (ADR-029): the generator's base and the panel, no logic; the released
        # tables.xml takes the discovered logic (tools/schematic/build_tables.py, data/schematic/discovered_sml.xml)
        audit.warn(f"the generated panel's tables hold no Signal Mast Logic: tools/schematic/build_tables.py adds "
                   f"the discovered logic (expect {want})")
    elif before and sorted(destinations) == sorted(carried) and (auto, manual, unknown) == (len(carried), 0, 0):
        audit.warn(f"stored SML destinations are the {len(carried)} between staging masts the build carried from "
                   f"{paths.rel(paths.TABLES_XML)}: run Stage 1 or stock discovery on this generated panel "
                   f"(expect {want})")
    elif (len(destinations), auto, manual, unknown) != (want, want, 0, 0):
        message = (
            f"stored SML destinations expected total={want}, useLayoutEditor=yes={want}, "
            f"manual=0; found total={len(destinations)}, yes={auto}, "
            f"manual={manual}, unspecified/other={unknown}"
        )
        (audit.error if required else audit.warn)(message)
    audit.facts["sml"] = tuple(sorted(destinations))


def block_definitions(root: ET.Element) -> dict[str, list[str]]:
    definitions: dict[str, list[str]] = {}
    for block in root.findall("./blocks/block"):
        name = text(block, "userName")
        if name:
            definitions.setdefault(name, []).append(text(block, "comment"))
    return definitions


def audit_occupancy_bindings(root: ET.Element, audit: Audit, *, required: bool) -> None:
    """The occupancy sensor hartlib.occupancy_bindings gives each block the CATS desks bind must be its JMRI block's
    occupancysensor."""
    problem = audit.error if required else audit.warn
    expected = occupancy_binding_map()
    found: dict[str, set[str]] = {}
    for block in root.findall("./blocks/block"):
        name = text(block, "userName")
        occ = text(block, "occupancysensor")
        if name and occ:
            found.setdefault(name, set()).add(occ)
    mismatches: list[str] = []
    for name, sensor in sorted(expected.items()):
        actual = found.get(name, set())
        if not actual:
            continue
        if actual != {sensor}:
            mismatches.append(f"{name}: master {sensor!r}, xml {sorted(actual)}")
    if mismatches:
        problem(
            "the device master's CATS bindings disagree with block occupancysensor: "
            + "; ".join(mismatches[:8])
            + (" ..." if len(mismatches) > 8 else "")
        )
    audit.facts["occupancy_bindings"] = tuple(sorted(expected.items()))


def audit_turnout_feedback_sensors(root: ET.Element, audit: Audit, *, required: bool) -> None:
    """TWOSENSOR sensor1/sensor2 must resolve to existing sensor userNames.

    Stale names make OpenLCB invent systemNames like MSSwitch 4-1 FB R.
    """
    problem = audit.error if required else audit.warn
    sensor_names = {
        text(sensor, "userName")
        for sensor in root.iter("sensor")
        if text(sensor, "userName")
    }
    missing: list[str] = []
    stale_old: list[str] = []
    for turnout in root.iter("turnout"):
        ident = text(turnout, "userName") or text(turnout, "systemName") or "?"
        for attr in ("sensor1", "sensor2"):
            name = (turnout.get(attr) or "").strip()
            if not name:
                continue
            if re.fullmatch(r"Switch \d+-\d+ FB [NR]", name):
                stale_old.append(f"{ident} {attr}={name}")
            if name not in sensor_names:
                missing.append(f"{ident} {attr}={name}")
    if stale_old:
        problem(
            "turnout feedback still uses pre-convert FB userNames: "
            + "; ".join(stale_old[:8])
            + (" ..." if len(stale_old) > 8 else "")
        )
    elif missing:
        problem(
            "turnout feedback sensors are not sensor userNames: "
            + "; ".join(missing[:8])
            + (" ..." if len(missing) > 8 else "")
        )
    audit.facts["turnout_feedback"] = tuple(sorted(missing or stale_old))


def audit_turnout_systemname_lookups(
    root: ET.Element, audit: Audit, *, required: bool
) -> None:
    """Block-path and route turnout lookups must resolve to a live turnout.

    JMRI may store M2T* or the public userName (Switch 13). Old convert names
    (Switch 116) do not resolve and make OpenLCB invent MTSwitch 116.
    """
    problem = audit.error if required else audit.warn
    real_sys: set[str] = set()
    real_user: set[str] = set()
    for manager in root.findall("turnouts"):
        for turnout in manager.findall("turnout"):
            sn = text(turnout, "systemName") or (turnout.get("systemName") or "").strip()
            un = text(turnout, "userName")
            if sn:
                real_sys.add(sn)
            if un:
                real_user.add(un)
    missing: list[str] = []
    for setting in root.iter("beansetting"):
        turnout = setting.find("turnout")
        if turnout is None:
            continue
        sn = (turnout.get("systemName") or text(turnout, "systemName")).strip()
        if sn and sn not in real_sys and sn not in real_user:
            missing.append(f"path {sn}")
    for route_to in root.iter("routeOutputTurnout"):
        sn = (route_to.get("systemName") or "").strip()
        if sn and sn not in real_sys and sn not in real_user:
            missing.append(f"route {sn}")
    if missing:
        problem(
            "turnout lookups do not resolve to a turnout systemName or userName: "
            + "; ".join(missing[:8])
            + (" ..." if len(missing) > 8 else "")
        )
    audit.facts["turnout_lookups"] = tuple(sorted(missing))


def audit_lcc_mqtt_turnout_aliases(
    root: ET.Element, audit: Audit, *, required: bool
) -> None:
    """Every MQTT DCC turnout has MTT{dcc} named and wired from the device map."""
    problem = audit.error if required else audit.warn
    csv_path = devices.MASTER
    issues = contract_violations(root, csv_path)
    if issues:
        problem(
            "LCC turnout aliases do not match MQTT plants / device map: "
            + "; ".join(issues[:8])
            + (" ..." if len(issues) > 8 else "")
        )
    audit.facts["lcc_turnout_aliases"] = tuple(issues)


def audit_stations(
    root: ET.Element, panel: ET.Element | None, audit: Audit, *, required: bool
) -> None:
    problem = audit.error if required else audit.warn
    try:
        expected_comments = station_comments()
    except devices.DevicesError as e:
        audit.error(f"Dispatcher stations: {e}")
        return
    definitions = block_definitions(root)
    station_names = {
        name
        for name, comments in definitions.items()
        if any(comment == "stop" or comment.endswith("; stop") for comment in comments)
    }
    expected_names = set(expected_comments)
    if station_names != expected_names:
        problem(
            "Dispatcher station block names differ; "
            f"missing={sorted(expected_names - station_names) or 'none'}, "
            f"extra={sorted(station_names - expected_names) or 'none'}"
        )
    station_snapshot: list[tuple[str, str]] = []
    for name, expected_comment in expected_comments.items():
        comments = definitions.get(name, [])
        if expected_comment not in comments:
            problem(
                f"Dispatcher station {name!r}: expected block comment "
                f"{expected_comment!r}, found {comments or ['<missing block>']}"
            )
        station_snapshot.append((name, expected_comment if expected_comment in comments else ""))

    sensors: list[str] = []
    for sensor in root.findall("./sensors/sensor"):
        name = text(sensor, "userName")
        if name.startswith("MoveTo") or name.startswith("MoveInProgress"):
            sensors.append(name)
    sensor_set = set(sensors)
    expected_sensors: set[str] = set()
    expected_icons: set[str] = set()
    # the Dispatcher System parked (hartlib.parked): the station blocks keep their comments, but no MoveTo or
    # move-in-progress sensor or icon is left in the tables
    for name in (() if "dispatcher" in parked.parked_in(root) else expected_comments):
        key = sensor_key(name)
        expected_sensors.update(
            {f"MoveTo{key}_stored", f"MoveInProgress{key}"}
        )
        expected_icons.update(
            {f"MoveTo{key}_stored", f"MoveInProgress{key}"}
        )
    if sensor_set != expected_sensors or len(sensors) != len(expected_sensors):
        problem(
            "Dispatcher station sensor pairs differ; "
            f"missing={sorted(expected_sensors - sensor_set) or 'none'}, "
            f"extra={sorted(sensor_set - expected_sensors) or 'none'}, "
            f"duplicates={sorted(name for name in sensor_set if sensors.count(name) > 1) or 'none'}"
        )

    icon_sensors: list[str] = []
    if panel is not None:
        for icon in panel.iter("sensoricon"):
            name = (icon.get("sensor") or "").strip()
            if name.startswith("MoveTo") or name.startswith("MoveInProgress"):
                icon_sensors.append(name)
    icon_set = set(icon_sensors)
    if icon_set != expected_icons or len(icon_sensors) != len(expected_icons):
        problem(
            "Dispatcher station sensor icons are not exactly one paired icon per station; "
            f"missing={sorted(expected_icons - icon_set) or 'none'}, "
            f"extra={sorted(icon_set - expected_icons) or 'none'}, "
            f"duplicates={sorted(name for name in icon_set if icon_sensors.count(name) > 1) or 'none'}"
        )
    audit.facts["stations"] = tuple(sorted(station_snapshot))
    audit.facts["station_sensors"] = tuple(sorted(sensor_set))
    audit.facts["station_icons"] = tuple(sorted(icon_set))


def audit_block_contents_visible(panel: ET.Element | None, audit: Audit) -> None:
    """Tracks paint at level 3; labels at 0 sit behind the panel background. Black text, in the plugin's Dialog font
    or JMRI's default."""
    if panel is None:
        return
    _, errors = tables.ensure_block_contents_visible(panel, check=True)
    for message in errors:
        audit.error(message)


def audit_placeholders(panel: ET.Element | None, audit: Audit) -> None:
    placeholders: list[str] = []
    redundant_occupancy_icons: list[str] = []
    # Intentional status-lamp captions (not temporary SIG… placeholders).
    _status_lamp_labels = {"LCOS", "Turnouts", "Signals", "Track Power"}
    if panel is not None:
        for label in panel.iter("positionablelabel"):
            value = (label.get("text") or text(label, "text")).strip()
            if value in _status_lamp_labels:
                continue
            if value.upper().startswith("SIG"):
                placeholders.append(value)
        for icon in panel.iter("sensoricon"):
            name = (icon.get("sensor") or "").strip()
            if re.fullmatch(r"Block \d+-\d+", name):
                redundant_occupancy_icons.append(name)
    if placeholders:
        audit.warn(f"stale SIG placeholder labels remain: {sorted(placeholders)}")
    if redundant_occupancy_icons:
        audit.error(
            "sensoricon still bound to retired Block n-n userNames "
            "(JMRI MQTT auto-creates M2SBlock n-n); "
            f"{sorted(redundant_occupancy_icons)}"
        )
    audit.facts["sig_placeholders"] = tuple(sorted(placeholders))
    audit.facts["occupancy_sensor_icons"] = tuple(
        sorted(redundant_occupancy_icons)
    )


def audit_dispatcher_startup(root: ET.Element, audit: Audit) -> None:
    """Run Dispatcher System must load stock Startup.py (no HART overlay); with the Dispatcher System parked
    (hartlib.parked) there is no Run Dispatcher Logix at all."""
    actions: list[str] = []
    found = False
    for conditional in root.findall("./conditionals/conditional"):
        user_name = conditional.get("userName") or text(conditional, "userName")
        if user_name != "Run Dispatcher":
            continue
        found = True
        for action in conditional.findall("conditionalAction"):
            if action.get("type") == "16":
                actions.append((action.get("string") or "").strip())
    if "dispatcher" in parked.parked_in(root):
        if found:
            audit.error("the Dispatcher System is parked, but the Run Dispatcher Logix (IX:DSLX:1C1) is in the tables")
    elif not actions:
        audit.error("missing Logix Run Dispatcher script action (IX:DSLX:1C1)")
    elif DISPATCHER_START_SCRIPT not in actions:
        audit.error(
            "Run Dispatcher Logix must run "
            f"{DISPATCHER_START_SCRIPT}; found {actions}"
        )
    audit.facts["dispatcher_startup_script"] = tuple(actions)


def expected_bundle(parked_features=None, band_panels: bool = True) -> tuple[int, int, int]:
    """(ctcdata, Panel Editor panels, Layout Editor panels) the deployment tables hold: the USS CTC machine's data and
    panel, the main panel, its band panels (tables.BAND_PANEL_NAMES, 2026-11-22; `band_panels` False for the Layout
    Editor build alone, before build_tables.py adds them) and the Dispatcher System's, less those parked
    (hartlib.parked)."""
    parked_features = parked.PARKED if parked_features is None else parked_features
    uss = 0 if "uss" in parked_features else 1
    bands = len(tables.BAND_PANEL_NAMES) if band_panels else 0
    return uss, uss, 1 + bands + (0 if "dispatcher" in parked_features else 1)


def band_panels_in(root: ET.Element) -> bool:
    """Whether the tables hold the band panels: all of them (True) or none (False, the Layout Editor build before
    build_tables.py adds them); ValueError on some but not all, naming the missing ones."""
    names = {(p.get("name") or "").strip() for p in tables.layout_editors(root)}
    want = set(tables.BAND_PANEL_NAMES.values())
    if not names & want:
        return False
    if want - names:
        raise ValueError(f"band panels missing: {', '.join(sorted(want - names))} (build_tables.py adds all three)")
    return True


def audit_generated_dispatcher(root: ET.Element, audit: Audit, *, generated: bool = False,
                               band_panels: bool = True) -> None:
    """`band_panels`: the tables must hold the band panels (build_tables.py's output, the deployment); False for the
    Layout Editor build alone, which must hold none."""
    ctc_bundle = (
        len(root.findall("ctcdata")),
        len(root.findall("paneleditor")),
        len(root.findall("LayoutEditor")),
    )
    left_out = parked.parked_in(root)      # the parked features these tables leave out (hartlib.parked)
    try:
        bands = band_panels_in(root)
    except ValueError as exc:
        audit.error(str(exc))
        bands = band_panels
    if bands != band_panels:
        audit.error("the band panels (" + ", ".join(tables.BAND_PANEL_NAMES.values()) + ") are "
                    + ("missing: build_tables.py adds them" if band_panels else "in tables the Layout Editor build "
                       "made alone"))
    want_bundle = expected_bundle(left_out, band_panels)
    if ctc_bundle != want_bundle:
        audit.error(
            "deployment bundle expected ctcdata={}, paneleditor={}, LayoutEditor={}; found {}".format(
                *want_bundle, ctc_bundle)
        )
    sections = len(root.findall("./sections/section"))
    transits = len(root.findall("./transits/transit"))
    want_sections, want_transits = EXPECTED_GRAPH[generated]
    if "dispatcher" in left_out:
        want_sections, want_transits = 0, 0
    if generated and (sections, transits) == EXPECTED_GRAPH[False] and "dispatcher" not in left_out:
        audit.warn(f"Dispatcher graph is the hand-drawn panel's {sections} sections / {transits} transits: run "
                   f"Stage 1 on this generated panel (expect {want_sections} / {want_transits})")
    elif (sections, transits) != (want_sections, want_transits):
        audit.error(
            f"generated Dispatcher graph expected {want_sections} sections / {want_transits} transits, "
            f"found {sections} / {transits}"
        )
    files = sorted(TRAININFO.glob("*.xml"))
    bad_detection: list[str] = []
    for path in files:
        try:
            train_root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            audit.error(f"invalid traininfo {path.name}: {exc}")
            continue
        values = [
            element.get("traindetection")
            for element in train_root.iter()
            if element.get("traindetection")
        ]
        if values != ["TRAINDETECTION_HEADANDTAIL"]:
            bad_detection.append(path.name)
    if len(files) != EXPECTED_TRAININFO:
        audit.error(f"expected {EXPECTED_TRAININFO} generated traininfo files, found {len(files)}")
    if bad_detection:
        audit.error(
            "traininfo not HEAD_AND_TAIL: "
            + ", ".join(bad_detection[:8])
            + (" ..." if len(bad_detection) > 8 else "")
        )
    audit.facts["dispatcher_generated"] = (
        *ctc_bundle,
        sections,
        transits,
        len(files),
    )


def audit_source(
    label: str, path: Path, staging: list[railroad_facts.Mast], *, generated: bool = False, band_panels: bool = True
) -> Audit:
    """`band_panels` False: the tables are the Layout Editor build alone (a test), before build_tables.py adds the
    band panels."""
    audit = Audit(label=label, path=path)
    try:
        root = tables.read(path)
    except (OSError, ET.ParseError, ValueError, TypeError) as exc:
        audit.error(f"cannot parse source: {exc}")
        return audit
    panel = select_panel(root, audit)
    audit_forbidden_mqtt_sensors(root, audit)
    full_config = label != "standalone"
    try:
        is_generated = panel is not None and tables.generated_panel(panel)
    except ValueError as exc:           # two markers: the audit's error, not a traceback
        audit.error(str(exc))
        is_generated = True
    levels = is_generated and draws_levels(panel)
    audit_masts(root, staging, audit, levels=levels)
    audit_bindings(panel, staging, audit, levels=levels)
    audit_generated_settings(root, audit)
    if full_config:
        audit_sml(root, audit, required=True, generated=is_generated)
        audit_nx(root, audit, required=True)
        audit_stations(root, panel, audit, required=True)
        audit_occupancy_bindings(root, audit, required=True)
        audit_turnout_feedback_sensors(root, audit, required=True)
        audit_turnout_systemname_lookups(root, audit, required=True)
        audit_lcc_mqtt_turnout_aliases(root, audit, required=True)
        audit_dispatcher_startup(root, audit)
        if label == "deployment":
            audit_generated_dispatcher(root, audit, generated=is_generated, band_panels=band_panels)
    else:
        # hart_prod.xml is intentionally a standalone monitor artifact, not a
        # complete JMRI configuration. Audit only its visual/topology contract.
        audit.facts["sml"] = ()
        audit.facts["stations"] = ()
        audit.facts["station_sensors"] = ()
        audit.facts["station_icons"] = ()
        audit_occupancy_bindings(root, audit, required=True)
        audit_turnout_feedback_sensors(root, audit, required=True)
        audit_turnout_systemname_lookups(root, audit, required=True)
        audit_lcc_mqtt_turnout_aliases(root, audit, required=True)
    audit_placeholders(panel, audit)
    try:
        marked = tables.generated_panel(panel)
    except ValueError as exc:
        audit.error(str(exc))
        marked = True
    if generated and not marked:
        audit.error("--generated, but the panel has no generated-panel marker (tools/schematic/build_tables.py "
                    "writes it)")
    audit.facts["generated_panel"] = marked
    audit_block_contents_visible(panel, audit)
    return audit


def concise_delta(reference: object, current: object) -> str:
    if isinstance(reference, tuple) and isinstance(current, tuple):
        reference_set = set(reference)
        current_set = set(current)
        removed = sorted(reference_set - current_set)
        added = sorted(current_set - reference_set)
        return f"missing={short_items(removed)}, extra={short_items(added)}"
    return f"expected={reference!r}, found={current!r}"


def short_items(items: list[object], limit: int = 8) -> object:
    if not items:
        return "none"
    if len(items) <= limit:
        return items
    return f"{items[:limit]} ... (+{len(items) - limit} more)"


def report_drift(audits: list[Audit]) -> list[str]:
    if not audits:
        return []
    reference = next((item for item in audits if item.label == "deployment"), audits[0])
    drift: list[str] = []
    full_sections = (
        "masts",
        "bindings",
        "sml",
        "nx_pairs",
        "isnx",
        "stations",
        "station_sensors",
        "station_icons",
        "dispatcher_startup_script",
        "cats_virtual",
        "sig_placeholders",
    )
    visual_sections = ("masts", "bindings", "cats_virtual", "sig_placeholders")
    for audit in audits:
        if audit is reference:
            continue
        sections = visual_sections if audit.label == "standalone" else full_sections
        for section in sections:
            expected = reference.facts.get(section)
            actual = audit.facts.get(section)
            if expected != actual:
                drift.append(
                    f"{audit.label} differs from {reference.label} in {section}: "
                    f"{concise_delta(expected, actual)}"
                )
    return drift


def print_messages(prefix: str, messages: Iterable[str]) -> None:
    for message in messages:
        print(f"  {prefix}: {message}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit HART panel contracts without modifying XML/configuration files."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail when warnings or semantic source drift are present",
    )
    parser.add_argument(
        "--tables",
        type=Path,
        help="audit this tables file as the deployment source instead of the live tables.xml "
        "(a cut-over candidate, say)",
    )
    parser.add_argument(
        "--generated",
        action="store_true",
        help="the panel is generated (tools/schematic/build_tables.py): fail if it has no generated-panel "
        "marker (a marked panel is recognised without this flag)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.generated and not args.tables:
        print("ERROR: --generated is for a generated candidate named by --tables; the live tables.xml is "
              "recognised by its marker")
        return 2
    try:
        staging = load_staging_masts()
    except (OSError, KeyError, ValueError, railroad_facts.FactsError) as exc:
        print(f"ERROR: cannot load the staging masts: {exc}")
        return 1
    sources = (("deployment", args.tables),) if args.tables else DEFAULT_SOURCES
    try:
        audits = [
            audit_source(label, path, staging, generated=args.generated)
            for label, path in sources
        ]
    except SetupError as exc:
        print(f"ERROR: {exc}")
        return 1
    for audit in audits:
        panel = audit.facts.get("panel", "<not selected>")
        print(
            f"{audit.label}: {paths.rel(audit.path)} "
            f"(panel={panel}, errors={len(audit.errors)}, warnings={len(audit.warnings)})"
        )
        print_messages("ERROR", audit.errors)
        print_messages("WARN", audit.warnings)

    drift = report_drift(audits)
    print(f"source drift: {len(drift)} difference(s)")
    print_messages("DRIFT", drift)

    errors = sum(len(audit.errors) for audit in audits)
    warnings = sum(len(audit.warnings) for audit in audits)
    failed = errors > 0 or (args.strict and (warnings > 0 or bool(drift)))
    mode = "strict" if args.strict else "default"
    print(
        f"RESULT: {'FAIL' if failed else 'PASS'} ({mode}; "
        f"hard errors={errors}, warnings={warnings}, drift={len(drift)})"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
