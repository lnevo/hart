"""build_cats_panel.py's desk bindings for every level: each switch's turnout and routes, each block's name, station,
discipline and occupancy sensor, each mast's JMRI name and template, and the main and upper masts placed on their
bands.

One builder for all three levels. A band's level says where its facts come from, never how a binding is made:

  level      band                         switches and OS blocks              blocks                    masts
  bound (1)  bound_bi (staging)           switches.csv,                       cats_discipline blocks,     signals.json
                                          M2T turnouts (Facts.turnout_io)     M2S detectors             [staging]
  2 and 3    level_band (bdm.band_level)  the rows' turnouts (tables.xml),    the device master block rows,   main_upper_
                                          the drawing's crossover halves      virtual sensors           masts.csv

Every binding is made by the same helpers whatever its level: turnout_routes (a switch's NORMAL leg and its close
and throw IOSPECs), occupancy_spec (a block's OCCUPIEDSPEC / UNOCCUPIEDSPEC), block_entry (a block's name, station
plate and discipline) and mast_template (a mast's CATS template). The two sources stay apart until the device
master holds staging's switch legs and detectors as it holds main and upper's; reading them is the only level
difference left here.
"""
import copy
import hashlib
import re
import sys
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple, NotRequired, Protocol, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_device_map as bdm  # noqa: E402  the device map's naming helpers (base, band_level, natural)
import plan_bands  # noqa: E402
from hartlib import devices, drawing_keys, level_devices, level_masts, paths  # noqa: E402
from hartlib.railroad_facts import FactsError  # noqa: E402

sys.path[:0] = [str(paths.CATS_DIR / "scripts"), str(paths.LAYOUT_SCRIPTS)]
from le_common import BuildError, plugin as schematic_plugin  # noqa: E402  the plugin's core: crossover halves

from cats_panel_facts import DEVICE_MAP, CatsPanelError, DeviceMap, mast_type, template_by_type  # noqa: E402,F401

# The shapes every level shares and the bound level (staging), re-exported: build_cats_panel.py and the tests
# take them from here.
from cats_panel_shapes import (LEVEL_SENSOR_PREFIX, MAIN_UPPER_DISCIPLINE, STAGING_DISCIPLINE,  # noqa: E402,F401
                               STAGING_SENSOR_PREFIX, STAGING_TURNOUT_PREFIX, _SYSTEM_NAME, block_entry, legs_of,
                               level_band, level_bands, mast_template, occupancy_spec, split_system_name,
                               turnout_routes)
from cats_panel_bound import (Band, Bands, BlockBinding, BlockKey, IoSpec, MastBinding,  # noqa: E402,F401
                              SwitchBinding, block_bindings, dest, half_label, mast_bindings, os_blocks, os_plates,
                              staging_names, switch_bindings, switch_of, track_block)
from cats_panel_facts import Facts  # noqa: E402
from hartlib.railroad_facts import DeviceRow  # noqa: E402


class DeskPanel(Protocol):
    """What the bindings read of the plugin's CATS panel (cats.panel): its desk block keys, a union-find over them
    (find: a key's root) and each root's panel name."""
    blocks: Collection[BlockKey]
    names: Mapping[BlockKey, str]

    def find(self, key: BlockKey) -> BlockKey: ...


class Unbound(TypedDict):
    """A device map block with no block of its own on the desk (dark_bindings' report): why, and its planned
    detector's user name when it has one."""
    why: str
    detector: NotRequired[str]


class DarkBindings(NamedTuple):
    """dark_bindings' result: the main and upper block bindings, the log lines, the report of blocks with no desk
    block of their own, and the staging keys of the helix blocks bound here."""
    bindings: dict[str, BlockBinding]
    log: list[str]
    report: dict[str, Unbound]
    joined: set[BlockKey]


class DeskSignal(TypedDict):
    """A main or upper mast put in a band's signals (level_signals), in the shape the plugin reads a drawn mast."""
    mast: str
    toward: str
    _toward_node: str
    _edge: str
    cm_from_toward: float
    edge_cm: float
    dir: str
    kind: str
    heads: int
    source: str


# --- main and upper (levels 2 and 3): the device master, internal turnouts, masts.csv --------------------------------------

