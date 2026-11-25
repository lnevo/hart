"""build_cats_panel.py's desk bindings for every level: each switch's turnout and routes, each block's name, station,
discipline and occupancy sensor, each mast's JMRI name and template, and the main and upper masts placed on their
bands.

One builder for all three levels. A band's level says where its facts come from, never how a binding is made:

  level      band                         switches and OS blocks              blocks                    masts
  bound (1)  bound_bi (staging)           switches.csv,                       occupancy_bindings.csv,   signals.json
                                          M2T turnouts (Facts.turnout_io)     M2S detectors             [staging]
  2 and 3    level_band (bdm.band_level)  internal turnouts (LEVEL_TURNOUT),  the device master block rows,   main_upper_
                                          the drawing's crossover halves      virtual sensors           masts.csv

Every binding is made by the same helpers whatever its level: turnout_routes (a switch's NORMAL leg and its close
and throw IOSPECs), occupancy_spec (a block's OCCUPIEDSPEC / UNOCCUPIEDSPEC), block_entry (a block's name, station
plate and discipline) and mast_template (a mast's CATS template). The two sources stay apart until the device
master holds staging's switch legs and detectors as it holds main and upper's (level unification steps 5 and 6);
reading them is the only level difference left here. Merged from cats_panel_staging.py and cats_panel_levels.py
(level unification step 4) with the desks byte-identical.
"""
import copy
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_device_map as bdm  # noqa: E402  the device map's naming helpers (base, band_level, natural)
import mast_rule as mr  # noqa: E402  the helix tracks (plan_overrides.json)
from hartlib import level_masts, paths  # noqa: E402
from hartlib.cats import station_plate  # noqa: E402

sys.path[:0] = [str(paths.CATS_DIR / "scripts"), str(paths.LAYOUT_SCRIPTS)]
from le_common import BuildError, plugin as schematic_plugin  # noqa: E402  the plugin's core: crossover halves

from cats_panel_facts import DEVICE_MAP, load_device_map, mast_type, template_by_type  # noqa: E402

# Main and upper: CTC on the CTC desk, CATS holds their signals and releases them (owner, 2026-11-17); ABS on the twin
MAIN_UPPER_DISCIPLINE = "CTC"
# The discipline of a staging block occupancy_bindings.csv gives none
STAGING_DISCIPLINE = "CTC"
# The staging turnouts and detectors: LCOS over MQTT (M2T, M2S)
STAGING_TURNOUT_PREFIX = "M2T"
STAGING_SENSOR_PREFIX = "M2S"
# Main and upper turnouts are internal until the device-map import (owner, 2026-11-16): IT:HART:C3:<switch number>,
# user name Switch <n>. On the desk each is commanded and reported by that internal turnout, closed on the drawn
# leg B: the Layout Editor builder gives these levels no normal leg, so the plugin draws leg B as the route the
# turnout's closed state sets (continuing 2 when leg B is Layout Editor leg B, 4 when it is leg C), as the desk's
# NORMAL is leg B.
LEVEL_TURNOUT_PREFIX = "IT"
LEVEL_TURNOUT = LEVEL_TURNOUT_PREFIX + ":HART:C3:"
LEVEL_SENSOR_PREFIX = "IS"          # a main or upper block's virtual occupancy sensor (IS:HART:C3:B:...)


# --- every level: the shapes of the bindings -------------------------------------------------------------------

def legs_of(d):
    """{leg: strand} of a drawn node, its in and out legs together."""
    return d["ins"] | d["outs"]


def level_band(bands, bi, bound_bi) -> bool:
    """True for band `bi` when it is a main or upper band (bdm.band_level by its title), not the bound one."""
    return bi != bound_bi and bool(bdm.band_level(bands[bi][0]))


def level_bands(bands, bound_bi):
    """[(band index, band, options)] of the main and upper bands."""
    return [(bi, band, opts) for bi, (_title, band, opts) in enumerate(bands) if level_band(bands, bi, bound_bi)]


def turnout_routes(prefix, addr, user, closed, thrown) -> dict:
    """The routes of a switch whose leg `closed` the turnout's closed state sets and leg `thrown` its thrown state:
    each leg's SELECTEDREPORT and ROUTECOMMAND, the turnout `prefix` + `addr` (user name `user`)."""
    if {closed, thrown} != {"B", "C"}:
        raise SystemExit(f"{user}: closed leg {closed!r} and thrown leg {thrown!r} must be legs B and C, one each")
    io = lambda cmd: {"DECADDR": addr, "JMRIPREFIX": prefix, "USER_NAME": user, "command": cmd}
    return {closed: {"SELECTEDREPORT": io("close"), "ROUTECOMMAND": io("close")},
            thrown: {"SELECTEDREPORT": io("throw"), "ROUTECOMMAND": io("throw")}}


def occupancy_spec(prefix, addr, user) -> dict:
    """The OCCUPIEDSPEC / UNOCCUPIEDSPEC of a block bound to sensor `prefix` + `addr` (user name `user`): occupied
    when it closes, unoccupied when it throws."""
    return {"occupied": {"DECADDR": addr, "JMRIPREFIX": prefix, "USER_NAME": user, "command": "close"},
            "unoccupied": {"DECADDR": addr, "JMRIPREFIX": prefix, "command": "throw"}}


