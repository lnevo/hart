"""build_cats_panel.py's main and upper levels: block names from the device map, switch and mast bindings, and the
masts drawn on the level bands. Moved out of build_cats_panel.py unchanged."""
import copy
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_device_map as bdm  # noqa: E402  the device map's naming helpers (base, band_level, natural)
import mast_rule as mr  # noqa: E402  the helix tracks (helix_tracks.csv)
from hartlib import level_devices, level_masts, paths  # noqa: E402
from hartlib.cats import station_plate  # noqa: E402

sys.path[:0] = [str(paths.CATS_DIR / "scripts"), str(paths.LAYOUT_SCRIPTS)]
from le_common import BuildError, plugin as schematic_plugin  # noqa: E402  the plugin's core: crossover halves

from cats_panel_facts import DEVICE_MAP, load_device_map, mast_type, template_by_type  # noqa: E402
from cats_panel_staging import legs_of  # noqa: E402

# Main and upper: CTC on the CTC desk, CATS holds their signals and releases them (owner, 2026-11-17); ABS on the twin
MAIN_UPPER_DISCIPLINE = "CTC"
# Main and upper turnouts are internal until the device-map import (owner, 2026-11-16): IT:HART:C3:<switch number>,
# user name Switch <n>. On the desk each is commanded and reported by that internal turnout, closed on the drawn
# leg B: the Layout Editor builder gives these levels no normal leg, so the plugin draws leg B as the route the
# turnout's closed state sets (continuing 2 when leg B is Layout Editor leg B, 4 when it is leg C), as the desk's
# NORMAL is leg B.
LEVEL_TURNOUT_PREFIX = "IT"
LEVEL_TURNOUT = LEVEL_TURNOUT_PREFIX + ":HART:C3:"


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
    """The device map trial name of a drawn strand: "Track <plan edge>" (plan_edge), and a balloon loop's half
    numbered (name_loop_halves)."""
    return bdm.loop_placeholder("Track " + plan_edge(strand), strand.get("loop_half"))


def name_loop_halves(bands, device=None):
    """A copy of `bands` whose balloon loops are two desk blocks, as the device map has them: each half's strand
    is named by its device map block less "Track " (the plugin parts a turnback between two differently named
    tracks in the middle of its run, and labels each half) and marked with its half (`loop_half`, read by
    placeholder)."""
    import build_layout_le as bl
    device = load_device_map() if device is None else device      # the caller's Facts.device, read once
    by_trial = {t: name for name, row in device.blocks.items() for t in row.trial}
    out = copy.deepcopy(bands)
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
    """The IOSPECs a block bound to sensor `system` (user name `user`) takes, as staging's: JMRIPREFIX the system
    prefix (M2S, or IS for an internal sensor), DECADDR the rest of the system name."""
    prefix = "M2S" if system.startswith("M2S") else "IS"
    if not system.startswith(prefix):
        raise SystemExit(f"{user}: sensor {system} is neither M2S nor internal")
    addr = system[len(prefix):]
    return {"occupied": {"DECADDR": addr, "JMRIPREFIX": prefix, "USER_NAME": user, "command": "close"},
            "unoccupied": {"DECADDR": addr, "JMRIPREFIX": prefix, "command": "throw"}}


def virtual_sensor(name, F):
    """The IOSPECs of block `name`'s virtual occupancy sensor (the device map's jmri_name for BS + the name less
    Track; BS Switch N for OS Switch N), or None: the middle of a double crossover's X has none (its corners do)."""
    user = level_devices.occupancy_user(name)
    system = F.device.sensors.get(user)
    return None if system is None else spec(system, user)


def planned_sensor(name, F):
    """The IOSPECs of block `name`'s planned detector (the device map's system_name, a draft), or None."""
    user = level_devices.occupancy_user(name)
    system = F.device.planned.get(user)
    return None if system is None else spec(system, user)


