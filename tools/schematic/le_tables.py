"""The tables side of the Layout Editor build: the panel put in place, the yard ladder retired, and the checks that
every name the panel binds is a bean of the base (hartlib.tables_build.base, which holds every level's beans since
naming-layers step 11) and that the main and upper blocks drawn are numbered as block_numbering.csv says."""
from __future__ import annotations

import copy
import functools
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
from le_common import BLOCK_SYS, BuildError, DEVICE_MAP  # noqa: E402  (and hartlib on the path)
from hartlib import block_numbering, devices, paths, tables  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402  a row's bean name
from hartlib import level_devices  # noqa: E402  the startup LogixNG's names
from hartlib.levels import MAIN_UPPER  # noqa: E402
from hartlib.railroad_facts import MasterRow  # noqa: E402


# One band's names as le_names gives them ({"turnouts", "os", "blocks", "xover_blocks", "masts", ...}).
BandNames = Mapping[str, Any]


class DrawnPanel(Protocol):
    """What the checks read of the plugin's drawn panel: its blocks, and its segments' and turnouts' rows."""
    blocks: Iterable[str]
    segments: Sequence[Mapping[str, Any]]
    turnouts: Sequence[Mapping[str, Any]]


# The main and upper blocks' numbers (IB:C3:<nnnn>, ILB<1000 + n>) are hartlib.block_numbering's: block_numbering.csv
# read and checked there, the rule there, and build_device_map.py copies them into the block rows' jmri_name and
# layout_block. The build reads them off the rows (level_block_beans) and keeps the numbering
# checks here (a retired block drawn again, a stale row), so a stale row stops the build.
NUMBERING = block_numbering.PATH
NUMBERING_COLUMNS = block_numbering.COLUMNS


def load_numbering(path: Path = NUMBERING,
                   names: Mapping[tuple[str, str], str] | None = None) -> block_numbering.Numbering:
    """block_numbering.csv by block name (hartlib.block_numbering.read, its ids named by `names`, default the repo's):
    numbered_as, appended and retired. BuildError on any problem."""
    try:
        return block_numbering.read(path, names)
    except block_numbering.NumberingError as exc:
        raise BuildError(str(exc)) from exc


@functools.cache
def numbering() -> block_numbering.Numbering:
    """The repo's block_numbering.csv (load_numbering), read once on first use, not at import: it names its blocks
    through the device master, and a master that does not load must not stop every importer of this module before
    device-map can rebuild it or say what is wrong. A test patches this function."""
    return load_numbering()


# The numbering's parts under the names build_layout_le re-exports and older tests read: {block: name it is numbered
# as}, the appended blocks, the retired blocks. Each reads numbering() when asked for.
NUMBERING_NAMES = ("BLOCK_NUMBERED_AS", "APPENDED_BLOCKS", "RETIRED_BLOCKS")
_NUMBERING_FIELDS = dict(zip(NUMBERING_NAMES, ("numbered_as", "appended", "retired")))


def __getattr__(name: str) -> Any:
    """BLOCK_NUMBERED_AS, APPENDED_BLOCKS and RETIRED_BLOCKS: numbering()'s fields (a dict and two tuples)."""
    if name in _NUMBERING_FIELDS:
        value = getattr(numbering(), _NUMBERING_FIELDS[name])
        return dict(value) if name == "BLOCK_NUMBERED_AS" else value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------------------------------------------------------------- tables

def place(parent: ET.Element, new: list[ET.Element], depth: int, after: ET.Element | None = None) -> None:
    """Insert `new` into `parent` after `after` (default: at the end), indented as JMRI writes."""
    kids = list(parent)
    idx = kids.index(after) + 1 if after is not None else len(kids)
    prev = kids[idx - 1] if idx else None
    pad = "\n" + "  " * depth
    tail = prev.tail if prev is not None else parent.text
    for k, el in enumerate(new):
        ET.indent(el, space="  ", level=depth)
        parent.insert(idx + k, el)
        el.tail = pad
    if new:
        if prev is not None:
            prev.tail = pad
        else:
            parent.text = pad
        new[-1].tail = tail


