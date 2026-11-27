"""The device master's invariants (hartlib.devices.check_rows), one step per concern. devices.check_rows calls
check_rows here; this module reads devices' column lists and helpers, so it is imported when the check runs."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from . import devices       # read at call time: tests patch its lists (WRITERS)


@dataclass
class _Seen:
    """What check_rows has met so far, by the row (devices.row_text) that holds it."""
    keys: dict[tuple[str, str, str], str] = field(default_factory=dict)        # (level, layer, user_name)
    jmri: dict[tuple[str, bool, str], str] = field(default_factory=dict)       # (layer, is an LCC alias, jmri_name)
    field_systems: dict[str, dict[str, str]] = field(default_factory=dict)     # layer -> field system_name -> row
    ids: dict[tuple[str, str], str] = field(default_factory=dict)              # (level, id)
    ranks: list[tuple[tuple[int, int, int], str]] = field(default_factory=list)
    parts: list[tuple[str, str, str]] = field(default_factory=list)            # (row, level, part_of)
    part_names: set[tuple[str, str]] = field(default_factory=set)              # (level, user_name) of each part
    whole: set[tuple[str, str]] = field(default_factory=set)                   # (level, user_name) of each block


def _check_words(r: Mapping[str, str], at: str, bad: list[str]) -> bool:
    """role, assignment and written_by are known words, user_name and description are set, no cell holds a line
    break; True when written_by is unknown (the row then has no rank)."""
    broken = [c for c in devices.COLUMNS if "\n" in r[c] or "\r" in r[c]]
    if broken:
        bad.append(f"{at}: {', '.join(broken)} hold a line break (a record would no longer be one file line)")
    unknown = False
    allowed_by: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("role", devices.ROLES), ("assignment", devices.ASSIGNMENTS), ("written_by", ("",) + devices.WRITERS))
    for col, allowed in allowed_by:
        if col == "role" and not r["level"] and not r[col]:
            continue                            # a level-less device has no role yet
        if r[col] not in allowed:
            bad.append(f"{at}: {col} {r[col]!r} is not one of {', '.join(a or 'empty' for a in allowed)}")
            unknown = unknown or col == "written_by"
    for col in ("user_name", "description"):
        if not r[col].strip():
            bad.append(f"{at}: {col} is empty")
    return unknown


def _check_id(r: Mapping[str, str], at: str, seen: _Seen, bad: list[str]) -> None:
    """A row with a level has an id, unique on its level; a turnout row's id follows its role's grammar."""
    if not r["level"]:                      # a Store's level-less row has none (devices._unplaced_problems)
        return
    if not r["id"].strip():
        bad.append(f"{at}: id is empty (the builders give every row with a level one, hartlib.device_ids)")
    elif (r["level"], r["id"]) in seen.ids:
        bad.append(f"{at}: id {r['id']!r} is {seen.ids[(r['level'], r['id'])]}'s as well (an id is unique on "
                   "its level)")
    else:
        seen.ids[(r["level"], r["id"])] = at
    if r["layer"] == "turnout":
        grammar = devices.TURNOUT_IDS.get(r["role"])
        if grammar is None:
            bad.append(f"{at}: a turnout row's role is {' or '.join(devices.TURNOUT_IDS)}, not {r['role']!r}")
        elif not grammar.fullmatch(r["id"]):
            bad.append(f"{at}: id {r['id']!r} is not {grammar.pattern.split(':')[0]}:<switch number> (a "
                       f"{r['role']} row's id names its switch, hartlib.device_ids)")


def _check_names(r: Mapping[str, str], at: str, seen: _Seen, bad: list[str]) -> None:
    """(level, layer, user_name) is one row's; a jmri_name is one bean's (a virtual turnout and its LCC alias share
    one internal turnout, so whether a row is an alias is part of the key)."""
    key = (r["level"], r["layer"], r["user_name"])
    if key in seen.keys:
        bad.append(f"{at}: the same level, layer and user_name twice")
    seen.keys[key] = at
    jn = r["jmri_name"]
    if jn:
        jk = (r["layer"], r["role"] == "lcc_alias", jn)
        if jk in seen.jmri:
            bad.append(f"{at}: jmri_name {jn!r} is {seen.jmri[jk]}'s as well")
        seen.jmri[jk] = at


def _check_assignment(r: Mapping[str, str], at: str, seen: _Seen, bad: list[str]) -> None:
    """The names an assignment needs: a field device its system_name (one per layer) and jmri_name, a virtual one
    its jmri_name, none none, a spare its M2S name in both."""
    a, jn = r["assignment"], r["jmri_name"]
    if a == "field":
        if not r["system_name"] or not jn:
            bad.append(f"{at}: a field device needs a system_name and a jmri_name")
        elif r["system_name"] != jn and not (r["role"] == "turnout" and jn == r["user_name"]):
            # a staging turnout the tables and panels bind by its user name (staging_device_map.py): the one exception
            bad.append(f"{at}: field, but system_name {r['system_name']!r} is not jmri_name {jn!r}")
        if r["system_name"]:
            if r["system_name"] in seen.field_systems.get(r["layer"], {}):
                bad.append(f"{at}: field system_name {r['system_name']!r} is "
                           f"{seen.field_systems[r['layer']][r['system_name']]}'s as well")
            seen.field_systems.setdefault(r["layer"], {})[r["system_name"]] = at
    elif a == "virtual" and not jn:
        bad.append(f"{at}: a virtual device needs a jmri_name")
    elif a == "none" and jn:
        bad.append(f"{at}: assignment none, but jmri_name is {jn!r}")
    if (a == "spare") != (r["role"] == "spare"):
        bad.append(f"{at}: assignment spare and role spare go together")
    if a == "spare" and not (r["system_name"] and r["system_name"] == jn):
        bad.append(f"{at}: a spare detector has its M2S name as system_name and jmri_name")


def _check_cells(r: Mapping[str, str], at: str, bad: list[str]) -> None:
    """The cells that belong to one layer or role: panel_status, layout_block, cats_discipline, cp, start, wiring."""
    jn = r["jmri_name"]
    if (r["role"] == "panel_status") != (r["written_by"] == "panel_items.json"):
        bad.append(f"{at}: role panel_status and written_by panel_items.json go together")
    if r["layout_block"] and (r["layer"] != "block" or not r["layout_block"].startswith("ILB")):
        bad.append(f"{at}: layout_block {r['layout_block']!r} is for a block row, an ILB name")
    if r["cats_discipline"] and (r["layer"] != "block" or r["cats_discipline"] not in devices.CATS_DISCIPLINES):
        bad.append(f"{at}: cats_discipline {r['cats_discipline']!r} is for a block row, one of "
                   f"{', '.join(devices.CATS_DISCIPLINES)}")
    if r["cp"] and r["layer"] == "turnout":
        bad.append(f"{at}: a turnout row has no cp; its switch's place is in the switch lists (places.of)")
    if devices.LIST in r["cp"] and r["role"] not in devices.LINE_ROLES:
        bad.append(f"{at}: cp {r['cp']!r} is a list, but a {r['role'] or r['layer']} sits in one control point "
                   f"(only a line block, roles {', '.join(devices.LINE_ROLES)}, lists the places it joins)")
    if r["start"] and r["start"] not in devices.START.get(r["layer"], ()):
        bad.append(f"{at}: start {r['start']!r} is not one a {r['layer']} row takes "
                   f"({', '.join(devices.START.get(r['layer'], ())) or 'none'})")
    elif r["start"] and (not jn or r["role"] == "lcc_alias"):
        bad.append(f"{at}: start is set, but the row makes no bean of its own (no jmri_name, or an LCC alias)")
    if r["wiring"] and r["jmri_comment"]:
        bad.append(f"{at}: wiring and jmri_comment are both set; a row has one comment")


def _check_part(r: Mapping[str, str], at: str, seen: _Seen, bad: list[str]) -> None:
    """A part is a block row with part_of and role part; a part is a JMRI block and layout block of its own on every
    level whose occupancy sensor is its block's, so it has no detector, wiring, node or DCC address of its own."""
    if (r["role"] == "part") != bool(r["part_of"]):
        bad.append(f"{at}: role part and part_of go together")
    if r["part_of"]:
        if r["layer"] != "block":
            bad.append(f"{at}: part_of is for a block row (a piece of track inside another block)")
        made = [c for c in ("node", "detector", "wiring", "dcc") if r[c]]
        if made or r["assignment"] not in ("none", "virtual"):
            bad.append(f"{at}: a part has no detector of its own (its sensor is its block's), so assignment "
                       "none or virtual and no " + ", ".join(made or ["field facts"]))
        seen.parts.append((at, r["level"], r["part_of"]))
        seen.part_names.add((r["level"], r["user_name"]))
    elif r["layer"] == "block":
        seen.whole.add((r["level"], r["user_name"]))


