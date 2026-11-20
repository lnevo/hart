"""build_cats_panel.py [--check]

Generate the live CATS Designer desks for all three levels (staging, main, upper) from the schematic grid, with the
schematic-maps plugin's cats module (the code behind `schematic cats --bindings`): cats/panels/HART_CTC.xml (CTC)
and its ABS twin HART_ABS.xml, the desks the deploy installs (sync_hart_package.sh LIVE_PANELS) and the launchers
open (CATS cut-over; ADR-023). This script is their only writer; the hand-wired Designer panel HART_Digicon.xml is not
read. tools/check.sh validates the desks with cats/scripts/validate_cats_panel.py and checks them against the layout
facts (tools/audit/check_layout_facts.py).

Bands stack in the sheet's order (staging on top). Staging is bound to the live JMRI objects through the bindings
file cats/panels/HART_CTC.bindings.json, which this script writes from the railroad's facts, never by
hand:
  switches.csv / switch_legs.csv  which OS block each switch's points are in (and a crossover half's label, 23A
                                  or 23B, from its OS block's letter), which leg is closed and which thrown,
                                  and whether CATS normal is JMRI thrown (cats_inverted); Switch 9 and 13 follow them
  public_name_map.csv + tables.xml  each switch's M2T turnout (cats_turnout_io.load_turnouts)
  occupancy_bindings.csv + tables.xml  each block's M2S sensor and discipline (digicon_lib.load_occupancy: the
                                  layout block table and the sensors, not a Layout Editor panel)
  staging.signals.json + signal_head_plan.csv  the masts drawn on staging (field and planned) and their templates
  device_map_staging.csv  the block of a short unnamed track between two switches that has no JMRI block of its own:
                         the one block the staging device map's track between them holds
                         (staging_device_map.staging_chains)
Main and upper blocks are CTC on the CTC desk, as staging's are (owner, 2026-11-17: CATS holds their signals and
releases them, so a route set from staging up the helix stops at the first main or upper signal); the ABS twin
turns them ABS with the rest. They take their names from the block rows of
jmri/layouts/hart/data/schematic/device_map_main_upper.csv (by the schematic tracks each holds). Their switches
command and report their internal turnouts (LEVEL_TURNOUT: IT:HART:C3:<n>, closed on the drawn leg B, which is
NORMAL; double crossover 225 too, its one turnout moving all four points, and a desk block per corner as in the
Layout Editor, OS Switch 225a to d on their corners' detectors, with the middle of its X a block of its own and no
detector: the plugin's `corners` binding, which opens a row between its tracks on the upper level; owner,
2026-11-17), and their
control-point masts (main_upper_masts.csv, on virtual heads) are drawn and bound as staging's are: each on the track
it faces at the switch it protects (level_signals), its CATS template the one staging's masts of its appearance type
take. Every main and upper desk block is bound to its virtual occupancy sensor (the device map's jmri_name,
IS:HART:C3:B:<block key>, hartlib.level_devices), as OCCUPIEDSPEC / UNOCCUPIEDSPEC (owner,
2026-11-17: the physical plant is a draft, swapped in later by the device map alone); the planned detector, when the
map has one, is kept in the bindings as _planned_occupied / _planned_unoccupied for the record and is not on the
panel. The middle of 225's X, a desk-only block, has no sensor (owner, 2026-11-17). Each helix track is one desk
block over both bands it is drawn on (cats_helix_blocks "one"; owner, 2026-11-20: one JMRI block from its staging
switch to its main or upper switch), named and bound as the main and upper device map gives it (Track Helix Outer,
Track Helix Inner: its virtual sensor), the staging device map naming the same block for the staging piece.
Anything else without a JMRI block, an ambiguous track, or a fact that disagrees with the drawing stops the run.
The sheet is built once and tables.xml read once; bindings and panels come from the same plugin code.
The IOSPEC, STATION and SECSIGNAL conventions are the hand-wired desks' (cats_turnout_io.py, digicon_lib.py,
hartlib.cats). The header (fonts, counters, signal templates, train, job and crew stores, colours,
OPERATIONS, JMRI names) and the publication plate come from cats/data/generated_desk_header.xml, frozen from the
live desk on 2026-11-15; the ABS twin turns every CTC block ABS and says DS-ABS / ABS DIGICON on its plate, as the
hand-wired ABS desk did. Inputs and plugin are the same as tools/schematic/publish_draft.py (SCHEMATIC_PLUGIN for
other plugin code).

--check regenerates the files into a temporary folder and compares (exit 1 if any is stale). When SCHEMATIC_PLUGIN
is not set and the plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and
exits 0 (a failure with SCHEMATIC_REQUIRED=1).
"""
import copy
import difflib
import importlib
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
import build_device_map as bdm  # noqa: E402  the device map's naming helpers (base, band_level, natural)
import mast_rule as mr  # noqa: E402  the helix tracks (helix_tracks.csv)
import staging_device_map as sdm  # noqa: E402  the staging tracks and their blocks (device_map_staging.csv)
from hartlib import level_devices, level_masts, paths, railroad, tables  # noqa: E402
from hartlib.cats import appearance_templates, mast_templates, station_plate  # noqa: E402

