"""Names and bindings of the Layout Editor build: the main and upper levels' device-map names and masts, staging's
measured lengths and columns (its names are the staging device map's: staging_device_map.load), and the bands as
named for the plugin's label layer."""
from __future__ import annotations

import copy
import functools
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
from hartlib import paths, tables  # noqa: E402
from hartlib import level_masts as level_masts_lib  # noqa: E402  main_upper_masts.csv and its virtual names
from le_common import band_key, bare, BuildError, DEVICE_MAP, read_csv, STAGING, SWITCHES  # noqa: E402


# Main and upper at staging's grid (the three-level candidate): denser than staging, so every block's contents icon
# comes first and a track name with no room is left out (logged; the plugin's names_last), and the icons are 12 px,
# the short reserve still tried before none (owner, 2026-11-16): at 13 px three have no clean spot at any reserve.
LEVEL_LE_LABELS = {"names_last": True, "block_contents_size": 12}
# {band key: switch numbers} placed below their turnout first (the plugin's numbers_below): SW-101 on its crossover's
# bottom track side, clear of 103 drawn tight above it (owner, 2026-11-16)
NUMBERS_BELOW = {"Main": ["101"]}
# {band key: blocks} whose contents icon may be left out (the plugin's optional_block_contents, logged): Track 227-233
# is 16 px between switches 227 and 233, and with Masts 228RA and 228RB beside it no clean spot is left (2026-11-16)
OPTIONAL_READOUTS = {"Upper": ["Track 227-233"]}


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


# Staging switches whose generated turnout has the hand-drawn panel's leg letters B and C swapped (and so its
# continuing route): JMRI draws a plain turnout's leg A in line with leg B, so a switch whose hand-drawn leg B is the
# diverging track on the sheet is drawn as the sheet has it only with that track on leg C (owner, 2026-11-16). The
# plugin draws every staging turnout so by itself (leg B the straight leg), so this list sets nothing in the drawing:
# it records which switches differ from the hand-drawn letters. A mast on such a leg stands on the other letter
# (le_signal_boundaries.csv's generated_slot, held to this list by check_swapped_slots), and check_boundaries stops
# the build unless the drawn panel puts each mast there.
LEGS_SWAPPED = {"13": "Barn on leg C, so 15-13-11 is drawn level as on the sheet (owner, 2026-11-16)"}


def swapped_idents() -> set:
    """The live Layout Editor idents of the LEGS_SWAPPED switches (switches.csv)."""
    idents = {r["switch"]: r["le_ident"] for r in read_csv(SWITCHES)}
    missing = sorted(set(LEGS_SWAPPED) - set(idents))
    if missing:
        raise BuildError(f"LEGS_SWAPPED names switches switches.csv does not have: {missing}")
    return {idents[k] for k in LEGS_SWAPPED}


def staging_lengths(opts: dict, names: dict) -> dict:
    """{block: inches} for each staging block the schematic draws whose track has a measured length (layer 1
    `track_lengths_in`, by track name: block "Track S-1 West" is track "S-1 West"), so a track with several blocks
    is cut at their real shares: a short throat block (S-1 West, East Lead East, K-1 West) sits at its own end."""
    measured = opts.get("track_lengths_in") or {}
    if not isinstance(measured, dict):
        raise BuildError("staging track_lengths_in must be an object of track name: inches")
    used = {b for v in names["blocks"].values() for b in v}
    out = {}
    for track, inches in sorted(measured.items()):
        if isinstance(inches, bool) or not isinstance(inches, (int, float)) or not inches > 0:
            raise BuildError(f"staging track_lengths_in: {track!r} has length {inches!r}, not inches above zero")
        if f"Track {track}" not in used:
            raise BuildError(f"staging track_lengths_in: no drawn staging track has the block 'Track {track}' "
                             "(renamed or misspelt?)")
        out[f"Track {track}"] = float(inches)
    # A track that also holds an OS block (the Scale track ends in OS Switch 7) has no measured length for it, so
    # it is drawn with equal blocks as before; its track's length is left out rather than logged on every build.
    for blocks in names["blocks"].values():
        if any(b.startswith("OS ") for b in blocks):
            for b in blocks:
                out.pop(b, None)
    return out


MAIN_UPPER_MASTS = level_masts_lib.PATH      # build_main_upper_masts.py, from the device map


def read_level_masts(path: Path = MAIN_UPPER_MASTS) -> list[dict]:
    """main_upper_masts.csv's rows (hartlib.level_masts.read: each with `heads` as [(internal system name, user
    name)], every head internal), checked again against signal_coordinator.py's own test: no mast or head on a name
    it would enrol or publish (lcos_named)."""
    try:
        rows = level_masts_lib.read(path)
    except ValueError as exc:
        raise BuildError(f"{paths.rel(path)}: {exc}") from None
    bad = lcos_named([r["system_name"] for r in rows] + [h for r in rows for h, _u in r["heads"]])
    if bad:
        raise BuildError(f"{paths.rel(path)}: names signal_coordinator.py takes for LCOS heads, which would reach "
                         f"MQTT and the field before the cut-over: {bad}")
    return rows