def block_entry(panel_name, name, discipline) -> dict:
    """A desk block's binding before its sensor: the JMRI block `name` it takes (left out when it is the panel name
    `panel_name`), its station plate and its CATS discipline."""
    e = {"name": name, "station": station_plate(name), "discipline": discipline}
    if name == panel_name:
        del e["name"]
    return e


def mast_template(name, F, by_type):
    """The CATS template of mast `name` on any level: its own row in signal_head_plan.csv (a wired mast) wins, else
    the one masts of its appearance type take (`by_type`, template_by_type), by its system name in tables.xml; None
    when neither. One rule for every level: a main or upper mast given a row of its own takes that row's template."""
    return F.templates.get(name) or by_type.get(mast_type(F.mast_system.get(name)))


# --- the bound level (staging): switches.csv, occupancy_bindings.csv -------------------------------------------

def switch_of(F, d):
    try:
        return F.switches[int(d["label"])]
    except (KeyError, ValueError):
        raise SystemExit(f"switch {d.get('label')!r} on the staging band is not in switches.csv") from None


def staging_names(band, data) -> dict:
    """{strand: track name} of the staging band, from the name store of the schematic folder `data` the band was
    solved from, by each strand's ID (staging_device_map.staging_names), never read off the drawing: what os_blocks,
    dest, block_bindings and helix_block take as `stored`."""
    import staging_device_map as sdm
    try:
        return sdm.staging_names(band, data)
    except sdm.StagingMapError as exc:
        raise SystemExit(f"the staging track names: {exc}") from None


def os_blocks(band, F, stored):
    """{switch node: its OS block}: the switch's only one, else the switches.csv row whose named tracks its legs
    touch (`stored`: staging_names), else the one row left. Two nodes never get one row."""
    nodes = band["nodes"]
    sw_nodes = {n: d for n, d in nodes.items() if d["kind"] == "switch"}
    os_of = {}
    for n, d in sw_nodes.items():
        sw = switch_of(F, d)
        if len(sw.legs) == 1:
            os_of[n] = sw.legs[0].os_block
            continue
        touched = {track_block(stored[legs_of(d)[p]], F.helix) for p in "BC" if stored.get(legs_of(d)[p])}
        rows = [leg.os_block for leg in sw.legs if {leg.closed, leg.thrown} & touched]
        if len(rows) == 1:
            os_of[n] = rows[0]
    for n, d in sw_nodes.items():                    # the rest by elimination
        if n not in os_of:
            sw = switch_of(F, d)
            mates = [m for m in sw_nodes if sw_nodes[m]["label"] == d["label"]]
            left = [leg.os_block for leg in sw.legs if leg.os_block not in {os_of.get(m) for m in mates}]
            if len(left) != 1:
                raise SystemExit(f"switch {d['label']}: cannot tell which of {[l.os_block for l in sw.legs]} "
                                 f"node {n} is from switches.csv")
            os_of[n] = left[0]
    seen = {}
    for n, os_name in sorted(os_of.items()):
        if os_name in seen:
            raise SystemExit(f"switch nodes {seen[os_name]} and {n} would both be {os_name}")
        seen[os_name] = n
    return os_of


def track_block(name, helix) -> str:
    """The block of a staging track the plan names `name`: a helix track's helix block (`helix`, {plan name: block},
    Facts.helix: one block up the helix, owner 2026-11-20), any other "Track <name>"."""
    return helix.get(name) or "Track " + name


def dest(band, os_of, n, port, helix, stored):
    """The block leg `port` of switch node n leads to, beyond its own OS: a named track (`stored`, staging_names;
    track_block, with `helix`), the next switch's OS, or through a turnback to the named half beyond it."""
    nodes, strands = band["nodes"], band["strands"]
    sid, here, seen = legs_of(nodes[n])[port], n, set()
    while sid not in seen:
        seen.add(sid)
        s = strands[sid]
        if stored.get(sid):
            return track_block(stored[sid], helix or {})
        nxt = s["dst"][0] if s["src"][0] == here else s["src"][0]
        d = nodes[nxt]
        if d["kind"] == "switch":
            return os_of[nxt]
        if not d["kind"].startswith("turn"):
            break
        onward = [k for k in legs_of(d).values() if k != sid]      # the other half of a fold
        if len(onward) != 1:
            break
        sid, here = onward[0], nxt
    raise SystemExit(f"switch {nodes[n]['label']} leg {port}: the track from it reaches no named track or switch")