sys.path[:0] = [str(paths.CATS_DIR / "scripts"), str(paths.LAYOUT_SCRIPTS)]
import cats_turnout_io as tio  # noqa: E402
import digicon_lib as le  # noqa: E402
from le_common import BuildError, plugin as schematic_plugin  # noqa: E402  the plugin's core: crossover halves

# The live desks (CATS cut-over, owner approved the generated desks in real CATS on 2026-11-15): the names the hosts,
# launchers and shortcuts use. Nothing else writes them.
OUT = pd.REPO / "cats/panels/HART_CTC.xml"
OUT_ABS = OUT.with_name("HART_ABS.xml")
BINDINGS = OUT.with_name("HART_CTC.bindings.json")
HEADER = paths.CATS_DIR / "data/generated_desk_header.xml"   # frozen from the live desk (2026-11-15)
DEVICE_MAP = railroad.Sources.under().device_map
BOUND = "Staging"                                    # the band bound to JMRI (its title starts with this)
# The ABS twin: every CTC block ABS, and the plate's words (the hand-wired ABS desk's)
ABS_PLATE = {"CTC DIGICON": "ABS DIGICON", "DS-CTC": "DS-ABS"}
# Main and upper: CTC on the CTC desk, CATS holds their signals and releases them (owner, 2026-11-17); ABS on the twin
MAIN_UPPER_DISCIPLINE = "CTC"
# Main and upper turnouts are internal until the device-map import (owner, 2026-11-16): IT:HART:C3:<switch number>,
# user name Switch <n>. On the desk each is commanded and reported by that internal turnout, closed on the drawn
# leg B: the Layout Editor builder gives these levels no normal leg, so the plugin draws leg B as the route the
# turnout's closed state sets (continuing 2 when leg B is Layout Editor leg B, 4 when it is leg C), as the desk's
# NORMAL is leg B.
LEVEL_TURNOUT_PREFIX = "IT"
LEVEL_TURNOUT = LEVEL_TURNOUT_PREFIX + ":HART:C3:"
# The release candidate tables (build_layout_le.py --as-live): every name the desk binds must be in it
TABLES_CANDIDATE = paths.LAYOUT_OUTPUT / "trial/tables_cutover.xml"
# The live desk's top-level order (HART_CTC.xml); the plugin's ROWWRAPTAG follows COMPRESSIONTAG
ORDER = ("FONTDEFINITION", "LINE", "COUNTER", "SIGNALTEMPLATE", "TRAINSTORE", "JOBSTORE", "CREWSTORE",
         "COLORDEFINITION", "TRAINSTATLABEL", "COMPRESSIONTAG", "ROWWRAPTAG", "OPERATIONS", "JMRINAME", "TRACKPLAN")
PLATE_PX = {"FONT_SUBTITLE": (9, 15)}   # pixels per character, line height, for plate fonts the plugin does not size
# The desks' window, cells per grid unit, helix blocks and row gaps are page preferences (main_upper.preferences.json:
# cats_window, cats_cells_per_unit, cats_helix_blocks, cats_band_gap, cats_title_gap) the plugin reads (schematic/cats_prefs.py, cats.options),
# which also gives the cells the desk must fit in that window.

def plugin_modules(plugin):
    """The plugin's cats and sheet modules, imported from `plugin` (the same code the command would run)."""
    sys.path.insert(0, str(plugin))
    for name in [m for m in sys.modules if m == "schematic" or m.startswith("schematic.")]:
        if not str(getattr(sys.modules[name], "__file__", "")).startswith(str(plugin)):
            del sys.modules[name]                  # another copy of the plugin was imported first
    from schematic import cats, sheet
    return cats, sheet


