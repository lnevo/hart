#!/usr/bin/env python3
"""Staging's signal masts by rule (owner, 2026-11-18/19), written into the files the staging builds read.

    python3 tools/schematic/build_staging_masts.py           # write the files
    python3 tools/schematic/build_staging_masts.py --check   # exit 1 if a file is stale
    python3 tools/schematic/build_staging_masts.py --show    # print the masts, write nothing

When the plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and exits 0 (1 with
SCHEMATIC_REQUIRED=1, set in CI), as the other schematic checks do; a write or --show names the fault and exits 2.

Visible masts come from the main and upper levels' rule (mast_rule.masts) over the staging band, with staging's
interlockings (interlockings_staging.csv, owner 2026-11-19: Brick 1, 3, 5; Barn 7; East End 23, 33; Princess 35, 37,
39) as its control points. Staging's control_points stay the stations the drawings group by (brackets on the station
sheets, gantries on the panels); a mast's cp column names the control point of its switch.
- a home mast where a track from outside a control point meets one of its switches, or where a track inside one is
  long enough to hold a train (mast_rule.LONG_CM: K-1/K-2 in the Princess interlocking);
- its heads: two when any route it governs meets facing points inside its interlocking before the next signal
  (mast_rule.facing_on_route), else one; high (searchlight) facing from running track, a dwarf (low) from a yard or
  lead track: two-searchlight, one-searchlight, two-low or one-low (stock JMRI basic appearances);
- an intermediate (APB) pair at each block boundary of a track between home masts where both blocks can hold a train
  (over LONG_CM), named from the milepost in tenths, odd westbound and even eastbound (prototype numbering: MP 6.7
  gives Mast 67 west and Mast 68 east);
- a mast stands at its switch's leg when the block boundary is there (a turnout mast), else on the anchor where the
  switch's own OS block ends (an anchor mast, no switch: Mast 8RA on Scale, 25 cm from Switch 7).

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

Virtual masts (IF$vsm, hidden, one-low) by rule too (owner, 2026-11-20; virtual_masts): a bumper mast at each
buffer stop, a stub-leaving mast where a track meets a switch with a stub leg (mast_rule.leads_to_bumpers_only)
and no visible mast stands, and the partner of an anchor mast that has none. Each keeps the system name its
device-map row had (virtual_rows). None is hand-kept: the last two, the helix-foot masts 38RA and 40RA, went when
each helix track became one block (2026-11-20), and with them staging_masts_virtual.csv and
staging_signals_virtual.csv.

Writes (jmri/layouts/hart/data/schematic/): staging_masts.csv, staging_signals.csv, and the mast and head rows of
device_map_staging.csv (each mast and head row's system_name and jmri_name are its JMRI name; there is no planned
physical head for the internal ones).
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
import mast_rule  # noqa: E402
import publish_draft as pd  # noqa: E402
import le_names as ln  # noqa: E402
import staging_device_map as sdm  # noqa: E402
from hartlib import level_masts, railroad  # noqa: E402

DATA = pd.DATA
MASTS, SIGNALS, DEVICE_MAP = sdm.MASTS, sdm.SIGNALS, sdm.DEVICE_MAP
CPS, OVERRIDES = sdm.CPS, sdm.OVERRIDES
INTERLOCKINGS = DATA / "interlockings_staging.csv"   # the signal rule's control points (owner, 2026-11-19)
LEVELS = {"Staging": 1}
HEAD_PREFIX = "IH:HART:C1:"
FACTS = railroad.DEVICE_FACTS          # the device map's fact columns; a mast row fills switch, facing, protects, dir
HEAD_USER = re.compile(r"Head (\d+[LR]?[A-Z]?)(?: (Top|Bottom))?")   # a staging head's user name: key, position
WIRED_HEAD = re.compile(r"IH\d+")      # an LCOS head: signal_coordinator.py publishes IH and digits to MQTT
CM_PER_MILE = 63360 * 2.54
INCH = 2.54


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


def node_mileposts(band) -> dict:
    """{node: milepost} of every node the band's milepost count reaches (band["mp"]: strand -> (start node, start
    milepost, length in miles, end node))."""
    out = {}
    for start, mp, length, end in band["mp"].values():
        out.setdefault(start, mp)
        out.setdefault(end, mp + length)
    return out


def signal_number(mp: float, west: bool) -> int:
    """An intermediate signal's number from its milepost in tenths: odd westbound, even eastbound. Stops at 100 and
    up: a three-digit staging name would read as a main or upper home mast (hartlib.level_devices.LEVEL_USER)."""
    n = int(mp * 10 + 1e-9)
    if n >= 99:
        raise RuleError(f"MP {mp:.2f} gives intermediate number {n} or more; staging names stop at 98")
    if west:
        return n if n % 2 else n + 1
    return n if n % 2 == 0 else n + 1


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


def generate(band, bands, runs, joined, names, cps: dict, wired: dict) -> list[dict]:
    """The visible staging masts by rule (a mast in `wired`, from wired_heads, is a field signal): [{mast, cp, switch, facing, protects, kind, heads, dir, toward, run, names,
    edge_cm, cm_from_toward, edge, node}], in name order."""
    found = mast_rule.tracks(bands, runs, joined, {1: "H"}, levels=LEVELS)
    mast_rule.track_names(found)
    home = mast_rule.masts(bands, None, found, cps, {}, levels=LEVELS, joined=joined)
    cm = block_cm()
    seqs = {}                      # (node, leg) -> the blocks from that switch leg along its run
    for start, seq, end in with_lengths(sdm.run_blocks(band, names), cm):
        seqs[tuple(start)] = (seq, tuple(end))
        seqs[tuple(end)] = (seq[::-1], tuple(start))
    strands, nodes = band["strands"], band["nodes"]
    chains = run_strands(band)
    out = []
    for m in home:
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
    for m in out:
        # two heads when any route the mast governs can still diverge inside its interlocking (owner, 2026-11-19)
        if m["heads"] == 1 and mast_rule.facing_on_route(band, m["node"], m["leg"], cps):
            m["heads"] = 2
        # high from running track, a dwarf from a yard or lead track (8LA out of Barn, 32R off the ladder)
        m["kind"] = f"{'two' if m['heads'] == 2 else 'one'}-{'searchlight' if m['running'] else 'low'}"
    out += intermediates(band, names, cps, cm, chains)
    for m in out:                    # home and intermediate alike: a mast with wired heads is a field signal
        m["signal_kind"] = "field" if m["mast"] in wired else "planned"
    taken = [m["mast"] for m in out]
    if len(set(taken)) != len(taken):
        raise RuleError(f"the rule names a mast twice: {sorted({x for x in taken if taken.count(x) > 1})}")
    return sorted(out, key=lambda m: (int(re.search(r"\d+", m["mast"]).group()), m["mast"]))


def intermediates(band, names, cps, cm, chains) -> list[dict]:
    """An APB pair at each block boundary of a track between two control-point switches where both blocks hold a
    train (over LONG_CM), named from its milepost (signal_number)."""
    nodes, strands = band["nodes"], band["strands"]
    mp_at = node_mileposts(band)
    out = []
    for start, seq, end in with_lengths(sdm.run_blocks(band, names), cm):
        ends = [nodes[e[0]] for e in (start, end)]
        if any(d["kind"] != "switch" for d in ends):
            continue
        sw = [mast_rule.base(d["label"]) for d in ends]
        if any(s not in cps for s in sw):
            continue
        body = [b for b in seq if b not in (names["os"][start[0]], names["os"][end[0]])]
        for i in range(len(body) - 1):
            a, b = body[i], body[i + 1]
            if cm[a] <= mast_rule.LONG_CM or cm[b] <= mast_rule.LONG_CM:
                continue
            from_start = sum(cm[x] for x in seq[:seq.index(b)])
            total = sum(cm[x] for x in seq)
            # the milepost at the boundary: from the end the count reaches lower, adding the distance; both ends
            # must be on the count, or the way it runs along this track is unknown
            if start[0] not in mp_at or end[0] not in mp_at:
                raise RuleError(f"the boundary {a}|{b} cannot be numbered: switch "
                                f"{sw[0] if start[0] not in mp_at else sw[1]} is not on the milepost count")
            mp = (mp_at[start[0]] + from_start / (CM_PER_MILE / 87.1) if mp_at[start[0]] <= mp_at[end[0]]
                  else mp_at[end[0]] + (total - from_start) / (CM_PER_MILE / 87.1))
            low_is_start = (start[0] in mp_at) and (mp_at.get(start[0], 1e9) <= mp_at.get(end[0], 1e9))
            edge, track_names = plan_edge(band, chains[tuple(start)])
            # westbound runs toward the lower milepost (the count rises east)
            west_to, east_to = (start, end) if low_is_start else (end, start)
            for west, protects, facing, to in ((True, a if west_to is start else b, b if west_to is start else a, west_to),
                                               (False, b if west_to is start else a, a if west_to is start else b, east_to)):
                to_sw = mast_rule.base(nodes[to[0]]["label"])
                other = sw[1] if to is start else sw[0]
                dist = from_start if to is start else total - from_start
                out.append(dict(mast=f"Mast {signal_number(mp, west)}", cp=cps[to_sw], switch="", facing=facing,
                                protects=protects, kind="one-searchlight", heads=1, dir="west" if west else "east",
                                toward=to_sw, run=f"{to_sw};{other}", names=track_names,
                                edge_cm=round(total, 1), cm_from_toward=round(dist, 1), edge=edge, node=to[0],
                                milepost=round(mp, 3)))
    return out


VIRTUAL_KIND = "one-low"
VSM = re.compile(r"IF\$vsm:basic:one-low\(\$(\d+)\)")


def letter_at(band, node: str, leg: str) -> str:
    """The direction letter of a mast at switch `node`'s `leg` facing into the switch, as mast_rule.masts names it."""
    return "L" if mast_rule.TAU[leg] * band["rail"][node] == 1 else "R"


