#!/usr/bin/env python3
"""Staging's signal masts by rule (owner, 2026-11-18/19), written into the files the staging builds read.

    python3 tools/schematic/build_staging_masts.py           # write the files
    python3 tools/schematic/build_staging_masts.py --check   # exit 1 if a file is stale
    python3 tools/schematic/build_staging_masts.py --show    # print the masts, write nothing

When the plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and exits 0 (1 with
SCHEMATIC_REQUIRED=1, set in CI), as the other schematic checks do; a write or --show names the fault and exits 2.

The masts come from the one mast process every level uses (mast_plan.plan, owner 2026-11-20): home masts,
running track and exit dwarfs by rule, intermediates and virtual masts only as destinations, over staging's
interlockings (interlockings.csv, level 1: Brick 1, 3, 5; Barn 7; East End 23, 31, 33; Princess 35, 37, 39) and the
staging device map's block layer with block_lengths.csv. Staging's control_points stay the stations the drawings group
by (brackets on the station sheets, gantries on the panels); a mast's cp column names the control point of its
switch. What this script adds is staging's own:
- a mast stands at its switch's leg when the block boundary is there (a turnout mast), else on the anchor where the
  switch's own OS block ends (an anchor mast, no switch: Mast 8RA on Scale, 25 cm from Switch 7);
- intermediates carry no line code (prototype numbering: MP 6.7 gives Mast 67 west and Mast 68 east).

Heads are internal, from the mast's name (IH:HART:C1:<n><L|R>[A|B][_Top|_Bottom]: hartlib.level_devices names main
and upper the same way under C3), so nothing unwired reaches MQTT: signal_coordinator.py publishes only IH and
digits.

A wired head is read from device_map_staging.csv itself, as main and upper swap a physical device in through the
device map's jmri_name (build_device_map.py): a head row whose jmri_name is not the internal name of its user name is
wired (today one: Head 6LB on IH432, Switch 5, owner 2026-11-18), and the rebuild keeps it, with its node and notes.
The build stops on a head row whose system_name and jmri_name differ, a wired head that is not an LCOS head (IH and
digits), whose mast the rule does not place, or whose mast the rule gives a different set of heads; on a mast row
that names an IH-digits head that is not one of its own wired head rows; and if a wired head is missing from the rows
it writes. A wired mast keeps its node, or takes its wired heads' node when its row has none.

Virtual masts (IF$vsm, hidden, one-low) only where a visible mast's route reaches a buffer stop first (mast_plan;
owner, 2026-11-20): 4LA, 4LB, 10LA, 10LB and 12L. Each keeps the system name its device-map row had, a new one the
next ordinal of staging's thousand (mast_plan.virtual_system_names); a dropped one's ordinal stays in
retired_virtual_masts.csv.

Writes (jmri/layouts/hart/data/schematic/): staging_masts.csv, staging_signals.csv, and the staging mast and head
rows of ../devices.csv (written_by build_staging_masts.py; hartlib.devices holds it to those rows), then the three
files devices.csv generates, device_map_staging.csv among them (each mast and head row's system_name and jmri_name
are its JMRI name; there is no planned physical head for the internal ones).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_device_map as bdm  # noqa: E402
import mast_plan  # noqa: E402  the one mast process for every level
import mast_rule  # noqa: E402
import publish_draft as pd  # noqa: E402
import le_names as ln  # noqa: E402
import staging_device_map as sdm  # noqa: E402
from hartlib import devices, level_masts, railroad  # noqa: E402

DATA = pd.DATA
MASTS, SIGNALS, DEVICE_MAP = sdm.MASTS, sdm.SIGNALS, sdm.DEVICE_MAP
WRITES = ("mast", "head")              # the layers of the devices.csv rows this script holds (written_by below)


def device_files() -> devices.Files:
    """The master and its generated files as build() uses them: DEVICE_MAP, as it is when it runs (a test may patch it)."""
    return devices.Files.under(DEVICE_MAP.parent.parent)
CPS, OVERRIDES = sdm.CPS, sdm.OVERRIDES
INTERLOCKINGS = DATA / "interlockings.csv"   # the signal rule's control points, every level (owner, 2026-11-20)
SPLIT = DATA / "block_splits.csv"            # the owner's block splits, every level (none on staging)
LEVELS = {"Staging": 1}
HEAD_PREFIX = "IH:HART:C1:"
FACTS = railroad.DEVICE_FACTS          # the device map's fact columns; a mast row fills switch, facing, protects, dir
HEAD_USER = re.compile(r"Head (\d+[LR]?[A-Z]?)(?: (Top|Bottom))?")   # a staging head's user name: key, position
WIRED_HEAD = re.compile(r"IH\d+")      # an LCOS head: signal_coordinator.py publishes IH and digits to MQTT


class RuleError(RuntimeError):
    pass


def internal_head(user: str) -> str:
    """The internal system name of a staging head from its user name: "Head 24RA Top" -> IH:HART:C1:24RA_Top.
    RuleError on a user name that is not Head <key>[ Top| Bottom]."""
    m = HEAD_USER.fullmatch(user)
    if not m:
        raise RuleError(f"head {user!r} is not named Head <key>[ Top| Bottom]")
    return HEAD_PREFIX + m.group(1) + (f"_{m.group(2)}" if m.group(2) else "")


def head_users(mast: str, heads: int) -> list[str]:
    """A mast's head user names, in order: Top and Bottom on a two-head mast."""
    key = mast.removeprefix("Mast ")
    return [f"Head {key}"] if heads == 1 else [f"Head {key} {p}" for p in ("Top", "Bottom")]


