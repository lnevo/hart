"""The main and upper mast and head rows of the device map: each mast's device ID and name, the virtual masts'
system names, and the home, intermediate and virtual masts' rows with their heads' (staging's: device_map_masts).

build_device_map.build() calls name_masts, head_rows and virtual_mast_rows, in that order, over the masts
mast_plan.plan placed and one MapBuild (device_map_records), once every switch, OS block and track has its row
(device_map_plant): heads take the 5V board room left after the turnouts' 12V boards.
"""
from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import le_common  # noqa: E402  bare: a switch label as the plan prints it
import mast_plan  # noqa: E402  virtual_system_names
from device_map_nodes import NoBoardRoom  # noqa: E402
from device_map_plant import add  # noqa: E402
from device_map_records import Group, MapBuild, MastEntry, MastKind, VirtualNames  # noqa: E402
from hartlib import device_ids, devices, level_masts, railroad  # noqa: E402
from mast_rule import MapError  # noqa: E402

HEAD_NOT_WIRED = "head planned, no board room on the draft plant: placed when the wiring plan is reworked (owner, 2026-11-19)"
LEVELS = ("2", "3")     # the main and upper levels, as the master writes them


class Head(NamedTuple):
    """One head of a mast and where it is wired: `system` empty (and no index or ports) with no board room yet."""
    user: str
    system: str
    signal: int | None      # its signal number on the node
    ports: str | None       # its board and pins, as the comment gives them


class HeadWiring(NamedTuple):
    """A mast's heads on their node: `node` and `mast` (the physical mast's system name) empty with no board room."""
    node: int | str
    mast: str
    heads: list[Head]


def head_name(user: str, level: int | str) -> str:
    """The internal system name of a head of `level` (hartlib.level_masts.head_name: the level's prefix is data,
    HEAD_PREFIXES; every level's builder names its heads so); MapError on a name out of the
    grammar."""
    try:
        return level_masts.head_name(user, int(level))
    except ValueError as exc:
        raise MapError(str(exc)) from exc


def master_virtual_names(files: devices.Files) -> VirtualNames:
    """{mast id: (user name, system name)} of the main and upper virtual masts as the builder last wrote them (each
    keeps its ordinal by its ID, so a mast whose letter changed keeps its system name): name memory, its one
    read-back of its own output (devices.allocated_names)."""
    return {r["id"]: (u, r["jmri_name"])
            for u, r in devices.allocated_names(LEVELS, "mast", files=files).items()
            if level_masts.virtual_ordinal(r["jmri_name"])}


def owner_mast_names(files: devices.Files) -> dict[str, str]:
    """{mast id: the owner's user name} of the main and upper masts the field file names (by ID, hartlib.devices
    .KEY): the owner's name wins, and the mast's heads are named from it."""
    return {f["id"]: f["user_name"] for f in devices.field_index(files).values()
            if f["level"] in LEVELS and f["layer"] == "mast" and f["user_name"]}


def virtual_memory(virtual: Iterable[Mapping[str, object]], old: Mapping[str, tuple[str, str]]
                   ) -> dict[int, dict[str, str]]:
    """{level: {"Mast <name>": system name}} of the virtual masts' old system names (`old`: master_virtual_names,
    by ID), each under its mast's name now (`virtual`: the planned virtual masts, each with its `id` and final
    `name`), an old ID the rule no longer places under its old name (mast_plan.virtual_system_names asks for it in
    retired_virtual_masts.csv). MapError when that old name is now another mast's."""
    now = {m["id"]: f"Mast {m['name']}" for m in virtual}
    out: dict[int, dict[str, str]] = {}
    bad: list[str] = []
    for ident, (user, system) in old.items():
        key = now.get(ident, user)
        level = level_masts.virtual_level(system)
        if level is None:
            raise MapError(f"{user}: {system} (id {ident}) is not a main or upper virtual mast's system name")
        mine = out.setdefault(level, {})
        if key in mine or (ident not in now and key in now.values()):
            bad.append(f"{key}: the virtual mast of id {ident} had that name, and another mast now has it: add "
                       f"{user} ({system}) to retired_virtual_masts.csv under another name, or give the mast its old "
                       "ID back")
        mine[key] = system
    if bad:
        raise MapError("; ".join(bad))
    return out


def facing_id(st: MapBuild, level: int | str, block: str) -> str:
    """The device ID of the block `block` a mast faces: its row on the mast's level, else its one row on another
    level (a helix block, a link drawn on the other band). MapError when it has none or several there."""
    got = st.block_ids.get((str(level), block))
    if got is None:
        other = [v for (_lv, b), v in st.block_ids.items() if b == block]
        if len(other) != 1:
            raise MapError(f"a mast faces {block}, which has {len(other)} block rows: no device ID to name it by")
        got = other[0]
    return got