block_sort = block_numbering.block_sort


# Retired: the hand-wired Digicon desk's yard-ladder buttons, internal turnouts IT:HART:YL:*
# and the routes IO:AUTO:0201-0210 they fire. No desk or panel uses them; the build leaves them out.
RETIRED_TURNOUT_PREFIX = "IT:HART:YL:"


def retire_yard_ladder(root: ET.Element) -> int:
    """Take the yard-ladder internal turnouts, and every route one of them controls or sets, out of tables `root`;
    the count taken out. Stops when any other reference to one is left."""
    gone, users = 0, set[str]()
    for sec in root.findall("turnouts"):
        for t in [t for t in sec.findall("turnout")
                  if (t.findtext("systemName") or "").startswith(RETIRED_TURNOUT_PREFIX)]:
            users |= {(t.findtext("userName") or "").strip()} - {""}
            sec.remove(t)
            gone += 1
    for sec in root.findall("routes"):
        for r in [r for r in sec.findall("route")
                  if (r.get("controlTurnout") or "").startswith(RETIRED_TURNOUT_PREFIX) or
                  any((o.get("systemName") or "").startswith(RETIRED_TURNOUT_PREFIX)
                      for o in r.findall("routeOutputTurnout"))]:
            sec.remove(r)
            gone += 1
    # by system or user name, anywhere: any text or attribute value of any element
    left = [el.tag for el in root.iter() if isinstance(el.tag, str) and tables.names_any(
        el, users, lambda v: RETIRED_TURNOUT_PREFIX in v, references_only=False, deep=False)]
    if left:
        raise BuildError(f"yard ladder: {RETIRED_TURNOUT_PREFIX}* still named by {sorted(set(left))}")
    return gone


def canon(el: ET.Element) -> str:
    """An element as text without layout whitespace."""
    e = copy.deepcopy(el)
    for c in e.iter():
        c.tail = None
        if c.text is not None and not c.text.strip():
            c.text = None
    return ET.tostring(e, encoding="unicode")


def level_bean_names(path: Path = DEVICE_MAP, rows: Sequence[MasterRow] | None = None) -> set[str]:
    """The system names of every bean the main and upper rows of the device master give (hartlib.tables_build
    master_beans; `rows` in place of reading `path`): each row's bean name (bean_name; an LCC alias names its
    turnout's) and a block row's layout block, and the startup LogixNG with its actions when a row has a start
    (start_logixng). By the rows, not by a naming rule, so a main or upper row bound to a physical name is found too.
    BuildError when the master does not load, or naming a row whose start the startup LogixNG has no action for."""
    if rows is None:
        try:
            rows = devices.load(path)
        except devices.DevicesError as exc:
            raise BuildError(f"{paths.rel(path)}: {exc}") from exc
    out: set[str] = set()
    bad = []
    for r in rows:
        if r.level not in MAIN_UPPER or r.assignment == "none":
            continue
        name = tb.bean_name(r.cells())
        out |= {name, r.layout_block} - {""}
        if r.start:
            action = level_devices.clear_action if r.layer == "occupancy" else level_devices.turnout_action
            try:
                out.add(action(name))
            except ValueError as exc:
                bad.append(f"{r.layer} {r.user_name!r} (level {r.level}): start {r.start!r}: {exc}")
            out |= {level_devices.CLEAR_LOGIXNG, level_devices.CLEAR_CONDITIONAL, level_devices.CLEAR_MANY}
    if bad:
        raise BuildError(f"{paths.rel(path)}: " + "; ".join(bad))
    return out


def is_level_bean(el: ET.Element, names: set[str]) -> bool:
    """Whether bean `el` (a turnout, sensor, block, layout block, head, mast or startup LogixNG element) is one a main
    or upper row gives: its system name is among `names` (level_bean_names, read once by the caller)."""
    return (el.findtext("systemName") or el.get("systemName") or "").strip() in names