def wired_heads(rows: list[dict]) -> dict:
    """{mast: {head user name: head row}} of the device map's wired heads: a head row whose jmri_name is not the
    internal name of its user name. RuleError on a head row named twice, a head row whose system_name and jmri_name
    differ (either may hold the wiring), a wired head that is not IH and digits, or a mast row that names an IH-digits
    head that is not one of its own wired head rows."""
    out, seen, bad = {}, set(), []
    for r in (r for r in rows if r["layer"] == "head"):
        user = r["user_name"]
        if user in seen:
            bad.append(f"head {user} has two rows")
            continue
        seen.add(user)
        internal = internal_head(user)
        if r["system_name"] != r["jmri_name"]:
            bad.append(f"head {user}: system_name {r['system_name']!r} and jmri_name {r['jmri_name']!r} differ "
                       f"(a staging head row gives its JMRI name in both)")
        elif r["jmri_name"] == internal:
            continue
        elif not WIRED_HEAD.fullmatch(r["jmri_name"]):
            bad.append(f"head {user}: jmri_name {r['jmri_name']!r} is neither {internal} nor a wired IH<digits>")
        else:
            out.setdefault("Mast " + HEAD_USER.fullmatch(user).group(1), {})[user] = r
    for r in (r for r in rows if r["layer"] == "mast" and r["system_name"].startswith("IF$shsm:")):
        own = {h["jmri_name"] for h in out.get(r["user_name"], {}).values()}
        stray = sorted(set(re.findall(r"\((IH\d+)\)", r["system_name"])) - own)
        if stray:
            bad.append(f"mast {r['user_name']} names wired head(s) {stray} that are not its own head rows")
    if bad:
        raise RuleError(f"{DEVICE_MAP.name}: " + "; ".join(bad))
    return out


def head_names(mast: str, heads: int, wired: dict) -> list[tuple[str, str]]:
    """[(system name, user name)] of a mast's heads: the wired heads' names (wired_heads) on a wired mast, else the
    internal names. RuleError when the rule gives a wired mast heads other than those the device map wires."""
    users = head_users(mast, heads)
    if mast not in wired:
        return [(internal_head(u), u) for u in users]
    if sorted(wired[mast]) != sorted(users):
        raise RuleError(f"{mast}: the rule gives {heads} head(s) ({', '.join(users)}), {DEVICE_MAP.name} wires "
                        f"{len(wired[mast])} ({', '.join(sorted(wired[mast]))})")
    return [(wired[mast][u]["jmri_name"], u) for u in users]


def block_cm() -> dict:
    """{block: cm} of the plan lengths in block_lengths.csv (hartlib.railroad.plan_cm), as build_signals.py reads
    them."""
    return railroad.plan_cm(railroad.read_block_lengths(railroad.Sources.under().block_lengths))


