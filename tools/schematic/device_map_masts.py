"""Staging's mast and head rows of the device master, from the one mast process (mast_plan.plan): part 1 of
build_masts.py until naming-layers step 12 (builder merge step 6), now build_device_map.py's, so one writer makes
every level's mast and head rows. build_masts.py reads the same plan (staging_masts) for the plan facts it writes to
masts.csv.

The rule (owner, 2026-11-18/19/20/21): home masts, running track and exit dwarfs by rule, intermediates and virtual
masts only as destinations, over staging's interlockings (interlockings.csv, level 1: Brick 1, 3, 5; Barn 7; East
End 23, 31, 33; Princess 35, 37, 39) and its block layer, read from the block rows build_device_map.py makes in the
same run (not from its last output) with block_lengths.csv. A mast's cp names the control point of its switch (the
stations the drawings group by). One anchor rule on every level (owner, 2026-11-23):
- a home mast stands at its switch's leg when the block boundary is there (a turnout mast), else on the anchor where
  the switch's own OS block ends (an anchor mast, no switch: Mast 8RA on Scale, 25 cm from Switch 7, before
  2026-11-20). Main and upper's OS blocks end at their switches, so every home mast there is a turnout mast;
- intermediates carry no line code on staging (prototype numbering: MP 6.7 gives Mast 67 west and Mast 68 east).

Every device is keyed by its ID (hartlib.device_ids), never by its name: a home mast by the switch label, leg and way
it looks (a staging crossover half's by its OS block's half too: mast:7:A-13C:B:east), an intermediate or hidden mast
by the block it faces, a head by its mast's ID and place. The owner's cells (devices_field.csv) are found by ID: a
mast's user_name (the owner's name wins: its heads take it, and so their internal names; staging's 6L and 8R pairs
keep their names so), a wired mast's node, a wired head's notes. A wired head is a level 1 head row of wiring.csv,
by its ID (the physical wiring source; today one: Head 6LB on IH432, Switch 5): its address, node and wiring text
(its JMRI comment, hartlib.tables_build) come from there, its notes from its field row, else wiring.csv's, else
"wired". A field head row must be a wired head. The build stops on a wired head the rule does not place (its mast is
not placed, or the rule gives that mast other heads), and on a wired head's node that is not staging's.

Heads are internal, from the mast's name and level (level_masts.head_name: the level's prefix is data,
level_masts.HEAD_PREFIXES: IH:HART:C1:<n><L|R>[A|B][_Top|_Bottom] on staging, C3 on main and upper), so nothing
unwired reaches MQTT: signal_coordinator.py publishes only IH and digits.

Virtual masts (IF$vsm, hidden, one-low) only where a visible mast's route reaches a buffer stop first (mast_plan;
owner, 2026-11-20): staging's 4LA, 4LB, 10LA, 10LB and 12L. Each keeps the system name its row had, by its ID; a new
one takes the next ordinal of its level's thousand (mast_plan.virtual_system_names); a dropped one's ordinal stays in
retired_virtual_masts.csv. The ordinals are the builder's one read-back of its own output (devices.allocated_names).
"""
from __future__ import annotations

import re
from pathlib import Path

import le_names as ln
import mast_plan
import mast_rule
import publish_draft as pd
import staging_device_map as sdm
from hartlib import device_ids, devices, level_masts, railroad, wiring

WRITER = "build_device_map.py"              # the one writer of every level's mast and head rows
LEVEL = sdm.LEVEL                           # staging
STATIONS = sdm.STATIONS
INTERLOCKINGS = pd.DATA / "interlockings.csv"   # the signal rule's control points, every level (owner, 2026-11-20)
LEVELS = mast_rule.band_levels(sdm.overrides())     # {band title: level}: staging's
FACTS = railroad.DEVICE_FACTS               # the device map's fact columns; a mast row fills switch, facing, protects, dir
WIRED_HEAD = level_masts.WIRED_HEAD         # an LCOS head: signal_coordinator.py publishes IH and digits to MQTT
# the note of a head on its internal name (no field head drives it), with the owner's decision (2026-11-19)
INTERNAL_HEAD_NOTE = "internal, not wired (owner, 2026-11-19)"
WIRING_TEXT = devices._NODE_TEXT            # a wired head's comment is its wiring (Node: ...), as the master tells it
VIRTUAL_KIND = "one-low"
LAYERS = ("mast", "head")


