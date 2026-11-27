"""cats_panel.py's bound level (staging): switches.csv and the cats_discipline blocks bound into the desk's
switches, OS blocks, blocks and masts, with the shapes of cats_panel_shapes.py; cats_panel.py re-exports every
name."""
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NotRequired, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hartlib.railroad_facts import Leg, Switch  # noqa: E402
from hartlib.railroad_facts import half_text  # noqa: E402
from hartlib.cats import station_plate  # noqa: E402
from hartlib.levels import level_text  # noqa: E402

from cats_panel_facts import CatsPanelError, Facts, template_by_type  # noqa: E402
from cats_panel_shapes import (STAGING_DISCIPLINE, STAGING_SENSOR_PREFIX, STAGING_TURNOUT_PREFIX,  # noqa: E402
                               block_entry, legs_of, mast_template, occupancy_spec, turnout_routes)

# A solved band of the schematic-maps plugin (nodes, strands ...): the plugin's own JSON shape, read by key, so its
# values are Any at this boundary.
Band = dict[str, Any]
Bands = Sequence[tuple[str, Band, dict]]      # (title, band, options) of every band, in the plugin's order
BlockKey = tuple[str, str]                    # a desk block key: (kind, "b<band index>:<strand or node>")


class IoSpec(TypedDict):
    """One IOSPEC of a binding (cats_panel_shapes.turnout_routes, occupancy_spec): the decoder address, its JMRI
    prefix, the user name (left out of an UNOCCUPIEDSPEC) and the command."""
    DECADDR: str
    JMRIPREFIX: str
    USER_NAME: NotRequired[str]
    command: str


Routes = dict[str, dict[str, IoSpec]]         # {leg: {"SELECTEDREPORT" | "ROUTECOMMAND": IoSpec}}


class SwitchBinding(TypedDict):
    """A desk switch's binding, as the bindings file holds it: its OS block (staging), half label (a staging
    crossover drawn as halves), NORMAL leg, routes and a double crossover's corners ({leg or "X": block})."""
    block: NotRequired[str]
    label: NotRequired[str]
    normal: str
    routes: Routes
    corners: NotRequired[dict[str, str]]


class BlockBinding(TypedDict, total=False):
    """A desk block's binding: its JMRI block (left out when it is the panel name), station plate, discipline, the
    sensor's OCCUPIEDSPEC / UNOCCUPIEDSPEC and a main or upper block's planned detector's (_planned_*)."""
    name: str
    station: str
    discipline: str
    occupied: IoSpec
    unoccupied: IoSpec
    _planned_occupied: IoSpec
    _planned_unoccupied: IoSpec


class MastBinding(TypedDict):
    """A desk mast's binding: its JMRI user name and CATS signal template."""
    name: str
    template: str


# --- the bound level (staging): switches.csv, the cats_discipline blocks --------------------------------------

def switch_of(F: Facts, d: Mapping[str, Any]) -> Switch:
    """The switches.csv switch of staging switch node `d` (its label is the switch number)."""
    try:
        return F.switches[int(d["label"])]
    except (KeyError, ValueError) as exc:
        raise CatsPanelError(f"switch {d.get('label')!r} on the staging band is not in switches.csv") from exc


def staging_names(band: Band, data: Path) -> dict[str, str]:
    """{strand: track name} of the staging band, from the name store of the schematic folder `data` the band was
    solved from, by each strand's ID (staging_device_map.staging_names), never read off the drawing: what os_blocks,
    dest, block_bindings and helix_block take as `stored`."""
    import staging_device_map as sdm
    try:
        return sdm.staging_names(band, data)
    except sdm.StagingMapError as exc:
        raise CatsPanelError(f"the staging track names: {exc}") from exc