def with_lengths(runs: list, cm: dict) -> list:
    """`runs` (staging_device_map.run_blocks) when `cm` gives every block on them a length; RuleError naming the
    blocks it does not (a block with no plan length has no place to put a mast)."""
    missing = sorted({b for _start, seq, _end in runs for b in seq} - set(cm))
    if missing:
        raise RuleError(f"block_lengths.csv has no plan length for {missing}")
    return runs


def plan_edge(band, sids) -> tuple[str, list[str]]:
    """(the plan graph edge a run's strands come from, every track name that edge carries), as build_signals.py
    checks a mast's schematic run: one edge, a strand's own suffix (".0", ".1") dropped."""
    strands = band["strands"]
    edges = sorted({re.sub(r"\.\d+$", "", strands[s]["edge"]) for s in sids})
    if len(edges) != 1:
        raise RuleError(f"a mast's run spans plan edges {edges}")
    names = sorted({strands[s]["name"] for s in strands
                    if re.sub(r"\.\d+$", "", strands[s]["edge"]) == edges[0] and strands[s]["name"]})
    return edges[0], names


def run_strands(band) -> dict:
    """{(node, port): [strand ids]} of the run that leaves each switch leg (le_names.runs, crossover insides left out)."""
    out = {}
    for start, chain, end in ln.runs(band, ln.crossover_strands(band)):
        sids = [sid for sid, _rev in chain]
        out[tuple(start)] = out[tuple(end)] = sids
    return out


def generate(band, names: dict, planned: dict, cm: dict, wired: dict) -> list[dict]:
    """The visible staging masts in the columns the files take, from mast_plan.plan's home masts and intermediates on
    the staging band (`names`: the device map's block layer, `cm`: block_cm; a mast in `wired`, from wired_heads, is a
    field signal): [{mast, cp, switch, facing, protects, kind, heads, dir, toward, run, names, edge_cm,
    cm_from_toward, edge, node}], in name order. A home mast stands at its switch's leg when the block boundary is
    there (a turnout mast), else on the anchor where the switch's own OS block ends (an anchor mast, no switch)."""
    seqs = {}                      # (node, leg) -> the blocks from that switch leg along its run
    for start, seq, end in with_lengths(mast_plan.run_blocks(band, names), cm):
        seqs[tuple(start)] = (seq, tuple(end))
        seqs[tuple(end)] = (seq[::-1], tuple(start))
    strands, nodes = band["strands"], band["nodes"]
    chains = run_strands(band)
    out = []
    for m in planned["home"]:
        n, p = m["node"], m["leg"]
        seq, far = seqs[(n, p)]
        own = names["os"][n]
        at_turnout = not seq or seq[0] != own
        facing = next((b for b in seq if b != own), None)
        if facing is None:
            far_node = nodes[far[0]]
            facing = names["os"].get(far[0]) if far_node["kind"] == "switch" else None
        if facing is None:
            raise RuleError(f"switch {m['switch']} leg {p}: no block to face")
        edge, names_ = plan_edge(band, chains[(n, p)])
        track_cm = sum(cm[b] for b in seq)
        back = 0.0
        if not at_turnout:
            # the boundary from this switch by block lengths, or from the track's far end when the timed blocks (which
            # count the switches' own length) put it past the track the plan draws: build_signals.check_lengths takes
            # either end, and the plugin draws the mast at that distance from its toward end (draw.mast_piece)
            back = sum(cm[b] for b in seq[:seq.index(facing)])
            drawn = sum(strands[s]["cm"] for s in chains[(n, p)])
            if back > drawn:
                back = track_cm - back
        far_label = nodes[far[0]].get("label") if nodes[far[0]]["kind"] == "switch" else ""
        out.append(dict(mast=f"Mast {m['name']}", cp=m["cp"], switch=m["switch"] if at_turnout else "",
                        facing=facing, protects=own, kind=m["kind"], heads=m["heads"],
                        dir=m["dir"], toward=m["switch"],
                        run=f"{m['switch']};{mast_rule.base(far_label) if far_label else ''}", names=names_,
                        edge_cm=round(track_cm, 1), cm_from_toward=round(back, 1), edge=edge, node=n,
                        leg=p, strand=m["strand"], running=m["running"]))
    for x in planned["intermediates"]:
        edge, track_names = plan_edge(band, chains[tuple(x["start"])])
        out.append(dict(mast=f"Mast {x['name']}", cp=x["cp"], switch="", facing=x["facing"],
                        protects=x["protects"], kind="one-searchlight", heads=1, dir=x["dir"],
                        toward=x["toward"], run=f"{x['toward']};{x['other']}", names=track_names,
                        edge_cm=x["total"], cm_from_toward=x["dist"], edge=edge, node=x["to"][0],
                        milepost=x["milepost"]))
    for m in out:                    # home and intermediate alike: a mast with wired heads is a field signal
        m["signal_kind"] = "field" if m["mast"] in wired else "planned"
    taken = [m["mast"] for m in out]
    if len(set(taken)) != len(taken):
        raise RuleError(f"the rule names a mast twice: {sorted({x for x in taken if taken.count(x) > 1})}")
    return sorted(out, key=lambda m: (int(re.search(r"\d+", m["mast"]).group()), m["mast"]))