def inside_os(bands, P, bound_bi, name, row):
    """Why device map block `name` has no block of its own on the desk, checked on the drawing: each schematic track
    it holds (its trial names) is drawn on main or upper from a switch to a switch (or through a turnback or a
    connector), and the plugin gave every cell of it to their OS blocks (its track key is no block, or one joined to
    an OS block). Anything else stops, naming the block."""
    found, cm = [], {}
    for bi, (title, band, _) in enumerate(bands):
        if bi == bound_bi or not bdm.band_level(title):
            continue
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
    if not found or any(t.removeprefix("Track ") not in
                        {plan_edge(bands[bi][1]["strands"][sid]) for bi, sid in found}
                        for t in row.trial):
        raise SystemExit(f"{name}: the device map's tracks {', '.join(sorted(row.trial))} are not all drawn on "
                         "main or upper")
    length = round(sum(cm.values()), 1)
    if length < bdm.SHORT_CM:
        return f"a short link ({length:g} cm) inside its switches' OS blocks"
    return (f"inside its switches' OS blocks on the desk ({length:g} cm, too short at one cell per grid unit for a "
            "block)")


def dark_bindings(bands, cats, P, F, bound_bi):
    """(bindings, log, report) for the main and upper blocks: device map names, MAIN_UPPER_DISCIPLINE, the station
    plate, the virtual occupancy sensor bound (the device map's jmri_name) and the planned
    detector kept as _planned_*; the report names each device map block with no block of its own on the desk, why,
    and its sensor."""
    groups = defaultdict(list)
    for key in P.blocks:
        groups[P.find(key)].append(key)
    band_of = lambda k: int(k[1].split(":", 1)[0][1:])
    out, log, seen, missing, joined = {}, [], set(), {}, set()
    helix = mr.read_helix_tracks()
    for root, keys in sorted(groups.items(), key=lambda kv: P.names[kv[0]]):
        panel_name = P.names[root]
        dark = [k for k in keys if band_of(k) != bound_bi and bdm.band_level(bands[band_of(k)][0])]
        if not dark:
            continue
        if len(dark) < len(keys):       # a helix track: one block from staging up the helix (owner, 2026-11-20)
            name = device_name(bands, cats, dark, F, log)
            staged = {helix_block(bands[bound_bi][1], k, helix) for k in keys if k not in dark}
            if staged != {name}:
                raise SystemExit(f"desk block {panel_name} holds track of staging ({', '.join(sorted(map(str, staged)))}"
                                 f") and of main or upper ({name}); only a helix block of "
                                 f"{mr.HELIX_TRACKS.name} may, and both device maps must name it")
        elif any(k[0] in ("corner", "xmid") for k in keys):
            # a double crossover's corner or the middle of its X: the plugin named it from the corners binding
            # (level_switch_bindings), which is the device map's name
            name = panel_name
            if name not in F.device.blocks and not xover_corners(name, F):
                raise SystemExit(f"{name}: no block row in {DEVICE_MAP.name}")
        else:
            name = device_name(bands, cats, keys, F, log)
        joined.update(k for k in keys if k not in dark)
        e = {"name": name, "station": station_plate(name), "discipline": MAIN_UPPER_DISCIPLINE}
        # from the device map alone: build_layout_le.py, which runs after this build in make panels, adds the sensor to
        # the tables, and check_layout_facts.py checks the desk against them
        bound = virtual_sensor(name, F)
        if bound:
            e.update(bound)
        elif name in F.device.blocks:
            raise SystemExit(f"{name}: no occupancy row in {DEVICE_MAP.name}")
        planned = planned_sensor(name, F)
        if planned:
            e.update({"_planned_" + k: v for k, v in planned.items()})
        if name == panel_name:
            del e["name"]
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
            report[name]["detector"] = level_devices.occupancy_user(name)
            log.append(f"{name}: not a block of its own on the desk ({why}); its detector "
                       f"{report[name]['detector']} has no block to bind")
    return out, log, report, joined


def helix_block(band, key, helix) -> str | None:
    """The helix block (helix_tracks.csv) of staging desk key `key`: its strand's plan name is a helix track's; else
    None. staging_device_map.check_helix holds the staging device map to the same block."""
    if key[0] != "track":
        return None
    s = band["strands"].get(key[1].split(":", 1)[1])
    return helix.get(s["name"], {}).get("block") if s else None


