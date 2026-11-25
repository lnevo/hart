"""Names and bindings of the Layout Editor build: the main and upper levels' device-map names and masts, staging's
plan lengths and columns (its names are the staging device map's: staging_device_map.load), and the bands as
named for the plugin's label layer."""
from __future__ import annotations

import copy
import functools
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402,F401  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
from hartlib import coordinator, devices, drawing_keys, level_devices, paths, railroad, tables  # noqa: E402
from hartlib import level_masts as level_masts_lib  # noqa: E402  masts.csv and its virtual names
from le_common import (  # noqa: E402
    band_key, band_levels, bare, STAGING_LEVELS, BuildError, DEVICE_MAP, main_upper_device_map,
)


def crossover_strands(band) -> set:
    """Tracks joining two switches of one number C to C: inside a single crossover, as the plugin draws it."""
    nodes = band["nodes"]
    out = set()
    for sid, s in band["strands"].items():
        (u, pu), (v, pv) = s["src"], s["dst"]
        if u != v and pu == pv == "C" and nodes[u]["kind"] == nodes[v]["kind"] == "switch" and \
                nodes[u].get("label") and nodes[u]["label"] == nodes[v]["label"]:
            out.add(sid)
    return out


def runs(band, skip=()):
    """Tracks joined through turnbacks: [(start (node, port), [(strand id, reversed)], end (node, port))]."""
    nodes, strands = band["nodes"], band["strands"]
    turn = lambda n: nodes[n]["kind"].startswith("turn")      # noqa: E731
    done, out = set(), []

    def beyond(cur, node):
        nxt = next((k for k in strands if k != cur and node in (strands[k]["src"][0], strands[k]["dst"][0])), None)
        if nxt is None:
            raise BuildError(f"turnback {node}: only track {cur} reaches it")
        return nxt

    for sid in sorted(strands):
        if sid in done or sid in skip:
            continue
        # walk back to a terminal end, then forward
        cur, rev = sid, False
        for _ in range(len(strands) + 1):
            head = strands[cur]["dst"] if rev else strands[cur]["src"]
            if not turn(head[0]):
                break
            nxt = beyond(cur, head[0])
            rev = strands[nxt]["src"][0] == head[0]
            cur = nxt
        else:
            raise BuildError(f"track {sid}: a closed loop of turnbacks with no switch or end")
        start = strands[cur]["dst"] if rev else strands[cur]["src"]
        chain = []
        for _ in range(len(strands)):
            chain.append((cur, rev))
            done.add(cur)
            tail = strands[cur]["src"] if rev else strands[cur]["dst"]
            if not turn(tail[0]):
                break
            cur = beyond(cur, tail[0])
            rev = strands[cur]["dst"][0] == tail[0]
        out.append((tuple(start), chain, tuple(tail)))
    return out


def staging_lengths(names: dict, plan_inches: dict | None = None) -> dict:
    """{block: inches} of every staging block the schematic draws, from block_lengths.csv's plan_in (the AnyRail plan
    5.3c, tools/schematic/plan_lengths.py; owner, 2026-11-20): the plugin cuts a track of several blocks at their
    plan shares (the Scale track ends in OS Switch 7, which is drawn its turnout's length). BuildError on a drawn
    block with no plan length."""
    plan_inches = plan_lengths() if plan_inches is None else plan_inches
    drawn = sorted({b for v in names["blocks"].values() for b in v})
    missing = [b for b in drawn if b not in plan_inches]
    if missing:
        raise BuildError(f"block_lengths.csv has no plan length for drawn staging blocks {missing}")
    return {b: float(plan_inches[b]) for b in drawn}


@functools.lru_cache(maxsize=1)
def plan_lengths() -> dict:
    """{block: plan inches} of block_lengths.csv (hartlib.railroad); read once. BuildError on a file hartlib cannot
    read."""
    from hartlib import railroad
    try:
        rows = railroad.read_block_lengths(railroad.Sources.under().block_lengths)
    except railroad.FactsError as exc:
        raise BuildError(f"block_lengths.csv: {exc}") from None
    return {name: r.plan_in for name, r in rows.items()}