def half_label(sw, leg):
    """The panel label of one half of a switch with several OS blocks (a crossover): its number and the letter of
    its OS block in switches.csv, upper case (OS Switch 23a -> 23A). The row without a letter is A when every
    other row has one (OS Switch 7 and 7b -> 7A, 7B)."""
    letter = lambda name: m.group(1) if (m := re.fullmatch(rf"OS Switch {sw.number}([a-z])", name)) else None
    own = letter(leg.os_block)
    if own is None:
        others = [letter(l.os_block) for l in sw.legs if l is not leg]
        if None in others or "a" in others:
            raise SystemExit(f"Switch {sw.number}: cannot tell which half {leg.os_block} is from switches.csv")
        own = "a"
    return f"{sw.number}{own.upper()}"


def switch_bindings(band, F, os_of, stored):
    """{switch key: binding} for the staging switches: each node's OS block (os_of), its M2T turnout, closed on the
    leg that leads to its switches.csv closed block (dest, by the `stored` names), NORMAL the thrown leg when CATS
    normal is JMRI thrown (cats_inverted); a switch drawn as halves is keyed label/alias and labelled by half
    (half_label)."""
    nodes = band["nodes"]
    sw_nodes = {n: d for n, d in nodes.items() if d["kind"] == "switch"}
    labels = Counter(d["label"] for d in sw_nodes.values())
    out = {}
    for n, d in sorted(sw_nodes.items(), key=lambda kv: (int(kv[1]["label"]), os_of[kv[0]])):
        sw = switch_of(F, d)
        leg = next(l for l in sw.legs if l.os_block == os_of[n])
        to = {p: dest(band, os_of, n, p, F.helix, stored) for p in "BC"}
        if sorted(to.values()) != sorted((leg.closed, leg.thrown)):
            raise SystemExit(f"{leg.os_block}: the schematic's legs lead to {to}, but switches.csv says "
                             f"closed {leg.closed}, thrown {leg.thrown}")
        closed = next(p for p in "BC" if to[p] == leg.closed)
        thrown = "C" if closed == "B" else "B"
        if sw.le_ident not in F.turnout_io:
            raise SystemExit(f"Switch {sw.number}: no {STAGING_TURNOUT_PREFIX} turnout for {sw.le_ident}")
        addr, uname = F.turnout_io[sw.le_ident]
        key = d["label"] if labels[d["label"]] == 1 else f"{d['label']}/{d['alias']}"
        out[key] = {
            "block": leg.os_block,
            **({"label": half_label(sw, leg)} if labels[d["label"]] > 1 else {}),     # drawn as halves
            "normal": thrown if sw.cats_inverted else closed,
            "routes": turnout_routes(STAGING_TURNOUT_PREFIX, addr, uname, closed, thrown),
        }
    return out


def block_bindings(band, F, names, stored):
    """names: {block key: panel block name} of the staging band's blocks (a helix block, bound with the main and
    upper ones, left out: dark_bindings). A block is its JMRI block (by name, or Track + name), bound to its detector;
    a short track joining two switches that the name store does not name (`stored`, staging_names), with no JMRI
    block of its own, joins the one block the staging device map gives it. Anything else stops."""
    nodes, strands = band["nodes"], band["strands"]
    out = {}
    for key, name in sorted(names.items(), key=lambda kv: kv[1]):
        layout = next((x for x in (name, "Track " + name) if x in F.occupancy), None)
        if layout is None:
            sid = key[1].split(":", 1)[1] if key[0] == "track" else None
            s = strands.get(sid) if sid else None
            ends = [nodes[e[0]] for e in (s["src"], s["dst"])] if s else []
            if not s or stored.get(sid) or not all(d["kind"] == "switch" for d in ends):
                raise SystemExit(f"block {name}: no JMRI block {name} or Track {name} in occupancy_bindings.csv / "
                                 "tables.xml, and it is not a short unnamed track between two switches")
            a, b = (switch_of(F, d).le_ident for d in ends)
            out[name] = {"name": F.layout.block_between(a, b, f"block {name}")}
            continue
        addr, sensor = F.occupancy[layout]
        out[name] = dict(block_entry(name, layout, F.discipline.get(layout, STAGING_DISCIPLINE)),
                         **occupancy_spec(STAGING_SENSOR_PREFIX, addr, sensor))
    return out


def mast_bindings(opts, F):
    """Every drawn mast (field and planned) by its JMRI user name and template: its own row in signal_head_plan.csv
    (a wired mast), else the template staging's masts of its appearance type take (mast_template), as main and
    upper masts get theirs. A name drawn twice stops."""
    out = {}
    by_type = template_by_type(F)
    for sg in opts.get("signals") or ():
        if sg["kind"] == "virtual":
            continue
        if sg["mast"] in out:
            raise SystemExit(f"mast {sg['mast']} is listed twice in the staging signals")
        name = opts.get("mast_prefix", "") + sg["mast"]
        template = mast_template(name, F, by_type)
        if name not in F.masts or template is None:
            raise SystemExit(f"{name}: not a JMRI mast, or no template for its type in signal_head_plan.csv")
        out[sg["mast"]] = {"name": name, "template": template}
    return out


# --- main and upper (levels 2 and 3): the device master, internal turnouts, masts.csv --------------------------------------

