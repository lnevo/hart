"""The frozen inputs of the generated staging Layout Editor panel (LE cut-over Phase 3b, owner requirement 2026-11-15).

    inputs = le_inputs.load()                       # every build (build_layout_le.py), and build_signals.py
    inputs = le_inputs.from_live(root, panel, ...)  # once, from the hand-drawn panel (build_layout_le.py --freeze)

The generated panel is rebuilt from scratch with no hand-drawn "HART Railroad" panel in the tables: everything the
build used to read off that panel was read once, on 2026-11-15, into layer 1 files in FOLDER
(jmri/layouts/hart/data/schematic/staging_le/), and the build reads only those and the schematic. Edit them there,
not in a panel. Each file starts with a note saying so (a `# ` line in a CSV, `_note` in JSON).

  panel.json     the panel's name, its attributes and drawing options (the generated panel takes them)
  turnouts.csv   each staging Layout Editor turnout: ident, turnout, type, continuing route, the blocks of its legs
  tracks.csv     each track between two turnout legs, or a leg and an end bumper: its ends and blocks in order
  idents.csv     the idents kept: each boundary anchor by its two blocks, each end bumper by its block, the track
                 segment of each block drawn as one segment
  sensors.csv    each Entry/Exit sensor: its slot and the facing and protected blocks JMRI resolves there
  masts.csv      each staging mast: its slot, facing and protected blocks, icon size and hidden flag (the Layout
                 Editor build), and its run on the schematic (build_signals.py writes staging.signals.json from it):
                 `run` is 'toward;far', the far switch left blank at a track end ('3;')
  overlay.json   each icon and label of the overlay with what it is tied to (le_overlay.py)

Main and upper are dark territory (no masts) until the owner's signal plan. Every file is checked for shape on load
(InputsError names the file, the row and the field).
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))      # le_overlay
sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402

FOLDER = paths.LAYOUT_DATA / "schematic" / "staging_le"
PANEL = "HART Railroad"
SIGNALS_SOURCE = "tables.xml"       # what staging.signals.json names as its source: the file it was first read from
NOTE = ("Frozen from the hand-drawn \"{panel}\" panel in {source} on {date} (build_layout_le.py --freeze); the "
        "generated panel is built from this file. Edit here, not in the panel.")
LIST = ";"                          # between the items of a list in one CSV cell

TURNOUT_COLUMNS = ("ident", "turnoutname", "type", "continuing", "blockname", "blockbname", "blockcname",
                   "blockdname")
TRACK_COLUMNS = ("from", "from_leg", "to", "to_leg", "blocks")
IDENT_COLUMNS = ("kind", "ident", "blocks")
SENSOR_COLUMNS = ("sensor", "kind", "ident", "slot", "facing", "protects")
MAST_COLUMNS = ("mast", "kind", "ident", "slot", "turnout", "facing", "protects", "hidden", "icon_w", "icon_h",
                "signal", "toward", "run", "names", "edge_cm", "cm_from_toward", "dir", "signal_kind", "heads",
                "schematic_edge", "schematic_toward_node")
PANEL_FIELDS = {"_note", "name", "attributes", "layoutTrackDrawingOptions"}
SLOT_KINDS = ("anchor", "end bumper", "turnout")
LEGS = ("A", "B", "C", "D")        # a tuple: membership is one whole leg letter, never a substring ("", "AB")
BUMPER = "bumper"                   # tracks.csv to_leg of a track that ends at an end bumper


class InputsError(RuntimeError):
    pass


@dataclass
class Inputs:
    """The frozen inputs, as the build uses them."""
    panel_name: str
    attrs: dict
    drawing_options: ET.Element | None
    turnouts: list[dict]            # {attribute: value} per turnout, as a layoutturnout element's attributes
    chains: list[dict]              # {ends: [(ident, leg) or ("END", bumper)], blocks: [...]}
    boundaries: list[dict]          # {blocks: [a, b], ident}
    ends: dict                      # block: end bumper ident
    segments: dict                  # block: track segment ident
    sensors: list[dict]             # {sensor, kind, ident, slot, facing, protects}
    masts: list[dict]               # one per mast, the columns of masts.csv
    overlay: dict | None = None     # overlay.json (le_overlay validates it)
    note: str = ""

    def turnout_facts(self) -> dict:
        """{ident: facts} as build_layout_le.check_live_turnouts compares them: name, type, continuing route, the
        four leg blocks and the block of the track on each leg."""
        legs = defaultdict(dict)
        for c in self.chains:
            for i in (0, 1):
                ident, leg = c["ends"][i]
                if ident != "END":
                    legs[ident][leg] = c["blocks"][0] if i == 0 else c["blocks"][-1]
        out = {}
        for t in self.turnouts:
            out[t["ident"]] = dict(name=t.get("turnoutname"), type=t.get("type"),
                                   continuing=t.get("continuing") if "XOVER" not in t["type"] else None,
                                   blocks=tuple(t.get(a) for a in ("blockname", "blockbname", "blockcname",
                                                                    "blockdname")),
                                   legs=dict(legs[t["ident"]]))
        return out


# ---------------------------------------------------------------- reading the hand-drawn panel (--freeze)

def live_chains(le: ET.Element) -> list[dict]:
    """Every track between two turnout legs or a leg and an end bumper on a panel: its two ends
    [(ident, leg letter) or ("END", bumper ident)] and its blocks in order from the first end (repeats folded)."""
    segs = {s.get("ident"): s for s in le.findall("tracksegment")}
    pts = {p.get("ident"): p for p in le.findall("positionablepoint")}
    turnouts = {t.get("ident") for t in le.findall("layoutturnout")}
    out, seen = [], set()
    for t in le.findall("layoutturnout"):
        for leg in "abcd":
            first = t.get(f"connect{leg}name")
            if not first:
                continue
            start = (t.get("ident"), f"TURNOUT_{leg.upper()}")
            here, seg, blocks = start, first, []
            for _ in range(len(segs) + 1):
                s = segs.get(seg)
                if s is None:
                    raise InputsError(f"live panel: {here[0]} connects to {seg!r}, which is no track segment")
                if not blocks or blocks[-1] != s.get("blockname"):
                    blocks.append(s.get("blockname"))
                ends = [(s.get("connect1name"), s.get("type1")), (s.get("connect2name"), s.get("type2"))]
                other = ends[1] if ends[0] == here else ends[0]
                if other[1] in ("TURNOUT_A", "TURNOUT_B", "TURNOUT_C", "TURNOUT_D") and other[0] in turnouts:
                    end = (other[0], other[1][-1])
                    break
                p = pts.get(other[0]) if other[1] == "POS_POINT" else None
                if p is None or p.get("type") not in ("ANCHOR", "END_BUMPER"):
                    raise InputsError(f"live panel: track {s.get('ident')} reaches {other[0]} ({other[1]}"
                                      f"{', ' + p.get('type') if p is not None else ''}), which this build does not "
                                      "follow (only turnouts, anchors and end bumpers)")
                if p.get("type") == "END_BUMPER":
                    end = ("END", other[0])
                    break
                here, seg = other, (p.get("connect2name") if p.get("connect1name") == seg else p.get("connect1name"))
            else:
                raise InputsError(f"live panel: the track from {start[0]} leg {leg.upper()} never ends")
            a = (start[0], start[1][-1])
            key = tuple(sorted((a, end)))
            if key not in seen:
                seen.add(key)
                out.append(dict(ends=[a, end], blocks=blocks))
    return out


def staging_idents(live_le: ET.Element, turnouts: dict) -> dict:
    """The plugin's `idents` for staging, from a panel: each switch's turnout ident (`turnouts`, node: ident), each
    anchor between two blocks by that pair, each end bumper by its block, and the track segment of each block the
    panel draws as one segment."""
    segs = {s.get("ident"): s for s in live_le.findall("tracksegment")}
    boundaries, ends, seen_pairs = [], {}, set()
    for p in live_le.findall("positionablepoint"):
        conns = [c for c in (p.get("connect1name"), p.get("connect2name")) if c]
        if not conns or any(c not in segs for c in conns):
            raise InputsError(f"live panel: {p.get('type')} {p.get('ident')} connects to "
                              f"{conns or 'no track'}, not to track segments of the panel")
        blocks = [segs[c].get("blockname") for c in conns]
        if not all(blocks):
            raise InputsError(f"live panel: {p.get('type')} {p.get('ident')} meets a track segment with no block")
        if p.get("type") == "END_BUMPER":
            if blocks[0] in ends:
                raise InputsError(f"live panel: block {blocks[0]} ends at two bumpers ({ends[blocks[0]]}, "
                                  f"{p.get('ident')}): which is which is a guess")
            ends[blocks[0]] = p.get("ident")
        elif p.get("type") == "ANCHOR" and len(blocks) == 2 and blocks[0] != blocks[1]:
            pair = frozenset(blocks)
            if pair in seen_pairs:
                raise InputsError(f"live panel: blocks {sorted(pair)} meet at two anchors: which is which is a guess")
            seen_pairs.add(pair)
            boundaries.append(dict(blocks=sorted(blocks), ident=p.get("ident")))
    count = defaultdict(list)
    for s in segs.values():
        count[s.get("blockname")].append(s.get("ident"))
    one = {b: v[0] for b, v in sorted(count.items()) if b and len(v) == 1}
    return dict(turnouts=dict(turnouts), boundaries=boundaries, ends=ends, segments=one)


def live_sensor_slots(live_le: ET.Element) -> dict:
    """{(ident, slot): sensor} for every sensor a panel binds in a slot (eastboundsensor / westboundsensor on a
    point, sensorA..D on a turnout): the Entry/Exit sensors."""
    out = {}
    for p in live_le.findall("positionablepoint"):
        for slot in ("east", "west"):
            if p.get(f"{slot}boundsensor"):
                out[(p.get("ident"), slot)] = p.get(f"{slot}boundsensor")
    for t in live_le.findall("layoutturnout"):
        for leg in LEGS:
            el = t.find(f"sensor{leg}")
            if el is not None and (el.text or "").strip():
                out[(t.get("ident"), leg)] = el.text.strip()
    return out


def live_sensors(live_le: ET.Element, slots_mod) -> list[dict]:
    """sensors.csv rows: each Entry/Exit sensor with the kind of its slot and the blocks JMRI resolves there."""
    ix = slots_mod.Index(live_le)
    out = []
    for (ident, slot), sensor in sorted(live_sensor_slots(live_le).items()):
        kind = "turnout" if ident in ix.turnouts else (
            "end bumper" if ix.points[ident].get("type") == "END_BUMPER" else "anchor")
        facing, protects = ix.blocks(kind, ident, slot)
        out.append(dict(sensor=sensor, kind=kind, ident=ident, slot=slot, facing=facing, protects=list(protects)))
    return out


def live_icons_hidden(live_le: ET.Element, system: dict) -> dict:
    """{mast system name: hidden} from a panel's icons: hidden only when every icon of that mast is."""
    seen = defaultdict(list)
    for icon in live_le.findall("signalmasticon"):
        name = icon.get("signalmast")
        seen[system.get(name, name)].append(icon.get("hidden") == "yes")
    return {k: all(v) for k, v in seen.items()}