def leg_row(band, node: str, leg: str) -> int:
    d = band["nodes"][node]
    return band["R"]["srow"].get(d["ins"].get(leg) or d["outs"].get(leg), 0)


def virtual_masts(band, names: dict, gen: list[dict], cm: dict, cps: dict) -> list[dict]:
    """Staging's hidden routing masts by rule (owner, 2026-11-20; they were hand-kept in staging_masts_virtual.csv),
    each a virtual one-low mast in the columns generate() gives, `cps` naming each switch's control point:
    - a bumper mast at the buffer stop of each track ending at one, facing it (4LA, 4LB, 10LA, 10LB, 12L);
    - a stub-leaving mast where a track meets a switch that has a stub leg (every route out of that leg ends at a
      buffer stop, mast_rule.leads_to_bumpers_only), facing into the switch, unless the visible rule already places a
      mast there (10RA, 10RB, 12R, 14R; at Switch 3 the visible 4RA and 4RB stand);
    - the partner of an anchor mast that has none: the same block boundary the other way (8LC, opposite 8RA; the
      intermediate pairs have theirs).
    A mast is named as a home mast is (switch number + 1, the letter of its direction); a bumper mast takes the letter
    a train heading for the buffer stop reads. Masts of one number and letter take A, B ... by row on the drawing,
    after any the visible masts already use. RuleError on a name the visible masts give, or a stub track whose
    boundary is not at the switch's leg."""
    nodes = band["nodes"]
    chains = run_strands(band)
    seqs = {}
    for start, seq, end in with_lengths(sdm.run_blocks(band, names), cm):
        seqs[tuple(start)] = (seq, tuple(end))
        seqs[tuple(end)] = (seq[::-1], tuple(start))
    os_blocks = set(names["os"].values())
    visible_at = {(m["node"], m.get("leg")) for m in gen if m.get("leg")}
    label = lambda n: mast_rule.base(nodes[n]["label"]) if nodes[n]["kind"] == "switch" else ""  # noqa: E731
    out = []                         # (number, letter, row, mast fields)
    for (n, p), (seq, far) in sorted(seqs.items()):
        if nodes[n]["kind"] != "switch" or not seq:
            continue
        sw, own = label(n), names["os"][n]
        edge, track_names = plan_edge(band, chains[(n, p)])
        total = round(sum(cm[b] for b in seq), 1)
        base = dict(cp=cps[sw], kind=VIRTUAL_KIND, heads=1, toward=sw, run=f"{sw};{label(far[0])}",
                    names=track_names, edge_cm=total, edge=edge, node=n, signal_kind="virtual")
        far_node = nodes[far[0]]
        if far_node["kind"] == "end" and far_node.get("sub") == "bumper":
            letter = "R" if letter_at(band, n, p) == "L" else "L"
            out.append((int(sw) + 1, letter, leg_row(band, n, p),
                        dict(base, switch="", facing=seq[-1], protects="", cm_from_toward=total,
                             dir="west" if letter == "L" else "east")))
        stub = any(mast_rule.leads_to_bumpers_only(band, n, q) for q in sorted(nodes[n]["ins"] | nodes[n]["outs"]))
        facing = next((b for b in seq if b != own), None)
        if not stub or facing is None or facing in os_blocks or (n, p) in visible_at:
            continue
        if seq[0] == own:
            raise RuleError(f"switch {sw} leg {p}: {facing} meets {own} past the leg; a stub-leaving mast stands at "
                            "the leg")
        letter = letter_at(band, n, p)
        out.append((int(sw) + 1, letter, leg_row(band, n, p),
                    dict(base, switch=sw, facing=facing, protects=own, cm_from_toward=0.0,
                         dir="west" if letter == "L" else "east")))
    pairs = {(m["facing"], m["protects"]) for m in gen}
    for m in gen:
        if m["switch"] or "milepost" in m or (m["protects"], m["facing"]) in pairs:
            continue
        seq, far = seqs[(m["node"], m["leg"])]
        letter = "R" if m["dir"] == "west" else "L"          # the partner faces the other way
        number = int(re.search(r"\d+", m["mast"]).group())
        toward = label(far[0])
        out.append((number, letter, 10 ** 6, dict(cp=m["cp"], kind=VIRTUAL_KIND, heads=1, switch="",
                                                  facing=m["protects"], protects=m["facing"], toward=toward,
                                                  run=f"{toward};{m['toward']}", names=m["names"],
                                                  edge_cm=m["edge_cm"],
                                                  cm_from_toward=round(m["edge_cm"] - m["cm_from_toward"], 1),
                                                  dir="west" if letter == "L" else "east", edge=m["edge"],
                                                  node=far[0], signal_kind="virtual")))
    taken = {m["mast"] for m in gen}
    groups = {}
    for number, letter, row, fields in out:
        groups.setdefault((number, letter), []).append((row, fields))
    masts = []
    for (number, letter), ms in sorted(groups.items()):
        stem = f"Mast {number}{letter}"
        used = sorted(t.removeprefix(stem) for t in taken if t == stem or re.fullmatch(re.escape(stem) + "[A-Z]", t))
        if "" in used:
            raise RuleError(f"{stem} stands already; its virtual partner(s) cannot be lettered")
        ms.sort(key=lambda x: x[0])
        letters = [c for c in "ABCD" if c not in used] if used or len(ms) > 1 else [""]
        if len(ms) > len(letters):
            raise RuleError(f"{stem}: {len(used) + len(ms)} masts, more than A to D")
        for (_row, fields), suffix in zip(ms, letters):
            masts.append(dict(fields, mast=stem + suffix))
    clash = sorted({m["mast"] for m in masts} & taken)
    if clash:
        raise RuleError(f"the virtual masts take names the visible masts have: {clash}")
    return sorted(masts, key=lambda m: (int(re.search(r"\d+", m["mast"]).group()), m["mast"]))