MM_PER_INCH = 25.4
MASTS = level_masts_lib.PATH      # masts.csv, every level's (build_masts.py)
# the levels the build adds (main and upper), whose masts it draws on internal heads: every level the base holds none of
ADDED_LEVELS = tuple(lv for lv in level_masts_lib.LEVELS if lv not in STAGING_LEVELS)


def read_level_masts(path: Path = MASTS) -> list[dict]:
    """masts.csv's rows of the levels the build adds (ADDED_LEVELS; hartlib.level_masts.read: each with `heads` as
    [(internal system name, user name)]), checked again against signal_coordinator.py's own test: no mast or head on
    a name it would enrol or publish (lcos_named)."""
    try:
        rows = level_masts_lib.read(path, levels=ADDED_LEVELS)
    except ValueError as exc:
        raise BuildError(str(exc)) from None      # hartlib names the file and the line itself
    bad = lcos_named([r["system_name"] for r in rows] + [h for r in rows for h, _u in r["heads"]])
    if bad:
        raise BuildError(f"{paths.rel(path)}: names signal_coordinator.py takes for LCOS heads, which would reach "
                         f"MQTT and the field before the cut-over: {bad}")
    return rows


@functools.lru_cache(maxsize=None)
def lcos_rule():
    """signal_coordinator.py's own test for an LCOS head's system name (_is_lcos_ih_sys) and the pattern it finds
    heads in a mast's system name by (_HEAD_IN_MAST), read from its source and its sibling modules' (hartlib.coordinator;
    it is Jython and imports jmri): the functions and constants they use, run here in CPython."""
    try:
        src = coordinator.source()
    except coordinator.CoordinatorError as exc:
        raise BuildError(str(exc)) from None
    parts = []
    for name in ("_LCOS_SIGNAL_UID_MIN", "_LCOS_SIGNAL_UID_MAX", "_HEAD_IN_MAST"):
        m = re.search(rf"^{name} = .*$", src, re.M)
        parts.append(m.group(0) if m else None)
    for name in ("_packed_is_lcos_signal", "_is_lcos_ih_sys"):    # a whole top-level def, to the next top level
        m = re.search(rf"^def {name}\(.*?(?=^\S)", src, re.M | re.S)
        parts.append(m.group(0) if m else None)
    if None in parts:
        raise BuildError("signal_coordinator.py and its sibling modules no longer define its LCOS head test as "
                         "lcos_rule reads it")
    ns = {"re": re}
    # the module is Jython (it imports jmri, and Java names CPython cannot parse), so only these pieces are run
    exec(compile("\n".join(parts), "signal_coordinator.py", "exec"), ns)  # noqa: S102
    return ns["_is_lcos_ih_sys"], ns["_HEAD_IN_MAST"]


def lcos_named(names: list[str]) -> list[str]:
    """The head and mast system names among `names` that signal_coordinator.py takes for LCOS heads: a head it would
    enrol, or a mast whose heads include one."""
    is_lcos, in_mast = lcos_rule()
    out = []
    for n in names:
        heads = [t[1:-1] for t in in_mast.findall(n)] if n.startswith("IF$") else [n]
        if any(is_lcos(h) for h in heads):
            out.append(n)
    return sorted(out)