def xover_corners(name, F) -> list:
    """The device map's corner blocks of double crossover OS block `name` ("OS Switch <n>" -> "OS Switch <n>a" to
    "<n>d"), or []. The desk draws each corner as a block of its own and the middle of the X as `name`, which the
    device map has no row for (level_switch_bindings)."""
    return [f"{name}{c}" for c in "abcd" if f"{name}{c}" in F.device.blocks]


def loop_half_edge(edge, half) -> str:
    """The edge level_signals gives one half of a balloon loop drawn from plan edge `edge` ("e33" -> "e33~1"): a
    suffix of its own, so it never reads as a connector's or helix's x/y piece (the plugin's mast_piece and
    mileposts read those); the strand keeps its plan edge as `plan_edge`."""
    return f"{edge}~{half}"


def plan_edge(strand) -> str:
    """The plan edge a drawn strand comes from: the edge level_signals kept before naming a loop half
    (`plan_edge`), else its own, with a connector's or helix's x/y piece suffix dropped."""
    return re.sub(r"(?<=\d)[xy]$", "", strand.get("plan_edge", strand["edge"]))


def placeholder(strand) -> str:
    """The device map trial name of a drawn main or upper strand: its switch-and-leg key ("Track 107B-107C #1"), which
    name_loop_halves gives it (`trial`). SystemExit on a strand with none: a band name_loop_halves did not key."""
    if "trial" not in strand:
        raise SystemExit(f"strand {strand['edge']} has no trial key: the bands were not read through name_loop_halves")
    return strand["trial"]


def name_loop_halves(bands, device=None):
    """A copy of `bands` as the device map holds them. Each main and upper strand carries its trial key (`trial`,
    read by placeholder): the switch-and-leg key of its piece (staging_device_map.band_refs, one grammar for every
    level, owner 2026-11-20; strand_placeholders, one desk block per strand; SystemExit on a connector the plugin's
    partners do not pair). Each balloon loop is two desk blocks: each half's strand is named by its device map
    block less "Track " (the plugin parts a turnback between two differently named tracks in the middle of its run,
    and labels each half) and marked with its half (`loop_half`). The plugin prints a track's track_labels label
    (the helix tracks' McKees Rocks and McKeesport) in place of its name."""
    import build_layout_le as bl
    import staging_device_map as sdm
    device = load_device_map() if device is None else device      # the caller's Facts.device, read once
    by_trial = {t: name for name, row in device.blocks.items() for t in row.trial}
    out = copy.deepcopy(bands)
    _sheet, le_mod, _core = bl.plugin()
    joined = le_mod.partners(out)
    for bi, (title, band, _) in enumerate(out):
        if not bdm.band_level(title):
            continue
        try:
            refs = sdm.band_refs(out, joined, bi)
        except sdm.StagingMapError as exc:
            raise SystemExit(f"{title}: {exc}") from None
        for sid, ref in refs.items():           # one desk block per strand on main and upper
            band["strands"][sid]["trial"] = sdm.strand_placeholders(ref)[0]
    for title, band, _ in out:
        if not bdm.band_level(title):
            continue
        try:
            halves = bdm.loop_halves(band, bl.runs)
        except bdm.MapError as exc:
            raise SystemExit(f"{title}: {exc}") from None
        for sid, half in halves.items():
            band["strands"][sid]["loop_half"] = half
            trial = placeholder(band["strands"][sid])
            if trial not in by_trial:
                raise SystemExit(f"{title}: balloon loop half {trial} has no block row in {DEVICE_MAP.name}")
            band["strands"][sid]["name"] = by_trial[trial].removeprefix("Track ")
    return out


def part_blocks() -> dict[str, tuple[str, str]]:
    """{trial name: (part name, the block it is part of)} of the main and upper parts (the device master's part_of: a link
    inside an OS block, step 5 part 2, owner 2026-11-20), which the device maps leave out: a block of its own on the
    desk, bound to its OS block's sensor."""
    out = {}
    for line, r in bdm.devices.part_lines(("2", "3")):
        for t in (x.strip() for x in r["trial_name"].split(",") if x.strip()):
            if t in out:
                raise SystemExit(f"{DEVICE_MAP.name}: {r['user_name']} (level {r['level']}, block): trial name {t} is "
                                 "given to two parts")
            out[t] = (r["user_name"], r["part_of"])
    return out


