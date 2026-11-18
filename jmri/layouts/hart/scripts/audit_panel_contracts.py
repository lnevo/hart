#!/usr/bin/env python3
"""Read-only audit of the HART panel contracts across stored XML sources."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace as dc_replace
from pathlib import Path
from typing import Iterable

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import level_masts, parked, paths, tables  # noqa: E402

REPO_ROOT = paths.REPO_ROOT
DEFAULT_SOURCES = (("deployment", paths.TABLES_XML),)
BOUNDARIES = paths.LAYOUT_DATA / "le_signal_boundaries.csv"
OCCUPANCY_BINDINGS = paths.CATS_DIR / "data" / "occupancy_bindings.csv"
TRAININFO = paths.LAYOUT_DIR / "dispatcher" / "traininfo"
DISPATCHER_START_SCRIPT = "program:jython/DispatcherSystem/Startup.py"
PANEL_NAMES = {"HART", "HART Railroad"}
# Packed MQTT 467–469 are not JMRI beans. Do not create them in tables.xml.
FORBIDDEN_MQTT_SENSORS = ("M2S467", "M2S468", "M2S469")
MQTT_SENSOR_SYSNAME = re.compile(r"^M2S\d+$")
sys.path.insert(0, str(paths.LAYOUT_SCRIPTS))
from lcc_turnout_contract import contract_violations
from nx_contract import EXPECTED_NX_PAIRS, ISNX_SYSTEM, LAYOUT_PANEL, NXTYPE_SML
from refresh_bean_comments import BLOCK_COMMENTS
from reconcile_dispatcher_stations import STATIONS as DISPATCHER_STATIONS

# The Dispatcher stations come from reconcile_dispatcher_stations.STATIONS.
STATION_COMMENTS = {name: BLOCK_COMMENTS[name] for name in DISPATCHER_STATIONS}

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
    out: dict[str, str] = {}
    with OCCUPANCY_BINDINGS.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("block_user_name") or "").strip()
            sensor = (row.get("occupancy_sensor_user_name") or "").strip()
            if name and sensor:
                out[name] = sensor
    return out


@dataclass(frozen=True)
class Boundary:
    kind: str
    ident: str
    slot: str
    mast: str
    generated_slot: str = ""        # the slot on a generated panel, where it swaps a turnout's legs; "" = slot

    @property
    def binding_name(self) -> str:
        if self.kind == "turnout":
            return f"signal{self.slot.upper()}Mast"
        return f"{self.slot.lower()}boundsignalmast"


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


def load_boundaries(path: Path) -> list[Boundary]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    boundaries = [
        Boundary(
            kind=row["kind"].strip(),
            ident=row["ident"].strip(),
            slot=row["slot"].strip(),
            mast=row["mast_user_name"].strip(),
            generated_slot=(row.get("generated_slot") or "").strip(),
        )
        for row in rows
    ]
    if len(boundaries) != 32 or len({item.mast for item in boundaries}) != 32:
        raise ValueError(f"{path}: expected 32 unique boundary mast names")
    return boundaries


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


def dispatcher_virtuals(expected: set[str], name_map: Path = paths.PUBLIC_NAME_MAP) -> set[str]:
    """The boundary masts that are hidden virtual masts for Dispatcher Stage 1, not field
    masts: those whose name-map hardware is `virtual $10nn` (Mast 8LC, 2R, 36L ...)."""
    with name_map.open(newline="", encoding="utf-8") as f:
        virtual = {
            row["proposed"] for row in csv.DictReader(f)
            if row["layer"] == "mast" and row["current"] == row["proposed"]
            and row["hardware"].startswith("virtual")
        }
    return expected & virtual


# The main and upper levels' masts, on virtual heads named from their user names (IH:HART:C3:108R_Top)
# (hartlib.level_masts; tools/schematic/build_main_upper_masts.py): counted apart from the staging field masts.


def draws_levels(panel: ET.Element | None) -> bool:
    """Whether a panel draws the main and upper levels: a turnout of it holds an OS block a main or upper mast
    protects (main_upper_masts.csv)."""
    if panel is None:
        return False
    protects = {r["protects"] for r in level_masts.read()}
    return any(t.get(a) in protects for t in panel.iter("layoutturnout")
               for a in ("blockname", "blockbname", "blockcname", "blockdname"))


def audit_masts(root: ET.Element, expected: set[str], audit: Audit, *, levels: bool = False) -> None:
    """The signal mast table: the 23 staging field masts exactly, the Dispatcher virtuals, no CATS runtime virtuals;
    and the main and upper masts on virtual heads, every one of main_upper_masts.csv when the panel draws those
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
        want = level_masts.names()
        if level != want:
            audit.error(f"main and upper masts on virtual heads differ from {level_masts.PATH.name}: missing="
                        f"{sorted(want - level) or 'none'}, extra={sorted(level - want) or 'none'}")
    audit.facts["level_masts"] = len(level)
    virtuals = dispatcher_virtuals(expected)
    field_expected = expected - virtuals
    missing = sorted(field_expected - names)
    extra = sorted(names - field_expected)
    if missing or extra or len(names) != 23:
        audit.error(
            f"signal mast names are not the exact expected 23; "
            f"missing={missing or 'none'}, extra={extra or 'none'}, count={len(names)}"
        )
    missing_virtuals = sorted(virtuals - virtual_names)
    if missing_virtuals:
        audit.error(f"missing dispatcher virtual masts: {missing_virtuals}")
    if cats_virtual:
        audit.error(f"CATS runtime virtual masts stored in file: {cats_virtual}")
    audit.facts["masts"] = tuple(sorted(names))
    audit.facts["cats_virtual"] = tuple(sorted(cats_virtual))