def level_masts(names: dict, rows: list[dict], skip: set) -> None:
    """Give each main and upper band in `names` (every key but `skip`: the bands of a level the base holds,
    le_common.base_keys) its masts (masts.csv rows) for the plugin: each in the
    band whose drawing has its facing track and its protected OS block (127-221 and Helix Inner meet Switches 127 and 131
    on the upper band), as a turnout mast with its icon's size (hartlib.tables.mast_icon_size) and `leg` where two
    masts share one facing and protected block; a virtual mast (a destination, no switch) hidden in the end bumper
    slot of the track it faces, as staging's are. Stops on a mast no band, or two, draws."""
    bad = []
    for r in rows:
        if level_masts_lib.is_level_virtual(r["system_name"]):    # a hidden destination mast at a buffer stop
            where = [k for k, v in names.items() if k not in skip
                     and r["facing"] in {b for bl in v["blocks"].values() for b in bl}]
        elif not r["switch"]:     # an APB intermediate (owner, 2026-11-19): between two track blocks of one band
            where = [k for k, v in names.items() if k not in skip
                     and r["facing"] in {b for bl in v["blocks"].values() for b in bl}
                     and r["protects"] in {b for bl in v["blocks"].values() for b in bl}]
        else:
            where = [k for k, v in names.items() if k not in skip
                     and r["facing"] in {b for bl in v["blocks"].values() for b in bl}
                     and r["protects"] in set(v["os"].values()) | {b for x in v.get("xover_blocks", {}).values()
                                                                  for b in x.values()}]
        if len(where) != 1:
            bad.append(f"{r['mast']} ({r['facing']} into {r['protects']}): drawn on {where or 'no band'}")
            continue
        size, known = tables.mast_icon_size(r["system_name"])
        if not known:
            bad.append(f"{r['mast']}: no icon size for {r['system_name']}")
            continue
        if level_masts_lib.is_level_virtual(r["system_name"]):
            entry = dict(mast=r["mast"], facing=r["facing"], protects=[], kind="end bumper", hidden=True,
                         icon=list(size))
        else:
            entry = dict(mast=r["mast"], facing=r["facing"], protects=[r["protects"]],
                         kind="turnout" if r["switch"] else "anchor", hidden=False, icon=list(size))
        if r["leg"]:
            entry["leg"] = r["leg"]
        names[where[0]].setdefault("masts", []).append(entry)
    if bad:
        raise BuildError("main and upper masts not placed: " + "; ".join(bad))
    for k, v in names.items():
        if k not in skip and v.get("masts"):
            v["masts"].sort(key=lambda m: m["mast"])


# ---------------------------------------------------------------- main and upper placeholders