def device_name(bands, cats, keys, F, log):
    """The device map's name of the main or upper block made of block keys `keys`: OS Switch N for an OS block
    (a crossover's halves are one block; switches whose OS blocks the plugin merges over a track too short to part
    them take the lowest number, logged), else the device map track that holds the block's schematic tracks."""
    labels = sorted({cats.label_of(bands, k) for k in keys if k[0] == "os"} - {""}, key=bdm.natural)
    if labels:
        numbers = sorted({bdm.base(lb) for lb in labels}, key=bdm.natural)
        name = f"OS Switch {numbers[0]}"
        if len(numbers) > 1:
            log.append(f"switches {', '.join(numbers)} share one OS block on the desk ({name}): the track between "
                       "them is too short to part them")
        if name not in F.device.blocks and not xover_corners(name, F):
            raise SystemExit(f"{name}: no block row in {DEVICE_MAP.name}")
        return name
    edges, ends = set(), set()
    for k in keys:
        bi, sid = k[1].split(":", 1)
        band = bands[int(bi[1:])][1]
        s = band["strands"][sid]
        edges.add(placeholder(s))
        ends |= {band["nodes"][e[0]].get("label") or "" for e in (s["src"], s["dst"])
                 if band["nodes"][e[0]]["kind"] in ("switch", "dx")}
    rows = sorted(n for n, r in F.device.blocks.items() if r.trial & edges)
    parts = part_blocks()
    if not rows and edges and edges <= set(parts):
        # a link inside an OS block that the desk draws as a block of its own: the part's name (its sensor is its OS
        # block's, dark_bindings)
        held = {parts[e][0] for e in edges}
        if len(held) != 1:
            raise SystemExit(f"desk block {sorted(keys)}: its tracks {', '.join(sorted(edges))} are parts "
                             f"{', '.join(sorted(held))}; a desk block lies in one")
        return held.pop()
    numbers = {bdm.base(lb) for lb in ends}
    if not rows and len(numbers) == 1 and len(ends) > 1:
        # the track between a crossover's halves (drawn on two bands, 127 and 131): the device map counts it in the
        # crossover's OS block
        name = f"OS Switch {numbers.pop()}"
        if name not in F.device.blocks:
            raise SystemExit(f"{name}: no block row in {DEVICE_MAP.name}")
        return name
    if len(rows) != 1 or not edges <= F.device.blocks[rows[0]].trial:
        raise SystemExit(f"desk block {sorted(keys)}: the schematic tracks {', '.join(sorted(edges))} is in "
                         f"{', '.join(rows) or 'no'} device map block rows; it must lie in exactly one")
    return rows[0]


def spec(system, user):
    """The IOSPECs a block bound to sensor `system` (user name `user`) takes, as staging's (occupancy_spec):
    JMRIPREFIX the system prefix (M2S, or IS for an internal sensor), DECADDR the rest of the system name."""
    prefix = STAGING_SENSOR_PREFIX if system.startswith(STAGING_SENSOR_PREFIX) else LEVEL_SENSOR_PREFIX
    if not system.startswith(prefix):
        raise SystemExit(f"{user}: sensor {system} is neither {STAGING_SENSOR_PREFIX} nor internal")
    return occupancy_spec(prefix, system[len(prefix):], user)


def virtual_sensor(name, F):
    """The IOSPECs of block `name`'s virtual occupancy sensor (the jmri_name of the device map's occupancy row that
    serves it, by that row's blocks column), or None: the middle of a double crossover's X has none (its corners do)."""
    row = F.device.occupancy.get(name)
    return None if row is None else spec(row.jmri_name, row.user_name)


def planned_sensor(name, F):
    """The IOSPECs of block `name`'s planned detector (its occupancy row's system_name, a draft), or None."""
    row = F.device.occupancy.get(name)
    return None if row is None or not row.system_name else spec(row.system_name, row.user_name)


def inside_os(bands, P, bound_bi, name, row):
    """Why device map block `name` has no block of its own on the desk, checked on the drawing: each schematic track
    it holds (its trial names) is drawn on main or upper from a switch to a switch (or through a turnback or a
    connector), and the plugin gave every cell of it to their OS blocks (its track key is no block, or one joined to
    an OS block). Anything else stops, naming the block."""
    found, cm = [], {}
    for bi, band, _opts in level_bands(bands, bound_bi):
        for sid, s in band["strands"].items():
            if placeholder(s) not in row.trial:
                continue
            found.append((bi, sid))
            key = ("track", f"b{bi}:{sid}")
            if key in P.blocks and P.find(key)[0] != "os":    # union-find roots: an OS key sorts before a track key
                raise SystemExit(f"{name}: its schematic track {s['edge']} is a desk block, but not one named {name}")
            ends = [band["nodes"][e[0]] for e in (s["src"], s["dst"])]
            if not all(d["kind"] in ("switch", "dx") or d["kind"].startswith("turn") or d.get("sub") == "link"
                       for d in ends) or not any(d["kind"] in ("switch", "dx") for d in ends):
                raise SystemExit(f"{name}: its schematic track {s['edge']} has no desk block and does not run "
                                 "between switches, so it is not inside their OS blocks")
            cm[plan_edge(s)] = s["cm"]     # as the device map measures it
    if not found or not row.trial <= {placeholder(bands[bi][1]["strands"][sid]) for bi, sid in found}:
        raise SystemExit(f"{name}: the device map's tracks {', '.join(sorted(row.trial))} are not all drawn on "
                         "main or upper")
    length = round(sum(cm.values()), 1)
    return (f"inside its switches' OS blocks on the desk ({length:g} cm, too short at one cell per grid unit for a "
            "block)")