def staging_masts(root: ET.Element, live_le: ET.Element, slots_mod) -> list[dict]:
    """Every mast in a slot of a panel: the slot, the facing and protected blocks and kind of slot JMRI resolves for
    it there, its icon size from its aspect type, and hidden as its icon is; sorted by mast."""
    system = tables.mast_system_names(root)
    hidden = live_icons_hidden(live_le, system)
    out = []
    for m in slots_mod.Index(live_le).masts():
        if not m["facing"]:
            raise InputsError(f"live panel: mast {m['mast']} on {m['kind']} {m['ident']} {m['slot']} has no facing "
                              "block")
        if m["mast"] not in system:
            raise InputsError(f"live panel: mast {m['mast']} is not in the signal mast table")
        size, known = tables.mast_icon_size(system[m["mast"]])
        if not known:
            print(f"  note: mast {m['mast']}: appearance {tables.mast_appearance(system[m['mast']])!r} has no known "
                  f"icon size; drawn as a high mast {size[0]} x {size[1]}")
        out.append(dict(mast=m["mast"], kind=m["kind"], ident=m["ident"], slot=m["slot"],
                        turnout=m.get("turnout") or "", facing=m["facing"], protects=list(m["protects"]),
                        hidden=hidden.get(system[m["mast"]], False), icon=list(size)))
    return sorted(out, key=lambda m: m["mast"])