RETIRED = DATA / "retired_virtual_masts.csv"


def read_retired(path: Path = RETIRED) -> dict:
    """{mast: system name} of the virtual masts dropped from staging (retired_virtual_masts.csv), so their ordinals
    stay taken; checked: the columns, one row per mast, each a VirtualSignalMast system name, no ordinal twice."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if rows and set(rows[0]) != {"mast", "system_name", "dropped", "notes"}:
        raise RuleError(f"{path.name}: expected the columns mast, system_name, dropped, notes")
    out, seen = {}, set()
    for n, r in enumerate(rows, 2):
        m, sysname = r["mast"].strip(), r["system_name"].strip()
        hit = VSM.fullmatch(sysname)
        if not m or m in out or not hit or hit.group(1) in seen:
            raise RuleError(f"{path.name} line {n}: {m!r} {sysname!r} is empty, listed twice, not a virtual mast's "
                            "system name, or reuses an ordinal")
        out[m] = sysname
        seen.add(hit.group(1))
    return out


def virtual_rows(vgen: list[dict], old_rows: list[dict]) -> list[dict]:
    """staging_masts.csv rows of the virtual masts: each keeps the system name its old device-map row gives it (a
    VirtualSignalMast's ordinal, $1001 ...), and a new one takes the next ordinal after every one the old rows use,
    so no system name shifts."""
    old = {r["user_name"]: r["system_name"] for r in old_rows if r["layer"] == "mast" and VSM.fullmatch(r["system_name"])}
    retired = read_retired(RETIRED)
    back = sorted(set(old) & set(retired))
    if back:
        raise RuleError(f"{RETIRED.name} lists {', '.join(back)}, which the device map still has; take the row out")
    used = [int(VSM.fullmatch(x).group(1)) for x in [*old.values(), *retired.values()]]
    nxt = max(used, default=1000) + 1          # a dropped mast's ordinal is never given to a new one
    rows = []
    for m in vgen:
        system = old.get(m["mast"])
        if system is None:
            system, nxt = f"IF$vsm:basic:{VIRTUAL_KIND}(${nxt})", nxt + 1
        rows.append(dict(mast=m["mast"], cp=m["cp"], switch=m["switch"], facing=m["facing"], protects=m["protects"],
                         dir=m["dir"], leg="", system_name=system, head_system_names="", device_system_name=system))
    return rows


def interlockings(switches: set, path: Path = INTERLOCKINGS) -> dict:
    """{switch: interlocking} from interlockings_staging.csv. Stops on a switch that is not a staging switch or is in
    two interlockings."""
    out, bad = {}, []
    for r in sdm.read_rows(path, ("interlocking", "switches", "notes")):
        for s in (x.strip() for x in r["switches"].split(",") if x.strip()):
            if s not in switches:
                bad.append(f"{r['interlocking']}: switch {s} is no staging switch")
            elif s in out:
                bad.append(f"switch {s} is in interlockings {out[s]} and {r['interlocking']}")
            out[s] = r["interlocking"]
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


def build():
    """({path: text} of every file this script writes, the visible masts, the virtual masts by rule)."""
    with pd.cache_on():
        band, _opts, _core = sdm.staging_band()
        bands, joined, runs, _corners = bdm.solve()
    names = sdm.load(band, device_map=DEVICE_MAP, with_masts=False)
    cp_of = {s.strip(): r["cp_name"] for r in sdm.read_rows(CPS, sdm.CP_COLUMNS) for s in r["switches"].split(",")}
    locks = interlockings(set(cp_of))
    old = sdm.read_rows(DEVICE_MAP, bdm.COLUMNS)
    wired = wired_heads(old)
    gen = generate(band, bands, runs, joined, names, locks, wired)
    unplaced = sorted(set(wired) - {m["mast"] for m in gen})
    if unplaced:
        raise RuleError(f"{DEVICE_MAP.name} wires heads on masts the rule does not place: "
                        + "; ".join(f"{m} ({', '.join(sorted(wired[m]))})" for m in unplaced))
    for m in gen:                    # the cp column names the control point (the drawings') of the mast's switch
        m["cp"] = cp_of[m["toward"]]
    vgen = virtual_masts(band, names, gen, block_cm(), cp_of)
    gm = mast_rows(gen, wired)
    vr = virtual_rows(vgen, old)
    taken = [r["system_name"] for r in gm + vr]
    if len(set(taken)) != len(taken):
        raise RuleError(f"two masts share a system name: {sorted({x for x in taken if taken.count(x) > 1})}")
    want = {MASTS: csv_text(gm + vr, level_masts.FIELDS),
            SIGNALS: csv_text(signal_rows(gen + vgen), sdm.SIGNAL_COLUMNS),
            DEVICE_MAP: csv_text(device_rows(gm, vr, old, wired), bdm.COLUMNS)}
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
    except (RuleError, sdm.StagingMapError, sdm.lc.BuildError, mast_rule.MapError, railroad.FactsError) as exc:
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
            print(f"{p.name} is stale: run python3 tools/schematic/build_staging_masts.py", file=sys.stderr)
        return 1 if stale else 0
    for p in stale:
        p.write_text(want[p], encoding="utf-8")
        print(f"wrote {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