class RuleError(mast_rule.MapError):
    pass


def internal_head(user: str, level: int = LEVEL) -> str:
    """The internal system name of a head from its user name and level (level_masts.head_name, the level's prefix
    from HEAD_PREFIXES): "Head 24RA Top" on staging -> IH:HART:C1:24RA_Top. RuleError on a user name that is not
    Head <key>[ Top| Bottom]."""
    try:
        return level_masts.head_name(user, level)
    except ValueError as exc:
        raise RuleError(str(exc)) from None


def head_users(mast: str, heads: int) -> list[str]:
    """A mast's head user names, in order: Top and Bottom on a two-head mast."""
    key = mast.removeprefix("Mast ")
    return [f"Head {key}"] if heads == 1 else [f"Head {key} {p}" for p in ("Top", "Bottom")]


def field_by_id(files: devices.Files) -> dict[str, dict]:
    """{id: field row} of staging's mast and head rows in devices_field.csv (the owner's cells), from the field file
    alone, by ID."""
    return {f["id"]: dict(f) for f in devices.field_index(files).values()
            if f["level"] == str(LEVEL) and f["layer"] in LAYERS}


def wired_heads(field: dict, path: Path | None = None, files: devices.Files | None = None) -> dict[str, dict]:
    """{head id: its wired values} of wiring.csv's level 1 head rows (`path`, default the committed file), the
    physical wiring source: system_name and jmri_name (the address), node and comment (its wiring text) from there,
    notes from the head's field row (`field`, field_by_id), else wiring.csv's, else "wired". RuleError on a wired
    head on a node that is not staging's, a wiring.csv row that is no head of a staging mast, or a field head row
    wiring.csv does not list."""
    try:
        heads = [w for w in wiring.read(path, levels=(1,), files=files) if w.level == LEVEL and w.kind == "head"]
        import device_map_inputs as dmi
        nodes = dmi.staging_nodes()
    except (railroad.FactsError, mast_rule.MapError) as exc:
        raise RuleError(str(exc)) from None
    bad = [f"{wiring.PATH.name} line {w.line}: {w.device} is on node {w.node}, no staging node "
           f"({', '.join(map(str, sorted(nodes)))})" for w in heads if w.node not in nodes]
    out = {}
    for w in heads:
        if not w.mast.startswith("Mast ") or not w.place:
            bad.append(f"{wiring.PATH.name} line {w.line}: {w.id!r} is no head of a staging mast")
            continue
        f = field.get(w.id)
        out[w.id] = dict(system_name=w.address, jmri_name=w.address, node=str(w.node), comment=w.wiring_text,
                         notes=(f or {}).get("notes") or w.notes or "wired")
    for ident in sorted(i for i, f in field.items() if f["layer"] == "head" and i not in out):
        bad.append(f"{devices.FIELD_FILE}: head {ident} has no head row in {wiring.PATH.name}: add its wiring there, "
                   "or remove the field row")
    if bad:
        raise RuleError("; ".join(bad))
    return out


def block_cm(rows: list, path: Path | None = None) -> dict:
    """{block: cm} of the plan lengths in block_lengths.csv (`path`, default the repo's; hartlib.railroad.plan_cm), each
    found by its (level, id) and named by its row in `rows` (the master's rows as the builder writes them), not by
    the file's user_name label, which the length-labels step writes after the device map."""
    lengths = railroad.read_block_lengths(path or railroad.Sources.under().block_lengths)
    by_id = {(b.level, b.id): cm for b, cm in zip(lengths.values(), railroad.plan_cm(lengths).values())}
    return {r["user_name"]: by_id[(r["level"], r["id"])] for r in rows
            if r["level"] == str(LEVEL) and r["layer"] == "block" and (r["level"], r["id"]) in by_id}


def with_lengths(runs: list, cm: dict) -> list:
    """`runs` (mast_plan.run_blocks) when `cm` gives every block on them a length; RuleError naming the blocks it does
    not (a block with no plan length has no place to put a mast)."""
    missing = sorted({b for _start, seq, _end in runs for b in seq} - set(cm))
    if missing:
        raise RuleError(f"block_lengths.csv has no plan length for {missing}")
    return runs


