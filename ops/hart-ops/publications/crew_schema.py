"""Schema check of the crew master ops/hart-ops/data/crew.json (ADR-039).

The master is nested JSON (jobs with steps, sequences and lineups; maps with tracks), which the column sidecar format
(docs/data/sidecars.md) cannot describe, so this checks it instead: the keys are unique, the required fields are
there (every map has its tracks and the spot sheet its desk notes, which the site pages draw), every reference names
a record that exists (a job's colors and maps, a map's connections and sheets, the spot
sheet's industries in industries.csv), and each `docx` object holds only the fields the docx scripts read (colors and the timetable hold none).
build_crew_json.py runs it before it builds; ops/hart-ops/tests/test_crew_master.py tests it.
"""
from __future__ import annotations

import re

TOP = ("_about", "colors", "timetable", "spotsheet", "scale", "overview", "maps", "jobs", "sheets", "levels",
       "schematic")
COLOR_FIELDS = ("id", "label", "hex", "ink", "dest", "train", "group", "spot")
GROUPS = ("interchange", "island")
JOB_FIELDS = ("id", "code", "kind", "name", "title", "pub", "revision", "effective", "summary", "colors", "maps",
              "talk", "source")
LEGEND_FIELDS = ("label", "hex", "ink", "dest", "train")  # a yardmaster job's legend_extra row: a color without an id
KINDS = ("crew", "yardmaster", "dispatcher")
TRACK_FIELDS = ("track", "purpose")  # a row of a map's Tracks table
DESK_FIELDS = ("id", "name", "tag", "about", "lists")  # a yard or desk note on the spot sheet
HEX = re.compile(r"#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})")
# where a docx object may sit, and the fields it may hold
DOCX = {
    "scale part": {"lead_items"},
    "crew job": {"photo", "intro", "engine", "steps"},
    "sequence row": {"action"},
}


def _dupes(values) -> list:
    seen, out = set(), []
    for v in values:
        if v in seen and v not in out:
            out.append(v)
        seen.add(v)
    return out


def _docx(where: str, obj: dict, place: str, out: list[str]) -> None:
    d = obj.get("docx")
    if d is None:
        return
    if not isinstance(d, dict) or not d:
        out.append(f"{where}: docx must be a non-empty object")
        return
    extra = sorted(set(d) - DOCX[place])
    if extra:
        out.append(f"{where}: docx holds {', '.join(extra)}; a {place} may hold only {', '.join(sorted(DOCX[place]))}")


def _colors(colors: list[dict]) -> list[str]:
    out: list[str] = []
    for c in colors:
        where = f"color {c.get('id')!r}"
        out += [f"{where}: no {f}" for f in COLOR_FIELDS if not c.get(f)]
        if c.get("group") and c["group"] not in GROUPS:
            out.append(f"{where}: group {c['group']!r} is not one of {', '.join(GROUPS)}")
        for f in ("hex", "ink"):
            if c.get(f) and not HEX.fullmatch(c[f]):
                out.append(f"{where}: {f} {c[f]!r} is not #rgb or #rrggbb")
        if "docx" in c:
            out.append(f"{where}: a color holds no docx object (the sheet prints the site wording)")
    out += [f"colors: id {v!r} is given twice" for v in _dupes(c.get("id") for c in colors)]
    return out


def _tracks(where: str, m: dict, map_ids: set) -> list[str]:
    """A map's Tracks table (crew.js draws one per map): a row per track, each saying what is there."""
    tracks = m.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        return [f"{where}: no tracks (the map page lists them)"]
    out: list[str] = []
    for k, t in enumerate(tracks, 1):
        if not isinstance(t, dict):
            out.append(f"{where}: track row {k} must be an object")
            continue
        out += [f"{where}: track row {k} has no {f}" for f in TRACK_FIELDS if not t.get(f)]
        if t.get("map") and t["map"] not in map_ids:
            out.append(f"{where}: track {t.get('track')!r} links map {t['map']!r}, which is no map")
    return out