def os_blocks(band: Band, F: Facts, stored: Mapping[str, str]) -> dict[str, str]:
    """{switch node: its OS block}: the switch's only one, else the switches.csv row whose named tracks its legs
    touch (`stored`: staging_names), else the one row left. Two nodes never get one row."""
    nodes = band["nodes"]
    sw_nodes = {n: d for n, d in nodes.items() if d["kind"] == "switch"}
    os_of: dict[str, str] = {}
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
                raise CatsPanelError(f"switch {d['label']}: cannot tell which of {[l.os_block for l in sw.legs]} "
                                 f"node {n} is from switches.csv")
            os_of[n] = left[0]
    seen: dict[str, str] = {}
    for n, os_name in sorted(os_of.items()):
        if os_name in seen:
            raise CatsPanelError(f"switch nodes {seen[os_name]} and {n} would both be {os_name}")
        seen[os_name] = n
    return os_of


def track_block(name: str, helix: Mapping[str, str]) -> str:
    """The block of a staging track the plan names `name`: a helix track's helix block (`helix`, {plan name: block},
    Facts.helix: one block up the helix), any other "Track <name>"."""
    return helix.get(name) or "Track " + name


def dest(band: Band, os_of: Mapping[str, str], n: str, port: str, helix: Mapping[str, str] | None,
         stored: Mapping[str, str]) -> str:
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
    raise CatsPanelError(f"switch {nodes[n]['label']} leg {port}: the track from it reaches no named track or switch")


def half_label(sw: Switch, leg: Leg, letters: Mapping[tuple[str, str], str]) -> str:
    """The panel label of one half of a switch with several OS blocks (a crossover): its number and the half's letter,
    upper case (23A, 23B), by its OS block's device ID (leg.os_id) from `letters` ({(level, id): letter},
    hartlib.hand_lists.half_letters: block_overrides.csv's crossover_half rows), never from its name, so the owner may
    rename the half (devices_field.csv). CatsPanelError on a half with no letter there."""
    own = letters.get((level_text(sw.level), leg.os_id))
    if own is None:
        raise CatsPanelError(f"Switch {sw.number}: {leg.os_block} ({leg.os_id or 'no OS block ID'}) has no crossover_half "
                         "row in block_overrides.csv to give its half letter")
    return f"{sw.number}{own.upper()}"


def os_plates(F: Facts) -> dict[str, str]:
    """{staging OS block name: its desk station plate}. A switch with one OS block: the name less "OS Switch " while
    the name keeps that form (19), else its number, so a renamed OS block keeps its plate rather than the first word
    of its name. A crossover half: its number and the letter of its ID (half_label; railroad_facts.half_text, so
    OS Switch 7 is 7), never a letter read off its name, so plate and label agree."""
    out: dict[str, str] = {}
    for sw in F.switches.values():
        for leg in sw.legs:
            if len(sw.legs) > 1:
                letter = half_label(sw, leg, F.half_letters)[-1].lower()
                out[leg.os_block] = half_text(sw.number, leg.os_block, letter)
            elif re.fullmatch(rf"OS Switch {sw.number}", leg.os_block):
                out[leg.os_block] = station_plate(leg.os_block)
            else:
                out[leg.os_block] = str(sw.number)
    return out


