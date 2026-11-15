"""build_cats_panel.py [--check]

Generate one CATS Designer panel for all three levels (staging, main, upper) from the schematic grid, with the
schematic-maps plugin's `cats` command, into cats/panels/generated/HART_Generated.xml. It sits beside the live
desks (ADR-023): cats/panels/HART_CTC.xml, HART_ABS.xml and HART_Digicon.xml are not touched, and the deploy installs
only its LIVE_PANELS list, so this file is not deployed. tools/check.sh validates it with
cats/scripts/validate_cats_panel.py, and cats/scripts/tests/test_generated_desk_parity.py proves its staging part
binds every turnout, block, sensor and mast the live desk binds, the same way.

Bands stack in the sheet's order (staging on top). Staging is bound to the live JMRI objects through the bindings
file cats/panels/generated/HART_Generated.bindings.json, which this script writes from the railroad's facts, never by
hand:
  switches.csv / switch_legs.csv  which OS block each switch's points are in, which leg is closed and which thrown,
                                  and whether CATS normal is JMRI thrown (cats_inverted); Switch 9 and 13 follow them
  public_name_map.csv + tables.xml  each switch's M2T turnout (cats_turnout_io.load_turnouts)
  occupancy_bindings.csv + tables.xml  each block's M2S sensor and discipline (digicon_lib.load_occupancy)
  staging.signals.json + signal_head_plan.csv  the masts drawn on staging (field and planned) and their templates
  tables.xml  the Layout Editor block of a short track between two switches, which has no block of its own
The IOSPEC, STATION and SECSIGNAL conventions are the live desk's (wire_digicon.py, cats_turnout_io.py,
digicon_lib.py), and the SIGNALTEMPLATE and JMRINAME lines are copied from HART_CTC.xml. Main and upper have no
JMRI objects yet, so they stay unbound. Inputs and plugin are the same as tools/schematic/publish_draft.py
(SCHEMATIC_PLUGIN for other plugin code).

--check regenerates both files into a temporary folder and compares (exit 1 if either is stale). When
SCHEMATIC_PLUGIN is not set and the plugin submodule is not checked out or not at its pinned commit, --check prints
SKIPPED and exits 0 (a failure with SCHEMATIC_REQUIRED=1).
"""
import difflib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
from hartlib import paths, tables  # noqa: E402

sys.path[:0] = [str(paths.CATS_DIR / "scripts"), str(paths.LAYOUT_SCRIPTS)]
import cats_turnout_io as tio  # noqa: E402
import digicon_lib as le  # noqa: E402
import layout_facts as facts  # noqa: E402
from wire_digicon import mast_templates, station_plate  # noqa: E402

OUT = pd.REPO / "cats/panels/generated/HART_Generated.xml"
BINDINGS = OUT.with_name("HART_Generated.bindings.json")
LIVE = paths.CATS_DIR / "panels/HART_CTC.xml"       # SIGNALTEMPLATE and JMRINAME lines come from here
BOUND = "Staging"                                    # the band bound to JMRI (its title starts with this)


def plugin_modules(plugin):
    sys.path.insert(0, str(plugin))
    from schematic import cats, sheet
    return cats, sheet


def le_graph(root):
    """The main Layout Editor panel as {node: [(segment, block, other node)]}; a node is a turnout ident or an
    anchor/end bumper ident."""
    panel = tables.layout_editor(root)
    out = defaultdict(list)
    for ts in panel.iter("tracksegment"):
        a, b, blk = ts.get("connect1name"), ts.get("connect2name"), ts.get("blockname") or ""
        out[a].append((ts.get("ident"), blk, b))
        out[b].append((ts.get("ident"), blk, a))
    return out


def le_blocks_between(graph, turnouts, a, b):
    """Block names of the Layout Editor segments on the track from turnout `a` to turnout `b` (anchors only
    between them), or None when no such track exists."""
    for seg, blk, nxt in graph[a]:
        path, prev = [blk], a
        while nxt not in turnouts:
            onward = [(s, bk, n) for s, bk, n in graph[nxt] if s != seg]
            if len(onward) != 1:
                break
            seg, bk, nxt2 = onward[0]
            path.append(bk)
            nxt = nxt2
        else:
            if nxt == b:
                return path
    return None