def xover_corners(name: str, F: Facts) -> list[str]:
    """The device map's corner blocks of double crossover OS block `name` ("OS Switch <n>" -> "OS Switch <n>a" to
    "<n>d"), or []. The desk draws each corner as a block of its own and the middle of the X as `name`, which the
    device map has no row for (level_switch_bindings)."""
    return [f"{name}{c}" for c in "abcd" if f"{name}{c}" in F.device.blocks]


def loop_half_edge(edge: str, half: int) -> str:
    """The edge level_signals gives one half of a balloon loop drawn from plan edge `edge` ("e33" -> "e33~1"): a
    suffix of its own, so it never reads as a connector's or helix's x/y piece (the plugin's mast_piece and
    mileposts read those); the strand keeps its plan edge as `plan_edge`."""
    return f"{edge}~{half}"


def plan_edge(strand: Mapping[str, Any]) -> str:
    """The plan edge a drawn strand comes from: the edge level_signals kept before naming a loop half
    (`plan_edge`), else its own, with a connector's or helix's x/y piece suffix dropped."""
    return re.sub(r"(?<=\d)[xy]$", "", strand.get("plan_edge", strand["edge"]))


def placeholder(strand: Mapping[str, Any]) -> str:
    """The device map trial name of a drawn main or upper strand: its switch-and-leg key ("Track 107B-107C #1"), which
    name_loop_halves gives it (`trial`). CatsPanelError on a strand with none: a band name_loop_halves did not key."""
    if "trial" not in strand:
        raise CatsPanelError(f"strand {strand['edge']} has no trial key: the bands were not read through name_loop_halves")
    return strand["trial"]


def name_loop_halves(bands: Bands, device: DeviceMap | None = None) -> list[tuple[str, Band, dict]]:
    """A copy of `bands` as the device map holds them. Each main and upper strand carries its trial key (`trial`,
    read by placeholder): the switch-and-leg key of its piece (staging_device_map.band_refs, one grammar for every
    level; strand_placeholders, one desk block per strand; CatsPanelError on a connector the plugin's
    partners do not pair). Each balloon loop is two desk blocks: each half's strand is named by its device map
    block less "Track " (the plugin parts a turnback between two differently named tracks in the middle of its run,
    and labels each half) and marked with its half (`loop_half`). The plugin prints a track's track_labels label
    (the helix tracks' McKees Rocks and McKeesport) in place of its name."""
    import build_layout_le as bl
    import staging_device_map as sdm
    keys = drawn_keys(device)
    out = copy.deepcopy(bands)
    _sheet, le_mod, _core = bl.plugin()
    joined = le_mod.partners(out)
    for bi, (title, band, _) in enumerate(out):
        if not bdm.band_level(title):
            continue
        try:
            refs = sdm.band_refs(out, joined, bi)
        except sdm.StagingMapError as exc:
            raise CatsPanelError(f"{title}: {exc}") from exc
        for sid, ref in refs.items():           # one desk block per strand on main and upper
            band["strands"][sid]["trial"] = sdm.strand_placeholders(ref)[0]
    for title, band, _ in out:
        if not bdm.band_level(title):
            continue
        try:
            halves = bdm.loop_halves(band, bl.runs)
        except bdm.MapError as exc:
            raise CatsPanelError(f"{title}: {exc}") from exc
        for sid, half in halves.items():
            band["strands"][sid]["loop_half"] = half
            trial = placeholder(band["strands"][sid])
            row, stored_name = keys.row(trial), keys.name(trial)
            if row is None or stored_name is None or row["layer"] != "block":
                raise CatsPanelError(f"{title}: balloon loop half {trial} has no block row in {DEVICE_MAP.name}")
            band["strands"][sid]["name"] = stored_name.removeprefix("Track ")    # the name store's, by its ID
    return out


