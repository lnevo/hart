#!/usr/bin/env python3
"""Every level's signal masts (owner, 2026-11-18/19/20/21): masts.csv, the level a column, and the planned level's
mast and head rows of the device master.

    python3 tools/schematic/build_masts.py           # write the files
    python3 tools/schematic/build_masts.py --check   # exit 1 if a file is stale
    python3 tools/schematic/build_masts.py --show    # print the masts this script places, write nothing

When the plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and exits 0 (1 with
SCHEMATIC_REQUIRED=1, set in CI), as the other schematic checks do; a write or --show names the fault and exits 2.

Two parts:
1. The mast and head rows of the planned level (PLANNED_LEVEL, staging) from the one mast process every level uses
   (mast_plan.plan, owner 2026-11-20) over its device map's block layer; main and upper's rows are
   build_device_map.py's (the same mast_plan over their own block layer, with their LCOS head plan), until the block
   layer is one process.
2. masts.csv for every level from the device master's mast and head rows (file_rows, one transform; the file's rules
   are hartlib.level_masts), with the plan facts (level_masts.PLAN_FIELDS: where the drawing puts each mast) of the
   masts part 1 places.

Part 1, the rule: home masts, running track and exit dwarfs by rule, intermediates and virtual masts only as
destinations, over the level's interlockings (interlockings.csv, level 1: Brick 1, 3, 5; Barn 7; East End 23, 31, 33;
Princess 35, 37, 39) and its device map's block layer with block_lengths.csv. Staging's control_points stay the
stations the drawings group by (brackets on the station sheets, gantries on the panels); a mast's cp column names the
control point of its switch. Over a block layer of its own:
- a mast stands at its switch's leg when the block boundary is there (a turnout mast), else on the anchor where the
  switch's own OS block ends (an anchor mast, no switch: Mast 8RA on Scale, 25 cm from Switch 7, before 2026-11-20);
- intermediates carry no line code (prototype numbering: MP 6.7 gives Mast 67 west and Mast 68 east).

Heads are internal, from the mast's name and level (level_masts.head_name: IH:HART:C1:<n><L|R>[A|B][_Top|_Bottom],
main and upper the same under C3), so nothing unwired reaches MQTT: signal_coordinator.py publishes only IH and
digits.

A wired head is a head row of wiring.csv of the planned level (hartlib.wiring, the physical wiring source; today one:
Head 6LB on IH432, Switch 5, one high head since the owner dropped IH433 on 2026-11-19): the rebuild writes its
address, node and wiring text (its JMRI comment, hartlib.tables_build) from there, and its notes from its field row
(devices_field.csv: the owner's words, which say so), else wiring.csv's, else "wired". A field head row must be a
wiring.csv head. The build stops on a wired head that is not an LCOS head (IH and digits), whose mast the rule does
not place, or whose mast the rule gives a different set of heads, and if a wired head is missing from the rows it
writes. A wired mast takes its node from its field row, or its wired heads' node when it has none. The owner's cells
(CARRIED) are read from devices_field.csv alone (field_rows), never back from this script's last output.

Virtual masts (IF$vsm, hidden, one-low) only where a visible mast's route reaches a buffer stop first (mast_plan;
owner, 2026-11-20): staging's 4LA, 4LB, 10LA, 10LB and 12L. Each keeps the system name its device-map row had, a new
one the next ordinal of its level's thousand (mast_plan.virtual_system_names); a dropped one's ordinal stays in
retired_virtual_masts.csv. The ordinals it gave are its one read-back of its own output (devices.allocated_names), so
no name shifts.

Writes (jmri/layouts/hart/data/schematic/): masts.csv, and the planned level's mast and head rows of ../devices_field.csv and devices_generated.csv
(written_by build_masts.py; hartlib.devices holds it to those rows, and the master is read and written only through
hartlib.devices). On staging each mast and head row's system_name and jmri_name are its JMRI name; on main and upper
system_name is the planned physical part, so masts.csv's device_system_name keeps it.
"""
from __future__ import annotations

