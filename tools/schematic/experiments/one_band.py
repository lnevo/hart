"""HART as one band: a test case for the schematic plugin (wiki/projects/one-band-solver.md, set C).

Staging's and main's plan graphs are joined into one graph, the two helix cuts spliced
(39 to 131A as Helix Outer, 37 to 131B as Helix Inner), and the plugin is given one input
with the switch numbers, track names and signals but no `levels`, `helix` or helix ends.
The approved three-band sheet is not touched; this writes only to OUT.

    python3 tools/schematic/experiments/one_band.py OUT [--cap N] [--seconds S] [--profile]

OUT gets whole.json, data/ and one_band.svg. `--cap` raises the plugin's turnback cap from a
wrapper (plugin files unchanged; the cap is fault F1 on the project page). `--seconds` stops the
run after S seconds; with `--profile` the cProfile stats so far are written to OUT/profile.txt.
"""
import argparse
import cProfile
import io
import itertools
import json
import pstats
import signal
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "jmri/layouts/hart/data/schematic"
PLUGIN = REPO / "external/model-railroad-skills/plugins/schematic-maps"
HELIX = (("CUT:T55", "CUT:T210", "Helix Outer"), ("CUT:T78", "CUT:T281", "Helix Inner"))


def load(p):
    return json.loads(Path(p).read_text())


def build(out):
    """Write the joined graph and its layer files into OUT."""
    (out / "data").mkdir(parents=True, exist_ok=True)
    s, m = load(DATA / "inputs/staging.json"), load(DATA / "inputs/main.json")
    nodes = {**s["nodes"], **m["nodes"]}
    edges = [dict(e, id=pre + e["id"]) for pre, g in (("s", s), ("m", m)) for e in g["edges"]]

    def cut_edge(cut):
        (e,) = [e for e in edges if cut in (e["u"], e["v"])]
        return (e, e["v"], e["vp"]) if e["u"] == cut else (e, e["u"], e["up"])

    for a, b, name in HELIX:
        ea, swa, pa = cut_edge(a)
        eb, swb, pb = cut_edge(b)
        edges.remove(ea)
        edges.remove(eb)
        del nodes[a], nodes[b]
        edges.append(dict(ea, u=swa, up=pa, v=swb, vp=pb, cm=round(ea["cm"] + eb["cm"], 1), names=[name],
                          main=True, id="h" + name.split()[1].lower()))
    (out / "whole.json").write_text(json.dumps({"nodes": nodes, "edges": edges}, indent=1))

    o, gen = load(DATA / "plan_overrides.json"), load(DATA / "plan_generated.json")
    st, mu = o["staging"], o["main_upper"]
    relabel = {}
    for sec in (st, mu):
        for e in sec["edits"]:
            if e["op"] == "relabel":
                relabel.update(e["map"])
    ed = [{"op": "relabel", "map": relabel}]
    for e in st["edits"]:
        if e["op"] == "name":
            ed.append(e)
        if e["op"] == "end":
            ed.append(dict(e, ends=[x for x in e["ends"] if x[3] != "helix"]))
    whole = {"edits": ed, "mast_prefix": "Mast ", "level_title": "HART Railroad", "left_end": st["left_end"]}
    for k in ("stations", "control_points"):
        whole[k] = {**gen["staging"].get(k, {}), **gen["main_upper"].get(k, {})}
    whole["name_main"] = gen["staging"]["name_main"]
    (out / "data/plan_overrides.json").write_text(json.dumps({"_sections": True, "whole": whole}, indent=1))
    sg = load(DATA / "signals.json")
    sigs = sg["staging"]["signals"] + sg["main_upper"]["signals"]
    (out / "data/signals.json").write_text(json.dumps({"_sections": True, "whole": {
        "schema": "schematic.signals/1", "source": "merged", "signals": sigs, "unplaced": []}}, indent=1))


def raise_cap(cap):
    """Wrap the plugin's orient with a fixed turnback cap (the same search, own cap)."""
    from schematic import layout as L, orient as O

    def search(g, max_turnbacks=3, keep=10, require=()):
        t = time.time()
        sw = [e for e in g["edges"] if all(g["nodes"][n]["kind"] in O.JUNCTION for n in (e["u"], e["v"]))]
        req = set(require)
        must = [e for e in sw if e["id"] in req]
        cand = [e for e in sw if not e["link"] and O.udot(g, e) > -0.5 and e["id"] not in req]
        print(f"orient: {len(sw)} switch-to-switch runs, {len(cand)} may turn back, cap {cap}", file=sys.stderr)
        best, found = None, []
        for k in range(cap + 1):
            for T in (tuple(must) + c for c in itertools.combinations(cand, k)):
                ids = {e["id"] for e in T}
                sig = O.colour(g, sw, ids)
                if sig is None:
                    continue
                nodes, strands = O.build(g, sig, ids)
                col = O.columns(nodes, strands)
                if col is None:
                    continue
                cost = 10 * k + 0.2 * max(col.values()) + sum(6 * (1 - O.udot(g, e)) for e in T)
                found.append((cost, sorted(ids), sig, ids))
                if best is None or cost < best[0] - 1e-9:
                    best = (cost, sig, ids)
            print(f"  k={k}: {len(found)} found, {time.time() - t:.1f} s", file=sys.stderr)
            if best is not None and k + len(must) > len(best[2]):
                break
        if best is None:
            raise O.SchematicError(f"no orientation with up to {cap} turnbacks")
        found.sort(key=lambda f: (f[0], f[1]))
        print(f"orient: {time.time() - t:.1f} s, turnbacks {sorted(best[2])}", file=sys.stderr)
        return [(sig, ids) for _, _, sig, ids in found[:keep]]

    L.orient = search


class Stop(Exception):
    pass


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--cap", type=int, help="turnback cap (wrapper; default: the plugin's own)")
    ap.add_argument("--seconds", type=int, help="stop the run after this many seconds")
    ap.add_argument("--profile", action="store_true", help="write cProfile stats to OUT/profile.txt")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    build(a.out)
    sys.path.insert(0, str(PLUGIN))
    from schematic import cli
    if a.cap:
        raise_cap(a.cap)
    if a.seconds:
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(Stop()))
        signal.alarm(a.seconds)
    args = [str(a.out / "one_band.svg"), "--data", str(a.out / "data"), f"{a.out / 'whole.json'}:whole",
            "--no-preferences"]
    prof = cProfile.Profile() if a.profile else None
    t, rc = time.time(), 1
    try:
        if prof:
            prof.enable()
        rc = cli.run(["draw"] + args)
    except Stop:
        print(f"one_band: stopped at {a.seconds} s", file=sys.stderr)
    finally:
        if prof:
            prof.disable()
            buf = io.StringIO()
            st = pstats.Stats(prof, stream=buf).sort_stats("cumulative")
            st.print_stats(60)
            st.sort_stats("tottime").print_stats(30)
            (a.out / "profile.txt").write_text(buf.getvalue())
        print(f"one_band: {time.time() - t:.1f} s, exit {rc}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