def join_signals(masts: list[dict], signals: dict, prefix: str) -> list[dict]:
    """The masts with their schematic run from the plugin's signal reader (`signals`: its result for the same panel),
    matched by name (`prefix`, the overrides' mast_prefix, dropped). Every mast needs exactly one run."""
    if signals.get("unplaced"):
        raise InputsError("the signal reader could not place: " + "; ".join(signals["unplaced"]))
    rows = {}
    for r in signals["signals"]:
        if r["mast"] in rows:
            raise InputsError(f"the signal reader gives mast {r['mast']} twice")
        rows[r["mast"]] = r
    out = []
    for m in masts:
        short = m["mast"][len(prefix):] if prefix and m["mast"].startswith(prefix) else m["mast"]
        r = rows.pop(short, None)
        if r is None:
            raise InputsError(f"mast {m['mast']}: the signal reader has no run for {short!r}")
        out.append(dict(m, signal=short, toward=r["toward"], run=list(r["run"]), names=list(r["names"]),
                        edge_cm=r["edge_cm"], cm_from_toward=r["cm_from_toward"], dir=r["dir"],
                        signal_kind=r["kind"], heads=r["heads"], schematic_edge=r["_edge"],
                        schematic_toward_node=r["_toward_node"]))
    if rows:
        raise InputsError(f"the signal reader gives runs for masts not bound on the panel: {sorted(rows)}")
    return out