VIRTUAL_KIND = "one-low"


def virtual_masts(band, planned: dict, cps: dict) -> list[dict]:
    """Staging's hidden routing masts in the columns generate() gives, from mast_plan.plan's virtual masts (only where
    a visible mast's route reaches a buffer stop first, owner 2026-11-20: 4LA, 4LB, 10LA, 10LB, 12L), `cps` naming
    each switch's control point (the drawings')."""
    chains = run_strands(band)
    out = []
    for m in planned["virtual"]:
        edge, track_names = plan_edge(band, chains[(m["node"], m["leg"])])
        out.append(dict(mast=f"Mast {m['name']}", cp=cps[m["switch"]], kind=VIRTUAL_KIND, heads=1,
                        toward=m["switch"], run=f"{m['switch']};", names=track_names, edge_cm=m["total"],
                        edge=edge, node=m["node"], signal_kind="virtual", switch="", facing=m["facing"],
                        protects="", cm_from_toward=m["total"], dir=m["dir"]))
    return out


def virtual_rows(vgen: list[dict], old_rows: list[dict]) -> list[dict]:
    """staging_masts.csv rows of the virtual masts: each keeps the system name its old device-map row gives it (a
    VirtualSignalMast's ordinal, $1001 ...), and a new one takes the next ordinal of staging's thousand
    (mast_plan.virtual_system_names), so no system name shifts."""
    old = {r["user_name"]: r["system_name"] for r in old_rows
           if r["layer"] == "mast" and level_masts.virtual_ordinal(r["system_name"])}
    try:
        names = mast_plan.virtual_system_names([m["mast"].removeprefix("Mast ") for m in vgen], 1, old)
    except mast_rule.MapError as exc:
        raise RuleError(str(exc)) from None
    return [dict(mast=m["mast"], cp=m["cp"], switch=m["switch"], facing=m["facing"], protects=m["protects"],
                 dir=m["dir"], leg="", system_name=names[m["mast"].removeprefix("Mast ")], head_system_names="",
                 device_system_name=names[m["mast"].removeprefix("Mast ")]) for m in vgen]


def interlockings(switches: set, path: Path = INTERLOCKINGS) -> dict:
    """{switch: interlocking} of staging's interlockings (interlockings.csv, level 1; hartlib.railroad
    .read_interlockings checks the whole file). Stops on a switch that is not a staging switch."""
    try:
        rows = railroad.read_interlockings(path, (1,))
    except railroad.FactsError as exc:
        raise RuleError(str(exc)) from None
    out, bad = {}, []
    for r in rows:
        for s in r.switches:
            if s not in switches:
                bad.append(f"{r.name}: switch {s} is no staging switch")
            out[s] = r.name
    if bad:
        raise RuleError(f"{path.name}: " + "; ".join(bad))
    return out


def mast_rows(gen: list[dict], wired: dict) -> list[dict]:
    rows = []
    for m in gen:
        heads = head_names(m["mast"], m["heads"], wired)
        system = f"IF$shsm:basic:{m['kind']}(" + ")(".join(h for h, _u in heads) + ")"
        rows.append(dict(mast=m["mast"], cp=m["cp"], switch=m["switch"], facing=m["facing"], protects=m["protects"],
                         dir=m["dir"], leg="", system_name=system, head_system_names=";".join(f"{h}={u}" for h, u in heads),
                         device_system_name=system))
    return rows