def switch_bindings(band: Band, F: Facts, os_of: Mapping[str, str],
                    stored: Mapping[str, str]) -> dict[str, SwitchBinding]:
    """{switch key: binding} for the staging switches: each node's OS block (os_of), its M2T turnout, closed on the
    leg that leads to its switches.csv closed block (dest, by the `stored` names), NORMAL the thrown leg when CATS
    normal is JMRI thrown (cats_inverted); a switch drawn as halves is keyed label/alias and labelled by half
    (half_label)."""
    nodes = band["nodes"]
    sw_nodes = {n: d for n, d in nodes.items() if d["kind"] == "switch"}
    labels = Counter(d["label"] for d in sw_nodes.values())
    out: dict[str, SwitchBinding] = {}
    for n, d in sorted(sw_nodes.items(), key=lambda kv: (int(kv[1]["label"]), os_of[kv[0]])):
        sw = switch_of(F, d)
        leg = next(l for l in sw.legs if l.os_block == os_of[n])
        to = {p: dest(band, os_of, n, p, F.helix, stored) for p in "BC"}
        if sorted(to.values()) != sorted((leg.closed, leg.thrown)):
            raise CatsPanelError(f"{leg.os_block}: the schematic's legs lead to {to}, but switches.csv says "
                             f"closed {leg.closed}, thrown {leg.thrown}")
        closed = next(p for p in "BC" if to[p] == leg.closed)
        thrown = "C" if closed == "B" else "B"
        if sw.le_ident not in F.turnout_io:
            raise CatsPanelError(f"Switch {sw.number}: no {STAGING_TURNOUT_PREFIX} turnout for {sw.le_ident}")
        addr, uname = F.turnout_io[sw.le_ident]
        key = d["label"] if labels[d["label"]] == 1 else f"{d['label']}/{d['alias']}"
        normal = thrown if sw.cats_inverted else closed
        routes = turnout_routes(STAGING_TURNOUT_PREFIX, addr, uname, closed, thrown)
        if labels[d["label"]] > 1:                                  # drawn as halves
            out[key] = SwitchBinding(block=leg.os_block, label=half_label(sw, leg, F.half_letters), normal=normal,
                                     routes=routes)
        else:
            out[key] = SwitchBinding(block=leg.os_block, normal=normal, routes=routes)
    return out


def block_bindings(band: Band, F: Facts, names: Mapping[BlockKey, str],
                   stored: Mapping[str, str]) -> dict[str, BlockBinding]:
    """names: {block key: panel block name} of the staging band's blocks (a helix block, bound with the main and
    upper ones, left out: dark_bindings). A block is its JMRI block (by name, or Track + name), bound to its detector;
    a short track joining two switches that the name store does not name (`stored`, staging_names), with no JMRI
    block of its own, joins the one block the staging device map gives it. Anything else stops."""
    nodes, strands = band["nodes"], band["strands"]
    out: dict[str, BlockBinding] = {}
    plates = os_plates(F)
    for key, name in sorted(names.items(), key=lambda kv: kv[1]):
        layout = next((x for x in (name, "Track " + name) if x in F.occupancy), None)
        if layout is None:
            sid = key[1].split(":", 1)[1] if key[0] == "track" else None
            s = strands.get(sid) if sid else None
            ends = [nodes[e[0]] for e in (s["src"], s["dst"])] if s else []
            if not s or not sid or stored.get(sid) or not all(d["kind"] == "switch" for d in ends):
                raise CatsPanelError(f"block {name}: no JMRI block {name} or Track {name} in the CATS bindings / "
                                 "tables.xml, and it is not a short unnamed track between two switches")
            a, b = (switch_of(F, d).le_ident for d in ends)
            out[name] = BlockBinding(name=F.layout.block_between(a, b, f"block {name}"))
            continue
        addr, sensor = F.occupancy[layout]
        out[name] = BlockBinding(**block_entry(name, layout, F.discipline.get(layout, STAGING_DISCIPLINE),
                                               plates.get(layout)),
                                 **occupancy_spec(STAGING_SENSOR_PREFIX, addr, sensor))
    return out


def mast_bindings(opts: Mapping[str, Any], F: Facts) -> dict[str, MastBinding]:
    """Every drawn mast (field and planned) by its JMRI user name and template: its own row in signal_head_plan.csv
    (a wired mast), else the template staging's masts of its appearance type take (mast_template), as main and
    upper masts get theirs. A name drawn twice stops."""
    out: dict[str, MastBinding] = {}
    by_type = template_by_type()
    for sg in opts.get("signals") or ():
        if sg["kind"] == "virtual":
            continue
        if sg["mast"] in out:
            raise CatsPanelError(f"mast {sg['mast']} is listed twice in the staging signals")
        name = opts.get("mast_prefix", "") + sg["mast"]
        template = mast_template(name, F, by_type)
        if name not in F.masts or template is None:
            raise CatsPanelError(f"{name}: not a JMRI mast, or no template for its type in signal_head_plan.csv")
        out[sg["mast"]] = MastBinding(name=name, template=template)
    return out