def numbered_blocks(blocks: Iterable[str], require_listed: bool = False) -> list[str]:
    """The main and upper blocks in the order their system names are numbered (hartlib.block_numbering.order over
    numbering()). Give it the retired blocks too to keep their numbers taken.
    With require_listed (the build), a block named in block_numbering.csv that is not among `blocks` stops it: the row
    is stale."""
    try:
        return block_numbering.order(blocks, numbering(), require_listed)
    except block_numbering.NumberingError as exc:
        raise BuildError(str(exc)) from exc


def level_block_beans(path: Path = DEVICE_MAP) -> dict[str, tuple[str, str]]:
    """{block: (jmri_name, layout_block)} of every main and upper block row of the device master that has its bean
    names: build_device_map.py copies them from block_numbering.csv (hartlib.block_numbering).
    A helix block row has none (its beans are staging's). BuildError on a row with one of the two only."""
    try:
        rows = devices.load(path)
    except devices.DevicesError as exc:
        raise BuildError(f"{paths.rel(path)}: {exc}") from exc
    out: dict[str, tuple[str, str]] = {}
    bad: list[str] = []
    for r in rows:
        if r.level not in MAIN_UPPER or r.layer != "block":
            continue
        jn, lb = r.jmri_name, r.layout_block
        if bool(jn) != bool(lb):
            bad.append(f"{r.user_name}: jmri_name {jn!r} and layout_block {lb!r}, not both or neither")
        elif jn:
            out[r.user_name] = (jn, lb)
            if jn.startswith(BLOCK_SYS) and (not jn[len(BLOCK_SYS):].isdigit() or
                                             lb != block_numbering.layout_block_name(int(jn[len(BLOCK_SYS):]))):
                bad.append(f"{r.user_name}: layout_block {lb!r} is not the pair of jmri_name {jn!r}")
    if bad:
        raise BuildError(f"{paths.rel(path)}: " + "; ".join(bad))
    stale = stale_block_beans(path)
    if stale:
        raise BuildError(f"{paths.rel(path)}: main and upper block rows whose jmri_name and layout_block are not "
                         f"{NUMBERING.name}'s: {', '.join(stale)}; run build_device_map.py")
    return out


def stale_block_beans(path: Path = DEVICE_MAP, numbering_path: Path = NUMBERING) -> list[str]:
    """The generated main and upper block rows (not a helix block's) whose jmri_name and layout_block are not the
    numbers block_numbering.csv gives now (hartlib.block_numbering over the generated names, as build_device_map.py
    numbers them): the file was edited after the last device-map build. An owner's field jmri_name (a swap) is not
    judged. BuildError on a numbering problem."""
    try:
        rows = [r for r in devices.generated_rows(path) if r["level"] in block_numbering.LEVELS
                and r["layer"] == "block" and r["role"] != "helix"]
        names = {(r["level"], r["id"]): r["user_name"] for r in rows}
        want = block_numbering.bean_names(names.values(), block_numbering.read(numbering_path, names))
    except (devices.DevicesError, block_numbering.NumberingError) as exc:
        raise BuildError(str(exc)) from exc
    return [f"{r['user_name']} ({r['jmri_name'] or 'none'}, not {want[r['user_name']][0]})" for r in rows
            if (r["jmri_name"], r["layout_block"]) != want[r["user_name"]]]


def band_blocks(nm: BandNames) -> set[str]:
    """Every block one band's names (`nm`: the plugin's names of a band) give its track: its OS blocks, a double
    crossover's corner blocks and each track's blocks."""
    return set(nm["os"].values()) | {b for v in nm.get("xover_blocks", {}).values() for b in v.values()} | \
        {b for v in nm["blocks"].values() for b in v}


def bean_names(root: ET.Element) -> dict[str, set[str]]:
    """{turnouts, blocks, masts}: the names a panel can bind in tables `root` (a turnout's system or user name, a
    layout block's user name, a mast's system or user name)."""
    return dict(turnouts=set(tables.by_any_name(tables.turnouts(root))),
                blocks={tables.user_name(b) for b in tables.layout_blocks(root)},
                masts=set(tables.mast_system_names(root)))


