"""build_cats_panel.py [--check]

Generate the CATS Designer desks for all three levels (staging, main, upper) from the schematic grid, with the
schematic-maps plugin's cats module (the code behind `schematic cats --bindings`), into
cats/panels/generated/HART_Generated.xml (CTC) and its ABS twin HART_Generated_ABS.xml. They sit beside the live
desks (ADR-023): cats/panels/HART_CTC.xml, HART_ABS.xml and HART_Digicon.xml are not read or touched, and the deploy
installs only its LIVE_PANELS list, so these files are not deployed. tools/check.sh validates them with
cats/scripts/validate_cats_panel.py, and cats/scripts/tests/test_generated_desk_parity.py proves their staging part
binds every turnout, block, sensor and mast the live desks bind, the same way.

Bands stack in the sheet's order (staging on top). Staging is bound to the live JMRI objects through the bindings
file cats/panels/generated/HART_Generated.bindings.json, which this script writes from the railroad's facts, never by
hand:
  switches.csv / switch_legs.csv  which OS block each switch's points are in (and a crossover half's label, 23A
                                  or 23B, from its OS block's letter), which leg is closed and which thrown,
                                  and whether CATS normal is JMRI thrown (cats_inverted); Switch 9 and 13 follow them
  public_name_map.csv + tables.xml  each switch's M2T turnout (cats_turnout_io.load_turnouts)
  occupancy_bindings.csv + tables.xml  each block's M2S sensor and discipline (digicon_lib.load_occupancy: the
                                  layout block table and the sensors, not a Layout Editor panel)
  staging.signals.json + signal_head_plan.csv  the masts drawn on staging (field and planned) and their templates
  staging_le/tracks.csv  the block of a short unnamed track between two switches that has no JMRI block of its own
                         (SHORT_TRACK_BLOCKS, which must be one of the blocks the frozen Layout Editor track holds)
Main and upper are dark territory: authority by track warrant, which CATS does not have, so their blocks are DTC
(owner, 2026-11-15). They take their names from the block rows of
jmri/layouts/hart/data/schematic/device_map_main_upper.csv (by the schematic tracks each holds) and have no masts.
Their detectors (the map's occupancy rows) are not in tables.xml yet, so each block's planned sensor is written to
the bindings as _planned_occupied / _planned_unoccupied and left off the panel; the main and upper wiring step sets
DETECT_MAIN_UPPER and the blocks take them (the sensors must then be in tables.xml).
Anything else without a JMRI block, an ambiguous track, or a fact that disagrees with the drawing stops the run.
The sheet is built once and tables.xml read once; bindings and panels come from the same plugin code.
The IOSPEC, STATION and SECSIGNAL conventions are the live desk's (wire_digicon.py, cats_turnout_io.py,
digicon_lib.py, hartlib.cats). The header (fonts, counters, signal templates, train, job and crew stores, colours,
OPERATIONS, JMRI names) and the publication plate come from cats/data/generated_desk_header.xml, frozen from the
live desk on 2026-11-15; the ABS twin turns every CTC block ABS and says DS-ABS / ABS DIGICON on its plate, as
wire_digicon.py does. Inputs and plugin are the same as tools/schematic/publish_draft.py (SCHEMATIC_PLUGIN for
other plugin code).

--check regenerates the files into a temporary folder and compares (exit 1 if any is stale). When SCHEMATIC_PLUGIN
is not set and the plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and
exits 0 (a failure with SCHEMATIC_REQUIRED=1).
"""
import copy
import csv
import difflib
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
import le_inputs  # noqa: E402  the frozen staging Layout Editor facts (staging_le/)
from hartlib import paths, tables  # noqa: E402
from hartlib.cats import mast_templates, station_plate  # noqa: E402

sys.path[:0] = [str(paths.CATS_DIR / "scripts"), str(paths.LAYOUT_SCRIPTS)]
import cats_turnout_io as tio  # noqa: E402
import digicon_lib as le  # noqa: E402
import layout_facts as facts  # noqa: E402