import argparse
import csv
import io
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
from hartlib import devices, level_masts, railroad, wiring  # noqa: E402

DATA = pd.DATA
MASTS, DEVICE_MAP = level_masts.PATH, sdm.DEVICE_MAP     # masts.csv, every level; the device master
WRITER = Path(__file__).name           # the written_by of the device master rows this script holds
WRITES = ("mast", "head")              # the layers of the device master rows this script holds (written_by below)


def device_files() -> devices.Files:
    """The master (the only device file) as build() uses it: DEVICE_MAP, as it is when it runs (a test may patch it)."""
    return devices.Files.under(DEVICE_MAP.parent)
STATIONS = sdm.STATIONS
INTERLOCKINGS = DATA / "interlockings.csv"   # the signal rule's control points, every level (owner, 2026-11-20)
LEVELS = mast_rule.band_levels(sdm.overrides())     # {band title: level}: staging's
PLANNED_LEVEL = sdm.LEVEL              # the level whose mast and head rows this script plans (staging, below)
# the levels a home mast may stand at no switch, as an anchor mast where its switch's OS block ends past the leg: the
# levels this script plans from a block layer of its own. Main and upper's OS blocks end at their switches
# (build_device_map.py), so a home mast at no switch there lost its switch
ANCHOR_LEVELS = (PLANNED_LEVEL,)
FACTS = railroad.DEVICE_FACTS          # the device map's fact columns; a mast row fills switch, facing, protects, dir
HEAD_USER = level_masts.HEAD_USER     # a head's user name: its mast's key, position
WIRED_HEAD = level_masts.WIRED_HEAD   # an LCOS head: signal_coordinator.py publishes IH and digits to MQTT
# the note of a head on its internal name (no field head drives it), with the owner's decision (2026-11-19)
INTERNAL_HEAD_NOTE = "internal, not wired (owner, 2026-11-19)"
WIRING_TEXT = devices._NODE_TEXT       # a wired head's comment is its wiring (Node: ...), as the master tells it
# the owner's cells of a mast or head (devices_field.csv, not the rule's): a wired mast's node, a wired head's notes.
# carried() is the one place that reads them, from the field row field_rows gives.
CARRIED = {"mast": ("node",), "head": ("notes",)}


class RuleError(RuntimeError):
    pass


def internal_head(user: str) -> str:
    """The internal system name of a head of the planned level from its user name (level_masts.head_name): "Head 24RA
    Top" -> IH:HART:C1:24RA_Top. RuleError on a user name that is not Head <key>[ Top| Bottom]."""
    try:
        return level_masts.head_name(user, PLANNED_LEVEL)
    except ValueError as exc:
        raise RuleError(str(exc)) from None


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


def carried(prior: dict | None, layer: str) -> dict:
    """The cells (CARRIED[layer]) a rebuilt mast or head row takes from its field row, {} when there is none."""
    return {c: prior[c] for c in CARRIED[layer]} if prior else {}


def field_rows(files: devices.Files | None = None) -> dict[str, list[dict]]:
    """{layer: field rows} of staging's mast and head rows in devices_field.csv (the owner's cells, CARRIED), read
    from the field file alone."""
    out: dict[str, list[dict]] = {"mast": [], "head": []}
    for k, f in devices.field_index(files or device_files()).items():
        if k[0] == str(PLANNED_LEVEL) and k[1] in out:
            out[k[1]].append(dict(f))
    return out


def allocated_masts(files: devices.Files | None = None) -> list[dict]:
    """Staging's mast rows as this script last wrote them, for the virtual masts' ordinals alone (virtual_rows): its
    one read-back of its own output (devices.allocated_names), so no system name shifts."""
    return [dict(r) for r in devices.allocated_names((str(PLANNED_LEVEL),), "mast", files=files or device_files()).values()]


