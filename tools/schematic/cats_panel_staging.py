"""build_cats_panel.py's staging section: each staging switch's OS block, its bindings and the staging blocks' and
masts'. Moved out of build_cats_panel.py unchanged."""
import re
from collections import Counter

from hartlib.cats import station_plate
from cats_panel_facts import mast_type, template_by_type


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