def bindings(bands, cats):
    """The bindings for the staging band, from the facts (see the module docstring)."""
    bi = next(i for i, (t, _, _) in enumerate(bands) if t.startswith(BOUND))
    _, band, opts = bands[bi]
    nodes, strands = band["nodes"], band["strands"]
    switches = facts.load_switches()
    turnout_io = tio.load_turnouts()                  # le_ident -> (address, user name)
    occupancy = le.load_occupancy()                   # block -> (address, sensor user name)
    discipline = le.load_disciplines()

    def leg_strand(n, port):
        d = nodes[n]
        return (d["ins"] | d["outs"])[port]

    def far(sid, n):
        s = strands[sid]
        return s["dst"][0] if s["src"][0] == n else s["src"][0]

    # each switch node's OS block: its switch's only one, or the leg row whose named tracks it touches
    sw_nodes = {n: d for n, d in nodes.items() if d["kind"] == "switch"}
    os_of = {}
    for n, d in sw_nodes.items():
        sw = switches[int(d["label"])]
        if len(sw.legs) == 1:
            os_of[n] = sw.legs[0].os_block
            continue
        touched = {"Track " + strands[leg_strand(n, p)]["name"] for p in "BC" if strands[leg_strand(n, p)]["name"]}
        rows = [leg.os_block for leg in sw.legs if {leg.closed, leg.thrown} & touched]
        if len(rows) == 1:
            os_of[n] = rows[0]
    for n, d in sw_nodes.items():                    # the rest by elimination
        if n not in os_of:
            sw = switches[int(d["label"])]
            mates = [m for m in sw_nodes if sw_nodes[m]["label"] == d["label"]]
            left = [leg.os_block for leg in sw.legs if leg.os_block not in {os_of.get(m) for m in mates}]
            if len(left) != 1:
                raise SystemExit(f"switch {d['label']}: cannot tell which of {[l.os_block for l in sw.legs]} "
                                 f"node {n} is from switch_legs.csv")
            os_of[n] = left[0]

    def dest(n, port):
        """The block leg `port` of switch node n leads to, beyond its own OS."""
        sid, here = leg_strand(n, port), n
        while True:
            s = strands[sid]
            if s["name"]:
                return "Track " + s["name"]
            nxt = far(sid, here)
            d = nodes[nxt]
            if d["kind"] == "switch":
                return os_of[nxt]
            if d["kind"].startswith("turn"):         # the other half of a fold
                sid = next(k for k in (d["ins"] | d["outs"]).values() if k != sid)
                here = nxt
                continue
            raise SystemExit(f"switch {nodes[n]['label']} leg {port} ends at {nxt} without a track name")

    labels = Counter(d["label"] for d in sw_nodes.values())
    out_sw = {}
    for n, d in sorted(sw_nodes.items(), key=lambda kv: (int(kv[1]["label"]), os_of[kv[0]])):
        sw = switches[int(d["label"])]
        leg = next(l for l in sw.legs if l.os_block == os_of[n])
        to = {p: dest(n, p) for p in "BC"}
        if sorted(to.values()) != sorted((leg.closed, leg.thrown)):
            raise SystemExit(f"{leg.os_block}: the schematic's legs lead to {to}, but switch_legs.csv says "
                             f"closed {leg.closed}, thrown {leg.thrown}")
        closed = next(p for p in "BC" if to[p] == leg.closed)
        thrown = "C" if closed == "B" else "B"
        if sw.le_ident not in turnout_io:
            raise SystemExit(f"Switch {sw.number}: no M2T turnout for {sw.le_ident}")
        addr, uname = turnout_io[sw.le_ident]
        io = lambda cmd: {"DECADDR": addr, "JMRIPREFIX": "M2T", "USER_NAME": uname, "command": cmd}
        key = d["label"] if labels[d["label"]] == 1 else f"{d['label']}/{d['alias']}"
        out_sw[key] = {
            "block": leg.os_block,
            "normal": thrown if sw.cats_inverted else closed,
            "routes": {closed: {"SELECTEDREPORT": io("close"), "ROUTECOMMAND": io("close")},
                       thrown: {"SELECTEDREPORT": io("throw"), "ROUTECOMMAND": io("throw")}},
        }

    # blocks: the panel's names once the switches name their OS blocks
    P = cats.panel(bands, bindings={"switches": {k: {"block": v["block"]} for k, v in out_sw.items()}})
    root = tables.read(paths.TABLES_XML)
    graph = le_graph(root)
    turnouts = {lt.get("ident") for lt in tables.layout_turnouts(tables.layout_editor(root))}
    out_blk = {}
    for key, name in sorted(P.names.items(), key=lambda kv: kv[1]):
        if not key[1].startswith(f"b{bi}:"):
            continue
        layout = name if name in occupancy else "Track " + name
        if layout not in occupancy:            # a short track between two switches: the Layout Editor's block
            s = strands[key[1].split(":", 1)[1]]
            a, b = (switches[int(nodes[e[0]]["label"])].le_ident for e in (s["src"], s["dst"]))
            found = le_blocks_between(graph, turnouts, a, b)
            if not found:
                raise SystemExit(f"block {name}: no Layout Editor track joins {a} and {b}")
            layout, _ = Counter(found).most_common(1)[0]
            out_blk[name] = {"name": layout}
            continue
        addr, sensor = occupancy[layout]
        out_blk[name] = {
            "name": layout,
            "station": station_plate(layout),
            "discipline": discipline.get(layout, "CTC"),
            "occupied": {"DECADDR": addr, "JMRIPREFIX": "M2S", "USER_NAME": sensor, "command": "close"},
            "unoccupied": {"DECADDR": addr, "JMRIPREFIX": "M2S", "command": "throw"},
        }
        if out_blk[name]["name"] == name:
            del out_blk[name]["name"]

    # masts: every drawn one (field and planned) on staging, by its JMRI user name
    templates = mast_templates()
    in_jmri = {tables.user_name(m) for m in tables.masts(root)}
    out_mast = {}
    for sg in opts.get("signals") or ():
        if sg["kind"] == "virtual":
            continue
        name = opts.get("mast_prefix", "") + sg["mast"]
        if name not in in_jmri or name not in templates:
            raise SystemExit(f"{name}: not a JMRI mast with a template in signal_head_plan.csv")
        out_mast[sg["mast"]] = {"name": name, "template": templates[name]}
    return {"_note": "Written by tools/schematic/build_cats_panel.py from the railroad's facts; do not edit.",
            "switches": out_sw, "blocks": out_blk, "masts": out_mast}


def generate(plugin, out, bindings_out):
    cats, sheet = plugin_modules(plugin)
    bands = sheet.build([(f"{pd.GRAPHS}/{g}", n) for g, n in pd.INPUTS], str(pd.DATA)).bands
    bindings_out.write_text(json.dumps(bindings(bands, cats), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    run = subprocess.run([str(plugin / "bin/schematic"), "cats", str(out), "--data", str(pd.DATA),
                          *(f"{pd.GRAPHS}/{g}:{n}" for g, n in pd.INPUTS),
                          "--bindings", str(bindings_out), "--templates-from", str(LIVE)],
                         capture_output=True, text=True)
    print(run.stdout + run.stderr, end="")
    if run.returncode:
        sys.exit(run.returncode)


def main(argv):
    check = "--check" in argv
    try:
        plugin = pd.plugin()
    except SystemExit as e:
        if not check:
            raise
        print(f"SKIPPED CATS panel check: {e.code}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    with tempfile.TemporaryDirectory() as tmp:
        fresh = {OUT: Path(tmp) / OUT.name, BINDINGS: Path(tmp) / BINDINGS.name}
        generate(plugin, fresh[OUT], fresh[BINDINGS])
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