def dark_bindings(bands, cats, P, F, bound_bi, stored):
    """(bindings, log, report, joined) for the main and upper blocks: device map names, MAIN_UPPER_DISCIPLINE, the
    station plate, the virtual occupancy sensor bound (the device map's jmri_name) and the planned detector kept as
    _planned_*; the report names each device map block with no block of its own on the desk, why, and its sensor;
    `joined` the staging keys of helix blocks, bound here (helix_block, by the `stored` staging names)."""
    groups = defaultdict(list)
    for key in P.blocks:
        groups[P.find(key)].append(key)
    band_of = lambda k: int(k[1].split(":", 1)[0][1:])
    out, log, seen, missing, joined = {}, [], set(), {}, set()
    helix = mr.read_helix_tracks()
    part_of = dict(part_blocks().values())                  # {part: its OS block}
    for root, keys in sorted(groups.items(), key=lambda kv: P.names[kv[0]]):
        panel_name = P.names[root]
        dark = [k for k in keys if level_band(bands, band_of(k), bound_bi)]
        if not dark:
            continue
        if len(dark) < len(keys):       # a helix track: one block from staging up the helix (owner, 2026-11-20)
            name = device_name(bands, cats, dark, F, log)
            staged = {helix_block(k, helix, stored) for k in keys if k not in dark}
            if staged != {name}:
                raise SystemExit(f"desk block {panel_name} holds track of staging ({', '.join(sorted(map(str, staged)))}"
                                 f") and of main or upper ({name}); only a helix block of "
                                 f"{mr.HELIX_SOURCE.name} may, and both device maps must name it")
        elif any(k[0] in ("corner", "xmid") for k in keys):
            # a double crossover's corner or the middle of its X: the plugin named it from the corners binding
            # (level_switch_bindings), which is the device map's name
            name = panel_name
            if name not in F.device.blocks and not xover_corners(name, F):
                raise SystemExit(f"{name}: no block row in {DEVICE_MAP.name}")
        else:
            name = device_name(bands, cats, keys, F, log)
        joined.update(k for k in keys if k not in dark)
        e = block_entry(panel_name, name, MAIN_UPPER_DISCIPLINE)
        # from the device map alone: build_layout_le.py, which runs after this build in make panels, adds the sensor to
        # the tables, and check_layout_facts.py checks the desk against them
        sensor_of = part_of.get(name, name)                 # a part: its OS block's sensor
        bound = virtual_sensor(sensor_of, F)
        if bound:
            e.update(bound)
        elif name in F.device.blocks:
            raise SystemExit(f"{name}: no occupancy row in {DEVICE_MAP.name}")
        planned = planned_sensor(sensor_of, F)
        if planned:
            e.update({"_planned_" + k: v for k, v in planned.items()})
        if name in seen:
            log.append(f"blocks named {name} on the desk are one block")
        seen.add(name)
        out[panel_name] = e
    for name, row in sorted(F.device.blocks.items()):
        if name not in seen and name not in missing:
            missing[name] = inside_os(bands, P, bound_bi, name, row)
    report = {}
    for name, why in sorted(missing.items()):
        report[name] = {"why": why}
        if planned_sensor(name, F):
            report[name]["detector"] = F.device.occupancy[name].user_name
            log.append(f"{name}: not a block of its own on the desk ({why}); its detector "
                       f"{report[name]['detector']} has no block to bind")
    return out, log, report, joined


def helix_block(key, helix, stored) -> str | None:
    """The helix block of staging desk key `key` (`helix`: {plan name: its read_helix_tracks entry}): the name store's
    name of its strand (`stored`, staging_names) is a helix track's; else None. staging_device_map.check_helix holds
    the staging device map to the same block."""
    if key[0] != "track":
        return None
    name = stored.get(key[1].split(":", 1)[1])
    return helix.get(name, {}).get("block") if name else None