def level_bands(bands, bound_bi):
    """[(band index, band, options)] of the main and upper bands."""
    return [(bi, band, opts) for bi, (title, band, opts) in enumerate(bands)
            if bi != bound_bi and bdm.band_level(title)]


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
            io = lambda cmd, u=user, a=addr: {"DECADDR": a, "JMRIPREFIX": LEVEL_TURNOUT_PREFIX, "USER_NAME": u,
                                              "command": cmd}
            out[label] = {"normal": closed,
                          "routes": {closed: {"SELECTEDREPORT": io("close"), "ROUTECOMMAND": io("close")},
                                     thrown: {"SELECTEDREPORT": io("throw"), "ROUTECOMMAND": io("throw")}}}
            if d["kind"] == "dx" and dx_corners is not None:
                if num not in dx_corners:
                    raise SystemExit(f"double crossover {label}: no corners found for it")
                out[label]["corners"] = dict(bdm.xover_corners(num, dx_corners[num]), X=f"OS Switch {num}")
    return out


def intermediate_signal(bands, F, bound_bi, r, by_trial):
    """(band index, signal) of an APB intermediate (a main_upper_masts.csv row with no switch): at the turnback where
    the loop or split track's half it faces meets the half it protects, heading west when its number is odd. The
    piece it stands on is the one that meets the protected half at a turnback, whatever the strands' order; only the
    halves joined there get edges of their own (loop_half_edge), so other loops on the band keep theirs."""
    num = int(re.sub(r"\D", "", r["mast"]))
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
                "dir": "west" if num % 2 else "east", "kind": "field", "heads": len(r["heads"]),
                "source": level_masts.PATH.name}


def level_signals(bands, F, bound_bi):
    """Put each main and upper mast (main_upper_masts.csv) in its band's signals, as the plugin reads a band's drawn
    masts: on the track it faces (the device map block holding the schematic track at that leg of its switch), at
    that switch (its toward end), heading west for an L mast (ADR-005), its heads from its row. The two halves of a
    balloon loop are one schematic track drawn twice: each half's piece gets an edge of its own (loop_half_edge,
    which placeholder reads back as the one track), so a mast finds its own half. `bands` is changed in place (a copy:
    name_loop_halves). Stops on a mast drawn at no switch leg or at two."""
    by_trial = {t: name for name, row in F.device.blocks.items() for t in row.trial}
    added = defaultdict(list)
    for r in F.level_masts:
        if not r["switch"]:                         # an APB intermediate (owner, 2026-11-19)
            placed = intermediate_signal(bands, F, bound_bi, r, by_trial)
            if placed is not None:
                bi, sg = placed
                added[bi].append(sg)
            continue
        m = re.fullmatch(r"Mast (\d+)([LR])([AB]?)", r["mast"])
        if not m:
            raise SystemExit(f"{level_masts.PATH.name}: {r['mast']} is not a mast name in the device map's grammar")
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
                          "dir": "west" if m.group(2) == "L" else "east", "kind": "field",
                          "heads": len(r["heads"]), "source": level_masts.PATH.name})
    # the sheet's main_upper.signals.json draws these masts too; the desk places its own (balloon loop halves have
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
    system name is its main_upper_masts.csv row's, with the template staging's masts of its appearance type take.
    A row not drawn stops."""
    rows = {r["mast"]: r for r in F.level_masts}
    templates = template_by_type(F)
    out = {}
    for _bi, _band, opts in level_bands(bands, bound_bi):
        for sg in opts.get("signals") or ():
            name = opts.get("mast_prefix", "") + sg["mast"]
            r = rows.get(name)
            if r is None:
                continue
            if F.mast_system.get(name) != r["system_name"]:
                raise SystemExit(f"{name}: tables.xml has {F.mast_system.get(name) or 'no such mast'}, "
                                 f"{level_masts.PATH.name} says {r['system_name']}")
            template = templates.get(mast_type(r["system_name"]))
            if template is None:
                raise SystemExit(f"{name}: no staging mast of type {mast_type(r['system_name'])} gives a CATS "
                                 "template (signal_head_plan.csv)")
            out[sg["mast"]] = {"name": name, "template": template}
    missing = sorted(set(rows) - {e["name"] for e in out.values()})
    if missing:
        raise SystemExit(f"main and upper masts not on the desk: {', '.join(missing)}")
    return out