def audit_bindings(
    panel: ET.Element | None, boundaries: list[Boundary], audit: Audit, *, generated: bool = False
) -> None:
    """Each boundary mast in its slot; on a generated panel (`generated`) in its generated_slot where it has one."""
    actual: dict[tuple[str, str, str], str] = {}
    if panel is None:
        audit.facts["bindings"] = ()
        return
    by_key: dict[tuple[str, str], list[ET.Element]] = {}
    for element in panel.iter():
        ident = element.get("ident")
        if ident and element.tag in {"layoutturnout", "positionablepoint"}:
            kind = "turnout" if element.tag == "layoutturnout" else "anchor"
            by_key.setdefault((kind, ident), []).append(element)
    for boundary in boundaries:
        if generated and boundary.generated_slot:
            boundary = dc_replace(boundary, slot=boundary.generated_slot)
        elements = by_key.get((boundary.kind, boundary.ident), [])
        if len(elements) != 1:
            audit.error(
                f"boundary {boundary.kind} {boundary.ident} expected once in selected panel, "
                f"found {len(elements)}"
            )
            continue
        value = attr_or_child(elements[0], boundary.binding_name)
        actual[(boundary.kind, boundary.ident, boundary.slot)] = value
        if value != boundary.mast:
            audit.error(
                f"boundary {boundary.kind} {boundary.ident} slot {boundary.slot}: "
                f"expected {boundary.mast!r}, found {value or '<unbound>'!r}"
            )
    audit.facts["bindings"] = tuple(
        sorted((*key, value) for key, value in actual.items())
    )


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
# three-level panel (build_layout_le.py --as-live): unjoined (2026-11-16 cut-over) staging kept its NX and transits but
# lost the 8 head-on pairs 10RA/10RB/12R/14R -> 22L/26L, and the main and upper control points added 71 SML destinations
# and 98 sections of their own (163 SML, 197 sections). Joined at the helix (the helix-join release, owner 2026-11-17),
# stock SML discovery in a sandbox stored 171: staging gains 10RA/10RB/12R/14R -> 16L and loses 36RB -> 40RB
# (accepted), the 107 Loop and Switch 225 splits give 108LB -> 110LA and drop the false 226RA/226RB -> 224LB/224LA,
# and the helix adds 130LA/130LB -> 38LA/40LA, 38RA -> 136RB and 40RA -> 136RA. Staging from its device map (the
# device-map switch-over, owner 2026-11-17): stock discovery in a sandbox stored 180, every earlier pair kept and 9
# gained, the head-on 10RA/10RB/12R/14R -> 22L/26L and 36RB -> 40RB. The Dispatcher graph is parked
# (hartlib.parked): no section or transit while it is.
EXPECTED_SML = {False: 100, True: 180}
EXPECTED_GRAPH = {False: (107, 187), True: (197, 187)}
# A generated panel before its Stage 1 (the cut-over candidate as built) still carries the hand-drawn panel's SML and
# Dispatcher graph: allowed, with a warning that Stage 1 is still to run.
EXPECTED_TRAININFO = 374