class StagingTracks:
    """The staging tracks between switches and ends, each with its blocks in order: staging_device_map.staging_chains
    (ends by switches.csv le_ident)."""

    def __init__(self, chains):
        self.chains = chains            # [{ends: [(le_ident or "END", band port), ...], blocks: [...]}]

    def block_between(self, a, b, what):
        """The block of the one staging track from turnout `a` to `b`: its only block. Stops when there is no such
        track, several, or a track of several blocks (one desk cell takes one block: the staging device map must give
        the track to one of them, where its gap is)."""
        found = [c for c in self.chains if {e[0] for e in c["ends"]} == {a, b} and "END" not in
                 {e[0] for e in c["ends"]} and a != b]
        if len(found) != 1:
            raise SystemExit(f"{what}: {'no' if not found else len(found)} staging tracks join {a} and {b} "
                             "in the staging device map; cannot tell which block it is part of")
        blocks = found[0]["blocks"]
        if len(set(blocks)) != 1:
            raise SystemExit(f"{what}: the staging track from {a} to {b} holds blocks "
                             f"{', '.join(sorted(set(blocks)))}; give it to the one its gap leaves it in "
                             "(short_tracks_staging.csv, or its own block row in device_map_staging.csv)")
        return blocks[0]


# The main and upper device map: block rows (each with its level and the schematic tracks it holds, `trial`) and
# occupancy sensors by name (virtual, and the planned detector when there is one); hartlib.railroad reads and checks it.
DeviceMap = railroad.DeviceMap


def load_device_map(path=DEVICE_MAP):
    try:
        return railroad.read_device_map(path)
    except railroad.FactsError as exc:
        raise SystemExit(f"build_cats_panel.py: {exc}") from None


@dataclass
class Facts:
    """What the bindings are written from (load_facts reads them from the repo)."""
    switches: dict              # number -> hartlib.railroad.Switch
    turnout_io: dict            # Layout Editor turnout -> (M2T address, user name)
    occupancy: dict             # block -> (M2S address, sensor user name)
    discipline: dict            # block -> CATS discipline
    layout: StagingTracks
    templates: dict             # mast user name -> signal template
    masts: set                  # JMRI mast user names
    device: DeviceMap = field(default_factory=DeviceMap)   # main and upper
    sensors: dict = field(default_factory=dict)             # JMRI sensor user name -> system name
    turnouts: dict = field(default_factory=dict)            # JMRI turnout user name -> system name
    mast_system: dict = field(default_factory=dict)         # JMRI mast user name -> system name
    level_masts: list = field(default_factory=list)         # main_upper_masts.csv rows (hartlib.level_masts)
    helix: dict = field(default_factory=dict)               # plan helix track name -> its block (helix_tracks.csv)


def staging_tracks() -> list[dict]:
    """The staging tracks (staging_device_map.staging_chains) of the staging band as the Layout Editor draws it."""
    try:
        with pd.cache_on():
            band, _opts, _core = sdm.staging_band()
        return sdm.staging_chains(band, sdm.load(band))
    except (sdm.StagingMapError, sdm.lc.BuildError) as exc:      # the map, or the plugin and the drawing
        raise SystemExit(f"build_cats_panel.py: staging device map: {exc}") from None


def load_facts():
    """The facts from the repo (hartlib.railroad, every layer: the desks are built after the device map and the
    main and upper masts): tables.xml (read once) for its turnouts, sensors, layout blocks and masts, never a Layout
    Editor panel; the staging tracks from the staging device map."""
    rr = railroad.Railroad()
    try:
        t = rr.tables
        return Facts(rr.switches, tio.load_turnouts(t.root, rr.switches), le.load_occupancy(t.root), le.load_disciplines(),
                     StagingTracks(staging_tracks()), mast_templates(systems=t.masts), set(t.masts),
                     rr.device_map,
                     t.sensors, t.turnouts, t.masts, rr.level_masts,
                     {plan: h["block"] for plan, h in mr.read_helix_tracks().items()})
    except (railroad.FactsError, mr.MapError) as exc:
        raise SystemExit(f"build_cats_panel.py: {exc}") from None


def legs_of(d):
    return d["ins"] | d["outs"]


def switch_of(F, d):
    try:
        return F.switches[int(d["label"])]
    except (KeyError, ValueError):
        raise SystemExit(f"switch {d.get('label')!r} on the staging band is not in switches.csv") from None