@functools.lru_cache(maxsize=None)
def lcos_rule():
    """signal_coordinator.py's own test for an LCOS head's system name (_is_lcos_ih_sys) and the pattern it finds
    heads in a mast's system name by (_HEAD_IN_MAST), read from its source (it is Jython and imports jmri): the
    functions and constants they use, run here in CPython."""
    src = (pd.REPO / "jmri/scripts/signal_coordinator.py").read_text(encoding="utf-8")
    parts = []
    for name in ("_LCOS_SIGNAL_UID_MIN", "_LCOS_SIGNAL_UID_MAX", "_HEAD_IN_MAST"):
        m = re.search(rf"^{name} = .*$", src, re.M)
        parts.append(m.group(0) if m else None)
    for name in ("_packed_is_lcos_signal", "_is_lcos_ih_sys"):    # a whole top-level def, to the next top level
        m = re.search(rf"^def {name}\(.*?(?=^\S)", src, re.M | re.S)
        parts.append(m.group(0) if m else None)
    if None in parts:
        raise BuildError("signal_coordinator.py no longer defines its LCOS head test as lcos_rule reads it")
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


def level_masts(names: dict, rows: list[dict]) -> None:
    """Give each main and upper band in `names` its masts (main_upper_masts.csv rows) for the plugin: each in the
    band whose drawing has its facing track and its protected OS block (129-221 and 135-H2 meet Switches 129 and 135
    on the upper band), as a turnout mast with its icon's size (hartlib.tables.mast_icon_size) and `leg` where two
    masts share one facing and protected block. Stops on a mast no band, or two, draws."""
    bad = []
    for r in rows:
        where = [k for k, v in names.items() if k != STAGING
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
        entry = dict(mast=r["mast"], facing=r["facing"], protects=[r["protects"]], kind="turnout", hidden=False,
                     icon=list(size))
        if r["leg"]:
            entry["leg"] = r["leg"]
        names[where[0]].setdefault("masts", []).append(entry)
    if bad:
        raise BuildError("main and upper masts not placed: " + "; ".join(bad))
    for k, v in names.items():
        if k != STAGING and v.get("masts"):
            v["masts"].sort(key=lambda m: m["mast"])


# ---------------------------------------------------------------- main and upper placeholders

def placeholder_names(bands, le_mod, page=None) -> tuple[dict, dict]:
    """({band key: names}, {block: length mm}) for every band but staging. A balloon loop is two blocks (the device
    map's loop_halves) and a double crossover four, one per corner (`xover_blocks`, named by the corner each leg
    reaches as the plugin draws it: the device map's xover_corners; `page`: the sheet's options, for rotate_bands)."""
    joined = le_mod.partners(bands)
    import build_device_map as bdm
    out, lengths, counted = {}, defaultdict(float), set()
    for bi, (title, band, _) in enumerate(bands):
        key = band_key(title)
        if key == STAGING:
            continue
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
                edge = s["edge"]
                if any(nodes[x[0]].get("sub") == "link" for x in (s["src"], s["dst"])):
                    edge = re.sub(r"(?<=\d)[xy]$", "", edge)
                block = f"OS Switch {a[:-1]}" if inside_xover else \
                    bdm.loop_placeholder(f"Track {edge}", loop_half.get(sid))
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
    """{placeholder: device-map user name} for the main and upper turnouts and blocks: each turnout or block row's
    `trial_name` (comma separated: a crossover's two halves are one turnout, "Switch 101A, Switch 101B" -> "Switch
    101") is the placeholder placeholder_names gives. Stops on a row with no trial name, a trial name given twice, a
    turnout not named "Switch <n>" or a block not named "Track ..." or "OS Switch <n>"."""
    try:
        rows = read_csv(path)
    except OSError as exc:
        raise BuildError(f"cannot read the device map {path}: {exc}") from None
    need = {"layer", "user_name", "trial_name"}
    if rows and not need <= set(rows[0]):
        raise BuildError(f"{paths.rel(path)}: columns {sorted(rows[0])} lack {sorted(need - set(rows[0]))}")
    out, bad = {}, []
    for i, r in enumerate(rows, 2):
        if r["layer"] not in ("turnout", "block"):
            continue
        user = (r["user_name"] or "").strip()
        if r["layer"] == "turnout" and user.startswith("DCC "):
            continue                    # the LCC alias of a turnout: not a panel object
        form = r"Switch \d+" if r["layer"] == "turnout" else r"(Track \S.*|OS Switch \d+[a-d]?)"
        if not re.fullmatch(form, user):
            bad.append(f"line {i}: {r['layer']} {user!r} is not named {form}")
            continue
        # a trailing "*" marks a switch the plan's label carries one on (223, owner-confirmed hand); the drawing's
        # placeholder is the bare name, as placeholder_names writes it
        trial = [bare(t.strip()) for t in (r["trial_name"] or "").split(",") if t.strip()]
        if not trial:
            bad.append(f"line {i}: {user} has no trial_name")
        for t in trial:
            if t in out:
                bad.append(f"line {i}: trial_name {t} is given to {out[t]} and {user}")
            out[t] = user
    if bad:
        raise BuildError(f"{paths.rel(path)}: " + "; ".join(bad))
    if not out:
        raise BuildError(f"{paths.rel(path)}: no turnout or block rows")
    return out


def level_names(bands, le_mod, device: dict | None = None, page=None) -> tuple[dict, dict]:
    """placeholder_names with every placeholder replaced by its device-map name (device_names): ({band key: names},
    {block: length mm}). Stops on a placeholder the device map does not name, or a device-map name the drawing does
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
    out_len = defaultdict(float)
    for ph, mm in lengths.items():
        out_len[to(ph)] += mm
    if missing:
        raise BuildError(f"main and upper placeholders {paths.rel(DEVICE_MAP)} names nowhere: {sorted(missing)}")
    unused = sorted(set(device) - used)
    if unused:
        raise BuildError(f"{paths.rel(DEVICE_MAP)} trial names the drawing does not have: {unused}")
    return out, dict(out_len)


def shared_turnouts(names: dict) -> None:
    """Give each main and upper band's names the turnouts it shares with another band (`shared_turnouts`): a
    crossover whose halves stand on two levels (the helix-top 129 and 135) is one device-map turnout drawn as two
    Layout Editor turnouts, which JMRI throws together."""
    bands_of = defaultdict(set)
    for key, nm in names.items():
        if key != STAGING:
            for t in nm["turnouts"].values():
                bands_of[t].add(key)
    for key, nm in names.items():
        if key != STAGING:
            nm["shared_turnouts"] = sorted(t for t in set(nm["turnouts"].values()) if len(bands_of[t]) > 1)


# Track names on the cut-over candidates that stand on one centre x (owner, 2026-11-16): South Yard's, in the middle
# of the yard between its ladders (the plugin's name_columns)
NAME_COLUMNS = [["S-R", "S-1", "S-2", "S-3", "S-4"]]
# Occupancy lamps that share one x on the cut-over candidates (owner, 2026-11-16): South Yard's, each on its track
LAMP_COLUMNS = [{"BS S-R": "S-R", "BS S-1": "S-1", "BS S-2": "S-2", "BS S-3": "S-3", "BS S-4": "S-4"}]


def staging_columns(bands):
    """`bands` with the staging band's le_labels (its preferences' own, a copy) also giving NAME_COLUMNS and
    LAMP_COLUMNS (the lamps' tracks, bound to their sensors here)."""
    out = []
    for title, band, opts in bands:
        if band_key(title) == STAGING:
            own = dict((opts or {}).get("le_labels") or {})
            set_here = sorted({"name_columns", "lamp_columns"} & set(own))
            if set_here:
                raise BuildError(f"{title}: its preferences' le_labels already hold {', '.join(set_here)}; HART sets "
                                 "them here (NAME_COLUMNS, LAMP_COLUMNS)")
            opts = dict(opts or {}, le_labels=dict(own, name_columns=[list(g) for g in NAME_COLUMNS],
                                                   lamp_columns=[list(g.values()) for g in LAMP_COLUMNS]))
        out.append((title, band, opts))
    return out


def named_bands(bands, names: dict):
    """A copy of `bands` in which each main and upper track block is named on one of its tracks (the longest; its
    name the block's without "Track "), so the plugin's label layer writes the device-map track names there; every
    other main and upper track is unnamed, but a helix track keeps its plan name (McKees Rocks, McKeesport): the
    plugin joins the helix ends of two levels by that name (le.partners), so it is the label there too. Staging is
    left as it is."""
    out = []
    for title, band, opts in bands:
        key = band_key(title)
        if key == STAGING:
            out.append((title, band, opts))
            continue
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
            if blocks[0].startswith("Track "):
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
            name = block.removeprefix("Track ")
            if name not in NO_NAME.get(band_key(title), []):
                band["strands"][best]["name"] = name
        hart = dict(LEVEL_LE_LABELS, numbers_below=list(NUMBERS_BELOW.get(band_key(title), [])),
                    optional_block_contents=list(OPTIONAL_READOUTS.get(band_key(title), [])))
        own = dict((opts or {}).get("le_labels") or {})       # the band's own, from its preferences
        set_here = sorted(set(own) & set(hart))
        if set_here:
            raise BuildError(f"{title}: its preferences' le_labels already hold {', '.join(set_here)}; HART sets them "
                             "here (LEVEL_LE_LABELS, NUMBERS_BELOW, OPTIONAL_READOUTS)")
        labels = dict(own, **hart)
        out.append((title, band, dict(opts or {}, le_labels=labels)))
    return out



# track names left off the panel (owner, 2026-11-16): the short track inside the three-way
NO_NAME = {"Main": ["101-103"]}
