#!/usr/bin/env python3
"""The Layout Editor, the CATS desks and the USS CTC must agree with the switch facts.

    python3 tools/audit/check_layout_facts.py

The facts are the staging rows of jmri/layouts/hart/data/switches.csv (read by
layout_facts.py), with hardware, DCC address and control point from
staging's rows of the device master and the desk areas of stations.csv. For every switch this checks:

Layout Editor (tables.xml)
  - the turnout's hardware and DCC address, and the layout turnout's name and OS block;
  - which leg the continuing sense closes to (plain turnouts);
  - the stored block paths: the closed leg needs Closed or no setting, the thrown
    leg Thrown, and neither may be reached with the other setting. The generated tables.xml stores none (ADR-029:
    JMRI derives them from the panel on load), so this part runs only on a tables file that stores them (--tables,
    a PanelPro Store: tools/hosts/run_panelpro_roundtrip.sh runs it on its Store);
  - a crossover's legs against the panel's track: its OS block one half, its thrown leg the other half, its closed
    leg a block the track reaches from that half (check_crossover_legs; plain turnouts by continuing sense above).
CATS desks (HART_CTC.xml, HART_ABS.xml: the live desks, generated from the schematic since the CATS cut-over)
  - each bound plant's turnout, the leg each command (close/throw) leads to, and which
    leg is NORMAL (the closed one, unless the switch is CATS-inverted); the main and upper
    plants (internal turnouts) are checked below;
  - every block bound to a detector is a Layout Editor block (main and upper ones only where the tables hold those
    levels), and each main and upper desk block reports, occupied and unoccupied, the virtual sensor
    (IS:HART:C3:B:) its block has in tables.xml; only the desk-only middle of a double crossover's X reports none;
  - the desk's staging masts are mast_cells.csv's, each once, its lamp on the edge of the block it
    protects (schematic/masts.csv's staging rows, hartlib.railroad); each is a staging mast row of the device master and in tables.xml, with one head
    (the one named) for a d1 icon and two for h2;
  - main and upper (bound to their internal turnouts IT:HART:C3:<n>, their masts and their blocks' virtual
    sensors): each plant commands and reports one internal turnout of tables.xml, NORMAL on its close
    leg, and no plain turnout's close and throw legs are the Layout Editor's swapped; every internal
    turnout has a plant (a double crossover four points, one turnout); each mast of
    masts.csv's main and upper rows has one lamp, on the edge of the block it protects (a double crossover's
    corner is its one desk block), and is that mast in tables.xml.
Levels (stations.csv desk areas, switches.csv, staging's rows of the device master)
  - each control point's switches are on its level, and every cp of a staging row has a desk area;
  - every mast and block has one level: its switch's, its control point's, or, for a
    main between control points, the one level of the blocks it joins (its stored paths, else the panel's track).
USS CTC (CTC code buttons in tables.xml, ctc/GUIObjects.xml and the copy in tables.xml)
  - the code button's turnout, OS sensors, lever and signal levers;
  - the lever, the points dot and its polarity in the switch's column;
  - the track jewels and labels are the ones the board's grid gives (uss_board_cells.csv,
    frozen from the hand-wired CATS desk; gen_ctc_track_plan.py reads it too).

Track names are the CATS occupancy names; a Layout Editor throat block such as
Track S-R West (same occupancy sensor as Track S-R) counts as Track S-R.
A failure names the switch or track and the two sources that disagree.
KNOWN lists differences already reported to the owner, each by its exact message;
they print but do not fail, any other message fails, and a KNOWN message that no
longer happens fails so the list stays honest.

The checks live in layout_facts_tables (Layout Editor), layout_facts_desks (CATS desks), layout_facts_uss (USS CTC)
and layout_facts_levels (data and levels), on the sources and report of layout_facts_base. A missing file, element
or source row is a LayoutFactsError, which main prints and exits 1 on.
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, level_masts, parked, paths  # noqa: E402,F401  devices, level_masts: read by the tests

sys.path[:0] = [str(paths.LAYOUT_SCRIPTS), str(Path(__file__).resolve().parent)]     # the layout_facts_* parts beside this

# the parts' names the tests and cats/scripts/tests/test_mast_cells.py read through this module
from layout_facts_base import (DESKS, DEVICE_MAP, GUI, HART, MASTS, ROOT, TABLES, Report,  # noqa: E402,F401
                               facts, trace)
from layout_facts_desks import (check_desk, check_level_desk, desk_block_of, desk_mast_blocks,  # noqa: E402,F401
                                desk_plants, device_map_blocks, device_map_rows, field_sensors, level_turnouts,
                                same_place)
from layout_facts_levels import check_data, check_levels, check_mast_cells, protected_blocks, staging_mast_rows  # noqa: E402,F401,E501
from layout_facts_tables import Tables, check_tables, desk_leg, part_map  # noqa: E402,F401
from layout_facts_uss import check_ctc_buttons, check_uss_panel, occupancy_sensors, uss_panel  # noqa: E402
from layout_facts_xml import LayoutFactsError, parse  # noqa: E402,F401

# Differences already reported to the owner and accepted, each by its exact message.
KNOWN: dict[str, str] = {}


def need_inputs(data: Path, files: Sequence[tuple[str, Path]]) -> None:
    """LayoutFactsError naming the first input that is missing: the `data` folder, or one of `files` ((option, path))."""
    if not Path(data).is_dir():
        raise LayoutFactsError(f"--data {data}: no such folder")
    for option, path in files:
        if not Path(path).is_file():
            raise LayoutFactsError(f"--{option} {path}: no such file")


def run(data: Path = facts.DATA, tables: Path = TABLES, desks: Sequence[Path] = DESKS, gui: Path = GUI,
        device_map: Path = DEVICE_MAP) -> Report:
    """Every check on these sources. `device_map`: the master that goes with `tables` (its parts, part_map).
    LayoutFactsError when an input is missing or lacks what a check reads."""
    need_inputs(data, [("tables", tables), ("gui", gui), ("devices", device_map), *(("desk", d) for d in desks)])
    import gen_ctc_track_plan as gen

    r = Report()
    switches = facts.load_switches(data)
    r.switch_count = len(switches)
    parts = part_map(device_map)
    t = Tables(tables, parts=parts)
    r.paths_stored = t.paths_stored
    check_data(switches, data, r)
    rows = facts.staging_rows(data)  # staging's rows of the device master, read once for the checks below
    check_levels(switches, data, rows, t, r)
    check_mast_cells(data, rows, desks, t, r)
    for sw in switches.values():
        check_tables(sw, t, r)
    for desk in desks:
        check_desk(Path(desk), switches, t, r)
        check_level_desk(Path(desk), t, r)
    # the USS CTC machine parked (hartlib.parked): its code buttons and panel are checked in the parked file, put
    # back into a copy of the tables, against the same switches (the tables parsed once above; the copy stays in
    # memory, with no temporary file to write and parse again)
    uss_root = parked.with_parked({"uss"}, tables, root=t.root)
    if uss_root is t.root:
        uss, uss_text = t, Path(tables).read_text(encoding="utf-8")
    else:
        uss = Tables(tables, root=uss_root, parts=parts)
        pe = next(iter(uss_root.iter("paneleditor")), None)       # only the USS panel is read from the text
        uss_text = ET.tostring(pe, encoding="unicode") if pe is not None else ""
    check_ctc_buttons(switches, uss, occupancy_sensors(device_map), r)
    cells = facts.load_uss_cells(data)  # the board's grid, frozen from the hand-wired desk (uss_board_cells.csv)
    gui_text = Path(gui).read_text(encoding="utf-8")
    for label, text in (("GUIObjects.xml", gui_text), ("tables.xml USS panel", uss_text)):
        check_uss_panel(label, uss_panel(text), switches, gen, cells, r)
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, default=facts.DATA)
    ap.add_argument("--tables", type=Path, default=TABLES)
    ap.add_argument("--desk", type=Path, action="append",
                    help="CATS desk (repeat); default the last hand-wired CTC and ABS (git)")
    ap.add_argument("--gui", type=Path, default=GUI)
    ap.add_argument("--devices", type=Path, default=DEVICE_MAP,
                    help="the master that goes with --tables (its parts: a part is read as the block it is in)")
    args = ap.parse_args(argv)
    try:
        r = run(args.data, args.tables, tuple(args.desk) if args.desk else DESKS, args.gui, device_map=args.devices)
    except LayoutFactsError as err:
        print(f"check_layout_facts: {err}", file=sys.stderr)
        return 1
    for line in r.known(KNOWN):
        print(f"KNOWN {line}")
    failures = r.failures(KNOWN)
    for line in failures:
        print(f"FAIL {line}", file=sys.stderr)
    if not r.paths_stored:
        print(f"note: {paths.rel(args.tables)} stores no block paths (ADR-029: JMRI derives them from the panel); the "
              "stored-path leg check runs on a tables file that stores them (--tables, a PanelPro Store)")
    print(f"layout facts: {r.switch_count} switches, {len(failures)} failure(s), {len(r.known(KNOWN))} known")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