def from_live(root: ET.Element, live_le: ET.Element, slots_mod, signals: dict, prefix: str, note: str) -> Inputs:
    """The inputs read off the hand-drawn panel `live_le` (all but the overlay, which le_overlay.freeze reads)."""
    if tables.generated_panel(live_le):
        raise InputsError(f"the {live_le.get('name')!r} panel is a generated one (it holds the generated-panel "
                          "marker): the inputs are frozen from the hand-drawn panel only")
    turnouts = []
    for t in live_le.findall("layoutturnout"):
        turnouts.append({a: t.get(a) for a in TURNOUT_COLUMNS if t.get(a) is not None})
    idents = staging_idents(live_le, {})
    opts = live_le.find("layoutTrackDrawingOptions")
    return Inputs(panel_name=live_le.get("name"), attrs=dict(live_le.attrib),
                  drawing_options=opts, turnouts=turnouts, chains=live_chains(live_le),
                  boundaries=idents["boundaries"], ends=idents["ends"], segments=idents["segments"],
                  sensors=live_sensors(live_le, slots_mod),
                  masts=join_signals(staging_masts(root, live_le, slots_mod), signals, prefix), note=note)


# ---------------------------------------------------------------- the files

def _cell(v, what) -> str:
    if isinstance(v, list):
        for x in v:
            if LIST in str(x):
                raise InputsError(f"{what}: {x!r} holds {LIST!r}, the list separator")
        return LIST.join(str(x) for x in v)
    if isinstance(v, bool):
        return "yes" if v else "no"
    if v is None:
        return ""
    return str(v)


