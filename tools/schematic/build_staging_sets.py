"""build_staging_sets.py [--check]

Write staging's station and control-point membership, in every place the build reads it, from the two files the owner
edits (jmri/layouts/hart/data/schematic/):

  stations.csv   level,station,switches,tracks,desk_code,desk_plate,notes   the stations of every level (one file, a level
                 column); `tracks` blank counts the tracks that run from the switches, `none` counts none, else track
                 names, ";" between; `desk_code` names the station's desk area (owner, 2026-11-20)
  sheets.csv     level,sheet,stations,notes                       the station detail sheets of every level, each the
                 stations named in `stations` (";" between), its switches the sorted union of theirs

The control points (the limits the drawings bracket and the CATS desk names, plan_generated.json's control_points)
are the desk areas: the stations that share a desk code, named by the first of them, each holding its stations' own
switches. A station whose switches all lie in another's is nested in it and takes them for its own desk area (Engine
House in Barn: BN is Switch 7, EH Switches 9, 11, 13). hartlib.railroad_facts.read_desk_areas is the one reader;
stations that partly overlap, or a switch in two nested stations, stop it. The signal rule's own interlockings are
another fact: interlockings.csv, every level.

Only staging (level 1) has stations so far; a row of another level stops the build until this builds that level too
(the main and upper levels' two whole-level sheets stay in preferences.json's main_upper section meanwhile).

What it writes, and nothing else of those files:

  plan_generated.json          staging's section: the keys control_points, stations and station_tracks
  preferences_generated.json   staging's section: the key detail_sheets
(through hartlib.layer_files, which keeps the other sections and the notes as they are, and merges each file under
the owner's hand file, plan_overrides.json and preferences.json, for every reader). It writes neither hand file, and
stops when preferences.json's staging section holds detail_sheets: a hand value wins the merge and would hide the
generated one.

The older data/control_points.csv and schematic/control_points_staging.csv are gone (level-unification step 8; owner
2026-11-20): their readers build the same rows from stations.csv and switches.csv
(hartlib.railroad_facts.station_group_rows).

Every staging switch (level 1 of switches.csv) is in one desk area and every station switch is a staging switch; a
sheet's stations are stations. A row that breaks a rule stops the
build with the file and line. --check regenerates in memory and exits 1 if a file differs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA
from hartlib import layer_files, paths  # noqa: E402
from hartlib import railroad_facts as rf  # noqa: E402
from hartlib.railroad_facts import DeskArea, FactsError, read_rows, station_group_rows  # noqa: E402

LEVEL = "1"
STATIONS = pd.DATA / "stations.csv"
SHEETS = pd.DATA / "sheets.csv"
SHEET = "staging"     # the sections of plan_generated.json and preferences_generated.json this writes
SWITCHES = paths.LAYOUT_DATA / "switches.csv"
NONE = "none"        # the `tracks` cell of a station that counts no track


class SetsError(ValueError):
    """A master file breaks a rule; the message names the file and line."""


@dataclass(frozen=True)
class Station:
    line: int
    name: str
    switches: tuple[str, ...]
    tracks: tuple[str, ...] | None       # None: the tracks that run from its switches


@dataclass(frozen=True)
class Sheet:
    line: int
    name: str
    stations: tuple[str, ...]


def _rows(path, required, optional=()):
    try:
        return read_rows(path, required, optional=optional)
    except FactsError as exc:
        raise SetsError(str(exc)) from None


def _where(path: Path, line: int) -> str:
    return f"{path.name} line {line}"


def _split(cell: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in re.split(r"[;,]", cell) if p.strip())


def _staging_row(where: str, name: str, level: str) -> None:
    """Stop on a row of a level this builder does not build yet: the files hold every level, this writes staging's."""
    try:
        number = int(level)
    except ValueError:
        raise SetsError(f"{where} ({name}): level {level!r} is not a level number (1 staging, 2 main, 3 upper)") from None
    if number != int(LEVEL):
        raise SetsError(f"{where} ({name}): level {level!r}; only staging (level {LEVEL}) stations and sheets are "
                        "built so far")


def staging_switches(path: Path = SWITCHES) -> set[str]:
    """The switch numbers of level 1 in switches.csv (rf.read_switch_rows, every row checked)."""
    try:
        return {str(r.switch) for r in rf.read_switch_rows(path) if r.level == int(LEVEL)}
    except FactsError as exc:
        raise SetsError(str(exc)) from None


def read_masters(path: Path = STATIONS, switches: set[str] | None = None) -> tuple[list[DeskArea], list[Station]]:
    """(the desk areas, the stations) of stations.csv, each in file order (rf.read_desk_areas' rules, `switches` the
    staging switches, switches.csv's level 1 unless given). Stops, too, on a row of a level this does not build yet."""
    known = staging_switches() if switches is None else switches
    try:
        rows = rf.read_stations(path)
        for st in rows:
            _staging_row(_where(path, st.line), st.name, str(st.level))
        areas = rf.desk_areas(rows, path, known)
    except FactsError as exc:
        raise SetsError(str(exc)) from None
    stations = [Station(st.line, st.name, st.switches,
                        None if not st.tracks else () if st.tracks == NONE else _split(st.tracks)) for st in rows]
    return areas, stations