def _check_row(r: Mapping[str, str], seen: _Seen, bad: list[str]) -> None:
    """One row's own invariants and its share of the master's (names, ids, ranks)."""
    at = devices.row_text(r)
    if r["level"] and r["level"] not in devices.LEVELS:
        bad.append(f"{at}: level is one of {', '.join(devices.LEVELS)}, or empty for a device kept by its jmri_bean")
        return
    if not r["level"]:
        bad += [f"{at}: {b}" for b in devices._unplaced_problems(r)]
    elif r["jmri_bean"]:
        bad.append(f"{at}: jmri_bean is for a level-less device; a row with a level is made by the build")
    if r["layer"] not in devices.LAYERS:
        bad.append(f"{at}: layer is one of {', '.join(devices.LAYERS)}")
        return
    unknown = _check_words(r, at, bad)
    _check_id(r, at, seen, bad)
    _check_names(r, at, seen, bad)
    _check_assignment(r, at, seen, bad)
    _check_cells(r, at, bad)
    _check_part(r, at, seen, bad)
    if not unknown:
        seen.ranks.append((devices.row_rank(r), at))


def _check_mast_ids(rows: Sequence[Mapping[str, str]], bad: list[str]) -> None:
    """An intermediate or hidden mast's id names the block it faces (hartlib.device_ids.block_mast_id): that
    block's row on the mast's level, else its one row on another level (a helix block)."""
    block_id = {(r["level"], r["user_name"]): r["id"] for r in rows if r["layer"] == "block" and r["level"]}
    for r in rows:
        if r["layer"] != "mast" or r["role"] not in ("intermediate", "hidden") or not r["level"]:
            continue
        got = block_id.get((r["level"], r["facing"]))
        if got is None:
            other = [v for (_lv, b), v in block_id.items() if b == r["facing"]]
            got = other[0] if len(other) == 1 else None
        if got is not None and r["id"] != f"mast:{got}:{r['dir']}":
            bad.append(f"{devices.row_text(r)}: id {r['id']!r} does not name the block it faces, {r['facing']} "
                       f"(id {got!r}), and its dir {r['dir']!r}")