def drawn_keys(device: DeviceMap | None = None) -> drawing_keys.Keys:
    """The main and upper drawing keys (hartlib.drawing_keys: each schematic piece's device by ID, named from the
    merged view, the name store) of the master `device` was read from (a Facts.device; None: the committed master).
    CatsPanelError on a device made in memory (no path: its rows hold no parts and no ids, so the desk would mix it with
    the committed master), and naming the file on keys that do not read as one device per piece. A device map's
    master is read once per content of its files (_master_state: the desk build asks for every block), and only the
    latest read of each master is kept; the committed master is read each call."""
    if device is None:
        path = DEVICE_MAP
    elif getattr(device, "path", None):
        path = device.path
    else:
        raise CatsPanelError("cats_panel.drawn_keys: the device map was made in memory and names no master to read the "
                         "drawing keys of")
    state = None if device is None else _master_state(Path(path))
    if state is not None and state[0] in _DRAWN_KEYS and _DRAWN_KEYS[state[0]][0] == state[1]:
        return _DRAWN_KEYS[state[0]][1]
    try:
        keys = drawing_keys.read(level_devices.LEVELS, path)
    except (drawing_keys.DrawingKeyError, FactsError) as exc:
        raise CatsPanelError(f"{paths.rel(path)}: {exc}") from exc
    if state is not None:
        _DRAWN_KEYS[state[0]] = (state[1], keys)       # replaces the master's older read
    return keys


MasterState = tuple[Path, str]
_DRAWN_KEYS: dict[Path, tuple[str, drawing_keys.Keys]] = {}   # master path -> (content hash, its keys): the latest only


def _master_state(path: Path) -> MasterState:
    """The master at `path` and a SHA-256 of the name and bytes of each file of it (the two files hartlib.devices
    merges, in the master's folder): a key that changes when either file's content does, whatever its size or time."""
    digest = hashlib.sha256()
    for f in (path.parent / name for name in (devices.FIELD_FILE, devices.GENERATED_FILE)):
        if f.exists():
            data = f.read_bytes()
            digest.update(f"{f.name}\0{len(data)}\0".encode())
            digest.update(data)
    return path.resolve(), digest.hexdigest()


def part_blocks(device: DeviceMap | None = None) -> dict[str, tuple[str, str]]:
    """{trial name: (part name, the block it is part of)} of the main and upper parts (the device master's part_of: a
    link inside an OS block), which the device maps leave out: a block of its own on
    the desk, bound to its OS block's sensor. Read through drawn_keys, which stops on a key two rows give, from the
    master `device` was read from; a device map made in memory (a test's, no path) holds no part."""
    if device is not None and not getattr(device, "path", None):
        return {}
    keys = drawn_keys(device)
    return {k: (keys.rows[i]["user_name"], keys.rows[i]["part_of"]) for k, i in keys.ids.items()
            if keys.rows[i]["role"] == "part"}


def block_names(device: DeviceMap | None, parts: bool | None = None) -> dict[str, str]:
    """{drawing key: block name} of the main and upper block rows of `device` (a Facts.device): read through the one
    reader (drawn_keys: by device ID, the name store's name; parts alone when `parts` is True, none when False, both
    when None), so a block is found by its ID, not by its row's own cells. A device map made
    in memory (a test's, no path, no parts) by its rows' trial cells."""
    if device is not None and not getattr(device, "path", None):
        return {} if parts else {t: n for n, r in device.blocks.items() for t in r.trial}
    return dict(drawn_keys(device).of("block", parts=parts))