def signal_rows(gen: list[dict]) -> list[dict]:
    return [dict(mast=m["mast"], signal=m["mast"].removeprefix("Mast "), toward=m["toward"], run=m["run"],
                 names=sdm.LIST.join(m["names"]), edge_cm=f"{m['edge_cm']:.1f}", cm_from_toward=f"{m['cm_from_toward']:.1f}",
                 dir=m["dir"], signal_kind=m["signal_kind"], heads=str(m["heads"]), schematic_edge=m["edge"],
                 schematic_toward_node=m["node"]) for m in gen]


def csv_text(rows: list[dict], columns) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def mast_node(mast: str, old: dict | None, heads: dict) -> str:
    """The node of a mast row: none on an internal mast; on a wired one its old row's node, or, when that is blank
    (a newly wired mast), the node its wired head rows share. RuleError when they name different nodes or none."""
    if not heads:
        return ""
    if old and old["node"]:
        return old["node"]
    nodes = sorted({h["node"] for h in heads.values()})
    if len(nodes) != 1 or not nodes[0]:
        raise RuleError(f"{DEVICE_MAP.name}: wired {mast} has no node and its head rows give {nodes or 'none'}: "
                        f"set the mast row's node")
    return nodes[0]


def device_rows(gen_masts: list[dict], virtual: list[dict], old_rows: list[dict], wired: dict) -> list[dict]:
    """device_map_staging.csv with its mast and head rows replaced: one mast row per mast (generated and virtual) and
    one head row per head of a visible mast, every name its JMRI name; a wired mast keeps its node (mast_node), a
    wired head its node and notes (wired_heads); other rows unchanged and in place. RuleError if a wired head would be
    dropped."""
    keep = [r for r in old_rows if r["layer"] not in ("mast", "head")]
    old_mast = {r["user_name"]: r for r in old_rows if r["layer"] == "mast"}
    masts, heads = [], []
    for r in gen_masts + virtual:
        on = wired.get(r["mast"], {})
        where = " | ".join(x for x in (r["cp"], f"Switch {r['switch']}" if r["switch"] else "") if x)
        note = (f"facing {r['facing']} into {r['protects']}" if r["protects"] else f"facing {r['facing']}, buffer stop")
        masts.append(dict(level="1", cp=r["cp"], layer="mast", user_name=r["mast"], system_name=r["system_name"],
                          jmri_name=r["system_name"], node=mast_node(r["mast"], old_mast.get(r["mast"]), on),
                          dcc="", comment=where, trial_name="", notes=note, **{**dict.fromkeys(FACTS, ""),
                          "switch": r["switch"], "facing": r["facing"], "protects": r["protects"], "dir": r["dir"]}))
        for pair in [x for x in r["head_system_names"].split(";") if x]:
            h, user = pair.split("=", 1)
            prev = on.get(user)
            heads.append(dict(level="1", cp=r["cp"], layer="head", user_name=user, system_name=h, jmri_name=h,
                              node=prev["node"] if prev else "", dcc="", comment=where, trial_name="",
                              notes=prev["notes"] if prev else "internal, not wired", **dict.fromkeys(FACTS, "")))
    written = {(h["user_name"], h["jmri_name"]) for h in heads}
    lost = sorted(f"{u} ({h['jmri_name']})" for m in wired.values() for u, h in m.items()
                  if (u, h["jmri_name"]) not in written)
    if lost:
        raise RuleError(f"the rebuild would drop wired head(s) {lost} from {DEVICE_MAP.name}")
    return keep + sorted(masts, key=lambda r: r["user_name"]) + sorted(heads, key=lambda r: r["user_name"])


