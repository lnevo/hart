#!/usr/bin/env python3
"""Staging's facts in the main and upper levels' shape: a device map, control points, masts and their signal plan.

    python3 tools/schematic/staging_device_map.py           # convert again: write the four files where they differ
    python3 tools/schematic/staging_device_map.py --check   # exit 1 if a file differs from a fresh conversion

`make panels` runs it as its staging-map step, before build_signals.py, and tools/check.sh runs --check. --check
prints SKIPPED and exits 0 when the plugin submodule is not checked out (1 with SCHEMATIC_REQUIRED=1), as
build_device_map.py does. It also stops when a staging bean in tables.xml changes, which is the point: the files
must follow the railroad.

One input path for the Layout Editor build. build_layout_le.py draws staging from the frozen hand-drawn panel
(staging_le/, read by le_inputs.py and le_overlay.py) by default, and from these files with `--staging devicemap`
(owner review pending; main and upper come from device_map_main_upper.csv, control_points_main_upper.csv and
main_upper_masts.csv). This script writes staging in that shape, converted from the frozen files, the live
tables.xml beans and the staging control points of staging.plan_overrides.json. Until the switch-over the frozen
files stay the source and this conversion keeps the two equal; afterwards these files are kept by hand and the
conversion goes.

Staging's objects are field devices. The conversion changes the input shape only: every system name, user name and
binding is copied from tables.xml as it is, and the conversion stops if a frozen fact and the tables disagree.

Outputs (jmri/layouts/hart/data/schematic/):
- device_map_staging.csv, build_device_map.COLUMNS. Layers as main and upper: turnout (and its LCC alias
  "DCC Switch <n>"), fb, block, occupancy, mast, head. Staging is the field, so system_name is the live device;
  jmri_name is the name tables.xml and the panels bind it by: a turnout's is the Layout Editor's turnoutname (some
  panels bind "M2T408", some "Switch 23", kept as they are), every other row's its system name. node and dcc are
  read off the bean's comment ("Node: 4 Turnout: 0 | DCC: 100"). trial_name is the link to the drawing, as for main
  and upper (placeholders(), below).
- control_points_staging.csv, the columns of control_points_main_upper.csv, from staging.plan_overrides.json's
  control_points (the station names: Brick, Plane, ...). The overrides stay the schematic's source; --check keeps
  this file in step.
- staging_masts.csv, hartlib.level_masts.FIELDS. A mast's kind of slot follows from its row (mast_kind): a switch
  number means a turnout mast, no protected block an end bumper (buffer stop) mast, else an anchor mast. Hidden is
  a virtual mast (IF$vsm), its icon size hartlib.tables.mast_icon_size. The conversion checks all three against the
  frozen masts.csv.
- staging_signals.csv (SIGNAL_COLUMNS): each mast's signal-plan facts (its schematic run, lengths, direction,
  kind and heads), the frozen masts.csv's columns of those names. build_signals.py writes staging.signals.json from
  it and staging_masts.csv (load_signal_masts).

Readers that took staging from the frozen files read these instead (2026-11-17): build_signals.py
(load_signal_masts, and staging_chains for the track lengths), build_cats_panel.py (staging_chains),
hartlib.railroad's staging masts and check_layout_facts.py (staging_masts.csv), test_le_mast_parity.py
(mast_facts). The frozen files stay the source of this conversion until staging switches to the device-map path;
--check holds the two forms equal.

Trial names (placeholders()): the drawing's own keys for staging, as placeholder_names gives main and upper theirs.
- turnout: "Switch <n>" (both halves of a single crossover: one turnout).
- OS block: "OS Switch <n>" of a plain switch; "OS <n> at <node>" of a crossover half (staging's crossovers 7, 23
  and 35 have an OS block per half: OS Switch 7 and 7b, 23a and 23b, 35a and 35b; the half's key is not written as
  a block name, so check_name_copies.py does not take it for one).
- track block: "Track <strand>" for a track of one block, "Track <strand> <k>/<n>" for the k-th of its n blocks from
  the strand's first end (S-1 is "Track e23 1/3" West, "2/3" the body, "3/3" East). Strand and node ids are the
  plan's (as main and upper's "Track <edge>"); --check stops when the plan renames one.
A block that several tracks or a switch share lists every placeholder, comma separated.

load() reads the three files back for the builder (no frozen staging_le file): the plugin's names for the staging
band, each check failing loudly (a placeholder no row names, a row the drawing does not use, a broken k/n run).

The panel's own icons and labels are not device facts and are not here: the status cluster, captions and backdrop
are in panel_items.json (panel_items.py); the occupancy lamps and station clusters are parked with the Dispatcher
System (jmri/layouts/hart/parked/staging_panel_lamps.json).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_device_map as bdm  # noqa: E402  COLUMNS, natural, read_csv, check_virtual, MapError
import le_common as lc  # noqa: E402  the band key, plugin, solved schematic and the files the build reads
import le_names as ln  # noqa: E402  runs, crossovers and the staging binding as built today (read only)
import build_main_upper_masts as bmm  # noqa: E402  LEGS: two masts on one block pair, by letter
import publish_draft as pd  # noqa: E402  DATA and the plugin cache
from hartlib import level_masts, paths, railroad, tables  # noqa: E402

LEVEL = 1
DEVICE_MAP = pd.DATA / "device_map_staging.csv"
CPS = pd.DATA / "control_points_staging.csv"
MASTS = pd.DATA / "staging_masts.csv"
SIGNALS = pd.DATA / "staging_signals.csv"
OVERRIDES = pd.DATA / "staging.plan_overrides.json"
# staging_signals.csv: the signal-plan facts build_signals.py writes staging.signals.json from (the frozen masts.csv's
# columns of the same names); lists inside a cell are LIST separated, as in the frozen file
SIGNAL_COLUMNS = ["mast", "signal", "toward", "run", "names", "edge_cm", "cm_from_toward", "dir", "signal_kind",
                  "heads", "schematic_edge", "schematic_toward_node"]
LIST = ";"
CP_COLUMNS = ["cp_id", "cp_name", "level", "switches", "area", "notes"]
LAYERS = ("turnout", "fb", "block", "occupancy", "mast", "head")
DCC_NOTE = "LCC alias of the MQTT turnout (ADR-005)"
TRACK_RE = re.compile(r"Track (\S+?)(?: (\d+)/(\d+))?")
TURNOUT_COMMENT = re.compile(r"Node: (\d+) Turnout: \d+(?: \| DCC: (\d+))?")
NODE_COMMENT = re.compile(r"Node: (\d+) ")


class StagingMapError(RuntimeError):
    pass


# ---------------------------------------------------------------- placeholders: the drawing's keys

def crossover_halves(band) -> dict:
    """{node: other half} for each switch that is half of a single crossover (two switches of one label joined C to C,
    build_layout_le.crossover_strands)."""
    out = {}
    for sid in ln.crossover_strands(band):
        u, v = band["strands"][sid]["src"][0], band["strands"][sid]["dst"][0]
        out[u], out[v] = v, u
    return out


def placeholders(band) -> tuple[dict, dict, list]:
    """({switch node: turnout placeholder}, {switch node: OS placeholder}, [strand ids that carry blocks]) of the
    staging band. Inner crossover strands carry none (the plugin draws them inside the crossover)."""
    halves = crossover_halves(band)
    turnouts, os_ = {}, {}
    for n, d in sorted(band["nodes"].items()):
        if d["kind"] == "dx":
            raise StagingMapError(f"staging switch {d.get('label')}: a double crossover, which staging has none of")
        if d["kind"] != "switch":
            continue
        label = lc.bare(d.get("label"))
        if not re.fullmatch(r"\d+", label or ""):
            raise StagingMapError(f"staging switch node {n}: label {d.get('label')!r} is no switch number")
        turnouts[n] = f"Switch {label}"
        os_[n] = f"OS {label} at {n}" if n in halves else f"OS Switch {label}"
    inner = ln.crossover_strands(band)
    return turnouts, os_, sorted(s for s in band["strands"] if s not in inner)


def track_placeholder(sid: str, k: int, count: int) -> str:
    return f"Track {sid}" if count == 1 else f"Track {sid} {k}/{count}"


def split_names(cell: str) -> list[str]:
    return [t.strip() for t in (cell or "").split(",") if t.strip()]


# ---------------------------------------------------------------- the conversion (one time, --check)

def bean_comment(el) -> str:
    return (el.findtext("comment") or "").strip()


def node_of(comment: str) -> str:
    m = NODE_COMMENT.match(comment)
    return m.group(1) if m else ""


def row(layer, user, system, jmri, *, cp="", node="", dcc="", comment="", trial="", notes="") -> dict:
    return dict(level=str(LEVEL), cp=cp, layer=layer, user_name=user, system_name=system, jmri_name=jmri, node=node,
                dcc=dcc, comment=comment, trial_name=trial, notes=notes)


def staging_band():
    """The staging band as build_layout_le.py draws it (the plugin's drawn_bands: the preferences' le_shift and
    le_longer_straights): (band, its options, the plugin's core)."""
    _sheet, le_mod, core = lc.plugin()
    bands, page = lc.schematic()
    try:
        bands = le_mod.drawn_bands(bands, page)
    except core.SchematicError as exc:
        raise StagingMapError(f"schematic le: {exc}") from None
    keys = [lc.band_key(t) for t, _b, _o in bands]
    if lc.STAGING not in keys:
        raise StagingMapError(f"no {lc.STAGING} band in the schematic (bands: {', '.join(keys)})")
    _t, band, opts = bands[keys.index(lc.STAGING)]
    return band, opts, core


def control_points(overrides: dict) -> tuple[list[dict], dict]:
    """(control_points_staging.csv rows, {switch: cp name}) from staging.plan_overrides.json's control_points."""
    cps = overrides.get("control_points")
    if not isinstance(cps, dict) or not cps:
        raise StagingMapError(f"{OVERRIDES.name}: no control_points object")
    rows, cp_of = [], {}
    for name, cp in cps.items():
        code = (cp or {}).get("code")
        switches = (cp or {}).get("switches")
        if not (isinstance(code, str) and re.fullmatch(r"[A-Z]{2}", code)) or not switches:
            raise StagingMapError(f"{OVERRIDES.name}: control point {name!r} needs a two-letter code and switches")
        for s in switches:
            if s in cp_of:
                raise StagingMapError(f"{OVERRIDES.name}: switch {s} is in {cp_of[s]} and {name}")
            cp_of[s] = name
        rows.append(dict(cp_id=f"cp_{code.lower()}", cp_name=name, level=str(LEVEL), switches=",".join(switches),
                         area=name, notes=f"station code {code} (staging.plan_overrides.json)"))
    return rows, cp_of


def mast_kind(r: dict) -> str:
    """The kind of slot a staging_masts.csv row stands in: a switch number means a turnout leg, no protected block an
    end bumper, else an anchor."""
    if r["switch"]:
        return "turnout"
    return "end bumper" if not r["protects"] else "anchor"


def convert(root, inputs, band, tidy, overrides: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """(device map rows, control point rows, mast rows) of staging. `root`: the live tables; `inputs`: the frozen
    staging_le files (le_inputs.load()); `band`: the staging band; `tidy`: the plugin's core.tidy."""
    names = ln.staging_names(band, inputs, tidy)        # the binding the build uses today, from the frozen files
    turnout_ph, os_ph, strands = placeholders(band)
    cp_rows, cp_of = control_points(overrides)
    turnouts = tables.by_any_name(tables.turnouts(root))
    sensors = tables.by_any_name(tables.sensors(root))
    heads = tables.by_any_name(tables.signal_heads(root))
    masts = {tables.user_name(m): m for m in tables.masts(root)}
    blocks = {tables.user_name(b): b for b in tables.blocks(root)}
    bad = []

    def need(table, name, what):
        el = table.get(name)
        if el is None:
            bad.append(f"{what} {name!r} is not in tables.xml")
        return el

    rows = []
    # turnouts: one per live turnout (a crossover's two halves are one), its LCC alias and its two feedback sensors
    by_turnout = defaultdict(set)
    for n, name in names["turnouts"].items():
        by_turnout[name].add(turnout_ph[n])
    switch_of = {}
    for name, phs in sorted(by_turnout.items()):
        if len(phs) != 1:
            bad.append(f"turnout {name} is drawn as switches {sorted(phs)}")
            continue
        t = need(turnouts, name, "turnout")
        if t is None:
            continue
        user, system, comment = tables.user_name(t), tables.system_name(t), bean_comment(t)
        number = next(iter(phs)).removeprefix("Switch ")
        if user != f"Switch {number}":
            bad.append(f"turnout {name}: user name {user!r}, the drawing's switch is {number}")
        switch_of[name] = number
        m = TURNOUT_COMMENT.match(comment)
        if not m or not m.group(2):
            bad.append(f"turnout {user}: comment {comment!r} gives no node and DCC address")
            continue
        cp = cp_of.get(number, "")
        rows.append(row("turnout", user, system, name, cp=cp, node=m.group(1), dcc=m.group(2), comment=comment,
                        trial=next(iter(phs))))
        alias = need(turnouts, f"DCC {user}", "LCC alias")
        if alias is not None:
            a_comment = bean_comment(alias)
            rows.append(row("turnout", f"DCC {user}", tables.system_name(alias), tables.system_name(alias), cp=cp,
                            node=node_of(a_comment), dcc=m.group(2), comment=a_comment, notes=DCC_NOTE))
        for attr in ("sensor2", "sensor1"):             # N then R, as the device map lists them
            s = need(sensors, t.get(attr), f"turnout {user} {attr}")
            if s is not None:
                s_comment = bean_comment(s)
                rows.append(row("fb", tables.user_name(s), tables.system_name(s), tables.system_name(s), cp=cp,
                                node=node_of(s_comment), comment=s_comment))
    # blocks: each with every placeholder that names it, and its occupancy sensor
    trial = defaultdict(list)
    for n, block in names["os"].items():
        trial[block].append(os_ph[n])
    drawn = set(names["blocks"])
    if drawn != set(strands):
        bad.append(f"tracks the binding and the placeholders disagree on: {sorted(drawn ^ set(strands))}")
    for sid in strands:
        bl = names["blocks"].get(sid) or []
        for k, block in enumerate(bl, 1):
            trial[block].append(track_placeholder(sid, k, len(bl)))
    occupied, occ_of = defaultdict(list), {}
    os_cp = {}
    for n, block in names["os"].items():
        os_cp[block] = cp_of.get(lc.bare(band["nodes"][n]["label"]), "")
    for block, phs in sorted(trial.items()):
        b = need(blocks, block, "block")
        if b is None:
            continue
        occ = (b.findtext("occupancysensor") or "").strip()
        s = need(sensors, occ, f"block {block}'s occupancy sensor") if occ else None
        if not occ:
            bad.append(f"block {block} has no occupancy sensor")
        node = node_of(bean_comment(s)) if s is not None else ""
        rows.append(row("block", block, tables.system_name(b), tables.system_name(b), cp=os_cp.get(block, ""),
                        node=node, comment=bean_comment(b), trial=", ".join(phs)))
        if s is not None:
            occupied[tables.system_name(s)].append(block)
            occ_of[tables.system_name(s)] = s
    # one occupancy row per detector: a throat block and its yard track, or a stub and its switch, share one
    for system, bl in sorted(occupied.items()):
        s = occ_of[system]
        rows.append(row("occupancy", tables.user_name(s), system, system, cp=next((os_cp[b] for b in bl
                                                                                   if os_cp.get(b)), ""),
                        node=node_of(bean_comment(s)), comment=bean_comment(s), notes="blocks " + "; ".join(bl)))
    # masts and their heads
    mast_rows = []
    seen_heads = set()
    for fm in sorted(inputs.masts, key=lambda m: m["mast"]):
        m = need(masts, fm["mast"], "mast")
        if m is None:
            continue
        system, comment = tables.system_name(m), bean_comment(m)
        cp = comment.split("|", 1)[0].strip()
        if cp not in {r["cp_name"] for r in cp_rows}:
            bad.append(f"{fm['mast']}: comment {comment!r} names no staging control point first")
            continue
        head_names = level_masts.mast_heads(system)
        head_pairs, node = [], ""
        for h in head_names:
            he = need(heads, h, f"{fm['mast']}'s head")
            if he is None:
                continue
            head_pairs.append(f"{h}={tables.user_name(he)}")
            node = node or node_of(bean_comment(he))
            if h not in seen_heads:
                seen_heads.add(h)
                rows.append(row("head", tables.user_name(he), h, h, cp=cp, node=node_of(bean_comment(he)),
                                comment=bean_comment(he)))
        protects = ";".join(fm["protects"])
        rows.append(row("mast", fm["mast"], system, system, cp=cp, node=node, comment=comment,
                        notes=f"facing {fm['facing']}" + (f" into {protects}" if protects else ", buffer stop")))
        switch = switch_of.get(fm["turnout"], "") if fm["turnout"] else ""
        if fm["turnout"] and not switch:
            bad.append(f"{fm['mast']}: turnout {fm['turnout']} is not a drawn staging turnout")
        mr = dict(mast=fm["mast"], cp=cp, switch=switch, facing=fm["facing"], protects=protects, leg="",
                  system_name=system, head_system_names=";".join(head_pairs), device_system_name=system)
        # the rules the builder places masts by give what the frozen file says
        size, known = tables.mast_icon_size(system)
        if mast_kind(mr) != fm["kind"]:
            bad.append(f"{fm['mast']}: kind by rule {mast_kind(mr)}, frozen {fm['kind']}")
        if system.startswith("IF$vsm:") != fm["hidden"]:
            bad.append(f"{fm['mast']}: hidden {fm['hidden']}, but {'a' if fm['hidden'] else 'no'} virtual mast "
                       f"({system})")
        if not known or list(size) != list(fm["icon"]):
            bad.append(f"{fm['mast']}: icon {list(size)} by rule ({'known' if known else 'unknown'} appearance), "
                       f"frozen {fm['icon']}")
        mast_rows.append(mr)
    pairs = defaultdict(list)
    for mr in mast_rows:
        if mr["protects"]:
            pairs[(mr["facing"], mr["protects"])].append(mr)
    for (facing, protects), group in pairs.items():
        if len(group) > 1:
            letters = {g["mast"][-1]: g for g in group}
            if len(group) != 2 or set(letters) != set(bmm.LEGS):
                bad.append(f"masts {[g['mast'] for g in group]} share {facing} into {protects}")
                continue
            for letter, g in letters.items():
                g["leg"] = bmm.LEGS[letter]
    if bad:
        raise StagingMapError("staging conversion: " + "; ".join(bad))
    order = {layer: i for i, layer in enumerate(LAYERS)}
    rows.sort(key=lambda r: (order[r["layer"]], railroad.natural(r["user_name"])))
    check_rows(rows)
    mast_rows.sort(key=lambda r: (int(re.search(r"\d+", r["mast"]).group()), r["mast"]))
    return rows, cp_rows, mast_rows


def occupancy_blocks(r: dict) -> list[str]:
    """The blocks an occupancy row's notes say its detector serves ("blocks Track S-1; Track S-1 West")."""
    if not r["notes"].startswith("blocks "):
        return []
    return [b.strip() for b in r["notes"].removeprefix("blocks ").split(";") if b.strip()]


def check_rows(rows: list[dict]) -> None:
    """Every block has exactly one occupancy row naming it; no two rows of one layer share a system name or (but the
    turnouts' LCC aliases, their own devices) a jmri_name; every row is a whole field device."""
    bad = []
    blocks = [r["user_name"] for r in rows if r["layer"] == "block"]
    served = [b for r in rows if r["layer"] == "occupancy" for b in occupancy_blocks(r)]
    if sorted(blocks) != sorted(served):
        bad.append(f"blocks and occupancy rows differ: {sorted(set(blocks) ^ set(served))} "
                   f"(or one is served twice)")
    for layer in LAYERS:
        mine = [r for r in rows if r["layer"] == layer]
        for col in ("system_name", "jmri_name", "user_name"):
            vals = [r[col] for r in mine]
            if not all(vals) or len(set(vals)) != len(vals):
                bad.append(f"{layer} rows: a {col} is empty or given twice")
    if bad:
        raise StagingMapError("staging device map: " + "; ".join(bad))


def texts(root=None, inputs=None) -> dict[Path, str]:
    """{path: text} of the three files from a fresh conversion (default: the live tables and the frozen files)."""
    import le_inputs
    root = tables.read(paths.TABLES_XML) if root is None else root
    inputs = le_inputs.load() if inputs is None else inputs
    band, _opts, core = staging_band()
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    rows, cp_rows, mast_rows = convert(root, inputs, band, core.tidy, overrides)
    return {DEVICE_MAP: bdm.csv_text(rows), CPS: bdm.csv_text(cp_rows, CP_COLUMNS),
            MASTS: bdm.csv_text(mast_rows, level_masts.FIELDS), SIGNALS: signals_text(inputs.masts)}


def signals_text(frozen_masts: list[dict]) -> str:
    """staging_signals.csv: each staging mast's signal-plan facts (the frozen masts.csv's schematic-run columns,
    which build_signals.py writes staging.signals.json from), one row per mast, in mast order."""
    rows = [{c: (LIST.join(m[c]) if isinstance(m[c], list) else str(m[c])) for c in SIGNAL_COLUMNS}
            for m in sorted(frozen_masts, key=lambda m: m["mast"])]
    return bdm.csv_text(rows, SIGNAL_COLUMNS)


def load_signal_masts(path: Path | None = None, masts_path: Path | None = None) -> list[dict]:
    """The staging masts as build_signals.py reads them: staging_signals.csv's plan facts joined with
    staging_masts.csv's blocks and slot kind (mast_kind), in the shape of le_inputs.load_masts (the fields its
    signal_rows and build_signals.check_lengths read). Stops on a mast in one file and not the other, or a value
    that is not as the frozen file held it."""
    path, masts_path = path or SIGNALS, masts_path or MASTS
    plan = read_rows(path, SIGNAL_COLUMNS)
    blocks = {r["mast"]: r for r in read_rows(masts_path, level_masts.FIELDS)}
    if {r["mast"] for r in plan} != set(blocks):
        raise StagingMapError(f"{paths.rel(path)} and {paths.rel(masts_path)} name different masts: "
                              f"{sorted({r['mast'] for r in plan} ^ set(blocks))}")
    out, bad = [], []
    for i, r in enumerate(plan, 2):
        try:
            run = r["run"].split(LIST)
            if len(run) != 2 or not run[0] or r["dir"] not in ("east", "west") or \
                    r["signal_kind"] not in ("field", "virtual", "planned"):
                raise ValueError("run, dir or signal_kind")
            b = blocks[r["mast"]]
            out.append(dict(mast=r["mast"], kind=mast_kind(b), facing=b["facing"],
                            protects=[x for x in b["protects"].split(";") if x], signal=r["signal"],
                            toward=r["toward"], run=run, names=[x for x in r["names"].split(LIST) if x],
                            edge_cm=float(r["edge_cm"]), cm_from_toward=float(r["cm_from_toward"]), dir=r["dir"],
                            signal_kind=r["signal_kind"], heads=int(r["heads"]), schematic_edge=r["schematic_edge"],
                            schematic_toward_node=r["schematic_toward_node"]))
        except (ValueError, KeyError) as exc:
            bad.append(f"line {i} ({r['mast']}): {exc}")
    if bad:
        raise StagingMapError(f"{paths.rel(path)}: " + "; ".join(bad))
    return out


def staging_chains(band, names: dict) -> list[dict]:
    """The staging tracks between switches and ends, in the shape of le_inputs' frozen chains (tracks.csv):
    [{ends: [(Layout Editor ident or "END", band port), ...], blocks: [...]}], each a run of the band (through
    turnbacks) with its blocks from the device map (load()) in order. A switch's ident is switches.csv's le_ident
    (names["idents"]); the port is the band's, not a Layout Editor leg letter."""
    nodes = band["nodes"]
    idents = names["idents"]["turnouts"]
    out = []
    for start, seq, end in run_blocks(band, names):
        ends = [("END", str(e[1])) if nodes[e[0]]["kind"] != "switch" else (idents[e[0]], str(e[1]))
                for e in (start, end)]
        out.append(dict(ends=ends, blocks=seq))
    return out


def run_blocks(band, names: dict) -> list[tuple]:
    """[(start (node, port), [block, ...], end (node, port))]: each run of the band (le_names.runs: tracks joined
    through turnbacks, crossover insides left out) with its blocks from `names` in order from its start; a block
    that runs on through a turnback (Brick-Plane) counted once."""
    out = []
    for start, chain, end in ln.runs(band, ln.crossover_strands(band)):
        seq = []
        for sid, rev in chain:
            bl = names["blocks"][sid]
            for b in (bl[::-1] if rev else bl):
                if not seq or seq[-1] != b:
                    seq.append(b)
        out.append((start, seq, end))
    return out


def mast_facts(device_map: Path = DEVICE_MAP, masts_path: Path = MASTS) -> dict:
    """{mast: {kind, facing, protects, hidden, turnout}} of every staging mast from staging_masts.csv: its slot kind
    (mast_kind), blocks, hidden (a virtual mast) and, for a turnout mast, the turnout name the panels bind its switch
    by (the device map's jmri_name)."""
    turnout_of = {r["trial_name"].removeprefix("Switch "): r["jmri_name"]
                  for r in read_rows(device_map, bdm.COLUMNS) if r["layer"] == "turnout" and r["trial_name"]}
    out = {}
    for r in read_rows(masts_path, level_masts.FIELDS):
        kind = mast_kind(r)
        if kind == "turnout" and r["switch"] not in turnout_of:
            raise StagingMapError(f"{paths.rel(masts_path)}: {r['mast']} is on switch {r['switch']}, which the "
                                  "device map has no turnout for")
        out[r["mast"]] = dict(kind=kind, facing=r["facing"], protects=[b for b in r["protects"].split(";") if b],
                              hidden=r["system_name"].startswith("IF$vsm:"),
                              **({"turnout": turnout_of[r["switch"]]} if kind == "turnout" else {}))
    return out


# ---------------------------------------------------------------- reading back (the builder's side)

def read_rows(path: Path, columns) -> list[dict]:
    try:
        rows = lc.read_csv(path)
    except OSError as exc:
        raise StagingMapError(f"cannot read {paths.rel(path)}: {exc}") from None
    if not rows:
        raise StagingMapError(f"{paths.rel(path)}: no rows")
    if list(rows[0]) != list(columns):
        raise StagingMapError(f"{paths.rel(path)}: columns {list(rows[0])}, not {list(columns)}")
    return rows


def closed_legs() -> dict:
    """{OS block: closed leg block} of every staging switch (switch_legs.csv, ADR-021)."""
    return {r["os_block"]: r["closed_leg"] for r in lc.read_csv(lc.SWITCH_LEGS)}


def leg_first_blocks(band, names: dict) -> dict:
    """{(switch node, leg): first block past the switch's own OS block along that leg}: along the run of tracks from
    that leg (through turnbacks), else the OS block of the switch at the run's far end; None at a bumper."""
    nodes = band["nodes"]
    out = {}
    for start, seq, end in run_blocks(band, names):
        for here, there, blocks_ in ((start, end, seq), (end, start, seq[::-1])):
            if nodes[here[0]]["kind"] != "switch":
                continue
            own = names["os"][here[0]]
            got = next((b for b in blocks_ if b != own), None)
            if got is None and nodes[there[0]]["kind"] == "switch":
                got = names["os"][there[0]]
            out[tuple(here)] = got
    return out


def normal_legs(band, names: dict) -> dict:
    """{plain switch node: "B" or "C"}: the drawn leg whose first block is the switch's closed leg in switch_legs.csv
    ("Track S-4 West" counts as S-4, as build_layout_le.staging_names reads it)."""
    closed = closed_legs()
    first = leg_first_blocks(band, names)
    halves = crossover_halves(band)
    track = lambda b: re.sub(r" (East|West)$", "", b or "")      # noqa: E731
    out, bad = {}, []
    for n, d in sorted(band["nodes"].items()):
        if d["kind"] != "switch" or n in halves:
            continue
        want = closed.get(names["os"][n])
        if want is None:
            bad.append(f"switch {d['label']}: {names['os'][n]} is not in switch_legs.csv")
            continue
        legs = [p for p in "BC" if first.get((n, p)) == want or track(first.get((n, p))) == want]
        if len(legs) != 1:
            bad.append(f"switch {d['label']}: closed leg {want} is first past {len(legs)} of its legs "
                       f"(B: {first.get((n, 'B'))}, C: {first.get((n, 'C'))})")
            continue
        out[n] = legs[0]
    if bad:
        raise StagingMapError("staging normal legs: " + "; ".join(bad))
    return out


def load(band, device_map: Path = DEVICE_MAP, masts_path: Path = MASTS, cps_path: Path = CPS,
         turnout_idents: bool = True) -> dict:
    """The plugin's names for the staging band from the three files alone: turnouts, os, blocks, normal (from
    switch_legs.csv), masts, and with `turnout_idents` each turnout's Layout Editor ident from switches.csv
    (le_ident, ADR-021). Stops on any placeholder no row names, any row the drawing does not use, a broken k/n run,
    or a mast row that is not well formed."""
    rows = read_rows(device_map, bdm.COLUMNS)
    cp_names = {r["cp_name"] for r in read_rows(cps_path, CP_COLUMNS)}
    turnout_ph, os_ph, strands = placeholders(band)
    by_ph, bad = {}, []
    for i, r in enumerate(rows, 2):
        if r["layer"] not in LAYERS:
            bad.append(f"line {i}: layer {r['layer']!r}")
            continue
        if r["level"] != str(LEVEL):
            bad.append(f"line {i}: level {r['level']!r}, staging is {LEVEL}")
        if r["cp"] and r["cp"] not in cp_names:
            bad.append(f"line {i}: cp {r['cp']!r} is no staging control point")
        if not (r["user_name"] and r["system_name"] and r["jmri_name"]):
            bad.append(f"line {i}: user_name, system_name and jmri_name are needed for a field device")
        phs = split_names(r["trial_name"])
        if phs and r["layer"] not in ("turnout", "block"):
            bad.append(f"line {i}: a {r['layer']} row has a trial_name")
        for ph in phs:
            if ph in by_ph:
                bad.append(f"line {i}: trial_name {ph} is given to {by_ph[ph][1]} and {r['user_name']}")
            by_ph[ph] = (r["layer"], r["user_name"], r["jmri_name"])
    if bad:
        raise StagingMapError(f"{paths.rel(device_map)}: " + "; ".join(bad))
    used = set()

    def get(ph, layer):
        got = by_ph.get(ph)
        if got is None or got[0] != layer:
            bad.append(f"no {layer} row has trial_name {ph}")
            return None
        used.add(ph)
        return got[2] if layer == "turnout" else got[1]

    names = dict(turnouts={n: get(ph, "turnout") for n, ph in turnout_ph.items()},
                 os={n: get(ph, "block") for n, ph in os_ph.items()}, blocks={})
    runs = defaultdict(dict)
    for ph, (layer, _u, _j) in by_ph.items():
        m = TRACK_RE.fullmatch(ph)
        if layer == "block" and m:
            k, count = (int(m.group(2)), int(m.group(3))) if m.group(2) else (1, 1)
            runs[m.group(1)][k] = (count, ph)
    for sid in strands:
        got = runs.pop(sid, {})
        counts = {c for c, _ph in got.values()}
        if len(counts) != 1 or sorted(got) != list(range(1, next(iter(counts)) + 1)):
            bad.append(f"track {sid}: blocks {sorted(ph for _c, ph in got.values()) or 'none'} are not 1/n to n/n")
            continue
        names["blocks"][sid] = [get(got[k][1], "block") for k in sorted(got)]
    for sid, got in runs.items():
        bad.append(f"trial names for track {sid}, which the staging drawing does not have: "
                   f"{sorted(ph for _c, ph in got.values())}")
    unused = sorted(set(by_ph) - used - {ph for got in runs.values() for _c, ph in got.values()})
    if unused:
        bad.append(f"trial names the staging drawing does not have: {unused}")
    if bad:
        raise StagingMapError(f"{paths.rel(device_map)}: " + "; ".join(bad))
    names["normal"] = normal_legs(band, names)
    if turnout_idents:
        ident_of = {r["switch"]: r["le_ident"] for r in lc.read_csv(lc.SWITCHES)}
        idents = {}
        for n, ph in turnout_ph.items():
            ident = ident_of.get(ph.removeprefix("Switch "))
            if not ident:
                bad.append(f"{ph} has no le_ident in switches.csv")
            idents[n] = ident
        names["idents"] = dict(turnouts=idents, boundaries=[], ends={}, segments={})
    names["masts"] = load_masts(masts_path, cp_names, rows)
    if bad:
        raise StagingMapError("; ".join(bad))
    return names


def load_masts(path: Path, cp_names: set, device_rows: list[dict]) -> list[dict]:
    """The plugin's staging masts from staging_masts.csv: each with its facing and protected blocks, its kind of slot
    (mast_kind), hidden for a virtual mast and its icon size (hartlib.tables.mast_icon_size). Stops on a row whose
    mast, heads or system name the device map does not hold as the same mast."""
    rows = read_rows(path, level_masts.FIELDS)
    dev = {(r["layer"], r["user_name"]): r for r in device_rows}
    heads = {r["system_name"]: r["user_name"] for r in device_rows if r["layer"] == "head"}
    out, bad, seen = [], [], set()
    for i, r in enumerate(rows, 2):
        name = r["mast"]
        d = dev.get(("mast", name))
        if name in seen or d is None:
            bad.append(f"line {i}: mast {name!r} given twice or not in the device map")
            continue
        seen.add(name)
        if r["system_name"] != d["system_name"] or r["device_system_name"] != d["system_name"]:
            bad.append(f"line {i}: {name} system name {r['system_name']!r}, the device map's {d['system_name']!r}")
        if r["cp"] not in cp_names or not r["facing"]:
            bad.append(f"line {i}: {name} needs a staging control point and a facing block")
        pairs = [tuple(h.split("=", 1)) for h in r["head_system_names"].split(";") if h]
        if [h for h, *_ in pairs] != level_masts.mast_heads(r["system_name"]) or \
                any(len(p) != 2 or heads.get(p[0]) != p[1] for p in pairs):
            bad.append(f"line {i}: {name} heads {r['head_system_names']!r} are not its system name's heads as the "
                       "device map names them")
        if r["leg"] not in ("", *bmm.LEGS.values()):
            bad.append(f"line {i}: {name} leg {r['leg']!r}")
        size, known = tables.mast_icon_size(r["system_name"])
        if not known:
            bad.append(f"line {i}: {name}: no icon size for {r['system_name']}")
        protects = [b for b in r["protects"].split(";") if b]
        entry = dict(mast=name, facing=r["facing"], protects=protects, kind=mast_kind(r),
                     hidden=r["system_name"].startswith("IF$vsm:"), icon=list(size))
        if r["leg"]:
            entry["leg"] = r["leg"]
        if entry["kind"] == "end bumper":       # may stand at a helix join instead (le_names.plugin_masts does too)
            entry["or_join"] = True
        out.append(entry)
    if bad:
        raise StagingMapError(f"{paths.rel(path)}: " + "; ".join(bad))
    return sorted(out, key=lambda m: m["mast"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a file differs from a fresh conversion")
    args = ap.parse_args(argv)
    if not args.check:
        message = paths.check_only_message(Path(__file__).name)
        if message:
            print(f"ERROR: {message}")
            return 1
    try:
        lc.plugin()
    except lc.BuildError as exc:
        if not args.check:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"SKIPPED staging device map check: {exc}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    try:
        with pd.cache_on():
            want = texts()
    except (StagingMapError, lc.BuildError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    stale = [p for p, text in want.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale:
            print(f"{paths.rel(p)} is stale: run python3 tools/schematic/staging_device_map.py", file=sys.stderr)
        if not stale:
            print("ok: " + ", ".join(p.name for p in want) + " current")
        return 1 if stale else 0
    for p in stale:
        p.write_text(want[p], encoding="utf-8")
        print(f"wrote {paths.rel(p)}")
    counts = defaultdict(int)
    for r in csv.DictReader(io.StringIO(want[DEVICE_MAP])):
        counts[r["layer"]] += 1
    print("device map: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
