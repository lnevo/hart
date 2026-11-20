"""build_staging_sets.py [--check]

Write staging's station and control-point membership, in every place the build reads it, from the three files the owner
edits (jmri/layouts/hart/data/schematic/):

  control_points_staging.csv  cp_id,cp_name,level,switches,area,code,notes   the control points: the limits the drawings
                              bracket and the CATS desk names (the signal rule's own interlockings are another fact:
                              interlockings_staging.csv)
  stations_staging.csv        station,switches,tracks,notes                  the stations; `tracks` blank counts the
                              tracks that run from the switches, `none` counts none, else track names, ";" between
  sheets_staging.csv          sheet,stations,notes                           the station detail sheets, each the
                              stations named in `stations` (";" between), its switches the sorted union of theirs

What it writes, and nothing else of those files:

  staging.plan_overrides.json   the keys control_points, stations and station_tracks
  staging.preferences.json      the key detail_sheets
  data/control_points.csv       the control points in the older shape the website build, check_layout_facts.py and the
                                scripts that run in JMRI read: cp_id is the name in lower case with underscores, a
                                crossover's switch is listed by its halves (7 is 7,7b; 23 is 23a,23b), taken from the
                                OS blocks in switch_legs.csv

Every switch is a staging switch (level 1 of switches.csv) in one control point at most and, in the end, in one; a
station's switches are in some control point; a sheet's stations are stations. A row that breaks a rule stops the
build with the file and line. --check regenerates in memory and exits 1 if a file differs.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA
from hartlib import paths  # noqa: E402
from hartlib.railroad_facts import FactsError, read_rows  # noqa: E402

LEVEL = "1"
CPS = pd.DATA / "control_points_staging.csv"
STATIONS = pd.DATA / "stations_staging.csv"
SHEETS = pd.DATA / "sheets_staging.csv"
OVERRIDES = pd.DATA / "staging.plan_overrides.json"
PREFERENCES = pd.DATA / "staging.preferences.json"
LEGACY = paths.LAYOUT_DATA / "control_points.csv"
SWITCHES = paths.LAYOUT_DATA / "switches.csv"
LEGS = paths.LAYOUT_DATA / "switch_legs.csv"
LEGACY_COLUMNS = ["cp_id", "cp_name", "level", "switches", "notes", "code"]
NONE = "none"        # the `tracks` cell of a station that counts no track


class SetsError(ValueError):
    """A master file breaks a rule; the message names the file and line."""


@dataclass(frozen=True)
class ControlPoint:
    line: int
    cp_id: str
    cp_name: str
    switches: tuple[str, ...]
    code: str
    notes: str


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


def staging_switches(path: Path = SWITCHES) -> set[str]:
    """The switch numbers of level 1 in switches.csv."""
    return {r["switch"] for _l, r in _rows(path, ("level", "switch")) if r["level"] == LEVEL}


def read_control_points(path: Path = CPS, switches: set[str] | None = None) -> list[ControlPoint]:
    """The control points in file order. Stops on a name, id or code given twice or empty, a level that is not
    staging's, a switch that is not a staging switch or is in two control points, or a staging switch in none."""
    known = staging_switches() if switches is None else switches
    out, ids, seen = [], {}, {}
    for line, r in _rows(path, ("cp_id", "cp_name", "level", "switches", "area", "code"), optional=("notes",)):
        where = _where(path, line)
        if r["level"] != LEVEL:
            raise SetsError(f"{where} ({r['cp_name']}): level {r['level']!r}, staging is {LEVEL}")
        for col in ("cp_id", "cp_name", "code"):
            if not r[col]:
                raise SetsError(f"{where}: {col} is empty")
            if (col, r[col]) in ids:
                raise SetsError(f"{where}: {col} {r[col]!r} is also on line {ids[(col, r[col])]}")
            ids[(col, r[col])] = line
        sw = _split(r["switches"])
        if not sw:
            raise SetsError(f"{where} ({r['cp_name']}): no switches")
        for s in sw:
            if s not in known:
                raise SetsError(f"{where} ({r['cp_name']}): switch {s} is no staging switch")
            if s in seen:
                raise SetsError(f"{where} ({r['cp_name']}): switch {s} is also in {seen[s]}")
            seen[s] = r["cp_name"]
        out.append(ControlPoint(line, r["cp_id"], r["cp_name"], sw, r["code"], r["notes"]))
    lost = sorted(known - set(seen), key=int)
    if lost:
        raise SetsError(f"{path.name}: staging switch(es) {', '.join(lost)} are in no control point")
    return out