def read_sheets(stations: list[Station], path: Path = SHEETS, stations_path: Path = STATIONS) -> list[Sheet]:
    """The detail sheets in file order. Stops on a name given twice or a sheet naming no station or an unknown one."""
    known = {s.name for s in stations}
    out, names = [], {}
    for line, r in _rows(path, ("level", "sheet", "stations"), optional=("notes",)):
        where = _where(path, line)
        _staging_row(where, r["sheet"], r["level"])
        if not r["sheet"] or r["sheet"] in names:
            raise SetsError(f"{where}: sheet {r['sheet']!r} is empty or also on line {names.get(r['sheet'])}")
        names[r["sheet"]] = line
        st = _split(r["stations"])
        if not st:
            raise SetsError(f"{where} ({r['sheet']}): no stations")
        bad = [s for s in st if s not in known]
        if bad:
            raise SetsError(f"{where} ({r['sheet']}): {', '.join(bad)} is no station in {stations_path.name}")
        out.append(Sheet(line, r["sheet"], st))
    return out


def sheet_switches(sheet: Sheet, stations: list[Station]) -> list[str]:
    by_name = {s.name: s for s in stations}
    return sorted({sw for n in sheet.stations for sw in by_name[n].switches}, key=int)


def generated_keys(cps, stations) -> dict:
    """The keys of plan_generated.json's staging section this writes, from the desk areas (stations.csv) alone."""
    over = {}
    over["stations"] = {s.name: list(s.switches) for s in stations}
    over["control_points"] = {c.name: {"switches": list(c.switches), "code": c.code} for c in cps}
    over["station_tracks"] = {s.name: list(s.tracks) for s in stations if s.tracks is not None}
    over["_control_points"] = ("Written by tools/schematic/build_staging_sets.py from stations.csv (stations, "
                               "station_tracks, and control_points: the desk areas, by desk_code); edit that "
                               "file, not these keys.")
    return over


DETAIL_NOTE = ("Layer 3: the station sheets `schematic detail` draws, name to switches. May overlap the stations above. "
               "South Yard covers the yard and the Barn (owner, 2026-11-14); West Yard pairs the hand map with Brick "
               "and Plane; Princess is the hand map's Shenango. Written by tools/schematic/build_staging_sets.py from "
               "sheets.csv (each sheet the sorted union of its stations' switches); edit that file, not this key.")


def generated_preferences(sheets, stations) -> dict:
    """The keys of preferences_generated.json's staging section this writes, from sheets.csv and stations.csv."""
    return {"detail_sheets": {s.name: sheet_switches(s, stations) for s in sheets}, "_detail_sheets": DETAIL_NOTE}


def check_hand_preferences(data: Path) -> None:
    """Stop when preferences.json's staging section holds a key this writes: the merge keeps a hand value over a
    generated one (hartlib.layer_files.merge), so a hand copy would hide what sheets.csv says."""
    hand = layer_files.read("preferences", SHEET, data)
    clash = [k for k in generated_preferences([], []) if k in hand]
    if clash:
        raise SetsError(f"preferences.json[{SHEET}] holds {', '.join(clash)}: build_staging_sets.py writes "
                        f"{'it' if len(clash) == 1 else 'them'} to preferences_generated.json from sheets.csv; "
                        "delete the hand copy")


def wanted(data: Path | None = None) -> dict[Path, str]:
    """{layer file: the whole text it should hold} (data: the layer folder, pd.DATA unless given)."""
    data = pd.DATA if data is None else data
    cps, stations = read_masters()
    sheets = read_sheets(stations)
    try:      # stop here, at the source, if a switch has no OS block: the website build and the layout checks read
              # these rows through station_group_rows and would stop later (step 8)
        station_group_rows(STATIONS, SWITCHES)
    except FactsError as exc:
        raise SetsError(str(exc)) from None
    try:
        check_hand_preferences(data)
        return {**layer_files.generated_texts({SHEET: generated_keys(cps, stations)}, data),
                **layer_files.generated_texts({SHEET: generated_preferences(sheets, stations)}, data,
                                              layer_files.PREFS_GENERATED)}
    except layer_files.LayerFileError as exc:
        raise SetsError(str(exc)) from None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a file is stale")
    args = ap.parse_args(argv)
    try:
        want = wanted()
    except SetsError as exc:
        print(f"build_staging_sets.py: {exc}", file=sys.stderr)
        return 2
    stale = [p for p, text in want.items() if p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale:
            print(f"{p.name} is stale: run python3 tools/schematic/build_staging_sets.py", file=sys.stderr)
        if not stale:
            print("staging stations, control points and sheets are current")
        return 1 if stale else 0
    for p in stale:
        p.write_text(want[p], encoding="utf-8")
        print(f"wrote {p.name}")
    if not stale:
        print("staging stations, control points and sheets are current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