def os_blocks(band, F):
    """{switch node: its OS block}: the switch's only one, else the switch_legs.csv row whose named tracks its legs
    touch, else the one row left. Two nodes never get one row."""
    nodes, strands = band["nodes"], band["strands"]
    sw_nodes = {n: d for n, d in nodes.items() if d["kind"] == "switch"}
    os_of = {}
    for n, d in sw_nodes.items():
        sw = switch_of(F, d)
        if len(sw.legs) == 1:
            os_of[n] = sw.legs[0].os_block
            continue
        touched = {track_block(strands[legs_of(d)[p]]["name"], F.helix) for p in "BC" if strands[legs_of(d)[p]]["name"]}
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
                                 f"node {n} is from switch_legs.csv")
            os_of[n] = left[0]
    seen = {}
    for n, os_name in sorted(os_of.items()):
        if os_name in seen:
            raise SystemExit(f"switch nodes {seen[os_name]} and {n} would both be {os_name}")
        seen[os_name] = n
    return os_of


def track_block(name, helix) -> str:
    """The block of a staging track the plan names `name`: a helix track's helix block (`helix`, {plan name: block}:
    one block up the helix, owner 2026-11-20), any other "Track <name>"."""
    return helix.get(name) or "Track " + name


def dest(band, os_of, n, port, helix=None):
    """The block leg `port` of switch node n leads to, beyond its own OS: a named track (track_block, with `helix`),
    the next switch's OS, or through a turnback to the named half beyond it."""
    nodes, strands = band["nodes"], band["strands"]
    sid, here, seen = legs_of(nodes[n])[port], n, set()
    while sid not in seen:
        seen.add(sid)
        s = strands[sid]
        if s["name"]:
            return track_block(s["name"], helix or {})
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
    its OS block in switch_legs.csv, upper case (OS Switch 23a -> 23A). The row without a letter is A when every
    other row has one (OS Switch 7 and 7b -> 7A, 7B)."""
    letter = lambda name: m.group(1) if (m := re.fullmatch(rf"OS Switch {sw.number}([a-z])", name)) else None
    own = letter(leg.os_block)
    if own is None:
        others = [letter(l.os_block) for l in sw.legs if l is not leg]
        if None in others or "a" in others:
            raise SystemExit(f"Switch {sw.number}: cannot tell which half {leg.os_block} is from switch_legs.csv")
        own = "a"
    return f"{sw.number}{own.upper()}"


def switch_bindings(band, F, os_of):
    nodes = band["nodes"]
    sw_nodes = {n: d for n, d in nodes.items() if d["kind"] == "switch"}
    labels = Counter(d["label"] for d in sw_nodes.values())
    out = {}
    for n, d in sorted(sw_nodes.items(), key=lambda kv: (int(kv[1]["label"]), os_of[kv[0]])):
        sw = switch_of(F, d)
        leg = next(l for l in sw.legs if l.os_block == os_of[n])
        to = {p: dest(band, os_of, n, p, F.helix) for p in "BC"}
        if sorted(to.values()) != sorted((leg.closed, leg.thrown)):
            raise SystemExit(f"{leg.os_block}: the schematic's legs lead to {to}, but switch_legs.csv says "
                             f"closed {leg.closed}, thrown {leg.thrown}")
        closed = next(p for p in "BC" if to[p] == leg.closed)
        thrown = "C" if closed == "B" else "B"
        if sw.le_ident not in F.turnout_io:
            raise SystemExit(f"Switch {sw.number}: no M2T turnout for {sw.le_ident}")
        addr, uname = F.turnout_io[sw.le_ident]
        io = lambda cmd: {"DECADDR": addr, "JMRIPREFIX": "M2T", "USER_NAME": uname, "command": cmd}
        key = d["label"] if labels[d["label"]] == 1 else f"{d['label']}/{d['alias']}"
        out[key] = {
            "block": leg.os_block,
            **({"label": half_label(sw, leg)} if labels[d["label"]] > 1 else {}),     # drawn as halves
            "normal": thrown if sw.cats_inverted else closed,
            "routes": {closed: {"SELECTEDREPORT": io("close"), "ROUTECOMMAND": io("close")},
                       thrown: {"SELECTEDREPORT": io("throw"), "ROUTECOMMAND": io("throw")}},
        }
    return out


def block_bindings(band, F, names):
    """names: {block key: panel block name} of the staging band's blocks (a helix block, bound with the main and
    upper ones, left out: dark_bindings). A block is its JMRI block (by name, or Track + name), bound to its detector;
    a short unnamed track joining two switches, with no JMRI block of its own, joins the one block the staging device
    map gives it. Anything else stops."""
    nodes, strands = band["nodes"], band["strands"]
    out = {}
    for key, name in sorted(names.items(), key=lambda kv: kv[1]):
        layout = next((x for x in (name, "Track " + name) if x in F.occupancy), None)
        if layout is None:
            sid = key[1].split(":", 1)[1] if key[0] == "track" else None
            s = strands.get(sid) if sid else None
            ends = [nodes[e[0]] for e in (s["src"], s["dst"])] if s else []
            if not s or s["name"] or not all(d["kind"] == "switch" for d in ends):
                raise SystemExit(f"block {name}: no JMRI block {name} or Track {name} in occupancy_bindings.csv / "
                                 "tables.xml, and it is not a short unnamed track between two switches")
            a, b = (switch_of(F, d).le_ident for d in ends)
            out[name] = {"name": F.layout.block_between(a, b, f"block {name}")}
            continue
        addr, sensor = F.occupancy[layout]
        out[name] = {
            "name": layout,
            "station": station_plate(layout),
            "discipline": F.discipline.get(layout, "CTC"),
            "occupied": {"DECADDR": addr, "JMRIPREFIX": "M2S", "USER_NAME": sensor, "command": "close"},
            "unoccupied": {"DECADDR": addr, "JMRIPREFIX": "M2S", "command": "throw"},
        }
        if layout == name:
            del out[name]["name"]
    return out


def mast_bindings(opts, F):
    """Every drawn mast (field and planned) by its JMRI user name and template: its own row in signal_head_plan.csv
    (a wired mast), else the template staging's masts of its appearance type take (template_by_type), as main and
    upper masts get theirs. A name drawn twice stops."""
    out = {}
    by_type = template_by_type(F)
    for sg in opts.get("signals") or ():
        if sg["kind"] == "virtual":
            continue
        if sg["mast"] in out:
            raise SystemExit(f"mast {sg['mast']} is listed twice in the staging signals")
        name = opts.get("mast_prefix", "") + sg["mast"]
        template = F.templates.get(name) or by_type.get(mast_type(F.mast_system.get(name)))
        if name not in F.masts or template is None:
            raise SystemExit(f"{name}: not a JMRI mast, or no template for its type in signal_head_plan.csv")
        out[sg["mast"]] = {"name": name, "template": template}
    return out


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


def cats_le(cats):
    """The plugin's le module, beside its cats module."""
    return importlib.import_module(cats.__name__.rpartition(".")[0] + ".le")


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
        # the track between a crossover's halves (drawn on two bands, 129 and 135): the device map counts it in the
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