def device_name(bands: Bands, cats: ModuleType, keys: Iterable[BlockKey], F: Facts, log: list[str]) -> str:
    """The device map's name of the main or upper block made of block keys `keys`: the OS block of switch N for an
    OS block (a crossover's halves are one block; switches whose OS blocks the plugin merges over a track too short
    to part them take the lowest number, logged), else the device map track that holds the block's schematic tracks.
    Each is found by its drawing key through the one reader (drawn_keys, hartlib.drawing_keys: by device ID, so the
    name is the name store's), not by a row's own cells."""
    named = block_names(F.device, parts=False)              # {drawing key: its block's name}
    labels = sorted({cats.label_of(bands, k) for k in keys if k[0] == "os"} - {""}, key=bdm.natural)
    if labels:
        numbers = sorted({bdm.base(lb) for lb in labels}, key=bdm.natural)
        key = f"OS Switch {numbers[0]}"                     # the OS block's drawing key
        name = named.get(key) or key                        # a double crossover's has none: its corners do
        if len(numbers) > 1:
            log.append(f"switches {', '.join(numbers)} share one OS block on the desk ({name}): the track between "
                       "them is too short to part them")
        if name not in F.device.blocks and not xover_corners(name, F):
            raise CatsPanelError(f"{name}: no block row in {DEVICE_MAP.name}")
        return name
    edges, ends = set(), set()
    for k in keys:
        bi, sid = k[1].split(":", 1)
        band = bands[int(bi[1:])][1]
        s = band["strands"][sid]
        edges.add(placeholder(s))
        ends |= {band["nodes"][e[0]].get("label") or "" for e in (s["src"], s["dst"])
                 if band["nodes"][e[0]]["kind"] in ("switch", "dx")}
    rows = sorted({named[e] for e in edges if e in named})
    parts = part_blocks(F.device)
    if not rows and edges and edges <= set(parts):
        # a link inside an OS block that the desk draws as a block of its own: the part's name (its sensor is its OS
        # block's, dark_bindings)
        held = {parts[e][0] for e in edges}
        if len(held) != 1:
            raise CatsPanelError(f"desk block {sorted(keys)}: its tracks {', '.join(sorted(edges))} are parts "
                             f"{', '.join(sorted(held))}; a desk block lies in one")
        return held.pop()
    end_numbers = {bdm.base(lb) for lb in ends}
    if not rows and len(end_numbers) == 1 and len(ends) > 1:
        # the track between a crossover's halves (drawn on two bands, 127 and 131): the device map counts it in the
        # crossover's OS block
        key = f"OS Switch {end_numbers.pop()}"
        name = named.get(key) or key
        if name not in F.device.blocks:
            raise CatsPanelError(f"{name}: no block row in {DEVICE_MAP.name}")
        return name
    if len(rows) != 1 or not edges <= set(named):
        raise CatsPanelError(f"desk block {sorted(keys)}: the schematic tracks {', '.join(sorted(edges))} is in "
                         f"{', '.join(rows) or 'no'} device map block rows; it must lie in exactly one")
    return rows[0]


def spec(system: str, user: str) -> dict[str, IoSpec]:
    """The IOSPECs a block bound to sensor `system` (user name `user`) takes, as staging's (occupancy_spec):
    JMRIPREFIX the system prefix (M2S, or IS for an internal sensor), DECADDR the rest of the system name."""
    prefix = STAGING_SENSOR_PREFIX if system.startswith(STAGING_SENSOR_PREFIX) else LEVEL_SENSOR_PREFIX
    if not system.startswith(prefix):
        raise CatsPanelError(f"{user}: sensor {system} is neither {STAGING_SENSOR_PREFIX} nor internal")
    return occupancy_spec(prefix, system[len(prefix):], user)


def virtual_sensor(name: str, F: Facts) -> dict[str, IoSpec] | None:
    """The IOSPECs of block `name`'s virtual occupancy sensor (the jmri_name of the device map's occupancy row that
    serves it, by that row's blocks column), or None: the middle of a double crossover's X has none (its corners do)."""
    row = F.device.occupancy.get(name)
    return None if row is None else spec(row.jmri_name, row.user_name)


def planned_sensor(name: str, F: Facts) -> dict[str, IoSpec] | None:
    """The IOSPECs of block `name`'s planned detector (its occupancy row's system_name, a draft), or None."""
    row = F.device.occupancy.get(name)
    return None if row is None or not row.system_name else spec(row.system_name, row.user_name)