def placeholder_names(bands, le_mod, page=None) -> tuple[dict, dict]:
    """({band key: names}, {block: length mm}) for every band but staging's (not STAGING_LEVELS: the
    staging band, whose names are the staging device map's, by its level). `bands` are the solved sheet's, titles
    unchanged (build_layout_le passes the plugin's drawn_bands, which keep them): each band's level is found by its
    title in plan_overrides.json (le_common.band_levels), so a band the plan does not title stops with BuildError.
    A balloon loop is two blocks (the device map's loop_halves) and a double crossover four, one per corner
    (`xover_blocks`, named by the corner each leg reaches as the plugin draws it: the device map's xover_corners;
    `page`: the sheet's options, for rotate_bands). A track's placeholder is its switch-and-leg key
    (staging_device_map.band_refs); BuildError on a connector the plugin's partners do not pair, which has no switch
    and leg beyond it to key a track by."""
    joined = le_mod.partners(bands)
    import build_device_map as bdm
    out, lengths, counted = {}, defaultdict(float), set()
    for bi, ((title, band, _), level) in enumerate(zip(bands, band_levels(bands))):
        if level in STAGING_LEVELS:
            continue
        key = band_key(title)
        nodes, strands = band["nodes"], band["strands"]
        try:
            loop_half = bdm.loop_halves(band, runs)      # a balloon loop is two blocks, parted at its turnback
        except bdm.MapError as exc:
            raise BuildError(f"{title}: {exc}") from None
        names = dict(turnouts={}, os={}, blocks={}, xover_blocks={})
        for n, d in sorted(nodes.items()):
            if d["kind"] == "dx":
                names["turnouts"][n] = f"Switch {bare(d['label'])}"
                try:
                    corners = le_mod.double_corners(band, n, key in (page or {}).get("rotate_bands", ()))
                    names["xover_blocks"][n] = bdm.xover_corners(bdm.base(d["label"]), corners)
                except (bdm.MapError, le_mod.SchematicError) as exc:
                    raise BuildError(f"{title}: {exc}") from None
            elif d["kind"] == "switch":
                names["turnouts"][n] = f"Switch {bare(d['label'])}"
                names["os"][n] = "OS Switch " + re.sub(r"[AB]$", "", bare(d["label"]))
        # a track's placeholder is its switch-and-leg key, the grammar of every level's trial names (owner,
        # 2026-11-20: staging_device_map.band_refs and strand_placeholders; a balloon loop's halves are its pieces #1
        # and #2). A connector that `joined` does not pair stops the build here (band_refs)
        import staging_device_map as sdm
        try:
            refs = sdm.band_refs(bands, joined, bi)
        except sdm.StagingMapError as exc:
            raise BuildError(f"{title}: {exc}") from None
        for start, chain, end in runs(band):
            labels = []
            for n, _ in (start, end):
                if nodes[n].get("sub") == "link" and (bi, n) in joined:      # the far side of the connector
                    bj, m = joined[(bi, n)]
                    other = bands[bj][1]
                    sid = next(iter(list(other["nodes"][m]["ins"].values()) + list(other["nodes"][m]["outs"].values())))
                    s = other["strands"][sid]
                    n2 = s["dst"][0] if s["src"][0] == m else s["src"][0]
                    labels.append(bare(other["nodes"][n2].get("label")))
                else:
                    labels.append(bare(nodes[n].get("label")) if nodes[n]["kind"] in ("switch", "dx") else "")
            a, b = labels
            inside_xover = (a and b and a[-1:] in "AB" and b[-1:] in "AB" and a[:-1] == b[:-1] and a[:-1].isdigit())
            for sid, _ in chain:
                s = strands[sid]
                block = f"OS Switch {a[:-1]}" if inside_xover else sdm.strand_placeholders(refs[sid])[0]
                names["blocks"][sid] = [block]
                # a turnback's two tracks each carry their whole edge's length (count it once, or half each for a
                # balloon loop's two blocks); a connector or helix cut leaves a piece on each band (e36x, e36y):
                # count both
                if (block, s["edge"]) not in counted:
                    counted.add((block, s["edge"]))
                    lengths[block] += s["cm"] * 10 / (2 if sid in loop_half else 1)
        for n in list(names["os"].values()) + [b for v in names["xover_blocks"].values() for b in v.values()]:
            lengths[n] += 0.0
        out[key] = names
    return out, dict(lengths)


def device_names(path: Path = DEVICE_MAP) -> dict:
    """{placeholder: device-map user name} for the main and upper turnouts and blocks, parts among them: the one
    reader of the drawing keys (hartlib.drawing_keys, keyed by device ID; naming-layers step 13) over levels 2 and 3,
    each key named by its ID's row in the merged view (the owner's name, else the generated). A crossover's two halves
    are one turnout ("Switch 101A", "Switch 101B" -> "Switch 101"). A part (the device master's part_of: a link
    inside an OS block) is a JMRI block of its own under its own name (owner, 2026-11-20), whose occupancy sensor is
    its OS block's (hartlib.tables_build.master_beans). Stops on a row with no trial name, a trial name given twice,
    a part of no main or upper block row, or a generated name out of form: a turnout not named "Switch <n>" or a
    block not named "Track ..." or "OS Switch <n>". A name the owner gives in devices_field.csv is the owner's to
    choose (naming-layers step 13: as hartlib.railroad.check_virtual_names takes it)."""
    main_upper_device_map(path)         # read and checked by hartlib.railroad (BuildError naming the file)
    try:
        keys = drawing_keys.read(level_devices.LEVELS, path)
    except (drawing_keys.DrawingKeyError, railroad.FactsError) as exc:
        raise BuildError(f"{paths.rel(path)}: {exc}") from None
    try:            # the rows the owner names (devices_field.csv): their names are free, as railroad's check holds
        owned = {k for k, f in devices.field_index(path).items() if f.get("user_name")}
    except railroad.FactsError as exc:
        raise BuildError(f"{paths.rel(path)}: {exc}") from None
    bad = []
    for key, r in keys.rows.items():
        form = r"Switch \d+" if r["layer"] == "turnout" else r"(Track \S.*|OS Switch \d+[a-d]?)"
        if r["role"] != "part" and key not in owned and not re.fullmatch(form, r["user_name"]):
            bad.append(f"{devices.row_text(r)} is not named {form}")
    if bad:
        raise BuildError(f"{paths.rel(path)}: " + "; ".join(bad))
    out = {key: keys.rows[device_id]["user_name"] for key, device_id in keys.ids.items()}
    if not out:
        raise BuildError(f"{paths.rel(path)}: no turnout or block rows")
    return out