def mast_type(system):
    """A signal head mast's appearance type from its system name (IF$shsm:basic:one-low(IH1) -> one-low)."""
    m = re.match(r"IF\$(?:shsm|vsm):[^:]+:([^()]+)\(", system or "")
    return m.group(1) if m else None


def template_by_type(F):
    """{appearance type: CATS template}: as signal_head_plan.csv gives them (hartlib.cats.appearance_templates), and
    the stock basic types by head count where it gives none. `F` is unused: kept so the callers stay as they were."""
    try:
        out = appearance_templates()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    # the stock basic appearances by head count, where the plan gives none: one head shows Clear, Approach and Stop
    # (CATS "single"), two add the Diverging aspects ("double"); a dwarf shows the aspects of its high twin. The
    # wiring plan lists wired masts only (6LB since 2026-11-19), so most types come from here.
    for kind, template in (("one-low", "single"), ("one-searchlight", "single"), ("two-searchlight", "double"),
                           ("two-low", "double")):
        out.setdefault(kind, template)
    return out

def intermediate_signal(bands, F, bound_bi, r, by_trial):
    """(band index, signal) of an APB intermediate (a main_upper_masts.csv row with no switch): at the turnback where
    the loop or split track's half it faces meets the half it protects, heading west when its number is odd."""
    num = int(re.sub(r"\D", "", r["mast"]))
    for bi, band, opts in level_bands(bands, bound_bi):
        strands, nodes = band["strands"], band["nodes"]
        pieces = [k for k, t in strands.items() if by_trial.get(placeholder(t)) == r["facing"]]
        if not pieces:
            continue
        sid = pieces[0]
        t = strands[sid]
        ends = [t["src"][0], t["dst"][0]]
        if r["protects"] in by_trial.values() and any(by_trial.get(placeholder(x)) == r["protects"] for x in strands.values()):
            turn = next((n for n in ends if nodes[n]["kind"].startswith("turn")), None)
            if turn is None:
                raise SystemExit(f"{r['mast']}: {r['facing']} meets {r['protects']} at no turnback on the desk")
            for k in [k for k, x in strands.items() if x.get("loop_half")]:
                x = strands[k]
                x.setdefault("plan_edge", x["edge"])
                x["edge"] = loop_half_edge(x["plan_edge"], x["loop_half"])
            return bi, {"mast": r["mast"].removeprefix(opts.get("mast_prefix", "")), "toward": "", "_toward_node": turn,
                        "_edge": t["edge"], "cm_from_toward": 0.0, "edge_cm": t["cm"],
                        "dir": "west" if num % 2 else "east", "kind": "field", "heads": len(r["heads"]),
                        "source": level_masts.PATH.name}
        raise SystemExit(f"{r['mast']}: {r['facing']} and {r['protects']} meet at no turnback on the desk")
    raise SystemExit(f"{r['mast']}: no desk band draws {r['facing']}")


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