def level_switch_bindings(bands, F, bound_bi, dx_corners=None):
    """({switch label: binding}, {label: why not bound}) for the main and upper switches: each switch or crossover
    half drawn commands and reports its internal turnout (LEVEL_TURNOUT + number, user name Switch <n>, which
    tables.xml must hold), closed on leg B (NORMAL) and thrown on leg C. A crossover's halves, on one band or two,
    each take the one turnout, and each half is closed on the leg away from its other half and thrown on the leg
    toward it: on one band, the link leg the plugin pairs it by (schematic.core.crossover_halves: leg C for most
    halves, leg B for 121B and 125B, which the plan joins by their leg B); on two bands, leg C, which must lead to
    the link between the levels. A lettered half that is neither stops the build, with the plugin's reason. A double
    crossover's one turnout moves all four of its points (the plugin: B along the through tracks, C into the X).
    `dx_corners` ({switch number: {leg: Layout Editor corner}}, build_device_map.dx_corners) gives a double crossover
    a desk block per corner, named as the Layout Editor's (OS Switch <n>a to d, by the corner each leg reaches), and
    the middle of its X OS Switch <n>."""
    try:
        core = schematic_plugin()[2]
    except BuildError as exc:                   # the plugin not found, or not at its pinned commit
        raise SystemExit(str(exc)) from None
    out = {}
    for _bi, band, _ in level_bands(bands, bound_bi):
        nodes = band["nodes"]
        why = []
        half_legs = {n: got[0] for n, got in core.crossover_halves(nodes, band["strands"], why).items()}
        for n, d in sorted(nodes.items()):
            label = str(d.get("label") or "")
            if d["kind"] not in ("switch", "dx"):
                continue
            num = bdm.base(label)
            user = f"Switch {num}"
            if F.turnouts.get(user) != LEVEL_TURNOUT + num:
                raise SystemExit(f"switch {label}: tables.xml has no internal turnout {user} ({LEVEL_TURNOUT}{num}); "
                                 f"it has {F.turnouts.get(user) or 'none'}")
            if label in out:
                raise SystemExit(f"switch {label} is drawn twice on main and upper")
            thrown = half_legs.get(n, "C")      # a crossover half: its link leg toward the other half; else leg C
            # a lettered half (125B, or 125B* with an added branch) the plugin did not pair: its other half is on
            # another band
            if re.search(r"\d[AB]$", label.rstrip("*")) and n not in half_legs:
                s = band["strands"].get(legs_of(d).get("C"))
                far = (s["dst"][0] if s["src"][0] == n else s["src"][0]) if s else ""
                if not far.startswith("LINK:"):
                    raise SystemExit(f"switch {label}: a crossover half the plugin pairs with no other half, and its "
                                     "leg C does not lead to the link between the levels"
                                     + (f" ({'; '.join(why)})" if why else ""))
            closed = "C" if thrown == "B" else "B"
            addr = LEVEL_TURNOUT[len(LEVEL_TURNOUT_PREFIX):] + num
            out[label] = {"normal": closed,
                          "routes": turnout_routes(LEVEL_TURNOUT_PREFIX, addr, user, closed, thrown)}
            if d["kind"] == "dx" and dx_corners is not None:
                if num not in dx_corners:
                    raise SystemExit(f"double crossover {label}: no corners found for it")
                out[label]["corners"] = dict(bdm.xover_corners(num, dx_corners[num]), X=f"OS Switch {num}")
    return out


def intermediate_signal(bands, F, bound_bi, r, by_trial):
    """(band index, signal) of an APB intermediate (a masts.csv row with no switch): at the turnback where
    the loop or split track's half it faces meets the half it protects, heading the way its row's dir says. The
    piece it stands on is the one that meets the protected half at a turnback, whatever the strands' order; only the
    halves joined there get edges of their own (loop_half_edge), so other loops on the band keep theirs. Never
    returns None: a mast it cannot place stops the build."""
    drawn = False
    meets = []          # (band index, piece, turnback, the other strands ending there) where it meets the protected half
    for bi, band, _opts in level_bands(bands, bound_bi):
        strands, nodes = band["strands"], band["nodes"]
        block = lambda k, strands=strands: by_trial.get(placeholder(strands[k]))
        ends = lambda k, strands=strands: (strands[k]["src"][0], strands[k]["dst"][0])
        pieces = [k for k in strands if block(k) == r["facing"]]
        drawn = drawn or bool(pieces)
        for k in pieces:
            for n in dict.fromkeys(ends(k)):
                # a level link's end (LINK:...) is no node of the band
                if n in nodes and nodes[n]["kind"].startswith("turn"):
                    others = [j for j in strands if j != k and n in ends(j)]
                    if any(block(j) == r["protects"] for j in others):
                        meets.append((bi, k, n, others))
    if not drawn:
        raise SystemExit(f"{r['mast']}: no desk band draws {r['facing']}")
    if len(meets) != 1:
        raise SystemExit(f"{r['mast']}: {r['facing']} meets {r['protects']} at "
                         f"{'no' if not meets else len(meets)} turnback{'s' if len(meets) > 1 else ''} on the desk")
    bi, sid, turn, others = meets[0]
    strands, opts = bands[bi][1]["strands"], bands[bi][2]
    for x in [strands[k] for k in [sid] + others if strands[k].get("loop_half")]:
        x.setdefault("plan_edge", x["edge"])
        x["edge"] = loop_half_edge(x["plan_edge"], x["loop_half"])
    t = strands[sid]
    return bi, {"mast": r["mast"].removeprefix(opts.get("mast_prefix", "")), "toward": "", "_toward_node": turn,
                "_edge": t["edge"], "cm_from_toward": 0.0, "edge_cm": t["cm"],
                "dir": r["dir"], "kind": "field", "heads": len(r["heads"]),
                "source": level_masts.PATH.name}