def level_names(bands, le_mod, device: dict | None = None, page=None) -> tuple[dict, dict]:
    """placeholder_names with every placeholder replaced by its device-map name (device_names): ({band key: names},
    {block: length mm}, each block its block_lengths.csv plan length). Stops on a placeholder the device map does not name, or a device-map name the drawing does
    not use."""
    device = device_names() if device is None else device
    names, lengths = placeholder_names(bands, le_mod, page)
    used, missing = set(), set()

    def to(ph):
        if ph not in device:
            missing.add(ph)
            return ph
        used.add(ph)
        return device[ph]

    out = {}
    for key, nm in names.items():
        out[key] = dict(turnouts={n: to(t) for n, t in nm["turnouts"].items()},
                        os={n: to(b) for n, b in nm["os"].items()},
                        xover_blocks={n: {leg: to(b) for leg, b in v.items()} for n, v in nm["xover_blocks"].items()},
                        blocks={sid: [to(b) for b in v] for sid, v in nm["blocks"].items()})
    drawn = {to(ph) for ph in lengths}
    if missing:
        raise BuildError(f"main and upper placeholders {paths.rel(DEVICE_MAP)} names nowhere: {sorted(missing)}")
    unused = sorted(set(device) - used)
    if unused:
        raise BuildError(f"{paths.rel(DEVICE_MAP)} trial names the drawing does not have: {unused}")
    plan = plan_lengths()           # block_lengths.csv's plan_in, every level (owner, 2026-11-20, step 5 part 2)
    no_length = sorted(b for b in drawn if b not in plan)
    if no_length:
        raise BuildError(f"block_lengths.csv has no plan length for main and upper blocks {no_length}: run "
                         "python3 tools/schematic/plan_lengths.py")
    return out, {b: plan[b] * MM_PER_INCH for b in drawn}


def shared_turnouts(names: dict, skip: set) -> None:
    """Give each main and upper band's names (every key of `names` but `skip`: the bands of a level the base holds,
    le_common.base_keys) the turnouts it shares with another band (`shared_turnouts`): a
    crossover whose halves stand on two levels (the helix-top 127 and 131) is one device-map turnout drawn as two
    Layout Editor turnouts, which JMRI throws together. A crossover whose halves stand on one level is the plugin's
    own (schematic.core.crossover_halves pairs halves joined C to C or B to C, 121 and 125 among them)."""
    bands_of = defaultdict(set)
    for key, nm in names.items():
        if key not in skip:
            for t in nm["turnouts"].values():
                bands_of[t].add(key)
    for key, nm in names.items():
        if key not in skip:
            nm["shared_turnouts"] = sorted(t for t in set(nm["turnouts"].values()) if len(bands_of[t]) > 1)