def plan_edge(band, sids, stored: dict) -> tuple[str, list[str]]:
    """(the plan graph edge a run's strands come from, every track name the name store gives a strand of that edge:
    `stored`, {strand: name}, staging_device_map.staging_names), as build_signals.py checks a mast's schematic run:
    one edge, a strand's own suffix (".0", ".1") dropped."""
    strands = band["strands"]
    edges = sorted({re.sub(r"\.\d+$", "", strands[s]["edge"]) for s in sids})
    if len(edges) != 1:
        raise RuleError(f"a mast's run spans plan edges {edges}")
    names = sorted({stored[s] for s in strands
                    if re.sub(r"\.\d+$", "", strands[s]["edge"]) == edges[0] and stored.get(s)})
    return edges[0], names


def run_strands(band) -> dict:
    """{(node, port): [strand ids]} of the run that leaves each switch leg (le_names.runs, crossover insides left out)."""
    out = {}
    for start, chain, end in ln.runs(band, ln.crossover_strands(band)):
        sids = [sid for sid, _rev in chain]
        out[tuple(start)] = out[tuple(end)] = sids
    return out


def generate(band, names: dict, planned: dict, cm: dict, parts: dict, stored: dict) -> list[dict]:
    """The visible staging masts in the columns the files take, from mast_plan.plan's home masts and intermediates on
    the staging band (`names`: the block layer, `cm`: block_cm): [{mast, cp, switch, facing, protects, kind, heads,
    dir, toward, run, names, edge_cm, cm_from_toward, edge, node, role}], in name order; role (hartlib.devices.ROLES)
    is home or intermediate, as the plan places the mast. A home mast stands at its switch's leg when the block
    boundary is there (a turnout mast), else on the anchor where the switch's own OS block ends (an anchor mast, no
    switch); a part of the OS block (a JMRI block of its own, owner 2026-11-20) is inside it, as mast_plan reads the
    layer (staging_device_map.os_layer). It faces the JMRI block next to that boundary (Mast 32R: Track 29-31), and
    its lengths are the JMRI blocks' (block_lengths.csv), as build_signals.check_lengths reads them. A mast's `names`
    are the name store's for its run's plan edge (`stored`: staging_device_map.staging_names of `band`, plan_edge)."""
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
        inside = lambda b, own=own: parts.get(b, b) == own        # noqa: E731  the OS block or a part of it
        at_turnout = not seq or not inside(seq[0])
        facing = next((b for b in seq if not inside(b)), None)
        if facing is None:
            far_node = nodes[far[0]]
            facing = names["os"].get(far[0]) if far_node["kind"] == "switch" else None
        if facing is None:
            raise RuleError(f"switch {m['switch']} leg {p}: no block to face")
        edge, names_ = plan_edge(band, chains[(n, p)], stored)
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
        edge, track_names = plan_edge(band, chains[tuple(x["start"])], stored)
        out.append(dict(mast=f"Mast {x['name']}", cp=x["cp"], switch="", facing=x["facing"],
                        protects=x["protects"], kind="one-searchlight", heads=1, dir=x["dir"],
                        toward=x["toward"], run=f"{x['toward']};{x['other']}", names=track_names,
                        edge_cm=x["total"], cm_from_toward=x["dist"], edge=edge, node=x["to"][0],
                        milepost=x["milepost"], role="intermediate"))
    return out


def virtual_masts(band, planned: dict, cps: dict, stored: dict) -> list[dict]:
    """Staging's hidden routing masts in the columns generate() gives, from mast_plan.plan's virtual masts (only where
    a visible mast's route reaches a buffer stop first, owner 2026-11-20: 4LA, 4LB, 10LA, 10LB, 12L), `cps` naming
    each switch's control point (the drawings'), `stored` the name store's strand names (generate)."""
    chains = run_strands(band)
    out = []
    for m in planned["virtual"]:
        edge, track_names = plan_edge(band, chains[(m["node"], m["leg"])], stored)
        out.append(dict(mast=f"Mast {m['name']}", cp=cps[m["switch"]], kind=VIRTUAL_KIND, heads=1,
                        toward=m["switch"], run=f"{m['switch']};", names=track_names, edge_cm=m["total"],
                        edge=edge, node=m["node"], signal_kind="virtual", switch="", facing=m["facing"],
                        protects="", cm_from_toward=m["total"], dir=m["dir"], role="hidden"))
    return out


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


