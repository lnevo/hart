#!/usr/bin/env python3
"""Read-only audit of the HART panel contracts across stored XML sources.

This file holds the masts, their slot bindings, the Dispatcher stations and the run (audit_source, main). The
checks of the tables' own settings are in audit_panel_tables.py, those of what Discover and Stage 1 store in
audit_panel_graph.py, and the Audit record they fill in audit_panel_base.py; their names are imported here, so
tests and tools reach every check through this module.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Iterable, Protocol, TypedDict

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, level_masts, levels, parked, paths, railroad_facts, tables, tables_build  # noqa: E402

# Sibling modules in this script's folder (paths.LAYOUT_SCRIPTS), also when another tool loads this file by path.
sys.path.insert(0, str(paths.LAYOUT_SCRIPTS))
from audit_panel_base import SHOWN, Audit, text  # noqa: E402
from audit_panel_graph import (  # noqa: E402,F401 (expected_*, TRAININFO and the SML reads: tests and tools)
    TRAININFO, PanelCountsError, audit_generated_dispatcher, audit_nx, audit_sml, band_panels_in,
    carried_destinations, expected_bundle, expected_graph, expected_sml, expected_traininfo, panel_counts,
    sml_destinations,
)
from audit_panel_tables import (  # noqa: E402,F401 (continuing_closed_idents: tests)
    audit_block_contents_visible, audit_forbidden_mqtt_sensors, audit_generated_settings, audit_lcc_mqtt_turnout_aliases,
    audit_occupancy_bindings, audit_placeholders, audit_turnout_feedback_sensors, audit_turnout_systemname_lookups,
    continuing_closed_idents,
)

REPO_ROOT = paths.REPO_ROOT
DEFAULT_SOURCES = (("deployment", paths.TABLES_XML),)
MASTS = level_masts.PATH      # masts.csv, every level's masts (build_masts.py)
# the staging level (its field masts), and the main and upper levels (on virtual heads)
STAGING_LEVELS = (int(railroad_facts.STAGING_LEVEL),)
ADDED_LEVELS = tuple(lv for lv in level_masts.LEVELS if lv not in STAGING_LEVELS)
DISPATCHER_START_SCRIPT = "program:jython/DispatcherSystem/Startup.py"
PANEL_NAMES = {"HART", "HART Railroad"}


def station_comments(rows: Iterable[railroad_facts.MasterRow] | None = None) -> dict[str, str]:
    """{block: its JMRI comment} of the Dispatcher stations: the device master's staging block rows marked `stop`.
    The master is the one copy of the station list and the comments. While the Dispatcher stations are parked the
    master marks none, so the audit holds tables.xml to no block comment marking a stop (the former stations and
    the parked scripts' own copies are listed in docs/parked/UNPARK.md)."""
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


def sensor_key(block_name: str) -> str:
    return block_name.replace(" ", "_")


class SetupError(Exception):
    """The audit cannot run (a tool it needs is missing): main() reports it as one line and exits 1."""


def load_staging_masts(path: Path | None = None) -> list[railroad_facts.Mast]:
    """The masts of the base levels (masts.csv's staging rows) the mast rule writes: the audit's expected set."""
    # stops on a file that breaks its rules (hartlib.level_masts.read)
    return railroad_facts.read_masts(MASTS if path is None else path, levels=STAGING_LEVELS)


class SlotMast(TypedDict):
    """One mast bound in a slot, as the plugin's slot index lists it (schematic.slots.Index.masts)."""
    mast: str
    kind: str
    ident: str
    slot: str
    facing: str
    protects: list[str]


class SlotIndex(Protocol):
    """The part of the plugin's slot index (schematic.slots.Index) the audit reads."""
    def masts(self) -> list[SlotMast]: ...


def slots_index(panel: ET.Element) -> SlotIndex:
    """The plugin's slot index of a Layout Editor panel (the rule the LE build places masts by). SetupError when the
    plugin is missing: the deploy audit needs it, so it fails and does not skip."""
    folder = Path(os.environ.get("SCHEMATIC_PLUGIN")
                  or REPO_ROOT / "external/model-railroad-skills/plugins/schematic-maps")
    if not (folder / "schematic" / "slots.py").is_file():
        raise SetupError(f"schematic-maps plugin not found at {folder}: run git submodule update --init "
                         "external/model-railroad-skills")
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    index: SlotIndex = importlib.import_module("schematic.slots").Index(panel)
    return index


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
    placed: dict[str, list[SlotMast]] = {}
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


def block_definitions(root: ET.Element) -> dict[str, list[str]]:
    definitions: dict[str, list[str]] = {}
    for block in root.findall("./blocks/block"):
        name = text(block, "userName")
        if name:
            definitions.setdefault(name, []).append(text(block, "comment"))
    return definitions


def _pair_problem(what: str, expected: set[str], found: list[str]) -> str | None:
    """The message when `found` (names, in file order) is not `expected` once each: missing, extra and duplicates."""
    have = set(found)
    if have == expected and len(found) == len(expected):
        return None
    return (f"{what}; missing={sorted(expected - have) or 'none'}, extra={sorted(have - expected) or 'none'}, "
            f"duplicates={sorted(name for name in have if found.count(name) > 1) or 'none'}")


def is_station_name(name: str) -> bool:
    """Whether a sensor or icon name is a Dispatcher station's MoveTo or move-in-progress sensor."""
    return name.startswith("MoveTo") or name.startswith("MoveInProgress")


def _station_comment_problems(root: ET.Element, expected_comments: dict[str, str]) -> tuple[list[str],
                                                                                           list[tuple[str, str]]]:
    """(problems, (station, its comment or "") per expected station) for the block comments that mark a stop."""
    problems: list[str] = []
    definitions = block_definitions(root)
    station_names = {
        name
        for name, comments in definitions.items()
        if any(comment == "stop" or comment.endswith("; stop") for comment in comments)
    }
    expected_names = set(expected_comments)
    if station_names != expected_names:
        problems.append(
            "Dispatcher station block names differ; "
            f"missing={sorted(expected_names - station_names) or 'none'}, "
            f"extra={sorted(station_names - expected_names) or 'none'}"
        )
    snapshot: list[tuple[str, str]] = []
    for name, expected_comment in expected_comments.items():
        comments = definitions.get(name, [])
        if expected_comment not in comments:
            problems.append(
                f"Dispatcher station {name!r}: expected block comment "
                f"{expected_comment!r}, found {comments or ['<missing block>']}"
            )
        snapshot.append((name, expected_comment if expected_comment in comments else ""))
    return problems, snapshot


def audit_stations(root: ET.Element, panel: ET.Element | None, audit: Audit, *, required: bool) -> None:
    """The Dispatcher stations (station_comments): their block comments, and one MoveTo and one move-in-progress
    sensor and icon each, none while the Dispatcher System is parked."""
    problem = audit.reporter(required)
    try:
        expected_comments = station_comments()
    except devices.DevicesError as e:
        audit.error(f"Dispatcher stations: {e}")
        return
    problems, station_snapshot = _station_comment_problems(root, expected_comments)

    sensors = [name for name in (text(sensor, "userName") for sensor in root.findall("./sensors/sensor"))
               if is_station_name(name)]
    # the Dispatcher System parked (hartlib.parked): the station blocks keep their comments, but no MoveTo or
    # move-in-progress sensor or icon is left in the tables
    expected: set[str] = set()
    for name in (() if "dispatcher" in parked.parked_in(root) else expected_comments):
        key = sensor_key(name)
        expected.update({f"MoveTo{key}_stored", f"MoveInProgress{key}"})
    icons = [] if panel is None else [
        name for name in ((icon.get("sensor") or "").strip() for icon in panel.iter("sensoricon"))
        if is_station_name(name)]
    for message in (_pair_problem("Dispatcher station sensor pairs differ", expected, sensors),
                    _pair_problem("Dispatcher station sensor icons are not exactly one paired icon per station",
                                  expected, icons)):
        if message:
            problems.append(message)
    for message in problems:
        problem(message)
    audit.facts["stations"] = tuple(sorted(station_snapshot))
    audit.facts["station_sensors"] = tuple(sorted(set(sensors)))
    audit.facts["station_icons"] = tuple(sorted(set(icons)))


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
        is_generated = tables.generated_panel(panel)        # False with no panel
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
    if generated and not is_generated:
        audit.error("--generated, but the panel has no generated-panel marker (tools/schematic/build_tables.py "
                    "writes it)")
    audit.facts["generated_panel"] = is_generated
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


def short_items(items: list[object], limit: int = SHOWN) -> object:
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
    try:
        panel_counts()
    except PanelCountsError as exc:
        print(f"ERROR: {exc}")
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