OUT = pd.REPO / "cats/panels/generated/HART_Generated.xml"
OUT_ABS = OUT.with_name("HART_Generated_ABS.xml")
BINDINGS = OUT.with_name("HART_Generated.bindings.json")
HEADER = paths.CATS_DIR / "data/generated_desk_header.xml"   # frozen from the live desk (2026-11-15)
DEVICE_MAP = pd.DATA / "device_map_main_upper.csv"
BOUND = "Staging"                                    # the band bound to JMRI (its title starts with this)
# The ABS twin: every CTC block ABS, and the plate's words (wire_digicon.py write_desk, digicon_header.PANELS)
ABS_PLATE = {"CTC DIGICON": "ABS DIGICON", "DS-CTC": "DS-ABS"}
# Main and upper: dark territory under track warrants, which CATS does not have; DTC is the closest it reads
MAIN_UPPER_DISCIPLINE = "DTC"
DETECT_MAIN_UPPER = False   # the main and upper wiring step sets this once their sensors are in tables.xml
# The live desk's top-level order (HART_CTC.xml); the plugin's ROWWRAPTAG follows COMPRESSIONTAG
ORDER = ("FONTDEFINITION", "LINE", "COUNTER", "SIGNALTEMPLATE", "TRAINSTORE", "JOBSTORE", "CREWSTORE",
         "COLORDEFINITION", "TRAINSTATLABEL", "COMPRESSIONTAG", "ROWWRAPTAG", "OPERATIONS", "JMRINAME", "TRACKPLAN")