def block_roles(path: Path = DEVICE_MAP) -> dict[str, str]:
    """{block: role} of the main and upper block rows of the device map at `path`, parts among them (placed rows of
    levels 2 and 3 only: a Store's level-less row is no block of the drawing). BuildError when the map cannot be
    read."""
    out = {name: r.role for name, r in main_upper_device_map(path).blocks.items()}
    try:
        out.update((r["user_name"], r["role"]) for _line, r in devices.part_lines(("2", "3"), path))
    except railroad.FactsError as exc:
        raise BuildError(f"the device map: {exc}") from None
    return out


def named_bands(bands, names: dict, roles: dict[str, str] | None = None):
    """A copy of `bands` in which each main and upper track block is named on one of its tracks (the longest; its
    name the block's without "Track "), so the plugin's label layer writes the device-map track names there; every
    other main and upper track is unnamed, but a helix track keeps its plan name (Helix Outer, Helix Inner): the
    plugin joins the helix ends of two levels by that name (le.partners) and draws its track_labels label (McKees
    Rocks for Helix Outer) in its place. A track block is a line block by its role (devices.LINE_ROLES, a part among
    them; an OS block or crossover corner is not) in `roles` (block_roles: default the main and upper rows of
    DEVICE_MAP, the map level_names reads by default; give block_roles(path) for names made from another map): a
    block it does not hold stops with BuildError. A band of
    the staging level (STAGING_LEVELS, by its level) is left as it is. `bands` are the solved sheet's,
    titles unchanged, as for placeholder_names: a band plan_overrides.json does not title stops with BuildError.
    The label options (preferences.json[main_upper]'s le_labels and le_band_labels, a name left off the panel among
    them: hidden_names) reach the plugin through each band's own preferences, unchanged here."""
    out = []

    def line_block(block: str) -> bool:
        nonlocal roles
        roles = block_roles() if roles is None else roles      # read once a band names a block
        if block not in roles:
            raise BuildError(f"the device map has no main or upper block row {block!r}")
        return roles[block] in devices.LINE_ROLES

    for (title, band, opts), level in zip(bands, band_levels(bands)):
        if level in STAGING_LEVELS:
            out.append((title, band, opts))
            continue
        key = band_key(title)
        band = copy.deepcopy(band)
        nodes = band["nodes"]
        # a crossover's two halves on this band ("101A", "101B" joined C to C), one device-map turnout: labelled by
        # its number, so the plugin draws them as one single crossover, as staging's 7, 23 and 35
        for s in band["strands"].values():
            (u, pu), (v, pv) = s["src"], s["dst"]
            a, b = (bare(nodes[x].get("label")) for x in (u, v))
            if u != v and pu == pv == "C" and nodes[u]["kind"] == nodes[v]["kind"] == "switch" and \
                    re.fullmatch(r"\d+[AB]", a or "") and a[:-1] == b[:-1] and a != b:
                if names[key]["turnouts"].get(u) != names[key]["turnouts"].get(v):
                    raise BuildError(f"{title}: switches {a} and {b} are joined as a crossover but the device map "
                                     f"gives them two turnouts")
                nodes[u]["label"] = nodes[v]["label"] = a[:-1]
        by_block = defaultdict(list)
        for sid, blocks in names[key]["blocks"].items():
            if len(blocks) != 1:
                raise BuildError(f"{title}: track {sid} has blocks {blocks}, not one")
            if line_block(blocks[0]):
                by_block[blocks[0]].append(sid)
        helix = {sid for sid, s in band["strands"].items()
                 if any(nodes[e[0]].get("sub") == "helix" for e in (s["src"], s["dst"]))}
        for sid, s in band["strands"].items():
            if sid not in helix:        # a helix track keeps its plan name: le.partners joins the levels by it
                s["name"] = ""
        for block, sids in by_block.items():
            if helix & set(sids):
                continue
            best = max(sids, key=lambda k: (band["strands"][k]["cm"], k))
            band["strands"][best]["name"] = block.removeprefix("Track ")
        out.append((title, band, opts))
    return out