def check_apart(staging, dark):
    """Stop when a staging and a main or upper block binding share a panel name or the block name they take (which
    would make them one CATS block)."""
    clash = sorted(set(staging) & set(dark))
    if clash:
        raise SystemExit(f"staging and main/upper blocks share panel names {', '.join(clash)}")
    bound = lambda bs: {e.get("name", k) for k, e in bs.items()}     # the block name each desk block takes
    clash = sorted(bound(staging) & bound(dark))
    if clash:
        raise SystemExit(f"staging and main/upper desk blocks would both be {', '.join(clash)}")


def bound_index(bands):
    """The index of the staging band, the one bound to the field (its title starts with BOUND)."""
    bi = next((i for i, (t, _, _) in enumerate(bands) if t.startswith(BOUND)), None)
    if bi is None:
        raise SystemExit(f"no band title starts with {BOUND}")
    return bi


def bindings(bands, cats, F, o, page):
    """The bindings for every band, from the facts (see the module docstring); `o` the page's CATS preferences
    (cats.options), `page` the schematic's page preferences (the solved sheet's opts)."""
    bi = bound_index(bands)
    _, band, opts = bands[bi]
    os_of = os_blocks(band, F)
    out_sw = switch_bindings(band, F, os_of)
    le_mod = cats_le(cats)
    level_sw = level_switch_bindings(bands, F, bi, bdm.dx_corners(bands, le_mod, page))
    # the panel's block names once the switches name their OS blocks (and a double crossover its corners)
    named = {k: {"block": v["block"]} for k, v in out_sw.items()}
    named.update({k: {"corners": v["corners"]} for k, v in level_sw.items() if "corners" in v})
    P = cats.panel(bands, scale=o["scale"], helix_blocks=o["helix_blocks"],   # names only: no column trimming
                   band_gap=o["band_gap"], title_gap=o["title_gap"],
                   bindings={"switches": named})
    dark, log, missing, joined = dark_bindings(bands, cats, P, F, bi)
    names = {k: v for k, v in P.names.items() if k[1].startswith(f"b{bi}:") and k not in joined}
    blocks = block_bindings(band, F, names)
    print("\n".join(log))
    check_apart(blocks, dark)
    masts, level = mast_bindings(opts, F), level_mast_bindings(bands, F, bi)
    for what, a, b in (("switch", out_sw, level_sw), ("mast", masts, level)):
        if set(a) & set(b):
            raise SystemExit(f"staging and main/upper share {what} keys {', '.join(sorted(set(a) & set(b)))}")
    return {"_note": "Written by tools/schematic/build_cats_panel.py from the railroad's facts; do not edit. Main and "
                     "upper switches command their internal turnouts, their masts are bound and their blocks report "
                     "their virtual occupancy sensors (IS:HART:C3:B:); a block's planned detector, a draft, is kept "
                     "as _planned_occupied / _planned_unoccupied.",
            "_main_upper_not_on_desk": missing,
            "switches": dict(out_sw, **level_sw), "blocks": dict(blocks, **dark), "masts": dict(masts, **level)}


def frozen_header(path=HEADER):
    """The template's elements (comments left out) and the plate SECTIONs of its TRACKPLAN."""
    root = ET.parse(path).getroot()
    if root.tag != "DOCUMENT":
        raise SystemExit(f"{path}: not a CATS panel template (its root is {root.tag})")
    els = [el for el in root if isinstance(el.tag, str)]
    bad = sorted({el.tag for el in els} - set(ORDER))
    if bad:
        raise SystemExit(f"{path}: elements {', '.join(bad)} are not header elements ({', '.join(ORDER)})")
    lacking = [t for t in ("SIGNALTEMPLATE", "JMRINAME") if not any(el.tag == t for el in els)]
    if lacking:
        raise SystemExit(f"{path}: no {' or '.join(lacking)} elements; the staging bindings' masts and IOSPECs "
                         "need them")
    plan = root.find("TRACKPLAN")
    return [el for el in els if el.tag != "TRACKPLAN"], list(plan) if plan is not None else []