def drawn_blocks(P: DrawnPanel, bands: set[int]) -> set[str]:
    """The blocks the plugin drew on `bands` (band indexes): its track segments' and turnouts' legs'."""
    return {s["block"] for s in P.segments if s.get("band") in bands and s.get("block")} | \
        {b for t in P.turnouts if t.get("band") in bands for b in (t.get("blocks") or {}).values() if b}


def check_level_blocks(root: ET.Element, P: DrawnPanel, staging_keys: set[str],
                       names: Mapping[str, BandNames]) -> None:
    """The numbering checks on the main and upper blocks the panel draws (every drawn block but the staging bands'
    names', `staging_keys`), now that the base holds their beans (hartlib.tables_build.base): none is a retired block
    drawn again (block_numbering.csv's retired rows), no block_numbering.csv row names a block not drawn (a stale row:
    numbered_blocks), each has its device-master row's jmri_name and layout_block, current with the numbering
    (level_block_beans), and each block bean of tables `root` is bound to an occupancy sensor (its detector row's,
    or its OS block's for a part). BuildError names them."""
    staging_blocks = {b for k in staging_keys for b in band_blocks(names[k])}
    drawn = {b for b in P.blocks if b not in staging_blocks}
    retired = set(numbering().retired)
    if drawn & retired:
        raise BuildError(f"retired blocks drawn again: {sorted(drawn & retired)}; take them out of "
                         f"{NUMBERING.name}'s retired rows")
    numbered_blocks(drawn | retired, require_listed=True)           # a stale block_numbering.csv row stops
    beans = level_block_beans()
    unnamed = sorted(drawn - set(beans))
    if unnamed:
        raise BuildError(f"main and upper blocks whose device-master row gives no jmri_name and layout_block: "
                         f"{unnamed}; run build_device_map.py")
    full = {tables.user_name(b): b for b in tables.blocks(root)}
    unbound = sorted(b for b in drawn if b in full and not (full[b].findtext("occupancysensor") or "").strip())
    if unbound:
        raise BuildError(f"main and upper blocks with no occupancy sensor (no detector row names them in the device "
                         f"map): {unbound}")


def check_bound(root: ET.Element, P: DrawnPanel, names: Mapping[str, BandNames], staging_keys: set[str],
                staging_ix: set[int], base_name: str) -> None:
    """One check for every level, on the tables the panel is drawn on (`root`: the base, which holds every level's
    beans, base_name names it): each turnout, block and mast a band's names bind (`names`: {band key: names}) is a
    bean of `root`; the staging bands (`staging_keys`, band indexes `staging_ix`: their names are the staging device
    map's) draw only blocks their names hold; and each block the panel draws (P.blocks) is a bean of `root`.
    BuildError names each by band."""
    if staging_keys - set(names):
        raise BuildError(f"the staging bands {sorted(staging_keys - set(names))} are not among the bands named "
                         f"{sorted(names)}")
    have = bean_names(root)
    bad = []
    for key, nm in names.items():
        lost = [f"turnouts {sorted(t for t in set(nm['turnouts'].values()) if t not in have['turnouts'])}",
                f"blocks {sorted(b for b in band_blocks(nm) if b not in have['blocks'])}",
                f"masts {sorted(m['mast'] for m in nm.get('masts', []) if m['mast'] not in have['masts'])}"]
        lost = [x for x in lost if not x.endswith(" []")]
        if lost:
            bad.append(f"{key}: {', '.join(lost)}")
    own = {b for k in staging_keys for b in band_blocks(names[k])}
    stray = sorted(drawn_blocks(P, staging_ix) - own)
    if stray:
        bad.append(f"{', '.join(sorted(staging_keys))} draws blocks its names do not hold: {stray}")
    drawn = sorted(set(P.blocks) - have["blocks"])
    if drawn:
        bad.append(f"the panel draws blocks {drawn}")
    if bad:
        raise BuildError(f"names the panel binds that are no bean of {base_name}: " + "; ".join(bad))