def wiring_heads(owned: list[dict], path: Path | None = None) -> dict:
    """{mast: {head user name: head row}} of the wired heads: wiring.csv's level 1 head rows (`path`, default the
    committed file), the physical wiring source, each with its address, node and wiring text from there and its notes
    from its field row (`owned`: the field file's staging head rows, field_rows), else wiring.csv's, else "wired".
    RuleError on a field head row that wiring.csv does not list, or a wiring.csv head that is not a staging head
    name."""
    by_user = {h["user_name"]: h for h in owned}
    try:
        heads = [w for w in wiring.read(path) if w.level == 1 and w.kind == "head"]
        nodes = bdm.staging_nodes()
    except (railroad.FactsError, bdm.MapError) as exc:
        raise RuleError(str(exc)) from None
    out, bad = {}, [f"{wiring.PATH.name} line {w.line}: {w.device} is on node {w.node}, no staging node "
                    f"({', '.join(map(str, sorted(nodes)))})" for w in heads if w.node not in nodes]
    for w in heads:
        m = HEAD_USER.fullmatch(w.device)
        if not m:
            bad.append(f"{wiring.PATH.name} line {w.line}: {w.device!r} is not a staging head name (Head <mast>)")
            continue
        prev = by_user.pop(w.device, None)              # the owner's notes of the head, if any
        row = dict(user_name=w.device, system_name=w.address, jmri_name=w.address, node=str(w.node),
                   comment=w.wiring_text, notes=carried(prev, "head").get("notes") or w.notes or "wired")
        out.setdefault("Mast " + m.group(1), {})[w.device] = row
    for user in sorted(by_user):
        bad.append(f"{devices.FIELD_FILE}: {devices.key_text((str(PLANNED_LEVEL), 'head', user))} has no head row in "
                   f"{wiring.PATH.name}: add its wiring there, or remove the field row")
    if bad:
        raise RuleError("; ".join(bad))
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


def generate(band, names: dict, planned: dict, cm: dict, wired: dict, parts: dict) -> list[dict]:
    """The visible staging masts in the columns the files take, from mast_plan.plan's home masts and intermediates on
    the staging band (`names`: the device map's block layer, `cm`: block_cm; a mast in `wired`, from wired_heads, is a
    field signal): [{mast, cp, switch, facing, protects, kind, heads, dir, toward, run, names, edge_cm,
    cm_from_toward, edge, node, role}], in name order; role (hartlib.devices.ROLES) is home or intermediate, as the
    plan places the mast, and goes to its device-master row (with_roles). A home mast stands at its switch's leg when the block boundary is
    there (a turnout mast), else on the anchor where the switch's own OS block ends (an anchor mast, no switch); a
    part of the OS block (a JMRI block of its own, owner 2026-11-20) is inside it, as mast_plan reads the layer
    (staging_device_map.os_layer). It faces the JMRI block next to that boundary (Mast 32R: Track 29-31), and its
    lengths are the JMRI blocks' (block_lengths.csv), as build_signals.check_lengths reads them."""
    part_of = parts
    seqs = {}                      # (node, leg) -> the JMRI blocks from that switch leg along its run
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
        inside = lambda b, own=own: part_of.get(b, b) == own        # noqa: E731  the OS block or a part of it
        at_turnout = not seq or not inside(seq[0])
        facing = next((b for b in seq if not inside(b)), None)
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
                        leg=p, strand=m["strand"], running=m["running"], role="home"))
    for x in planned["intermediates"]:
        edge, track_names = plan_edge(band, chains[tuple(x["start"])])
        out.append(dict(mast=f"Mast {x['name']}", cp=x["cp"], switch="", facing=x["facing"],
                        protects=x["protects"], kind="one-searchlight", heads=1, dir=x["dir"],
                        toward=x["toward"], run=f"{x['toward']};{x['other']}", names=track_names,
                        edge_cm=x["total"], cm_from_toward=x["dist"], edge=edge, node=x["to"][0],
                        milepost=x["milepost"], role="intermediate"))
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
                        protects="", cm_from_toward=m["total"], dir=m["dir"], role="hidden"))
    return out