def _write_csv(path: Path, note: str, columns, rows) -> None:
    buf = io.StringIO()
    buf.write(f"# {note}\n")
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: _cell(r.get(c), f"{path.name} {c}") for c in columns})
    path.write_text(buf.getvalue(), encoding="utf-8")


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def drawing_options_xml(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    e = ET.fromstring(ET.tostring(el))
    for c in e.iter():
        c.tail = None
        if c.text is not None and not c.text.strip():
            c.text = None
    return ET.tostring(e, encoding="unicode")


def write(inputs: Inputs, folder: Path = FOLDER) -> list[Path]:
    """Write every file of `inputs` into `folder` (made if missing). Returns the paths written."""
    if inputs.overlay is None:
        raise InputsError("no overlay to write (le_overlay.freeze gives it)")
    folder.mkdir(parents=True, exist_ok=True)
    note = inputs.note
    out = []
    p = folder / "panel.json"
    _write_json(p, {"_note": note, "name": inputs.panel_name, "attributes": inputs.attrs,
                    "layoutTrackDrawingOptions": drawing_options_xml(inputs.drawing_options)})
    out.append(p)
    p = folder / "turnouts.csv"
    _write_csv(p, note, TURNOUT_COLUMNS, inputs.turnouts)
    out.append(p)
    p = folder / "tracks.csv"
    rows = []
    for c in inputs.chains:
        (a, la), (b, lb) = c["ends"]
        rows.append({"from": a, "from_leg": la, "to": lb if b == "END" else b, "to_leg": BUMPER if b == "END" else lb,
                     "blocks": c["blocks"]})
    _write_csv(p, note, TRACK_COLUMNS, rows)
    out.append(p)
    p = folder / "idents.csv"
    rows = [dict(kind="boundary", ident=b["ident"], blocks=b["blocks"]) for b in inputs.boundaries]
    rows += [dict(kind="end bumper", ident=i, blocks=[b]) for b, i in inputs.ends.items()]
    rows += [dict(kind="segment", ident=i, blocks=[b]) for b, i in inputs.segments.items()]
    _write_csv(p, note, IDENT_COLUMNS, rows)
    out.append(p)
    p = folder / "sensors.csv"
    _write_csv(p, note, SENSOR_COLUMNS, inputs.sensors)
    out.append(p)
    p = folder / "masts.csv"
    _write_csv(p, note, MAST_COLUMNS, [dict(m, icon_w=m["icon"][0], icon_h=m["icon"][1]) for m in inputs.masts])
    out.append(p)
    p = folder / "overlay.json"
    _write_json(p, inputs.overlay)
    out.append(p)
    return out


def _read_csv(path: Path, columns) -> tuple[str, list[dict]]:
    """(note, rows) of a frozen CSV: its `# ` note line, then exactly `columns`; every row's cells as text."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputsError(f"{paths.rel(path)}: cannot read ({exc}); write it with build_layout_le.py --freeze")
    lines = text.splitlines(keepends=True)
    if not lines or not lines[0].startswith("# "):
        raise InputsError(f"{paths.rel(path)}: the first line must be its '# ' provenance note")
    reader = csv.DictReader(lines[1:])
    if tuple(reader.fieldnames or ()) != tuple(columns):
        raise InputsError(f"{paths.rel(path)}: columns {reader.fieldnames}, expected {list(columns)}")
    rows = []
    for k, r in enumerate(reader, 3):
        if None in r or any(v is None for v in r.values()):
            raise InputsError(f"{paths.rel(path)} line {k}: {len(columns)} cells expected")
        rows.append(dict(r, _line=k))
    return lines[0][2:].rstrip("\n"), rows


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputsError(f"{paths.rel(path)}: cannot read ({exc}); write it with build_layout_le.py --freeze")
    except json.JSONDecodeError as exc:
        raise InputsError(f"{paths.rel(path)}: not JSON ({exc})") from None


def _need(cond, path, row, msg):
    if not cond:
        where = f"{paths.rel(path)}" + (f" line {row['_line']}" if row else "")
        raise InputsError(f"{where}: {msg}")


def _list(v: str) -> list[str]:
    return v.split(LIST) if v else []


def _number(v: str, path, row, col, whole=False):
    try:
        x = int(v) if whole else float(v)
    except ValueError:
        x = None
    _need(x is not None and math.isfinite(x), path, row, f"{col} {v!r} is not a {'whole ' if whole else ''}number")
    return x


def load(folder: Path = FOLDER) -> Inputs:
    """The frozen inputs in `folder`, checked for shape (fields, kinds, numbers, duplicates, references)."""
    import le_overlay

    p = folder / "panel.json"
    panel = _read_json(p)
    _need(isinstance(panel, dict) and set(panel) == PANEL_FIELDS, p, None,
          f"fields {sorted(panel) if isinstance(panel, dict) else panel}, expected {sorted(PANEL_FIELDS)}")
    _need(isinstance(panel["name"], str) and panel["name"], p, None, "name must be the panel's name")
    _need(isinstance(panel["attributes"], dict) and all(isinstance(k, str) and isinstance(v, str)
                                                        for k, v in panel["attributes"].items()),
          p, None, "attributes must be an object of text")
    _need(panel["attributes"].get("name") == panel["name"], p, None, "attributes.name differs from name")
    opts = panel["layoutTrackDrawingOptions"]
    if opts is not None:
        _need(isinstance(opts, str), p, None, "layoutTrackDrawingOptions must be XML text or null")
        try:
            opts = ET.fromstring(opts)
        except ET.ParseError as exc:
            raise InputsError(f"{paths.rel(p)}: layoutTrackDrawingOptions does not parse ({exc})") from None
        _need(opts.tag == "layoutTrackDrawingOptions", p, None, f"layoutTrackDrawingOptions holds a {opts.tag}")
    note = panel["_note"]

    p = folder / "turnouts.csv"
    _n, rows = _read_csv(p, TURNOUT_COLUMNS)
    turnouts, seen = [], set()
    for r in rows:
        _need(r["ident"] and r["ident"] not in seen, p, r, f"ident {r['ident']!r} is empty or given twice")
        seen.add(r["ident"])
        _need(r["turnoutname"] and r["type"] and r["blockname"], p, r, "turnoutname, type and blockname are needed")
        _need(re.fullmatch(r"(RH|LH|WYE)_TURNOUT|(RH|LH|DOUBLE)_XOVER", r["type"]), p, r,
              f"type {r['type']!r} is no Layout Editor turnout type this build draws")
        _need(r["continuing"] in ("", "2", "4"), p, r,
              f"continuing {r['continuing']!r}: JMRI's continuing route is 2 (closed) or 4 (thrown), or blank")
        turnouts.append({k: v for k, v in r.items() if k != "_line" and v != ""})

    p = folder / "tracks.csv"
    _n, rows = _read_csv(p, TRACK_COLUMNS)
    chains = []
    for r in rows:
        _need(r["from"] in seen and r["from_leg"] in LEGS, p, r, f"from {r['from']} leg {r['from_leg']!r}: no such "
              "turnout leg in turnouts.csv")
        if r["to_leg"] == BUMPER:
            _need(r["to"], p, r, "an end bumper ident is needed")
            end = ("END", r["to"])
        else:
            _need(r["to"] in seen and r["to_leg"] in LEGS, p, r, f"to {r['to']} leg {r['to_leg']!r}: no such turnout "
                  f"leg in turnouts.csv (or {BUMPER!r})")
            end = (r["to"], r["to_leg"])
        blocks = _list(r["blocks"])
        _need(blocks and all(blocks), p, r, "blocks must name at least one block")
        chains.append(dict(ends=[(r["from"], r["from_leg"]), end], blocks=blocks))
    legs = [e for c in chains for e in c["ends"] if e[0] != "END"]
    dup = sorted({e for e in legs if legs.count(e) > 1})
    _need(not dup, p, None, f"turnout legs on two tracks: {dup}")

    p = folder / "idents.csv"
    _n, rows = _read_csv(p, IDENT_COLUMNS)
    boundaries, ends, segments, pairs, used = [], {}, {}, set(), set()
    for r in rows:
        blocks = _list(r["blocks"])
        _need(r["ident"] and r["ident"] not in used, p, r, f"ident {r['ident']!r} is empty or given twice")
        used.add(r["ident"])
        if r["kind"] == "boundary":
            _need(len(blocks) == 2 and blocks == sorted(blocks) and blocks[0] != blocks[1], p, r,
                  "a boundary names its two blocks, sorted")
            _need(tuple(blocks) not in pairs, p, r, f"blocks {blocks} meet at two anchors")
            pairs.add(tuple(blocks))
            boundaries.append(dict(blocks=blocks, ident=r["ident"]))
        elif r["kind"] in ("end bumper", "segment"):
            have = ends if r["kind"] == "end bumper" else segments
            _need(len(blocks) == 1 and blocks[0] and blocks[0] not in have, p, r,
                  f"an {r['kind']} names one block, once")
            have[blocks[0]] = r["ident"]
        else:
            _need(False, p, r, f"kind {r['kind']!r} is not boundary, end bumper or segment")

    p = folder / "sensors.csv"
    _n, rows = _read_csv(p, SENSOR_COLUMNS)
    sensors, slots_seen = [], set()
    for r in rows:
        _need(r["sensor"] and r["ident"] and r["facing"], p, r, "sensor, ident and facing are needed")
        _need(r["kind"] in SLOT_KINDS, p, r, f"kind {r['kind']!r} is not one of {', '.join(SLOT_KINDS)}")
        _need(r["slot"] in (LEGS if r["kind"] == "turnout" else ("east", "west")), p, r,
              f"slot {r['slot']!r} is no slot of a {r['kind']}")
        _need(r["kind"] != "turnout" or r["ident"] in seen, p, r, f"turnout {r['ident']} is not in turnouts.csv")
        _need((r["ident"], r["slot"]) not in slots_seen, p, r, f"{r['ident']} {r['slot']} holds two sensors")
        slots_seen.add((r["ident"], r["slot"]))
        sensors.append(dict(sensor=r["sensor"], kind=r["kind"], ident=r["ident"], slot=r["slot"],
                            facing=r["facing"], protects=_list(r["protects"])))

    masts = load_masts(folder)
    for m in masts:
        _need(m["kind"] != "turnout" or m["ident"] in seen, folder / "masts.csv", m,
              f"turnout {m['ident']} is not in turnouts.csv")
        m.pop("_line")

    overlay = _read_json(folder / "overlay.json")
    try:
        le_overlay.validate(overlay, paths.rel(folder / "overlay.json"))
    except le_overlay.OverlayError as exc:
        raise InputsError(str(exc)) from None
    return Inputs(panel_name=panel["name"], attrs=dict(panel["attributes"]), drawing_options=opts,
                  turnouts=turnouts, chains=chains, boundaries=boundaries, ends=ends, segments=segments,
                  sensors=sensors, masts=masts, overlay=overlay, note=note)


def load_masts(folder: Path = FOLDER) -> list[dict]:
    """masts.csv, checked: one row per mast, with its slot, blocks and icon (the build) and its schematic run
    (staging.signals.json). Each row keeps `_line` for messages."""
    p = folder / "masts.csv"
    _n, rows = _read_csv(p, MAST_COLUMNS)
    out, names, signals = [], set(), set()
    for r in rows:
        _need(r["mast"] and r["mast"] not in names, p, r, f"mast {r['mast']!r} is empty or given twice")
        names.add(r["mast"])
        _need(r["signal"] and r["signal"] not in signals, p, r, f"signal {r['signal']!r} is empty or given twice")
        signals.add(r["signal"])
        _need(r["kind"] in SLOT_KINDS, p, r, f"kind {r['kind']!r} is not one of {', '.join(SLOT_KINDS)}")
        _need(r["slot"] in (LEGS if r["kind"] == "turnout" else ("east", "west")), p, r,
              f"slot {r['slot']!r} is no slot of a {r['kind']}")
        _need(r["ident"] and r["facing"], p, r, "ident and facing are needed")
        _need((r["kind"] == "turnout") == bool(r["turnout"]), p, r, "turnout is given for a turnout mast only")
        _need(r["hidden"] in ("yes", "no"), p, r, f"hidden {r['hidden']!r} is not yes or no")
        icon = [_number(r[c], p, r, c, whole=True) for c in ("icon_w", "icon_h")]
        _need(all(v > 0 for v in icon), p, r, f"icon {icon} must be above zero")
        _need(r["dir"] in ("east", "west"), p, r, f"dir {r['dir']!r} is not east or west")
        _need(r["signal_kind"] in ("field", "virtual", "planned"), p, r,
              f"signal_kind {r['signal_kind']!r} is not field, virtual or planned")
        run = r["run"].split(LIST)
        _need(len(run) == 2 and run[0], p, r, f"run {r['run']!r} must be 'toward;far': the switch the mast heads "
              "for, then the one at the run's far end, left blank at a track end ('3;')")
        _need(r["schematic_edge"] and r["schematic_toward_node"], p, r,
              "schematic_edge and schematic_toward_node are needed")
        out.append(dict(mast=r["mast"], kind=r["kind"], ident=r["ident"], slot=r["slot"], turnout=r["turnout"],
                        facing=r["facing"], protects=_list(r["protects"]), hidden=r["hidden"] == "yes", icon=icon,
                        signal=r["signal"], toward=r["toward"], run=run, names=_list(r["names"]),
                        edge_cm=_number(r["edge_cm"], p, r, "edge_cm"),
                        cm_from_toward=_number(r["cm_from_toward"], p, r, "cm_from_toward"), dir=r["dir"],
                        signal_kind=r["signal_kind"], heads=_number(r["heads"], p, r, "heads", whole=True),
                        schematic_edge=r["schematic_edge"], schematic_toward_node=r["schematic_toward_node"],
                        _line=r["_line"]))
    return out


def signal_rows(masts: list[dict]) -> list[dict]:
    """staging.signals.json's signals from masts.csv rows, in the plugin's order (by number, then name)."""
    rows = [dict(mast=m["signal"], toward=m["toward"], run=list(m["run"]), names=list(m["names"]),
                 edge_cm=m["edge_cm"], cm_from_toward=m["cm_from_toward"], dir=m["dir"], kind=m["signal_kind"],
                 heads=m["heads"], source="le_panel", _edge=m["schematic_edge"],
                 _toward_node=m["schematic_toward_node"]) for m in masts]

    def key(r):
        n = re.match(r"\d+", r["mast"])
        return (int(n.group()) if n else 10 ** 9, r["mast"])
    return sorted(rows, key=key)