def read_stations(cps: list[ControlPoint], path: Path = STATIONS) -> list[Station]:
    """The stations in file order. Stops on a name given twice, a station with no switches, or a switch that is in no
    control point."""
    have = {s for cp in cps for s in cp.switches}
    out, names = [], {}
    for line, r in _rows(path, ("station", "switches", "tracks"), optional=("notes",)):
        where = _where(path, line)
        if not r["station"] or r["station"] in names:
            raise SetsError(f"{where}: station {r['station']!r} is empty or also on line {names.get(r['station'])}")
        names[r["station"]] = line
        sw = _split(r["switches"])
        if not sw:
            raise SetsError(f"{where} ({r['station']}): no switches")
        bad = [s for s in sw if s not in have]
        if bad:
            raise SetsError(f"{where} ({r['station']}): switch {', '.join(bad)} is in no control point")
        tracks = None if not r["tracks"] else () if r["tracks"] == NONE else _split(r["tracks"])
        out.append(Station(line, r["station"], sw, tracks))
    return out


def read_sheets(stations: list[Station], path: Path = SHEETS) -> list[Sheet]:
    """The detail sheets in file order. Stops on a name given twice or a sheet naming no station or an unknown one."""
    known = {s.name for s in stations}
    out, names = [], {}
    for line, r in _rows(path, ("sheet", "stations")):
        where = _where(path, line)
        if not r["sheet"] or r["sheet"] in names:
            raise SetsError(f"{where}: sheet {r['sheet']!r} is empty or also on line {names.get(r['sheet'])}")
        names[r["sheet"]] = line
        st = _split(r["stations"])
        if not st:
            raise SetsError(f"{where} ({r['sheet']}): no stations")
        bad = [s for s in st if s not in known]
        if bad:
            raise SetsError(f"{where} ({r['sheet']}): {', '.join(bad)} is no station in {STATIONS.name}")
        out.append(Sheet(line, r["sheet"], st))
    return out


def os_halves(path: Path = LEGS) -> dict[str, list[str]]:
    """{switch: its OS blocks' names without "OS Switch ", sorted}: 7 is 7 and 7b, 23 is 23a and 23b."""
    out: dict[str, list[str]] = {}
    for line, r in _rows(path, ("switch", "os_block")):
        m = re.fullmatch(r"OS Switch (\d+[a-z]?)", r["os_block"])
        if not m:
            raise SetsError(f"{_where(path, line)}: {r['os_block']!r} is not an OS Switch block")
        out.setdefault(r["switch"], []).append(m.group(1))
    return {k: sorted(v) for k, v in out.items()}


def sheet_switches(sheet: Sheet, stations: list[Station]) -> list[str]:
    by_name = {s.name: s for s in stations}
    return sorted({sw for n in sheet.stations for sw in by_name[n].switches}, key=int)


def dumps(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def overrides_text(over: dict, cps, stations) -> str:
    over = dict(over)
    over["stations"] = {s.name: list(s.switches) for s in stations}
    over["control_points"] = {c.cp_name: {"switches": list(c.switches), "code": c.code} for c in cps}
    over["station_tracks"] = {s.name: list(s.tracks) for s in stations if s.tracks is not None}
    over["_control_points"] = ("Written by tools/schematic/build_staging_sets.py from control_points_staging.csv "
                               "(control_points) and stations_staging.csv (stations, station_tracks); edit those "
                               "files, not these keys.")
    return dumps(over)


def preferences_text(prefs: dict, sheets, stations) -> str:
    prefs = dict(prefs)
    prefs["detail_sheets"] = {s.name: sheet_switches(s, stations) for s in sheets}
    return dumps(prefs)


def legacy_text(cps: list[ControlPoint], halves: dict[str, list[str]]) -> str:
    rows = []
    for c in cps:
        sw = []
        for s in c.switches:
            if s not in halves:
                raise SetsError(f"{CPS.name} line {c.line}: switch {s} has no OS block in {LEGS.name}")
            sw += halves[s]
        rows.append(dict(cp_id=re.sub(r"\W+", "_", c.cp_name.lower()), cp_name=c.cp_name, level=LEVEL,
                         switches=",".join(sw), notes=c.notes, code=c.code))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=LEGACY_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def wanted() -> dict[Path, str]:
    """{file: the text it should hold}."""
    cps = read_control_points()
    stations = read_stations(cps)
    sheets = read_sheets(stations)
    return {
        OVERRIDES: overrides_text(json.loads(OVERRIDES.read_text(encoding="utf-8")), cps, stations),
        PREFERENCES: preferences_text(json.loads(PREFERENCES.read_text(encoding="utf-8")), sheets, stations),
        LEGACY: legacy_text(cps, os_halves()),
    }


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