def plan(band, bands, joined, runs, names: dict, locks: dict, cm: dict) -> dict:
    """mast_plan.plan over the staging level: its tracks by mast_rule (a helix end tagged H, no helix blocks), its
    interlockings (`locks`), its device map's block layer (`names`, of `band`, the staging band of `bands`) and block
    lengths (`cm`), the owner's block splits. RuleError when `band` is not the staging band `bands` holds."""
    found = mast_rule.tracks(bands, runs, joined, {1: "H"}, levels=LEVELS)
    mast_rule.track_names(found)
    bi = [i for i, (title, _b, _o) in enumerate(bands) if mast_rule.band_level(title, LEVELS)]
    if len(bi) != 1 or set(bands[bi[0]][1]["strands"]) != set(band["strands"]):
        raise RuleError(f"the solved sheet has {len(bi)} staging band(s), or its staging band is not the device map's")
    return mast_plan.plan(bands, joined, found, levels=LEVELS, cp_of=locks, layer={bi[0]: names}, cm=cm,
                          split=mast_rule.read_block_splits(SPLIT, found, LEVELS))


def build():
    """({path: text} of every file this script writes, the visible masts, the virtual masts by rule)."""
    with pd.cache_on():
        band, _opts, _core = sdm.staging_band()
        bands, joined, runs, _corners = bdm.solve()
    names = sdm.load(band, device_map=DEVICE_MAP, with_masts=False)
    cp_of = {s.strip(): r["cp_name"] for r in sdm.read_rows(CPS, sdm.CP_COLUMNS) for s in r["switches"].split(",")}
    locks = interlockings(set(cp_of))
    files = device_files()
    problems = devices.stale(files)       # the master is read below: stop if it or the files generated from it are off
    if problems:
        raise RuleError("; ".join(problems))
    old = devices.device_map_rows(devices.load(files), ("1",))    # the master's staging rows, as the old file reads
    wired = wired_heads(old)
    cm = block_cm()
    planned = plan(band, bands, joined, runs, names, locks, cm)
    gen = generate(band, names, planned, cm, wired)
    unplaced = sorted(set(wired) - {m["mast"] for m in gen})
    if unplaced:
        raise RuleError(f"{DEVICE_MAP.name} wires heads on masts the rule does not place: "
                        + "; ".join(f"{m} ({', '.join(sorted(wired[m]))})" for m in unplaced))
    for m in gen:                    # the cp column names the control point (the drawings') of the mast's switch
        m["cp"] = cp_of[m["toward"]]
    vgen = virtual_masts(band, planned, cp_of)
    gm = mast_rows(gen, wired)
    vr = virtual_rows(vgen, old)
    taken = [r["system_name"] for r in gm + vr]
    if len(set(taken)) != len(taken):
        raise RuleError(f"two masts share a system name: {sorted({x for x in taken if taken.count(x) > 1})}")
    mine = [r for r in device_rows(gm, vr, old, wired) if r["layer"] in WRITES]   # the mast and head rows only
    want = {MASTS: csv_text(gm + vr, level_masts.FIELDS),
            SIGNALS: csv_text(signal_rows(gen + vgen), sdm.SIGNAL_COLUMNS),
            **devices.outputs_after("build_staging_masts.py", mine, files)}
    return want, gen, vgen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="exit 1 if a file is stale")
    g.add_argument("--show", action="store_true", help="print the masts and write nothing")
    args = ap.parse_args(argv)
    try:
        sdm.lc.plugin()
    except sdm.lc.BuildError as exc:
        if args.check:
            print(f"SKIPPED staging masts check: {exc}")
            return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
        print(f"build_staging_masts.py: {exc}", file=sys.stderr)
        return 2
    try:
        want, gen, vgen = build()
    except (RuleError, sdm.StagingMapError, sdm.lc.BuildError, mast_rule.MapError, railroad.FactsError) as exc:   # DevicesError is a FactsError
        print(f"build_staging_masts.py: {exc}", file=sys.stderr)
        return 2
    if args.show:
        for m in gen + vgen:
            print(f"{m['mast']:10} {m['kind']:16} {m['heads']}h  {m['facing']:22} -> {m['protects']:16} "
                  f"{'switch ' + m['switch'] if m['switch'] else 'anchor':10} {m['dir']}"
                  + (f"  MP {m['milepost']}" if "milepost" in m else ""))
        return 0
    stale = [p for p, text in want.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale:
            print(devices.stale_message(p, device_files(), "tools/schematic/build_staging_masts.py"), file=sys.stderr)
        return 1 if stale else 0
    for p in stale:
        p.write_text(want[p], encoding="utf-8")
        print(f"wrote {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