PLATE_PX = {"FONT_SUBTITLE": (9, 15)}   # pixels per character, line height, for plate fonts the plugin does not size
# The dispatcher's screen is 1900 x 1200 pixels. CATS opens the panel in WINDOW and draws each cell at its default
# 30 x 30 pixel grid (the plugin's GRID_PX) with no zoom (the Grid Size is not kept in the panel). Inside the window
# about CHROME pixels go to the frame and scrollbar (width) and to the title and menu bars and the train status line
# (height), so the panel must show at most FIT cells: (1900 - 20) // 30 = 62 columns, (1150 - 100) // 30 = 35 rows.
# One cell per schematic grid unit is what fits all three levels in that.
CELLS_PER_UNIT = 1
WINDOW = (1900, 1150)   # the dispatcher's 1900x1200 screen less a taskbar: CATS opens the panel at this size, uncropped
CHROME = (20, 100)
GRID_PX = 30            # checked against the plugin's cats.GRID_PX when the panel is built
FIT = ((WINDOW[0] - CHROME[0]) // GRID_PX, (WINDOW[1] - CHROME[1]) // GRID_PX)
MAX_COLS = FIT[0]       # the plugin drops level-only columns so the panel keeps within the window (a free column
                        # each side: column 0 is never drawn and the track starts at column 2)

# A short unnamed track whose block is a railroad fact: the frozen Layout Editor track (staging_le/tracks.csv)
# between the two switches holds both OS blocks, and the hand-drawn panel gave most of it to OS Switch 35a (the
# generated Layout Editor panel splits it evenly). The named block must be one the frozen track holds.
SHORT_TRACK_BLOCKS = {"35-37": "OS Switch 35a"}


def plugin_modules(plugin):
    """The plugin's cats and sheet modules, imported from `plugin` (the same code the command would run)."""
    sys.path.insert(0, str(plugin))
    for name in [m for m in sys.modules if m == "schematic" or m.startswith("schematic.")]:
        if not str(getattr(sys.modules[name], "__file__", "")).startswith(str(plugin)):
            del sys.modules[name]                  # another copy of the plugin was imported first
    from schematic import cats, sheet
    return cats, sheet


class FrozenTracks:
    """The staging Layout Editor tracks between turnout legs, as frozen in staging_le/tracks.csv (le_inputs)."""

    def __init__(self, chains):
        self.chains = chains            # [{ends: [(ident, leg), (ident, leg) or ("END", bumper)], blocks: [...]}]

    def block_between(self, a, b, what, fixed=None):
        """The block of the one frozen track from turnout `a` to `b`: its only block, or `fixed` when given (it must
        be one of the track's blocks). Stops when there is no such track, several, or a track of several blocks
        and no `fixed` (the frozen tracks have no lengths to choose by)."""
        found = [c for c in self.chains if {e[0] for e in c["ends"]} == {a, b} and "END" not in
                 {e[0] for e in c["ends"]} and a != b]
        if len(found) != 1:
            raise SystemExit(f"{what}: {'no' if not found else len(found)} Layout Editor tracks join {a} and {b} "
                             "in staging_le/tracks.csv; cannot tell which block it is part of")
        blocks = found[0]["blocks"]
        if fixed is not None:
            if fixed not in blocks:
                raise SystemExit(f"{what}: SHORT_TRACK_BLOCKS names {fixed}, but the Layout Editor track from {a} "
                                 f"to {b} holds only {', '.join(sorted(set(blocks)))}")
            return fixed
        if len(set(blocks)) != 1:
            raise SystemExit(f"{what}: the Layout Editor track from {a} to {b} holds blocks "
                             f"{', '.join(sorted(set(blocks)))}; name the one it is part of in SHORT_TRACK_BLOCKS")
        return blocks[0]


@dataclass
class DeviceMap:
    """The main and upper device map (device_map_main_upper.csv): block rows and occupancy sensors by name."""
    blocks: dict = field(default_factory=dict)      # user name -> {level, trial: set of "Track eNN"}
    sensors: dict = field(default_factory=dict)     # occupancy user name -> system name (M2S...)


def load_device_map(path=DEVICE_MAP):
    out = DeviceMap()
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = row["user_name"]
            if row["layer"] == "block":
                if name in out.blocks:
                    raise SystemExit(f"{path.name}: block {name} is listed twice")
                trial = {t.strip() for t in row["trial_name"].split(",") if t.strip()}
                out.blocks[name] = {"level": int(row["level"]), "trial": trial}
            elif row["layer"] == "occupancy":
                if name in out.sensors or not row["system_name"].startswith("M2S"):
                    raise SystemExit(f"{path.name}: occupancy {name} is listed twice or is no M2S sensor")
                out.sensors[name] = row["system_name"]
    return out


@dataclass
class Facts:
    """What the bindings are written from (load_facts reads them from the repo)."""
    switches: dict              # number -> layout_facts.Switch
    turnout_io: dict            # Layout Editor turnout -> (M2T address, user name)
    occupancy: dict             # block -> (M2S address, sensor user name)
    discipline: dict            # block -> CATS discipline
    layout: FrozenTracks
    templates: dict             # mast user name -> signal template
    masts: set                  # JMRI mast user names
    device: DeviceMap = field(default_factory=DeviceMap)   # main and upper
    sensors: dict = field(default_factory=dict)             # JMRI sensor user name -> system name


def load_facts():
    """The facts from the repo: tables.xml (read once) for its turnouts, sensors, layout blocks and masts, never a
    Layout Editor panel; the staging Layout Editor tracks from their frozen copy."""
    root = tables.read(paths.TABLES_XML)
    sensors = {tables.user_name(s): tables.system_name(s) for s in tables.sensors(root) if tables.user_name(s)}
    masts = {tables.user_name(m) for m in tables.masts(root)}
    return Facts(facts.load_switches(), tio.load_turnouts(root), le.load_occupancy(root), le.load_disciplines(),
                 FrozenTracks(le_inputs.load().chains), mast_templates(), masts, load_device_map(), sensors)


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
        touched = {"Track " + strands[legs_of(d)[p]]["name"] for p in "BC" if strands[legs_of(d)[p]]["name"]}
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


def dest(band, os_of, n, port):
    """The block leg `port` of switch node n leads to, beyond its own OS: a named track, the next switch's OS, or
    through a turnback to the named half beyond it."""
    nodes, strands = band["nodes"], band["strands"]
    sid, here, seen = legs_of(nodes[n])[port], n, set()
    while sid not in seen:
        seen.add(sid)
        s = strands[sid]
        if s["name"]:
            return "Track " + s["name"]
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
        to = {p: dest(band, os_of, n, p) for p in "BC"}
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
    """names: {block key: panel block name} of the staging band's blocks. A block is its JMRI block (by name, or
    Track + name); a short unnamed track joining two switches, with no JMRI block of its own, joins the Layout
    Editor block that holds most of it. Anything else stops."""
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
            out[name] = {"name": F.layout.block_between(a, b, f"block {name}", SHORT_TRACK_BLOCKS.get(name))}
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
    """Every drawn mast (field and planned) by its JMRI user name and template; a name drawn twice stops."""
    out = {}
    for sg in opts.get("signals") or ():
        if sg["kind"] == "virtual":
            continue
        if sg["mast"] in out:
            raise SystemExit(f"mast {sg['mast']} is listed twice in the staging signals")
        name = opts.get("mast_prefix", "") + sg["mast"]
        if name not in F.masts or name not in F.templates:
            raise SystemExit(f"{name}: not a JMRI mast with a template in signal_head_plan.csv")
        out[sg["mast"]] = {"name": name, "template": F.templates[name]}
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
        if name not in F.device.blocks:
            raise SystemExit(f"{name}: no block row in {DEVICE_MAP.name}")
        return name
    edges, ends = set(), set()
    for k in keys:
        bi, sid = k[1].split(":", 1)
        band = bands[int(bi[1:])][1]
        s = band["strands"][sid]
        edges.add("Track " + re.sub(r"(?<=\d)[xy]$", "", s["edge"]))
        ends |= {band["nodes"][e[0]].get("label") or "" for e in (s["src"], s["dst"])
                 if band["nodes"][e[0]]["kind"] in ("switch", "dx")}
    rows = sorted(n for n, r in F.device.blocks.items() if r["trial"] & edges)
    numbers = {bdm.base(lb) for lb in ends}
    if not rows and len(numbers) == 1 and len(ends) > 1:
        # the track between a crossover's halves (drawn on two bands, 129 and 135): the device map counts it in the
        # crossover's OS block
        name = f"OS Switch {numbers.pop()}"
        if name not in F.device.blocks:
            raise SystemExit(f"{name}: no block row in {DEVICE_MAP.name}")
        return name
    if len(rows) != 1 or not edges <= F.device.blocks[rows[0]]["trial"]:
        raise SystemExit(f"desk block {sorted(keys)}: the schematic tracks {', '.join(sorted(edges))} is in "
                         f"{', '.join(rows) or 'no'} device map block rows; it must lie in exactly one")
    return rows[0]


def planned_sensor(name, F):
    """The device map's occupancy sensor of block `name` (BS + the name less Track; BS Switch N for OS Switch N),
    as the IOSPECs a bound block takes, or None (no detector)."""
    user = "BS " + (name.replace("OS Switch ", "Switch ", 1) if name.startswith("OS Switch ") else
                    name.removeprefix("Track "))
    system = F.device.sensors.get(user)
    if system is None:
        return None
    addr = system[3:]
    return {"occupied": {"DECADDR": addr, "JMRIPREFIX": "M2S", "USER_NAME": user, "command": "close"},
            "unoccupied": {"DECADDR": addr, "JMRIPREFIX": "M2S", "command": "throw"}}


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
            if "Track " + re.sub(r"(?<=\d)[xy]$", "", s["edge"]) not in row["trial"]:
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
            cm[re.sub(r"(?<=\d)[xy]$", "", s["edge"])] = s["cm"]     # as the device map measures it
    if not found or any(t.removeprefix("Track ") not in
                        {re.sub(r"(?<=\d)[xy]$", "", bands[bi][1]["strands"][sid]["edge"]) for bi, sid in found}
                        for t in row["trial"]):
        raise SystemExit(f"{name}: the device map's tracks {', '.join(sorted(row['trial']))} are not all drawn on "
                         "main or upper")
    length = round(sum(cm.values()), 1)
    if length < bdm.SHORT_CM:
        return f"a short link ({length:g} cm) inside its switches' OS blocks"
    return (f"inside its switches' OS blocks on the desk ({length:g} cm, too short at one cell per grid unit for a "
            "block)")


def dark_bindings(bands, cats, P, F, bound_bi):
    """(bindings, log, report) for the main and upper blocks: device map names, DTC, the station plate and the
    planned detector (bound only with DETECT_MAIN_UPPER, when the sensor must be in tables.xml); the report names each
    device map block with no block of its own on the desk, why, and its detector."""
    groups = defaultdict(list)
    for key in P.blocks:
        groups[P.find(key)].append(key)
    band_of = lambda k: int(k[1].split(":", 1)[0][1:])
    out, log, seen, missing = {}, [], set(), {}
    for root, keys in sorted(groups.items(), key=lambda kv: P.names[kv[0]]):
        panel_name = P.names[root]
        dark = [k for k in keys if band_of(k) != bound_bi and bdm.band_level(bands[band_of(k)][0])]
        if not dark:
            continue
        if len(dark) < len(keys):
            # a track drawn on staging and on main or upper, joined through the helix: the plugin makes it one block
            # (one track drawn on two bands), so it keeps the staging block's binding
            name = device_name(bands, cats, dark, F, log)
            missing[name] = f"one block with staging's {panel_name} on the desk (joined through the helix)"
            log.append(f"{name}: {missing[name]}, bound as staging")
            continue
        name = device_name(bands, cats, keys, F, log)
        e = {"name": name, "station": station_plate(name), "discipline": MAIN_UPPER_DISCIPLINE}
        spec = planned_sensor(name, F)
        if spec and DETECT_MAIN_UPPER:
            if F.sensors.get(spec["occupied"]["USER_NAME"]) != "M2S" + spec["occupied"]["DECADDR"]:
                raise SystemExit(f"{name}: DETECT_MAIN_UPPER is set, but tables.xml has no sensor "
                                 f"{spec['occupied']['USER_NAME']} (M2S{spec['occupied']['DECADDR']})")
            e.update(spec)
        elif spec:
            e.update({"_planned_" + k: v for k, v in spec.items()})
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
        spec = planned_sensor(name, F)
        if spec:
            report[name]["detector"] = spec["occupied"]["USER_NAME"]
            log.append(f"{name}: not a block of its own on the desk ({why}); its detector "
                       f"{report[name]['detector']} has no block to bind")
    return out, log, report


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


def bindings(bands, cats, F):
    """The bindings for every band, from the facts (see the module docstring)."""
    bi = next((i for i, (t, _, _) in enumerate(bands) if t.startswith(BOUND)), None)
    if bi is None:
        raise SystemExit(f"no band title starts with {BOUND}")
    _, band, opts = bands[bi]
    os_of = os_blocks(band, F)
    out_sw = switch_bindings(band, F, os_of)
    # the panel's block names once the switches name their OS blocks
    P = cats.panel(bands, scale=CELLS_PER_UNIT,          # names only: no column trimming needed here
                   bindings={"switches": {k: {"block": v["block"]} for k, v in out_sw.items()}})
    names = {k: v for k, v in P.names.items() if k[1].startswith(f"b{bi}:")}
    blocks = block_bindings(band, F, names)
    dark, log, missing = dark_bindings(bands, cats, P, F, bi)
    print("\n".join(log))
    check_apart(blocks, dark)
    return {"_note": "Written by tools/schematic/build_cats_panel.py from the railroad's facts; do not edit. Main and "
                     "upper blocks carry their planned detectors as _planned_occupied / _planned_unoccupied until "
                     "DETECT_MAIN_UPPER is set.",
            "_main_upper_not_on_desk": missing,
            "switches": out_sw, "blocks": dict(blocks, **dark), "masts": mast_bindings(opts, F)}


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


def dress(cats, root, header, plate, desk):
    """The generated document `root` with the frozen header and the plate: the template's fonts the plugin does
    not write (its own keep their values), the template's other elements in place of the plugin's copies, every
    element in the live desk's order, and the plate's labels on free cells of their row, clear of each other and of
    the labels there. desk "ABS": every CTC block ABS and the plate's ABS words."""
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
        if box[2] > (FIT[0] + 1) * GRID_PX:
            raise SystemExit(f"{HEADER.name}: plate label {n.get('NAME')!r} at {cell} runs past column {FIT[0]}")
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


def generate(plugin, out, bindings_out, out_abs=None):
    """Build the sheet once and write the bindings and the desks with the same plugin code."""
    cats, sheet = plugin_modules(plugin)
    bands = sheet.build([(f"{pd.GRAPHS}/{g}", n) for g, n in pd.INPUTS], str(pd.DATA)).bands
    text = json.dumps(bindings(bands, cats, load_facts()), indent=1, sort_keys=True) + "\n"
    bindings_out.write_text(text, encoding="utf-8")
    if cats.GRID_PX != GRID_PX:
        sys.exit(f"error: the plugin draws a {cats.GRID_PX} pixel grid; FIT here assumes {GRID_PX}")
    header, plate = frozen_header()
    try:
        P = cats.panel(bands, scale=CELLS_PER_UNIT, bindings=json.loads(text), max_cols=MAX_COLS)
        cats.check_fit(P, *FIT)
        for desk, path in (("CTC", out), ("ABS", out_abs)):
            if path is not None:
                Path(path).write_text(dress(cats, cats.to_xml(P, "CTC", header, WINDOW), header, plate, desk),
                                      encoding="utf-8")
    except cats.SchematicError as e:
        sys.exit(f"error: {e}")
    cols, rows = cats.shown(P)
    print(", ".join(t for t, _, _ in bands) + ": " + cats.summary(P) +
          f"; shows {cols} x {rows} cells ({cols * GRID_PX} x {rows * GRID_PX} pixels at the {GRID_PX} pixel grid), "
          f"fit {FIT[0]} x {FIT[1]} in a {WINDOW[0]} x {WINDOW[1]} window")
    print("\n".join(P.log))


def main(argv):
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