def mast_id(st: MapBuild, m: MastEntry, kind: MastKind) -> str:
    """A mast's device ID (hartlib.device_ids): a home mast's by its switch label, leg and way, others' by block."""
    if kind != "home":
        return device_ids.block_mast_id(facing_id(st, m["level"], m["facing"]), m["dir"])
    label = le_common.bare(st.bands[m["band"]][1]["nodes"][m["node"]].get("label"))
    return device_ids.home_mast_id(label, m["leg"], m["dir"])


def owner_renames(st: MapBuild, masts: Iterable[tuple[MastEntry, MastKind]], owner: Mapping[str, str]
                  ) -> dict[str, str]:
    """Give each mast its `id` (mast_id) and, where the owner names that ID, the owner's name. Returns {generated
    name: the owner's}. MapError on an owner's name out of the grammar."""
    renamed = {}
    for mast, kind in masts:
        mast["id"] = mast_id(st, mast, kind)
        name = owner.get(mast["id"], "")
        if name and name != f"Mast {mast['name']}":
            if not level_masts.MAST_USER.fullmatch(name):
                raise MapError(f"{devices.FIELD_FILE}: mast {mast['id']} named {name!r}, not Mast <number>[L|R][letter]")
            renamed[mast["name"]] = mast["name"] = name.removeprefix("Mast ")
    return renamed


def name_masts(st: MapBuild, ms: list[MastEntry], virtual: list[MastEntry], owner: Mapping[str, str],
               old_names: VirtualNames) -> dict[str, str]:
    """Every mast's ID, then the owner's name by it (the field file): a mast and its heads take it, as on staging
    (device_map_masts.owner_names); a virtual mast's needed_by follows the renames. Returns {virtual mast name: its
    system name}, each level's ordinals from its own thousand (hartlib.level_masts); `old_names`: the virtual masts
    that have a name already (master_virtual_names). MapError on an owner's name out of the grammar or two masts
    with one name."""
    kinds: list[tuple[MastEntry, MastKind]] = [(m, "intermediate" if m.get("intermediate") else "home") for m in ms]
    kinds += [(m, "virtual") for m in virtual]
    renamed = owner_renames(st, kinds, owner)
    taken = [m["name"] for m in ms + virtual]
    twice = sorted({x for x in taken if taken.count(x) > 1}, key=railroad.natural)
    if twice:
        raise MapError(f"two masts are named {', '.join('Mast ' + x for x in twice)} (an owner's name in "
                       f"{devices.FIELD_FILE} takes a generated one?)")
    for m in virtual:
        m["needed_by"] = [renamed.get(x, x) for x in m["needed_by"]]
    old_virtual = virtual_memory(virtual, old_names)
    vnames: dict[str, str] = {}
    for lv in (2, 3):
        vnames |= mast_plan.virtual_system_names([m["name"] for m in virtual if m["level"] == lv], lv,
                                                 old_virtual.get(lv, {}))
    return vnames


def head_rows(st: MapBuild, cps: Sequence[railroad.Interlocking], ms: list[MastEntry]) -> None:
    """The home and intermediate masts' rows and their heads', last, once every node's boards are known: each
    group's masts in name order, but every two-head mast of every group before any one-head mast (a stable sort),
    since a two-head mast takes six of a board's eight pins and a one-head mast placed first would take a board of
    its own that a two-head mast of the area needs. As many heads are placed as the boards hold; the rest wait as
    HEAD_NOT_WIRED."""
    groups = [(Group(cp.level, cp.area, cp.name), cp.switches[0]) for cp in cps]
    groups += [(Group(st.loc[s].level, st.loc[s].area, ""), s)
               for s in sorted({m["switch"] for m in ms if not m["cp"] and m["switch"]}, key=railroad.natural)]
    placing = [(group, first, m) for group, first in groups
               for m in sorted((m for m in ms if m["cp"] == group.cp and (group.cp or m["switch"] == first)),
                               key=lambda m: railroad.natural(m["name"]))]
    for group, first, m in sorted(placing, key=lambda g: -g[2]["heads"]):
        mast_rows(st, group, first, m)