def inside_os(bands: Bands, P: DeskPanel, bound_bi: int, name: str, row: DeviceRow,
              drawn: drawing_keys.Keys | None = None) -> str:
    """Why device map block `name` (its DeviceRow `row`) has no block of its own on the desk, checked on the drawing:
    each schematic track it holds (its drawing keys, read by its ID through `drawn`, drawn_keys of the master `row`
    came from; with no `drawn`, a device map made in memory, or a row with no ID, a test's: its trial names) is drawn on main or upper from a switch to a switch (or
    through a turnback or a connector), and the plugin gave every cell of it to their OS blocks (its track key is no
    block, or one joined to an OS block). Anything else stops, naming the block."""
    held = drawn.keys(row.id, str(row.level)) if drawn is not None and row.id else row.trial
    found, cm = [], {}
    for bi, band, _opts in level_bands(bands, bound_bi):
        for sid, s in band["strands"].items():
            if placeholder(s) not in held:
                continue
            found.append((bi, sid))
            key = ("track", f"b{bi}:{sid}")
            if key in P.blocks and P.find(key)[0] != "os":    # union-find roots: an OS key sorts before a track key
                raise CatsPanelError(f"{name}: its schematic track {s['edge']} is a desk block, but not one named {name}")
            ends = [band["nodes"][e[0]] for e in (s["src"], s["dst"])]
            if not all(d["kind"] in ("switch", "dx") or d["kind"].startswith("turn") or d.get("sub") == "link"
                       for d in ends) or not any(d["kind"] in ("switch", "dx") for d in ends):
                raise CatsPanelError(f"{name}: its schematic track {s['edge']} has no desk block and does not run "
                                 "between switches, so it is not inside their OS blocks")
            cm[plan_edge(s)] = s["cm"]     # as the device map measures it
    if not found or not held <= {placeholder(bands[bi][1]["strands"][sid]) for bi, sid in found}:
        raise CatsPanelError(f"{name}: the device map's tracks {', '.join(sorted(held))} are not all drawn on "
                         "main or upper")
    length = round(sum(cm.values()), 1)
    return (f"inside its switches' OS blocks on the desk ({length:g} cm, too short at one cell per grid unit for a "
            "block)")


def _band_of(key: BlockKey) -> int:
    """The band index of a desk block key ("b<index>:...")."""
    return int(key[1].split(":", 1)[0][1:])


def dark_bindings(bands: Bands, cats: ModuleType, P: DeskPanel, F: Facts, bound_bi: int,
                  stored: Mapping[str, str]) -> DarkBindings:
    """DarkBindings for the main and upper blocks: device map names, MAIN_UPPER_DISCIPLINE, the
    station plate, the virtual occupancy sensor bound (the device map's jmri_name) and the planned detector kept as
    _planned_*; the report names each device map block with no block of its own on the desk, why, and its sensor;
    `joined` the staging keys of helix blocks, bound here (helix_block, by the `stored` staging names)."""
    groups: defaultdict[BlockKey, list[BlockKey]] = defaultdict(list)
    for key in P.blocks:
        groups[P.find(key)].append(key)
    out: dict[str, BlockBinding] = {}
    log: list[str] = []
    seen: set[str] = set()
    missing: dict[str, str] = {}
    joined: set[BlockKey] = set()
    helix = plan_bands.read_helix_tracks()
    part_of = dict(part_blocks(F.device).values())                  # {part: its OS block}
    for root, keys in sorted(groups.items(), key=lambda kv: P.names[kv[0]]):
        panel_name = P.names[root]
        dark = [k for k in keys if level_band(bands, _band_of(k), bound_bi)]
        if not dark:
            continue
        if len(dark) < len(keys):       # a helix track: one block from staging up the helix
            name = device_name(bands, cats, dark, F, log)
            staged = {helix_block(k, helix, stored) for k in keys if k not in dark}
            if staged != {name}:
                raise CatsPanelError(f"desk block {panel_name} holds track of staging ({', '.join(sorted(map(str, staged)))}"
                                 f") and of main or upper ({name}); only a helix block of "
                                 f"{plan_bands.HELIX_SOURCE.name} may, and both device maps must name it")
        elif any(k[0] in ("corner", "xmid") for k in keys):
            # a double crossover's corner or the middle of its X: the plugin named it from the corners binding
            # (level_switch_bindings), which is the device map's name
            name = panel_name
            if name not in F.device.blocks and not xover_corners(name, F):
                raise CatsPanelError(f"{name}: no block row in {DEVICE_MAP.name}")
        else:
            name = device_name(bands, cats, keys, F, log)
        joined.update(k for k in keys if k not in dark)
        e: BlockBinding = block_entry(panel_name, name, MAIN_UPPER_DISCIPLINE)
        # from the device map alone: build_layout_le.py, which runs after this build in make panels, adds the sensor to
        # the tables, and check_layout_facts.py checks the desk against them
        sensor_of = part_of.get(name, name)                 # a part: its OS block's sensor
        bound = virtual_sensor(sensor_of, F)
        if bound:
            e.update(bound)
        elif name in F.device.blocks:
            raise CatsPanelError(f"{name}: no occupancy row in {DEVICE_MAP.name}")
        planned = planned_sensor(sensor_of, F)
        if planned:
            e.update({"_planned_" + k: v for k, v in planned.items()})
        if name in seen:
            log.append(f"blocks named {name} on the desk are one block")
        seen.add(name)
        out[panel_name] = e
    drawn = drawn_keys(F.device) if getattr(F.device, "path", None) else None     # None: a test's map in memory
    for name, row in sorted(F.device.blocks.items()):
        if name not in seen and name not in missing:
            missing[name] = inside_os(bands, P, bound_bi, name, row, drawn)
    report: dict[str, Unbound] = {}
    for name, why in sorted(missing.items()):
        report[name] = Unbound(why=why)
        if planned_sensor(name, F):
            report[name]["detector"] = F.device.occupancy[name].user_name
            log.append(f"{name}: not a block of its own on the desk ({why}); its detector "
                       f"{report[name]['detector']} has no block to bind")
    return DarkBindings(out, log, report, joined)