def mast_ids(band, placed: list[dict], block_ids: dict) -> list[str]:
    """The device ID of each mast of `placed` (generate's and virtual_masts', in order; hartlib.device_ids): a home
    mast's by the label of the switch node it stands at, its leg and the way it looks (an anchor mast too: the plan
    puts it at that leg), at a single crossover's half with the half its OS block's ID gives (mast:7:A-13C:B:east:
    both halves carry the label 7); an intermediate's or a hidden mast's by the device ID of the block it faces
    (`block_ids`: {block user name: device ID} of staging's block rows) and the way it looks. RuleError on a facing
    block with no ID, or two masts with one ID."""
    halves = {n: ident.split(":", 2)[2] for n, (_ph, ident) in sdm.os_keys(band).items() if ident.count(":") == 2}
    out, bad = [], []
    for m in placed:
        if m["role"] == "home":
            label = sdm.lc.bare(band["nodes"][m["node"]].get("label"))
            out.append(device_ids.home_mast_id(label, m["leg"], m["dir"], halves.get(m["node"], "")))
        elif m["facing"] in block_ids:
            out.append(device_ids.block_mast_id(block_ids[m["facing"]], m["dir"]))
        else:
            out.append("")
            bad.append(f"{m['mast']} faces {m['facing']}, which has no staging block row with a device ID")
    twice = sorted({i for i in out if i and out.count(i) > 1})
    bad += [f"two masts have device ID {i}" for i in twice]
    if bad:
        raise RuleError("; ".join(bad))
    return out


def owner_names(placed: list[dict], ids: list[str], field: dict) -> None:
    """Give each mast of `placed` the owner's name, its field row's user_name by its ID (`field`, field_by_id), in
    place: the owner's name wins, and its heads are named from it (naming-layers step 12). RuleError on a name out of
    the grammar (level_masts.MAST_USER) or one two masts would take."""
    bad = []
    for m, ident in zip(placed, ids):
        name = (field.get(ident) or {}).get("user_name")
        if name and name != m["mast"]:
            if not level_masts.MAST_USER.fullmatch(name):
                bad.append(f"{devices.FIELD_FILE}: mast {ident} named {name!r}, not Mast <number>[L|R][letter]")
                continue
            m["generated"], m["mast"] = m["mast"], name
    taken = [m["mast"] for m in placed]
    bad += [f"two masts are named {x} (an owner's name in {devices.FIELD_FILE} takes a generated one?)"
            for x in sorted({x for x in taken if taken.count(x) > 1})]
    if bad:
        raise RuleError("; ".join(bad))


def virtual_names(vgen: list[dict], ids: dict, old_rows: list[dict]) -> dict[str, str]:
    """{mast: system name} of the virtual masts: each keeps the system name its row had by its ID (a
    VirtualSignalMast's ordinal, $1001 ...; `old_rows`: staging's mast rows as last written, allocated_names), and a
    new one takes the next ordinal of staging's thousand (mast_plan.virtual_system_names), so no system name shifts.
    An old row whose ID the rule no longer places keeps its old name, so mast_plan asks for it in
    retired_virtual_masts.csv. RuleError when that old name is now another mast's."""
    name_of = {ids[m["mast"]]: m["mast"] for m in vgen}
    old, bad = {}, []
    for r in old_rows:
        if r["layer"] != "mast" or not level_masts.virtual_ordinal(r["system_name"]):
            continue
        key = name_of.get(r["id"], r["user_name"])
        if key in old:
            bad.append(f"{key}: the virtual mast of id {r['id']} had that name, and another mast now has it")
        old[key] = r["system_name"]
    if bad:
        raise RuleError("; ".join(bad))
    try:
        return {f"Mast {k}": v for k, v in mast_plan.virtual_system_names(
            [m["mast"].removeprefix("Mast ") for m in vgen], LEVEL, old).items()}
    except mast_rule.MapError as exc:
        raise RuleError(str(exc)) from None