def audit_sml(root: ET.Element, audit: Audit, *, required: bool, generated: bool = False) -> None:
    destinations: list[tuple[str, str, str]] = []
    for logic in root.findall("./signalmastlogics/signalmastlogic"):
        source = attr_or_child(logic, "sourceSignalMast") or logic.get("source", "")
        for destination in logic.findall("destinationMast"):
            target = (
                attr_or_child(destination, "destinationSignalMast")
                or destination.get("destination", "")
            )
            use_le = text(destination, "useLayoutEditor").lower()
            destinations.append((source, target, use_le))
    auto = sum(use_le == "yes" for _, _, use_le in destinations)
    manual = sum(use_le == "no" for _, _, use_le in destinations)
    unknown = len(destinations) - auto - manual
    # Every destination comes from Discover: the two manual Princess pairs were retired on 2026-11-15.
    want = EXPECTED_SML[generated]
    carried = EXPECTED_SML[False]
    if generated and (len(destinations), auto, manual, unknown) == (carried, carried, 0, 0):
        audit.warn(f"stored SML destinations are the hand-drawn panel's {carried}: run Stage 1 on this generated "
                   f"panel (expect {want})")
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
    """Plate names in occupancy_bindings.csv must match block occupancysensor."""
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
            mismatches.append(f"{name}: csv {sensor!r}, xml {sorted(actual)}")
    if mismatches:
        problem(
            "occupancy_bindings.csv disagrees with block occupancysensor: "
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
    csv_path = paths.PUBLIC_NAME_MAP
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
    definitions = block_definitions(root)
    station_names = {
        name
        for name, comments in definitions.items()
        if any(comment == "stop" or comment.endswith("; stop") for comment in comments)
    }
    expected_names = set(STATION_COMMENTS)
    if station_names != expected_names:
        problem(
            "Dispatcher station block names differ; "
            f"missing={sorted(expected_names - station_names) or 'none'}, "
            f"extra={sorted(station_names - expected_names) or 'none'}"
        )
    station_snapshot: list[tuple[str, str]] = []
    for name, expected_comment in STATION_COMMENTS.items():
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
    for name in (() if "dispatcher" in parked.parked_in(root) else STATION_COMMENTS):
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


def expected_bundle(parked_features=None) -> tuple[int, int, int]:
    """(ctcdata, Panel Editor panels, Layout Editor panels) the deployment tables hold: the USS CTC machine's data and
    panel, the main panel and the Dispatcher System's, less those parked (hartlib.parked)."""
    parked_features = parked.PARKED if parked_features is None else parked_features
    uss = 0 if "uss" in parked_features else 1
    return uss, uss, 1 if "dispatcher" in parked_features else 2


def audit_generated_dispatcher(root: ET.Element, audit: Audit, *, generated: bool = False) -> None:
    ctc_bundle = (
        len(root.findall("ctcdata")),
        len(root.findall("paneleditor")),
        len(root.findall("LayoutEditor")),
    )
    left_out = parked.parked_in(root)      # the parked features these tables leave out (hartlib.parked)
    want_bundle = expected_bundle(left_out)
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
    label: str, path: Path, boundaries: list[Boundary], expected_masts: set[str], *, generated: bool = False
) -> Audit:
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
    audit_masts(root, expected_masts, audit, levels=is_generated and draws_levels(panel))
    audit_bindings(panel, boundaries, audit, generated=is_generated)
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
            audit_generated_dispatcher(root, audit, generated=is_generated)
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
        audit.error("--generated, but the panel has no generated-panel marker (build_layout_le.py --as-live "
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
        "--boundaries",
        type=Path,
        default=BOUNDARIES,
        help="the mast boundary contract (default: data/le_signal_boundaries.csv)",
    )
    parser.add_argument(
        "--generated",
        action="store_true",
        help="the panel is generated (build_layout_le.py --as-live): fail if it has no generated-panel "
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
        boundaries = load_boundaries(args.boundaries)
    except (OSError, KeyError, ValueError) as exc:
        print(f"ERROR: cannot load boundary contract: {exc}")
        return 1
    expected_masts = {item.mast for item in boundaries}
    sources = (("deployment", args.tables),) if args.tables else DEFAULT_SOURCES
    audits = [
        audit_source(label, path, boundaries, expected_masts, generated=args.generated)
        for label, path in sources
    ]
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
