"""audit_panel_contracts checks of what stock Discover and Dispatcher System Stage 1 store: the Signal Mast Logic,
Entry/Exit, and the Dispatcher graph, bundle and traininfo files.

audit_panel_contracts.py imports this from its own folder (paths.LAYOUT_SCRIPTS) and runs each check from
audit_source.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import NamedTuple

from audit_panel_base import Audit, Problem, attr_or_child, first_items, text, SHOWN
from hartlib import level_devices, parked, paths, tables
from nx_contract import EXPECTED_NX_PAIRS, ISNX_SYSTEM, LAYOUT_PANEL, NXTYPE_SML

TRAININFO = paths.LAYOUT_DIR / "dispatcher" / "traininfo"


def audit_parked_nx(root: ET.Element, problem: Problem) -> None:
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
    problem = audit.reporter(required)
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
            f"missing={missing[:SHOWN]} extra={extra[:SHOWN]}"
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


def audit_nx_slots(root: ET.Element, problem: Problem) -> None:
    """Each NX sensor sits in the slot of its own mast. A sensor left behind when its mast moves is not at a
    block boundary, and Discover walks past the mast into false pairs (NX Mast 8RA on TO117 A did)."""
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


class StoredCounts(NamedTuple):
    """What stock Discover and Dispatcher System Stage 1 store on one kind of panel; the audit holds the stored
    tables to these counts."""
    sml: int            # SML destinations, every one from Discover (useLayoutEditor yes)
    sections: int
    transits: int


# The hand-drawn staging panel: 100 destinations.
HAND_DRAWN = StoredCounts(sml=100, sections=107, transits=187)
# The generated three-level panel (build_layout_le.build written by build_tables.py): 177 destinations from stock
# discovery from an empty list, with virtual masts only as destinations on every level (staging 5, main 10, upper
# 14) and the Scale running track.
GENERATED = StoredCounts(sml=177, sections=197, transits=187)
# The same counts by panel kind (True: generated). tools/audit/check_sml_invariants.py reads EXPECTED_SML[True].
# A generated panel before stock discovery carries the Signal Mast Logic of the live tables.xml it was built on,
# less every logic and destination that names a main or upper object: exactly the live tables' destinations between
# staging masts (carried_destinations), allowed with a warning that discovery is still to run. The audit reads that
# set from the live tables, so a later discovery moves it too.
EXPECTED_SML = {False: HAND_DRAWN.sml, True: GENERATED.sml}
# A generated panel before its Stage 1, with the Dispatcher System unparked, still carries the hand-drawn graph:
# allowed, with the same kind of warning. While the Dispatcher graph is parked (hartlib.parked) the tables hold no
# section or transit.
EXPECTED_GRAPH = {False: (HAND_DRAWN.sections, HAND_DRAWN.transits), True: (GENERATED.sections, GENERATED.transits)}
# The traininfo files in TRAININFO (panelpro_smoke_test.py holds the runtime copies to the same count).
EXPECTED_TRAININFO = 374


class SmlPair(NamedTuple):
    """One stored SML destination: its source and destination masts and its useLayoutEditor value (lower case)."""
    source: str
    target: str
    use_le: str


class SmlDestination(NamedTuple):
    """An SmlPair with its <destinationMast> element, whose bean references carried_destinations reads."""
    pair: SmlPair
    element: ET.Element


def sml_destinations(root: ET.Element) -> list[SmlDestination]:
    """Every stored SML destination of `root`."""
    out = []
    for logic in root.findall("./signalmastlogics/signalmastlogic"):
        source = attr_or_child(logic, "sourceSignalMast") or logic.get("source", "")
        for destination in logic.findall("destinationMast"):
            target = attr_or_child(destination, "destinationSignalMast") or destination.get("destination", "")
            out.append(SmlDestination(SmlPair(source, target, text(destination, "useLayoutEditor").lower()),
                                      destination))
    return out


def carried_destinations(destinations: list[SmlDestination]) -> list[SmlPair]:
    """The destinations (sml_destinations) a cut-over build keeps: from a staging mast, naming no main or upper
    object (hartlib.level_devices.is_level_name, by the fields JMRI keeps bean references in)."""
    return [d.pair for d in destinations
            if not level_devices.is_level_name(d.pair.source)
            and not tables.names_any(d.element, (), level_devices.is_level_name)]


def audit_sml(root: ET.Element, audit: Audit, *, required: bool, generated: bool = False,
              live: ET.Element | None = None) -> None:
    """The stored SML destinations against EXPECTED_SML, or, on a generated panel that holds no main or upper one
    yet, against the live tables' carried_destinations (`live`: their root; default this checkout's tables.xml)."""
    found = sml_destinations(root)
    destinations = [d.pair for d in found]
    auto = sum(use_le == "yes" for _, _, use_le in destinations)
    manual = sum(use_le == "no" for _, _, use_le in destinations)
    unknown = len(destinations) - auto - manual
    # Every destination comes from Discover: no manual pair is kept.
    want = EXPECTED_SML[generated]
    before = generated and len(carried_destinations(found)) == len(found)       # nothing on main or upper yet
    carried = carried_destinations(sml_destinations(live if live is not None else tables.read(paths.TABLES_XML))) \
        if before else []
    if generated and not found:
        # a cut-over candidate (ADR-029): the generator's base and the panel, no logic; the released tables.xml
        # takes the discovered logic (tools/schematic/build_tables.py, data/schematic/discovered_sml.xml)
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


def expected_bundle(parked_features=None, band_panels: bool = True) -> tuple[int, int, int]:
    """(ctcdata, Panel Editor panels, Layout Editor panels) the deployment tables hold: the USS CTC machine's data and
    panel, the main panel, its band panels (tables.BAND_PANEL_NAMES; `band_panels` False for the Layout
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
        audit.error("traininfo not HEAD_AND_TAIL: " + first_items(bad_detection, ", "))
    audit.facts["dispatcher_generated"] = (
        *ctc_bundle,
        sections,
        transits,
        len(files),
    )