def plate_box(cats, cell, loc, text, font):
    per, h = PLATE_PX.get(font) or cats.TEXT_PX.get(font, cats.TEXT_PX["FONT_LABEL"])
    return cats.frill_box(cell, loc, per * len(text) + 4, h)


def dress(cats, root, header, plate, desk, fit):
    """The generated document `root` with the frozen header and the plate: the template's fonts the plugin does
    not write (its own keep their values), the template's other elements in place of the plugin's copies, every
    element in the live desk's order, and the plate's labels on free cells of their row, clear of each other and of
    the labels there, within the `fit` columns. desk "ABS": every CTC block ABS and the plate's ABS words."""
    fonts = {el.get("FONTKEY"): el for el in root.findall("FONTDEFINITION")}
    taken = {el.tag for el in header}           # a tag the header supplies replaces the plugin's copies
    kids = [el for el in root if el.tag != "FONTDEFINITION"]
    for el in list(root):
        root.remove(el)
    picked = []
    for el in header:
        if el.tag == "FONTDEFINITION":
            own = fonts.pop(el.get("FONTKEY"), None)       # an Element with no children is falsy: test for None
            picked.append(own if own is not None else copy.deepcopy(el))
        else:
            picked.append(copy.deepcopy(el))
    picked += list(fonts.values()) + [el for el in kids if el.tag not in taken]
    unknown = sorted({el.tag for el in picked} - set(ORDER))
    if unknown:
        raise SystemExit(f"the generated desk has elements {', '.join(unknown)}, which ORDER does not place; add them")
    for el in sorted(picked, key=lambda el: ORDER.index(el.tag)):
        root.append(el)
    tp = root.find("TRACKPLAN")
    where = {(int(sec.get("X")), int(sec.get("Y"))): sec for sec in tp.findall("SECTION")}
    boxes = []
    for sec in tp.findall("SECTION"):
        n = sec.find("SEC_NAME")
        if n is not None:
            cell = (int(sec.get("X")), int(sec.get("Y")))
            boxes.append((cell, plate_box(cats, cell, n.get("LOC_NAME"), n.get("NAME"), n.get("FONT_NAME"))))
    for sec in plate:
        sec = copy.deepcopy(sec)
        cell = (int(sec.get("X")), int(sec.get("Y")))
        n = sec.find("SEC_NAME")
        if n is None or len(sec) != 1:
            raise SystemExit(f"{HEADER.name}: plate cell {cell} holds one SEC_NAME and nothing else")
        if desk == "ABS":
            text = n.get("NAME")
            for ctc, abs_ in ABS_PLATE.items():
                text = text.replace(ctc, abs_)
            n.set("NAME", text)
        if cell in where:
            raise SystemExit(f"{HEADER.name}: plate cell {cell} ({n.get('NAME')}) is a cell the desk uses")
        box = plate_box(cats, cell, n.get("LOC_NAME"), n.get("NAME"), n.get("FONT_NAME"))
        hit = [c for c, b in boxes if b[1] < box[3] and box[1] < b[3] and b[0] < box[2] + 6 and box[0] < b[2] + 6]
        if hit:
            raise SystemExit(f"{HEADER.name}: plate label {n.get('NAME')!r} at {cell} runs into the label at {hit[0]}")
        if box[2] > (fit[0] + 1) * cats.GRID_PX:
            raise SystemExit(f"{HEADER.name}: plate label {n.get('NAME')!r} at {cell} runs past column {fit[0]}")
        boxes.append((cell, box))
        where[cell] = sec
    for sec in tp.findall("SECTION"):
        tp.remove(sec)
    for cell in sorted(where, key=lambda c: (c[1], c[0])):
        tp.append(where[cell])
    if desk == "ABS":
        for b in root.iter("BLOCK"):
            if b.get("DISCIPLINE") == "CTC":
                b.set("DISCIPLINE", "ABS")
    ET.indent(root, "  ")
    return "<?xml version='1.0' encoding='UTF-8'?>\n" + ET.tostring(root, encoding="unicode") + "\n"