def mast_node(mast: str, field_row: dict | None, heads: list[dict]) -> str:
    """The node of a mast row: none on an internal mast; on a wired one its field row's node, or, when that is blank
    (a newly wired mast), the node its wired heads share. RuleError when they name different nodes or none."""
    if not heads:
        return ""
    node = (field_row or {}).get("node")
    if node:
        return node
    nodes = sorted({h["node"] for h in heads})
    if len(nodes) != 1 or not nodes[0]:
        raise RuleError(f"wired {mast} has no node and its head rows give {nodes or 'none'}: set the mast's node in "
                        f"{devices.FIELD_FILE}")
    return nodes[0]


def device_rows(placed: list[dict], ids: dict, wired: dict, field: dict, virtual: dict) -> list[dict]:
    """Staging's mast and head rows, in the device-map form with role and id (devices.master_row makes the master's):
    one mast row per mast of `placed` (generate's and virtual_masts', each with its final name) and one head row per
    head of a visible mast, every name its JMRI name; `ids` {mast: device ID} (mast_ids), a head's ID its mast's and
    its place, top first. A head in `wired` (wired_heads, by ID) takes its address, node, comment and notes from
    there, and its mast is a field signal with the node mast_node gives; the rest are internal. `virtual`: {mast:
    system name} of the hidden masts (virtual_names). Masts then heads, each in name order. RuleError on a wired head
    the rule does not place."""
    masts, heads, placed_heads = [], [], set()
    for m in placed:
        mid = ids[m["mast"]]
        # a hidden buffer-stop mast stands at no switch; its comment names the switch its track leaves (toward), as
        # a head mast's names the switch it stands at
        switch = m["switch"] or (m["toward"] if m["role"] == "hidden" else "")
        where = " | ".join(x for x in (m["cp"], f"Switch {switch}" if switch else "") if x)
        note = (f"facing {m['facing']} into {m['protects']}" if m["protects"] else f"facing {m['facing']}, buffer stop")
        if m["role"] == "hidden":
            system, node = virtual[m["mast"]], ""
        else:
            users = head_users(m["mast"], m["heads"])
            hids = [device_ids.head_id(mid, device_ids.head_place(i, m["heads"])) for i in range(m["heads"])]
            placed_heads |= set(hids)
            on = [wired[h] for h in hids if h in wired]
            names = []
            for user, hid in zip(users, hids):
                w = wired.get(hid)
                h = w["jmri_name"] if w else internal_head(user)
                names.append(h)
                heads.append(dict(level=str(LEVEL), cp=m["cp"], layer="head", role="head", id=hid, user_name=user,
                                  system_name=h, jmri_name=h, node=w["node"] if w else "", dcc="",
                                  comment=w["comment"] if w and WIRING_TEXT.match(w["comment"]) else where,
                                  trial_name="", notes=w["notes"] if w else INTERNAL_HEAD_NOTE,
                                  **dict.fromkeys(FACTS, "")))
            system = f"IF$shsm:basic:{m['kind']}(" + ")(".join(names) + ")"
            node = mast_node(m["mast"], field.get(mid), on)
            m["signal_kind"] = "field" if on else "planned"
        masts.append(dict(level=str(LEVEL), cp=m["cp"], layer="mast", role=m["role"], id=mid, user_name=m["mast"],
                          system_name=system, jmri_name=system, node=node, dcc="", comment=where, trial_name="",
                          notes=note, **{**dict.fromkeys(FACTS, ""), "switch": m["switch"], "facing": m["facing"],
                                         "protects": m["protects"], "dir": m["dir"]}))
    lost = sorted(set(wired) - placed_heads)
    if lost:
        raise RuleError(f"wiring.csv wires head(s) {', '.join(lost)}, which the rule does not place (its mast is not "
                        "placed, or the rule gives it other heads)")
    return sorted(masts, key=lambda r: r["user_name"]) + sorted(heads, key=lambda r: r["user_name"])