def _maps(master: dict, map_ids: set) -> list[str]:
    maps, sheets = master["maps"], master["sheets"]
    out = [f"maps: id {v!r} is given twice" for v in _dupes(m.get("id") for m in maps)]
    for m in maps:
        where = f"map {m.get('id')!r}"
        out += [f"{where}: connects to {v!r}, which is no map" for v in m.get("connects", []) if v not in map_ids]
        out += [f"{where}: sheet {v!r} is not in sheets" for v in m.get("sheets", []) if v not in sheets]
        out += _tracks(where, m, map_ids)
    out += [f"levels: {v!r} is not in sheets" for v in master["levels"] if v not in sheets]
    return out


def _timetable(tt: dict) -> list[str]:
    out = [f"timetable row {i + 1}: {len(r)} cells for {len(tt['columns'])} columns"
           for i, r in enumerate(tt["rows"]) if len(r) != len(tt["columns"])]
    if "docx" in tt:
        out.append("timetable: holds no docx object (the sheet prints the site wording)")
    return out


def _scale(scale: dict) -> list[str]:
    out: list[str] = []
    for sec in scale["sections"]:
        for part in sec["parts"]:
            where = f"scale part {part.get('h')!r}"
            _docx(where, part, "scale part", out)
            lead = part.get("docx", {}).get("lead_items", 0)
            if not isinstance(lead, int) or not 0 <= lead < len(part.get("items", [])):
                out.append(f"{where}: lead_items {lead!r} must leave at least one step")
    return out


def _desk(desk) -> list[str]:
    """The spot sheet's yard and desk notes (crew.js draws them after the interchange)."""
    if not isinstance(desk, list) or not desk:
        return ["spot sheet: no desk notes (the spot sheet page ends with them)"]
    out: list[str] = []
    for k, d in enumerate(desk, 1):
        if not isinstance(d, dict):
            out.append(f"spot sheet desk entry {k} must be an object")
            continue
        where = f"spot sheet desk {d.get('id')!r}"
        out += [f"{where}: no {f}" for f in DESK_FIELDS if not d.get(f)]
        for n, lst in enumerate(d.get("lists") or [], 1):
            if not isinstance(lst, dict) or not lst.get("label") or not lst.get("items"):
                out.append(f"{where}: list {n} needs a label and items")
    out += [f"spot sheet: desk id {v!r} is given twice" for v in _dupes(d.get("id") for d in desk if isinstance(d, dict))]
    return out


def _spotsheet(sheet: dict, industries: dict[str, dict], color_ids: set, map_ids: set) -> list[str]:
    out: list[str] = []
    for ind in sheet["industries"]:
        iid = ind.get("industry_id")
        where = f"spot sheet industry {iid!r}"
        if iid not in industries:
            out.append(f"{where}: not in ops/hart-ops/data/industries.csv")
        out += [f"{where}: {f} must come from industries.csv, not the crew master" for f in ("id", "name") if f in ind]
        if ind.get("color") not in color_ids:
            out.append(f"{where}: color {ind.get('color')!r} is no color")
    out += _desk(sheet.get("desk"))
    desk = [d for d in sheet.get("desk") or [] if isinstance(d, dict)]
    for entry in sheet["industries"] + sheet.get("offline", []) + desk:
        if entry.get("map") and entry["map"] not in map_ids:
            out.append(f"spot sheet {entry.get('industry_id') or entry.get('id')!r}: map {entry['map']!r} is no map")
    out += [f"spot sheet: industry {v!r} is given twice" for v in _dupes(i.get("industry_id") for i in sheet["industries"])]
    return out


def _legend_extra(where: str, j: dict, colors: list[dict]) -> list[str]:
    """A yardmaster job's blocking list: every color in the job's order, then its legend_extra rows."""
    out: list[str] = []
    extra = j.get("legend_extra", [])
    for k, row in enumerate(extra, 1):
        if not isinstance(row, dict):
            out.append(f"{where}: legend_extra row {k} must be an object")
            continue
        out += [f"{where}: legend_extra row {k} has no {f}" for f in LEGEND_FIELDS if not row.get(f)]
        out += [f"{where}: legend_extra row {k}: unknown field {f!r}" for f in row if f not in LEGEND_FIELDS]
        out += [f"{where}: legend_extra row {k}: {f} {row[f]!r} is not #rgb or #rrggbb"
                for f in ("hex", "ink") if row.get(f) and not HEX.fullmatch(row[f])]
    labels = [c.get("label") for c in colors if c.get("id") in j.get("colors", [])]
    labels += [r.get("label") for r in extra if isinstance(r, dict)]
    out += [f"{where}: blocking list label {v!r} is given twice" for v in _dupes(labels)]
    missing = [c.get("id") for c in colors if c.get("id") not in j.get("colors", [])]
    if missing:
        out.append(f"{where}: colors must list every color (the site shows legend_extra only then); "
                   f"missing {', '.join(map(str, missing))}")
    out += [f"{where}: colors gives {v!r} twice (YM-01's blocking list prints them in order)"
            for v in _dupes(j.get("colors", []))]
    return out