def _check_parts_and_order(seen: _Seen, bad: list[str]) -> None:
    """Each part names a whole block on its own level; the rows are in devices.row_rank order (else the first that
    is not)."""
    for at, level, target in seen.parts:
        if (level, target) in seen.part_names:
            bad.append(f"{at}: part_of {target!r} is itself a part (a part names a whole block: no chain or cycle)")
        elif (level, target) not in seen.whole:
            bad.append(f"{at}: part_of {target!r} is no block row")
    for (a, na), (b, nb) in zip(seen.ranks, seen.ranks[1:]):
        if b < a:
            bad.append(f"{nb}: out of order (level, layer, then a Store's level-less rows after every level, each "
                       f"writer's rows in WRITERS order); it follows {na}")
            break


def check_rows(rows: Iterable[Mapping[str, str]], where: str) -> None:
    """hartlib.devices.check_rows, in named steps."""
    rows = list(rows)
    bad: list[str] = []
    seen = _Seen()
    for r in rows:
        _check_row(r, seen, bad)
    _check_mast_ids(rows, bad)
    _check_parts_and_order(seen, bad)
    if bad:
        more = f"; and {len(bad) - 20} more" if len(bad) > 20 else ""
        raise devices.DevicesError(f"{where}: " + "; ".join(bad[:20]) + more)