def virtual_rows(vgen: list[dict], old_rows: list[dict]) -> list[dict]:
    """Mast rows (masts.csv's mast columns) of the virtual masts: each keeps the system name its old device-map row gives it (a
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


def with_roles(rows: list[dict], placed: list[dict]) -> list[dict]:
    """`rows` (device-map rows of masts and heads) each with its role (hartlib.devices.ROLES): a mast's is the one the
    rule placed it with (`placed`: generate's and virtual_masts' masts, each with its role), a head's is head. No role
    is read off a name (hand-off row 8). RuleError on a mast row the rule did not place."""
    roles = {m["mast"]: m["role"] for m in placed}
    out, bad = [], []
    for r in rows:
        if r["layer"] == "head":
            out.append(dict(r, role="head"))
        elif r["user_name"] in roles:
            out.append(dict(r, role=roles[r["user_name"]]))
        else:
            bad.append(r["user_name"])
    if bad:
        raise RuleError(f"mast row(s) {sorted(bad)} the rule did not place have no role to write")
    return out


def plan_facts(gen: list[dict], level: int = PLANNED_LEVEL) -> dict:
    """{(level, mast): its plan facts (level_masts.PLAN_FIELDS)} of the masts generate() and virtual_masts() place: where the
    drawing puts each (its run, lengths and plan graph edge and node). The signal's name, kind and heads are not
    facts of their own: they follow from the row (level_masts.signal_name, signal_kind, head_count)."""
    return {(level, m["mast"]): dict(toward=m["toward"], run=m["run"], names=level_masts.LIST.join(m["names"]),
                            edge_cm=f"{m['edge_cm']:.1f}", cm_from_toward=f"{m['cm_from_toward']:.1f}",
                            schematic_edge=m["edge"], schematic_toward_node=m["node"]) for m in gen}


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
    node = carried(old, "mast").get("node")
    if node:
        return node
    nodes = sorted({h["node"] for h in heads.values()})
    if len(nodes) != 1 or not nodes[0]:
        raise RuleError(f"{DEVICE_MAP.name}: wired {mast} has no node and its head rows give {nodes or 'none'}: "
                        f"set the mast row's node")
    return nodes[0]


def device_rows(gen_masts: list[dict], virtual: list[dict], old_rows: list[dict], wired: dict,
                toward: dict | None = None) -> list[dict]:
    """The staging device-map rows with their mast and head rows replaced: one mast row per mast (generated and virtual) and
    one head row per head of a visible mast, every name its JMRI name; a wired mast keeps its node (mast_node), a
    wired head its node and notes (wired_heads); other rows unchanged and in place. RuleError if a wired head would be
    dropped."""
    keep = [r for r in old_rows if r["layer"] not in ("mast", "head")]
    old_mast = {r["user_name"]: r for r in old_rows if r["layer"] == "mast"}
    masts, heads = [], []
    for r in gen_masts + virtual:
        on = wired.get(r["mast"], {})
        # a hidden buffer-stop mast stands at no switch; its comment names the switch its track leaves (`toward`:
        # {mast: switch}, from virtual_masts), as a head mast's names the switch it stands at
        switch = r["switch"] or (toward or {}).get(r["mast"], "")
        where = " | ".join(x for x in (r["cp"], f"Switch {switch}" if switch else "") if x)
        note = (f"facing {r['facing']} into {r['protects']}" if r["protects"] else f"facing {r['facing']}, buffer stop")
        masts.append(dict(level="1", cp=r["cp"], layer="mast", user_name=r["mast"], system_name=r["system_name"],
                          jmri_name=r["system_name"], node=mast_node(r["mast"], old_mast.get(r["mast"]), on),
                          dcc="", comment=where, trial_name="", notes=note, **{**dict.fromkeys(FACTS, ""),
                          "switch": r["switch"], "facing": r["facing"], "protects": r["protects"], "dir": r["dir"]}))
        for pair in [x for x in r["head_system_names"].split(";") if x]:
            h, user = pair.split("=", 1)
            prev = on.get(user)
            wired_text = prev["comment"] if prev and WIRING_TEXT.match(prev["comment"]) else ""
            heads.append(dict(level="1", cp=r["cp"], layer="head", user_name=user, system_name=h, jmri_name=h,
                              node=prev["node"] if prev else "", dcc="", comment=wired_text or where,
                              trial_name="",
                              notes=prev["notes"] if prev else INTERNAL_HEAD_NOTE, **dict.fromkeys(FACTS, "")))
    written = {(h["user_name"], h["jmri_name"]) for h in heads}
    lost = sorted(f"{u} ({h['jmri_name']})" for m in wired.values() for u, h in m.items()
                  if (u, h["jmri_name"]) not in written)
    if lost:
        raise RuleError(f"the rebuild would drop wired head(s) {lost} from {DEVICE_MAP.name}")
    return keep + sorted(masts, key=lambda r: r["user_name"]) + sorted(heads, key=lambda r: r["user_name"])


# ---------------------------------------------------------------- masts.csv: every level from the device master


def file_rows(master: list[dict], plan: dict) -> list[dict]:
    """masts.csv's rows, every level alike, from the mast and head rows of the device master (`master`, its rows as
    they will be written) and `plan` ({(level, mast): its PLAN_FIELDS}, the plan facts of the masts this script places; every
    other row's are empty): one row per mast, in level, number and name order. system_name and head_system_names are
    the JMRI names (the master's jmri_name), device_system_name the master's system_name (the same on staging, the
    planned physical mast on main and upper). A mast protects the OS block of its switch unless its row names one
    (an anchor mast, an intermediate, a double crossover's corner). RuleError, naming the level and mast, on a virtual
    mast out of its level's thousand or at a switch or protecting a block; a visible mast protecting more than one
    block, or none at no switch; a home mast at no switch on a level not in ANCHOR_LEVELS, or one that does not
    protect an OS block (an anchor mast does: a home signal that lost its switch?); a name out of the grammar
    (level_masts.MAST_USER, virtual masts too), a system name that is not a SignalHeadSignalMast over its heads; a head
    with no head row of its level, or neither its level's internal name nor, on a head row whose assignment is field,
    a wired LCOS head (level_masts.head_problem); a planned physical mast whose heads are not the JMRI mast's; two
    masts on one block pair that are not an A and a B (level_masts.LEGS); a mast named twice; and a plan fact for a
    mast the master does not have. A row on no level (a device a Store added, not yet placed: hartlib.devices
    is_unplaced) is on no level's map, and left out."""
    levels = {str(lv) for lv in level_masts.LEVELS}
    master = [r for r in master if r["level"] in levels]
    heads = {(r["level"], r["jmri_name"]): r for r in master if r["layer"] == "head"}
    physical = {(r["level"], r["system_name"]): r for r in master if r["layer"] == "head" and r["system_name"]}
    blocks = {(r["level"], r["user_name"]): r for r in master if r["layer"] == "block"}   # a protected block's role
    out, bad = [], []
    for r in (r for r in master if r["layer"] == "mast"):
        level, name, jmri, switch = r["level"], r["user_name"], r["jmri_name"], r["switch"]
        where = f"{DEVICE_MAP.name}: level {level} mast {name}"
        if not level_masts.MAST_USER.fullmatch(name):
            bad.append(f"{where}: the name is not Mast <number>[L|R][letter] or Mast <A|B><milepost number>")
            continue
        protects = railroad.device_list(r["protects"])
        row = dict(level=level, mast=name, cp=r["cp"], switch=switch, facing=r["facing"], dir=r["dir"], leg="",
                   system_name=jmri, device_system_name=r["system_name"],
                   **{**dict.fromkeys(level_masts.PLAN_FIELDS, ""), **plan.get((int(level), name), {})})
        if jmri.startswith("IF$vsm:"):          # a hidden destination mast at a buffer stop (mast_plan)
            if level_masts.virtual_level(jmri) != int(level) or r["system_name"] != jmri or switch or protects:
                bad.append(f"{where}: {jmri!r} is a VirtualSignalMast of its level's thousand (its system_name the "
                           "same) at a buffer stop: no switch, nothing protected")
            out.append(dict(row, protects="", head_system_names=""))
            continue
        if len(protects) > 1 or not (switch or protects):     # an intermediate: no switch, between two blocks
            bad.append(f"{where}: protects {protects or 'nothing'} and stands at "
                       f"{'Switch ' + switch if switch else 'no switch'}: a home signal is at a switch or protects "
                       "its OS block, an intermediate protects one block")
            continue
        if not switch and r["role"] == "home" and int(level) not in ANCHOR_LEVELS:
            bad.append(f"{where} is a home mast at no switch, but level {level}'s OS blocks end at their switches, so "
                       f"it is no anchor mast (anchor masts stand on levels {', '.join(map(str, ANCHOR_LEVELS))}): a "
                       "home signal lost its switch?")
        elif not switch and r["role"] == "home" and (level, protects[0]) not in blocks:
            bad.append(f"{where} is an anchor mast protecting {protects[0]}, which is no level {level} block row")
        elif not switch and r["role"] == "home" and not devices.is_os(blocks[(level, protects[0])], DEVICE_MAP.name):
            bad.append(f"{where} is a home mast at no switch, so an anchor mast, but protects {protects[0]}, no OS "
                       "block: a home signal lost its switch?")
        m = level_masts.SHSM.fullmatch(jmri)
        if not m:
            bad.append(f"{where}: jmri_name {jmri!r} is not a SignalHeadSignalMast over its heads")
            continue
        names = level_masts.mast_heads(jmri)
        missing = [h for h in names if (level, h) not in heads]
        if missing:
            bad.append(f"{where}: heads {missing} have no head row")
            continue
        bad += [f"{where}: {p}" for p in (level_masts.head_problem(h, heads[(level, h)]["user_name"], int(level),
                                                                   heads[(level, h)]["assignment"] == "field")
                                          for h in names) if p]
        if r["system_name"] and r["system_name"] != jmri:      # the planned physical mast: over the same heads
            planned = level_masts.SHSM.fullmatch(r["system_name"])
            got = [physical.get((level, h), {}).get("jmri_name") for h in level_masts.mast_heads(r["system_name"])]
            if not planned or planned.group(1, 2) != m.group(1, 2) or got != names:
                bad.append(f"{where}: system_name {r['system_name']!r} is not the planned physical mast of "
                           f"{jmri!r} (its heads' rows give {got})")
        out.append(dict(row, protects=protects[0] if protects else f"OS Switch {switch}",
                        head_system_names=level_masts.LIST.join(f"{h}={heads[(level, h)]['user_name']}"
                                                                for h in names)))
    pairs = {}
    for r in out:
        if r["protects"]:
            pairs.setdefault((r["facing"], r["protects"]), []).append(r)
    for (facing, protects), group in pairs.items():
        if len(group) == 1:
            continue
        letters = {r["mast"][-1]: r for r in group}
        if len(group) != 2 or set(letters) != set(level_masts.LEGS):
            bad.append(f"masts {[r['mast'] for r in group]} share {facing} into {protects}: only an A and a B mast "
                       "can, on the switch's normal and diverging legs")
            continue
        for letter, r in letters.items():
            r["leg"] = level_masts.LEGS[letter]
    taken = [r["mast"] for r in out]
    bad += [f"{DEVICE_MAP.name}: mast {x} is named twice" for x in sorted({x for x in taken if taken.count(x) > 1})]
    bad += [f"plan facts for level {lv} mast {x}, which the master has no mast row for"
            for lv, x in sorted(set(plan) - {(int(r["level"]), r["mast"]) for r in out})]
    if bad:
        raise RuleError("; ".join(bad))
    return sorted(out, key=lambda r: (int(r["level"]), int(re.search(r"\d+", r["mast"]).group()), r["mast"]))


# ---------------------------------------------------------------- staging: the rule over its device map


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
                          split=mast_rule.read_block_splits(bdm.block_overrides(), found, LEVELS))


def build():
    """({path: text} of every file this script writes, the visible masts, the virtual masts by rule)."""
    with pd.cache_on():
        band, _opts, _core = sdm.staging_band()
        bands, joined, runs, _corners = bdm.solve()
    names = sdm.load(band, device_map=DEVICE_MAP, with_masts=False)
    cp_of = sdm.switch_areas(STATIONS)
    locks = interlockings(set(cp_of))
    files = device_files()
    problems = devices.stale(files)       # the master is read below: stop if it or the files generated from it are off
    if problems:
        raise RuleError("; ".join(problems))
    owned = field_rows(files)                   # the owner's cells: devices_field.csv alone
    wired = wiring_heads(owned["head"])
    cm = block_cm()
    parts = sdm.staging_parts(DEVICE_MAP)
    planned = plan(band, bands, joined, runs, sdm.os_layer(names, parts), locks, cm)   # parts inside their blocks
    gen = generate(band, names, planned, cm, wired, parts)
    unplaced = sorted(set(wired) - {m["mast"] for m in gen})
    if unplaced:
        raise RuleError(f"{DEVICE_MAP.name} wires heads on masts the rule does not place: "
                        + "; ".join(f"{m} ({', '.join(sorted(wired[m]))})" for m in unplaced))
    for m in gen:                    # the cp column names the control point (the drawings') of the mast's switch
        m["cp"] = cp_of[m["toward"]]
    vgen = virtual_masts(band, planned, cp_of)
    gm = mast_rows(gen, wired)
    vr = virtual_rows(vgen, allocated_masts(files))
    taken = [r["system_name"] for r in gm + vr]
    if len(set(taken)) != len(taken):
        raise RuleError(f"two masts share a system name: {sorted({x for x in taken if taken.count(x) > 1})}")
    mine = with_roles([r for r in device_rows(gm, vr, owned["mast"], wired, {m["mast"]: m["toward"] for m in vgen})
                       if r["layer"] in WRITES], gen + vgen)   # the mast and head rows only
    want = devices.outputs_after(WRITER, mine, files)
    master = devices.parse(want[files.master], files.master.name, files)     # every level's rows, as they will be written
    rows = file_rows(master, plan_facts(gen + vgen))
    kinds = {m["mast"]: level_masts.signal_kind(m) for m in rows if m["mast"] in {g["mast"] for g in gen + vgen}}
    drift = sorted(m["mast"] for m in gen + vgen if kinds[m["mast"]] != m["signal_kind"])
    if drift:       # the file holds no kind: it must follow from the row as the rule gives it
        raise RuleError(f"the rule's signal kind of {drift} is not the one their heads give")
    want[MASTS] = csv_text(rows, level_masts.FIELDS)
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
            print(f"SKIPPED masts check: {exc}")
            return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
        print(f"{WRITER}: {exc}", file=sys.stderr)
        return 2
    try:
        want, gen, vgen = build()
    except (RuleError, sdm.StagingMapError, sdm.lc.BuildError, mast_rule.MapError, railroad.FactsError) as exc:   # DevicesError is a FactsError
        print(f"{WRITER}: {exc}", file=sys.stderr)
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
            print(devices.stale_message(p, device_files(), f"tools/schematic/{WRITER}"), file=sys.stderr)
        return 1 if stale else 0
    for p in stale:
        p.write_text(want[p], encoding="utf-8")
        print(f"wrote {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