def _job(j: dict, colors: list[dict], color_ids: set, map_ids: set) -> list[str]:
    where = f"job {j.get('id')!r}"
    out = [f"{where}: no {f}" for f in JOB_FIELDS if f not in j]
    if "site_note" in j and not (isinstance(j["site_note"], str) and j["site_note"].strip()):
        out.append(f"{where}: site_note must be a non-empty sentence")
    kind = j.get("kind")
    if kind not in KINDS:
        out.append(f"{where}: kind {kind!r} is not one of {', '.join(KINDS)}")
        return out
    out += [f"{where}: color {v!r} is no color" for v in j.get("colors", []) if v not in color_ids]
    out += [f"{where}: map {v!r} is no map" for v in j.get("maps", []) if v not in map_ids]
    needs = {"crew": ("steps",), "yardmaster": ("sequence",), "dispatcher": ("lineup", "priority")}[kind]
    out += [f"{where}: a {kind} job needs {f} (its docx prints it)" for f in needs if not j.get(f)]
    if kind == "crew":
        if not (j.get("engine") or {}).get("label"):
            out.append(f"{where}: a crew job needs engine.label")
        _docx(where, j, "crew job", out)
    elif j.get("docx") is not None:
        out.append(f"{where}: a {kind} job holds no docx object")
    if kind in ("yardmaster", "dispatcher") and not j.get("rules"):
        out.append(f"{where}: no rules (the sheet prints them and the site appends them to the summary)")
    for row in j.get("sequence", []) + j.get("lineup", []):
        rw = f"{where} row {row.get('n')!r}"
        out += [f"{rw}: color {v!r} is no color" for v in row.get("colors", []) if v not in color_ids]
        _docx(rw, row, "sequence row", out)
    for row in j.get("lineup", []):
        if not row.get("route") or not row.get("action"):
            out.append(f"{where} row {row.get('n')!r}: a lineup row needs route and action")
    if kind != "yardmaster" and "legend_extra" in j:
        out.append(f"{where}: only a yardmaster job holds legend_extra")
    if kind == "yardmaster":
        out += _legend_extra(where, j, colors)
    return out


def _jobs(jobs: list[dict], colors: list[dict], color_ids: set, map_ids: set) -> list[str]:
    out = [f"jobs: id {v!r} is given twice" for v in _dupes(j.get("id") for j in jobs)]
    out += [f"jobs: code {v!r} is given twice" for v in _dupes(j.get("code") for j in jobs)]
    for j in jobs:
        out += _job(j, colors, color_ids, map_ids)
    return out


def problems(master: dict, industries: dict[str, dict]) -> list[str]:
    """Every problem in the master, each naming the record; [] when it is sound."""
    missing = [k for k in TOP if k not in master]
    if missing:
        return [f"top level: no {', '.join(missing)}"]
    out = [f"top level: unknown key {k!r}" for k in master if k not in TOP]
    colors = master["colors"]
    color_ids = {c.get("id") for c in colors}
    map_ids = {m.get("id") for m in master["maps"]} | {master["overview"].get("id")}
    out += _colors(colors)
    out += _maps(master, map_ids)
    out += _timetable(master["timetable"])
    out += _scale(master["scale"])
    out += _spotsheet(master["spotsheet"], industries, color_ids, map_ids)
    out += _jobs(master["jobs"], colors, color_ids, map_ids)
    if {"revision", "effective"} & set(master["schematic"]):
        out.append("schematic: revision and effective come from the title block (hartlib.map_revision); "
                   "leave them out of the master")
    return out