def plan(band, bands, joined, runs, names: dict, locks: dict, cm: dict) -> dict:
    """mast_plan.plan over the staging level: its tracks by mast_rule (a helix end tagged H, no helix blocks), its
    interlockings (`locks`), its block layer (`names`, of `band`, the staging band of `bands`) and block lengths
    (`cm`), the owner's block splits. RuleError when `band` is not the staging band `bands` holds."""
    import device_map_schematic as dms
    found = mast_rule.tracks(bands, runs, joined, {1: "H"}, levels=LEVELS)
    mast_rule.track_names(found)
    bi = [i for i, (title, _b, _o) in enumerate(bands) if mast_rule.band_level(title, LEVELS)]
    if len(bi) != 1 or set(bands[bi[0]][1]["strands"]) != set(band["strands"]):
        raise RuleError(f"the solved sheet has {len(bi)} staging band(s), or its staging band is not the device map's")
    return mast_plan.plan(bands, joined, found, levels=LEVELS, cp_of=locks, layer={bi[0]: names}, cm=cm,
                          split=mast_rule.read_block_splits(dms.block_overrides(), found, LEVELS))


def plan_facts(placed: list[dict]) -> dict:
    """{(level, mast): its plan facts (level_masts.PLAN_FIELDS)} of the masts placed: where the drawing puts each (its
    run, lengths and plan graph edge and node). The signal's name, kind and heads are not facts of their own: they
    follow from the row (level_masts.signal_name, signal_kind, head_count)."""
    return {(LEVEL, m["mast"]): dict(toward=m["toward"], run=m["run"], names=level_masts.LIST.join(m["names"]),
                                     edge_cm=f"{m['edge_cm']:.1f}", cm_from_toward=f"{m['cm_from_toward']:.1f}",
                                     schematic_edge=m["edge"], schematic_toward_node=m["node"]) for m in placed}


def staging_masts(bands, joined, runs, rows: list, files: devices.Files) -> dict:
    """Staging's masts by the rule over `rows` (the device master's rows as the builder writes them: its block layer,
    parts and block IDs; `bands`, `joined`, `runs` the solved sheet) and `files`' field file and its last generated
    rows (the virtual ordinals): {"placed": generate's and virtual_masts' masts, final names, in the rule's order,
    "rows": their mast and head rows (device_rows, role and id set), "facts": plan_facts}."""
    with pd.cache_on():
        band, _opts, _core = sdm.staging_band()
    names = sdm.load(band, master_rows=rows, with_masts=False, turnout_idents=False, with_normal=False)
    cp_of = sdm.switch_areas(STATIONS)
    locks = interlockings(set(cp_of))
    field = field_by_id(files)
    wired = wired_heads(field, files=files)
    cm = block_cm(rows)
    parts = sdm.staging_parts(rows=rows)
    planned = plan(band, bands, joined, runs, sdm.os_layer(names, parts), locks, cm)   # parts inside their blocks
    stored = sdm.staging_names(band, pd.DATA)     # the name store's of the folder solved from, by each strand's ID
    gen = generate(band, names, planned, cm, parts, stored)
    for m in gen:                    # the cp column names the control point (the drawings') of the mast's switch
        m["cp"] = cp_of[m["toward"]]
    vgen = virtual_masts(band, planned, cp_of, stored)
    placed = gen + vgen
    block_ids = {r["user_name"]: r["id"] for r in rows if r["level"] == str(LEVEL) and r["layer"] == "block"}
    idents = mast_ids(band, placed, block_ids)
    owner_names(placed, idents, field)
    ids = {m["mast"]: i for m, i in zip(placed, idents)}
    old = [dict(r) for r in devices.allocated_names((str(LEVEL),), "mast", files=files).values()]
    made = device_rows(placed, ids, wired, field, virtual_names(vgen, ids, old))
    taken = [r["system_name"] for r in made if r["layer"] == "mast"]
    if len(set(taken)) != len(taken):
        raise RuleError(f"two masts share a system name: {sorted({x for x in taken if taken.count(x) > 1})}")
    placed.sort(key=lambda m: (int(re.search(r"\d+", m["mast"]).group()), m["mast"]))
    return {"placed": placed, "rows": made, "facts": plan_facts(placed)}