def helix_block(key: BlockKey, helix: Mapping[str, Mapping[str, str]], stored: Mapping[str, str]) -> str | None:
    """The helix block of staging desk key `key` (`helix`: {plan name: its read_helix_tracks entry}): the name store's
    name of its strand (`stored`, staging_names) is a helix track's; else None. staging_device_map.check_helix holds
    the staging device map to the same block."""
    if key[0] != "track":
        return None
    name = stored.get(key[1].split(":", 1)[1])
    return helix.get(name, {}).get("block") if name else None


def level_switch_bindings(bands: Bands, F: Facts, bound_bi: int, dx_corners: Mapping[str, Mapping[str, str]] | None = None) -> dict[str, SwitchBinding]:
    """({switch label: binding}, {label: why not bound}) for the main and upper switches: each switch or crossover
    half drawn commands and reports the turnout tables.xml holds as Switch <n> (its device-master row's bean, by its
    system name: split_system_name), closed on leg B (NORMAL) and thrown on leg C. A crossover's halves, on one band or two,
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
        raise CatsPanelError(str(exc)) from exc
    out: dict[str, SwitchBinding] = {}
    for _bi, band, _ in level_bands(bands, bound_bi):
        nodes = band["nodes"]
        why: list[str] = []
        half_legs = {n: got[0] for n, got in core.crossover_halves(nodes, band["strands"], why).items()}
        for n, d in sorted(nodes.items()):
            label = str(d.get("label") or "")
            if d["kind"] not in ("switch", "dx"):
                continue
            num = bdm.base(label)
            user = f"Switch {num}"
            system = F.turnouts.get(user)
            if not system:
                raise CatsPanelError(f"switch {label}: tables.xml has no turnout {user} (its device-master row's bean)")
            if label in out:
                raise CatsPanelError(f"switch {label} is drawn twice on main and upper")
            thrown = half_legs.get(n, "C")      # a crossover half: its link leg toward the other half; else leg C
            # a lettered half (125B, or 125B* with an added branch) the plugin did not pair: its other half is on
            # another band
            if re.search(r"\d[AB]$", label.rstrip("*")) and n not in half_legs:
                s = band["strands"].get(legs_of(d).get("C"))
                far = (s["dst"][0] if s["src"][0] == n else s["src"][0]) if s else ""
                if not far.startswith("LINK:"):
                    raise CatsPanelError(f"switch {label}: a crossover half the plugin pairs with no other half, and its "
                                     "leg C does not lead to the link between the levels"
                                     + (f" ({'; '.join(why)})" if why else ""))
            closed = "C" if thrown == "B" else "B"
            prefix, addr = split_system_name(system)
            out[label] = SwitchBinding(normal=closed, routes=turnout_routes(prefix, addr, user, closed, thrown))
            if d["kind"] == "dx" and dx_corners is not None:
                if num not in dx_corners:
                    raise CatsPanelError(f"double crossover {label}: no corners found for it")
                out[label]["corners"] = dict(bdm.xover_corners(num, dx_corners[num]), X=f"OS Switch {num}")
    return out


def intermediate_signal(bands: Bands, F: Facts, bound_bi: int, r: Mapping[str, Any], by_trial: Mapping[str, str]) -> tuple[int, DeskSignal]:
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
        raise CatsPanelError(f"{r['mast']}: no desk band draws {r['facing']}")
    if len(meets) != 1:
        raise CatsPanelError(f"{r['mast']}: {r['facing']} meets {r['protects']} at "
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


def level_signals(bands: Bands, F: Facts, bound_bi: int) -> None:
    """Put each main and upper mast (masts.csv) in its band's signals, as the plugin reads a band's drawn
    masts: on the track it faces (the device map block holding the schematic track at that leg of its switch), at
    that switch (its toward end), heading the way its row's dir says, its heads from its row. The two halves of a
    balloon loop are one schematic track drawn twice: each half's piece gets an edge of its own (loop_half_edge,
    which placeholder reads back as the one track), so a mast finds its own half. `bands` is changed in place (a copy:
    name_loop_halves). Stops on a mast drawn at no switch leg or at two."""
    # each drawing key's block by ID through the one reader (drawn_keys), parts among them: a
    # part (a link inside an OS block) is a block of its own, its sensor its OS block's, so a mast may face it
    by_trial = block_names(F.device)
    added: defaultdict[int, list[DeskSignal]] = defaultdict(list)
    for r in F.level_masts:
        if level_masts.is_level_virtual(r["system_name"]):
            continue                                # a hidden destination mast: no desk signal, as on staging
        if not r["switch"]:                         # an APB intermediate
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
            raise CatsPanelError(f"{r['mast']}: Switch {r['switch']} has {len(hits)} legs on track {r['facing']} on the "
                             "desk; it must have one")
        bi, n, _port, sid = hits[0]
        title, band, opts = bands[bi]
        s = band["strands"][sid]
        # pieces of its track that also end at this switch: the plugin would take the first (mast_piece)
        twins = [k for k, t in band["strands"].items() if k != sid and t["edge"] == s["edge"]
                 and n in (t["src"][0], t["dst"][0])]
        if twins:
            if not s.get("loop_half") or any(not band["strands"][k].get("loop_half") for k in twins):
                raise CatsPanelError(f"{r['mast']}: its track {s['edge']} is drawn more than once at Switch "
                                 f"{r['switch']} on {title}, and not as the halves of a balloon loop")
            for t in [band["strands"][k] for k in [sid] + twins]:
                t.setdefault("plan_edge", t["edge"])
                t["edge"] = loop_half_edge(t["plan_edge"], t["loop_half"])
        if s["edge"].endswith(("x", "y")) and not s.get("loop_half"):
            raise CatsPanelError(f"{r['mast']}: its track {s['edge']} is one piece of a track drawn on two levels")
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
            raise CatsPanelError(f"{bands[bi][0]}: masts {', '.join(clash)} are drawn there already")
        opts["signals"] = list(opts.get("signals") or ()) + sorted(sigs, key=lambda sg: sg["mast"])


def level_mast_bindings(bands: Bands, F: Facts, bound_bi: int) -> dict[str, MastBinding]:
    """{mast: {name, template}} for the main and upper masts level_signals drew: each a mast in tables.xml whose
    system name is its masts.csv row's, with its template by mast_template: its own signal_head_plan.csv
    row when it has one, else the template masts of its appearance type take. A row not drawn stops, but a virtual
    one (hidden, no desk signal)."""
    rows = {r["mast"]: r for r in F.level_masts}
    by_type = template_by_type(F)
    out: dict[str, MastBinding] = {}
    for bi, _band, opts in level_bands(bands, bound_bi):
        for sg in opts.get("signals") or ():
            name = opts.get("mast_prefix", "") + sg["mast"]
            r = rows.get(name)
            if r is None:
                continue
            if F.mast_system.get(name) != r["system_name"]:
                raise CatsPanelError(f"{name}: tables.xml has {F.mast_system.get(name) or 'no such mast'}, "
                                 f"{level_masts.PATH.name} says {r['system_name']}")
            template = mast_template(name, F, by_type)
            if template is None:
                raise CatsPanelError(f"{name} on {bands[bi][0]}: no row of its own and no template for its type "
                                 f"{mast_type(r['system_name'])} in signal_head_plan.csv")
            out[sg["mast"]] = MastBinding(name=name, template=template)
    missing = sorted(set(rows) - {e["name"] for e in out.values()}
                     - {m for m, r in rows.items() if level_masts.is_level_virtual(r["system_name"])})
    if missing:
        raise CatsPanelError(f"main and upper masts not on the desk: {', '.join(missing)}")
    return out