def level_signals(bands, F, bound_bi):
    """Put each main and upper mast (masts.csv) in its band's signals, as the plugin reads a band's drawn
    masts: on the track it faces (the device map block holding the schematic track at that leg of its switch), at
    that switch (its toward end), heading the way its row's dir says, its heads from its row. The two halves of a
    balloon loop are one schematic track drawn twice: each half's piece gets an edge of its own (loop_half_edge,
    which placeholder reads back as the one track), so a mast finds its own half. `bands` is changed in place (a copy:
    name_loop_halves). Stops on a mast drawn at no switch leg or at two."""
    by_trial = {t: name for name, row in F.device.blocks.items() for t in row.trial}
    # a part (a link inside an OS block) is a block of its own, its sensor its OS block's: a mast may face it
    # (a trial name on a part and a block row both stops le_names.device_names; the facts' own blocks come first)
    for t, (name, _of) in part_blocks().items():
        by_trial.setdefault(t, name)
    added = defaultdict(list)
    for r in F.level_masts:
        if level_masts.is_level_virtual(r["system_name"]):
            continue                                # a hidden destination mast: no desk signal, as on staging
        if not r["switch"]:                         # an APB intermediate (owner, 2026-11-19)
            bi, sg = intermediate_signal(bands, F, bound_bi, r, by_trial)
            added[bi].append(sg)
            continue
        hits = []
        for bi, band, _ in level_bands(bands, bound_bi):
            for n, d in band["nodes"].items():
                if d["kind"] not in ("switch", "dx") or bdm.base(d.get("label") or "") != r["switch"]:
                    continue
                for port, sid in legs_of(d).items():
                    if by_trial.get(placeholder(band["strands"][sid])) == r["facing"]:
                        hits.append((bi, n, port, sid))
        if len(hits) != 1:
            raise SystemExit(f"{r['mast']}: Switch {r['switch']} has {len(hits)} legs on track {r['facing']} on the "
                             "desk; it must have one")
        bi, n, _port, sid = hits[0]
        title, band, opts = bands[bi]
        s = band["strands"][sid]
        # pieces of its track that also end at this switch: the plugin would take the first (mast_piece)
        twins = [k for k, t in band["strands"].items() if k != sid and t["edge"] == s["edge"]
                 and n in (t["src"][0], t["dst"][0])]
        if twins:
            if not s.get("loop_half") or any(not band["strands"][k].get("loop_half") for k in twins):
                raise SystemExit(f"{r['mast']}: its track {s['edge']} is drawn more than once at Switch "
                                 f"{r['switch']} on {title}, and not as the halves of a balloon loop")
            for t in [band["strands"][k] for k in [sid] + twins]:
                t.setdefault("plan_edge", t["edge"])
                t["edge"] = loop_half_edge(t["plan_edge"], t["loop_half"])
        if s["edge"].endswith(("x", "y")) and not s.get("loop_half"):
            raise SystemExit(f"{r['mast']}: its track {s['edge']} is one piece of a track drawn on two levels")
        key = r["mast"].removeprefix(opts.get("mast_prefix", ""))
        added[bi].append({"mast": key, "toward": str(band["nodes"][n]["label"]), "_toward_node": n,
                          "_edge": s["edge"], "cm_from_toward": 0.0, "edge_cm": s["cm"],
                          "dir": r["dir"], "kind": "field",
                          "heads": len(r["heads"]), "source": level_masts.PATH.name})
    # the sheet's signals.json[main_upper] draws these masts too; the desk places its own (balloon loop halves have
    # edges of their own here), so it drops the file's, once: the main and upper bands share one options object
    for bi in added:
        opts = bands[bi][2]
        opts["signals"] = [sg for sg in opts.get("signals") or () if sg.get("source") != level_masts.PATH.name]
    for bi, sigs in sorted(added.items()):
        opts = bands[bi][2]
        clash = sorted({sg["mast"] for sg in opts.get("signals") or ()} & {sg["mast"] for sg in sigs})
        if clash:
            raise SystemExit(f"{bands[bi][0]}: masts {', '.join(clash)} are drawn there already")
        opts["signals"] = list(opts.get("signals") or ()) + sorted(sigs, key=lambda sg: sg["mast"])


def level_mast_bindings(bands, F, bound_bi):
    """{mast: {name, template}} for the main and upper masts level_signals drew: each a mast in tables.xml whose
    system name is its masts.csv row's, with its template by mast_template: its own signal_head_plan.csv
    row when it has one, else the template masts of its appearance type take. A row not drawn stops, but a virtual
    one (hidden, no desk signal)."""
    rows = {r["mast"]: r for r in F.level_masts}
    by_type = template_by_type(F)
    out = {}
    for bi, _band, opts in level_bands(bands, bound_bi):
        for sg in opts.get("signals") or ():
            name = opts.get("mast_prefix", "") + sg["mast"]
            r = rows.get(name)
            if r is None:
                continue
            if F.mast_system.get(name) != r["system_name"]:
                raise SystemExit(f"{name}: tables.xml has {F.mast_system.get(name) or 'no such mast'}, "
                                 f"{level_masts.PATH.name} says {r['system_name']}")
            template = mast_template(name, F, by_type)
            if template is None:
                raise SystemExit(f"{name} on {bands[bi][0]}: no row of its own and no template for its type "
                                 f"{mast_type(r['system_name'])} in signal_head_plan.csv")
            out[sg["mast"]] = {"name": name, "template": template}
    missing = sorted(set(rows) - {e["name"] for e in out.values()}
                     - {m for m, r in rows.items() if level_masts.is_level_virtual(r["system_name"])})
    if missing:
        raise SystemExit(f"main and upper masts not on the desk: {', '.join(missing)}")
    return out