def label_clashes(log):
    """The plugin's log lines (cats_labels.place_labels' words) for a label with no room or crossing something."""
    return [line for line in log if line.startswith("no room for label")
            or (line.startswith("label ") and " crosses " in line)]


def desk_options(cats, page, bands):
    """The page's CATS preferences (cats.options), which must hold the desks' window (they fit the dispatcher's) and
    each helix track one block over both bands (dark_bindings binds it as the main and upper device map gives it)."""
    try:
        o = cats.options(page, bands)
    except cats.SchematicError as e:
        sys.exit(f"error: {e}")
    if o["fit"] is None:
        sys.exit("error: the page's preferences hold no cats_window; the desks must fit the dispatcher's window")
    if o["helix_blocks"] != "one":
        sys.exit(f"error: cats_helix_blocks is {o['helix_blocks']!r}; the desks need \"one\" (a helix track one block "
                 "over both bands, as JMRI holds it; owner, 2026-11-20)")
    return o


def generate(plugin, out, bindings_out, out_abs=None):
    """Build the sheet once and write the bindings and the desks with the same plugin code."""
    cats, sheet = plugin_modules(plugin)
    F = load_facts()
    s = pd.solved_sheet(sheet)
    bands = name_loop_halves(s.bands, F.device)
    o = desk_options(cats, s.opts, bands)
    window, fit = o["window"], o["fit"]
    level_signals(bands, F, bound_index(bands))
    text = json.dumps(bindings(bands, cats, F, o, s.opts), indent=1, sort_keys=True) + "\n"
    bindings_out.write_text(text, encoding="utf-8")
    header, plate = frozen_header()
    try:
        P = cats.panel(bands, scale=o["scale"], bindings=json.loads(text), max_cols=fit[0],
                       helix_blocks=o["helix_blocks"], band_gap=o["band_gap"], title_gap=o["title_gap"])
        cats.check_fit(P, *fit)
        for desk, path in (("CTC", out), ("ABS", out_abs)):
            if path is not None:
                Path(path).write_text(dress(cats, cats.to_xml(P, "CTC", header, window), header, plate, desk, fit),
                                      encoding="utf-8")
    except cats.SchematicError as e:
        sys.exit(f"error: {e}")
    cols, rows = cats.shown(P)
    g = cats.GRID_PX
    print(", ".join(t for t, _, _ in bands) + ": " + cats.summary(P) +
          f"; shows {cols} x {rows} cells ({cols * g} x {rows * g} pixels at the {g} pixel grid), "
          f"fit {fit[0]} x {fit[1]} in a {window[0]} x {window[1]} window")
    print("\n".join(P.log))
    clashes = label_clashes(P.log)
    if clashes:     # the desks keep few spare rows (cats_band_gap, cats_title_gap): a lost or clashing label stops
        sys.exit("error: the desk's labels clash; give them room (cats_band_gap, cats_title_gap) or move them:\n  "
                 + "\n  ".join(clashes))


def main(argv):
    if {"-h", "--help"} & set(argv):     # help wins over --check and over a typo beside it: it only prints
        print(__doc__ or "build_cats_panel.py [--check]")       # python -OO strips the docstring
        return 0
    unknown = [a for a in argv if a != "--check"]
    if unknown:         # a typo must not fall through to a rebuild
        print(f"build_cats_panel.py: unknown argument {unknown[0]!r}; usage: build_cats_panel.py [--check] (--help for more)",
              file=sys.stderr)
        return 2
    check = "--check" in argv
    if not check:
        pd.paths.exit_if_overridden(Path(__file__).name)
    try:
        plugin = pd.plugin()
    except SystemExit as e:
        if not check:
            raise
        print(f"SKIPPED CATS panel check: {e.code}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    with tempfile.TemporaryDirectory() as tmp:
        fresh = {OUT: Path(tmp) / OUT.name, OUT_ABS: Path(tmp) / OUT_ABS.name, BINDINGS: Path(tmp) / BINDINGS.name}
        generate(plugin, fresh[OUT], fresh[BINDINGS], fresh[OUT_ABS])
        stale = 0
        for target, new_file in fresh.items():
            new = new_file.read_text(encoding="utf-8")
            old = target.read_text(encoding="utf-8") if target.exists() else ""
            rel = target.relative_to(pd.REPO)
            if new == old:
                print(f"{rel} is current")
            elif check:
                stale += 1
                print(f"{rel} is stale; run python3 tools/schematic/build_cats_panel.py")
                sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                           target.name, "fresh", n=1))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(new, encoding="utf-8")
                print(f"wrote {rel}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