def head_wiring(st: MapBuild, group: Group, first: str, m: MastEntry, users: Sequence[str]) -> HeadWiring:
    """Where the heads `users` of mast `m` are wired: a frozen mast's heads on their wiring.csv node, else a node
    with board room (Nodes.pick_mast, its first switch's node first). With no board room left in the area
    (NoBoardRoom) they wait for the wiring plan: no node. MapError on a mast frozen in part, or on two nodes."""
    frozen = [st.nodes.take_frozen("head", u) for u in users]
    try:
        if any(frozen):                          # wired and frozen (wiring.csv): every head of the mast, one node
            if not all(frozen) or len({w.node for w in frozen}) != 1:
                raise MapError(f"Mast {m['name']}: wiring.csv freezes {sum(map(bool, frozen))} of its "
                               f"{len(users)} head(s), or puts them on two nodes; freeze the mast whole")
            node = frozen[0].node
            heads = [Head(u, w.address, w.index, w.port_text) for u, w in zip(users, frozen)]
        else:
            node = st.nodes.pick_mast(group.level, group.area, m["heads"], prefer=[st.home[first]])
            heads = [Head(u, f"IH{packed}", k, f"OU: {board} Ports: {pin},{pin + 1},{pin + 2}")
                     for u, (k, packed, board, pin) in zip(users, st.nodes.place_mast(node, m["heads"]))]
    except NoBoardRoom:
        return HeadWiring("", "", [Head(u, "", None, None) for u in users])
    return HeadWiring(node, mast_system_name(m["kind"], [h.system for h in heads]), heads)


def mast_system_name(kind: str, heads: Iterable[str]) -> str:
    """A signal head mast's system name over its heads' system names: IF$shsm:basic:<kind>(<head>)(<head>)."""
    return f"IF$shsm:basic:{kind}(" + ")(".join(heads) + ")"


def mast_rows(st: MapBuild, group: Group, first: str, m: MastEntry) -> None:
    """One home or intermediate mast's row and its heads' rows (head_wiring). Heads with no board room keep their
    virtual names and wait as HEAD_NOT_WIRED, the comment saying where the mast stands."""
    lv, cp = group.level, group.cp
    parts = ["Top", "Bottom"] if m["heads"] == 2 else [""]
    users = [f"Head {m['name']}" + (f" {part}" if part else "") for part in parts]
    wired = head_wiring(st, group, first, m, users)
    virtual = mast_system_name(m["kind"], [head_name(u, lv) for u in users])
    stands = "intermediate" if m.get("intermediate") else f"Switch {m['switch']}"
    if m.get("intermediate"):
        notes = f"intermediate signal from {m['facing']} into {m['protects']} at MP {m['name'][0]} {m['milepost']:.2f}"
        facts: dict[str, str] = {}
    else:
        notes = f"home signal from {m['track']}" + (f" into {m['protects']}" if m["protects"] else "")
        facts = {"switch": m["switch"]}
    add(st, lv, cp, "mast", f"Mast {m['name']}", system=wired.mast, node=wired.node,
        comment=f"{group.place} | {stands}", notes=notes, jmri=virtual, facing=m["facing"], protects=m["protects"],
        dir=m["dir"], role="intermediate" if m.get("intermediate") else "home", ident=m["id"], **facts)
    for i, head in enumerate(wired.heads):
        ident = device_ids.head_id(m["id"], device_ids.head_place(i, len(users)))
        if not head.system:             # no node yet: the mast's comment says where it stands
            where = f"{group.place} | " + (f"Switch {m['switch']}" if m["switch"] else "intermediate")
            add(st, lv, cp, "head", head.user, comment=where, notes=HEAD_NOT_WIRED, jmri=head_name(head.user, lv),
                role="head", ident=ident)
            continue
        add(st, lv, cp, "head", head.user, system=head.system, node=wired.node,
            comment=f"Node: {wired.node} Signal: {head.signal} | {head.ports}", jmri=head_name(head.user, lv),
            role="head", ident=ident)


def virtual_mast_rows(st: MapBuild, virtual: list[MastEntry], vnames: Mapping[str, str]) -> None:
    """Each virtual mast's row: a destination for the visible masts' routes, hidden, with no heads and no node."""
    for m in virtual:
        sw = st.switches[m["switch"]]
        system = vnames[m["name"]]
        add(st, m["level"], sw.cp, "mast", f"Mast {m['name']}", system=system,
            comment=f"{sw.cp or sw.area} | buffer stop",
            notes=f"virtual bumper mast facing {m['facing']} at its buffer stop: the destination of "
                  f"{', '.join('Mast ' + x for x in m['needed_by'])}",
            jmri=system, facing=m["facing"], dir=m["dir"], role="hidden", ident=m["id"])
