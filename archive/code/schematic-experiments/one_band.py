"""HART as one band: a test case for the schematic plugin (archive/history/wiki/projects/one-band-solver.md, set C).

Staging's and main's plan graphs are joined into one graph, the two helix cuts spliced
(39 to 131A as Helix Outer, 37 to 131B as Helix Inner), and the plugin is given one input
with the switch numbers, track names and signals but no `levels`, `helix` or helix ends.
The approved three-band sheet is not touched; this writes only to OUT.

    python3 archive/code/schematic-experiments/one_band.py OUT [--cap N] [--row-seconds R] [--panels] [--seconds S] [--profile]

OUT gets whole.json, data/ and one_band.svg. `--cap` raises the plugin's turnback cap from a
wrapper (plugin files unchanged; the cap is fault F1 on the project page). `--seconds` stops the
run after S seconds; with `--profile` the cProfile stats so far are written to OUT/profile.txt. `--row-seconds` puts a
time limit on the row search (fault F4) from a wrapper. `--panels` also builds the Layout Editor panel and the CATS
desk from the same solve, with labels that find no clean spot listed and left out. Every run prints the time spent in
the orientation, the rows and the columns.
"""
import argparse
import cProfile
import collections
import io
import itertools
import json
import os
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


def disjoint(what, a, b):
    both = set(a) & set(b)
    if both:
        sys.exit(f"one_band: staging and main share {what} keys {sorted(both)[:5]}; the join would lose one")


def build(out):
    """Write the joined graph and its layer files into OUT."""
    (out / "data").mkdir(parents=True, exist_ok=True)
    s, m = load(DATA / "inputs/staging.json"), load(DATA / "inputs/main.json")
    disjoint("nodes", s["nodes"], m["nodes"])
    nodes = {**s["nodes"], **m["nodes"]}
    edges = [dict(e, id=pre + e["id"]) for pre, g in (("s", s), ("m", m)) for e in g["edges"]]

    def cut_edge(cut):
        found = [e for e in edges if cut in (e["u"], e["v"])]
        if len(found) != 1:
            sys.exit(f"one_band: helix cut {cut} has {len(found)} tracks, expected 1; were the inputs re-exported?")
        (e,) = found
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
                disjoint("relabel", relabel, e["map"])
                relabel.update(e["map"])
    if any(e["op"] in ("name", "end") for e in mu["edits"]) or "name_main" in gen["main_upper"]:
        sys.exit("one_band: main_upper now has name/end edits or name_main; carry them into the whole plan")
    ed = [{"op": "relabel", "map": relabel}]
    for e in st["edits"]:
        if e["op"] == "name":
            ed.append(e)
        if e["op"] == "end":
            ed.append(dict(e, ends=[x for x in e["ends"] if x[3] != "helix"]))
    whole = {"edits": ed, "mast_prefix": "Mast ", "level_title": "HART Railroad", "left_end": st["left_end"]}
    for k in ("stations", "control_points"):
        disjoint(k, gen["staging"].get(k, {}), gen["main_upper"].get(k, {}))
        whole[k] = {**gen["staging"].get(k, {}), **gen["main_upper"].get(k, {})}
    whole["name_main"] = gen["staging"]["name_main"]
    (out / "data/plan_overrides.json").write_text(json.dumps({"_sections": True, "whole": whole}, indent=1))
    sg = load(DATA / "signals.json")
    sigs = sg["staging"]["signals"] + sg["main_upper"]["signals"]
    (out / "data/signals.json").write_text(json.dumps({"_sections": True, "whole": {
        "schema": "schematic.signals/1", "source": "merged", "signals": sigs, "unplaced": []}}, indent=1))


def raise_cap(cap):
    """Wrap the plugin's orient with a fixed turnback cap: the plugin's search (its candidate filter
    on plans with more than 40 runs included) with only the cap changed."""
    from schematic import layout as L, orient as O

    def search(g, max_turnbacks=3, keep=10, require=(), log=None, seconds=None, **_):
        t = time.time()
        sw = [e for e in g["edges"] if all(g["nodes"][n]["kind"] in O.JUNCTION for n in (e["u"], e["v"]))]
        req = set(require)
        must = [e for e in sw if e["id"] in req]
        cand = [e for e in sw if not e["link"] and e["id"] not in req]
        if len(cand) > 40:
            cand = [e for e in cand if O.udot(g, e) > -0.5]
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


def limit_rows(seconds):
    """A time limit on the row search (fault F4), from a wrapper; the plugin's files are unchanged. Only the time
    spent inside the row optimisations counts. Once the limit has passed, each optimisation keeps the best
    arrangement it has and stops improving it."""
    from schematic import rows as R
    spent = [0.0]          # seconds spent inside Rows.optimise so far, this call's included from `entered`
    entered = [None]
    hit = []

    def late():
        now = spent[0] + (time.monotonic() - entered[0] if entered[0] is not None else 0.0)
        if now > seconds:
            if not hit:
                hit.append(1)
                print(f"one_band: row limit of {seconds} s reached; keeping the best rows found", file=sys.stderr)
            return True
        return False

    def optimise_from_here(self):
        self.tolerant = True

        def score(r):
            return (self.dropped, r["cost"] + self.broken())

        def flip(n):
            self.flat[n] = "C" if self.flat[n] == "B" else "B"

        best = self.solve()
        best_score = score(best)
        improved = True
        while improved and not late():
            improved = False
            for n in self.flat:
                if n in self.pins:
                    continue
                if late():
                    break
                flip(n)
                r = self.solve()
                sc = score(r)
                if sc[0] < best_score[0] or (sc[0] == best_score[0] and sc[1] < best_score[1] - 1e-9):
                    best, best_score, improved = r, sc, True
                else:
                    flip(n)
            if improved or late():
                continue
            pairs = {tuple(sorted((d["src"][0], d["dst"][0]))) for d in self.strands.values()
                     if d["src"][0] in self.flat and d["dst"][0] in self.flat}
            for a, b in sorted(pairs):
                if a in self.pins or b in self.pins:
                    continue
                if late():
                    break
                flip(a)
                flip(b)
                r = self.solve()
                sc = score(r)
                if sc[0] < best_score[0] or (sc[0] == best_score[0] and sc[1] < best_score[1] - 1e-9):
                    best, best_score, improved = r, sc, True
                    break
                flip(a)
                flip(b)
        self.dropped = best_score[0]
        return best

    optimise = R.Rows.optimise

    def timed_optimise(self):
        entered[0] = time.monotonic()
        try:
            return optimise(self)
        finally:
            spent[0] += time.monotonic() - entered[0]
            entered[0] = None

    R.Rows.optimise_from_here = optimise_from_here
    R.Rows.optimise = timed_optimise


TIMES = collections.defaultdict(float)
CALLS = collections.Counter()


def timed(owner, name, label):
    """Add the wall time of the outermost calls of owner.name to TIMES[label]."""
    fn = getattr(owner, name)
    depth = [0]

    def wrap(*args, **kw):
        depth[0] += 1
        t = time.monotonic()
        try:
            return fn(*args, **kw)
        finally:
            depth[0] -= 1
            if not depth[0]:
                TIMES[label] += time.monotonic() - t
                CALLS[label] += 1
    setattr(owner, name, wrap)


def time_phases():
    from schematic import layout as L, rows as R
    timed(L, "orient", "orient")
    timed(R.Rows, "optimise", "rows")
    timed(L, "place", "columns")


def loose_labels():
    """Layout Editor labels with no clean spot are listed and left out instead of stopping the panel (the plugin's
    own strict=False, which `le` does not offer)."""
    from schematic import le_labels as LL
    place = LL.place

    def loose(P, bands, opts, strict=True, **kw):
        out = place(P, bands, opts, strict=False, **kw)
        for _k, msg in P.labels_unplaced:
            print(f"one_band: left out: {P.text(msg)}", file=sys.stderr)
        try:            # strict=False skips the plugin's check of the placed labels: run it on what was placed
            LL.verify(P)
            print("one_band: the placed labels pass the label check", file=sys.stderr)
        except Exception as e:
            print(f"one_band: label check FAILED: {P.text(str(e))}", file=sys.stderr)
        return out
    LL.place = loose


class Stop(BaseException):  # not Exception: the plugin's `except Exception` must not swallow it
    pass


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--cap", type=int, help="turnback cap (wrapper; default: the plugin's own)")
    ap.add_argument("--seconds", type=int, help="stop the run after this many seconds")
    ap.add_argument("--row-seconds", type=int, help="time limit on the row search (wrapper; F4)")
    ap.add_argument("--panels", action="store_true",
                    help="also build the Layout Editor panel and the CATS desk from the same solve, each timed")
    ap.add_argument("--window", default="1920x1032", help="the CATS window (default the hosts' 1920x1032)")
    ap.add_argument("--profile", action="store_true", help="write cProfile stats to OUT/profile.txt")
    a = ap.parse_args(argv)
    if (a.cap is not None and a.cap < 0) or (a.seconds is not None and a.seconds < 1):
        ap.error("--cap must be 0 or more and --seconds 1 or more")
    # Always cold: the cache key cannot see the wrappers, and the results are timed cold. With --panels, a new empty
    # cache in OUT holds this run's solve so the panels reuse it; nothing else reads that folder.
    cache, mark = a.out / "cache", a.out / "cache" / ".one_band"
    if cache.exists():
        if not mark.exists():
            sys.exit(f"one_band: {cache} exists and this script did not make it; choose another OUT")
        import shutil
        shutil.rmtree(cache)
    if a.panels:
        cache.mkdir(parents=True)
        mark.touch()
    os.environ["SCHEMATIC_CACHE"] = str(cache) if a.panels else ""
    a.out.mkdir(parents=True, exist_ok=True)
    build(a.out)
    sys.path.insert(0, str(PLUGIN))
    from schematic import cli
    if a.cap is not None:
        raise_cap(a.cap)
    time_phases()           # after raise_cap, so the orientation it installs is the one timed
    if a.panels:
        loose_labels()
    if a.row_seconds is not None:
        limit_rows(a.row_seconds)
    if a.seconds is not None:
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
        TIMES["draw (whole command)"] = time.time() - t
        if a.panels and rc == 0:
            src = [str(x) for x in args[1:]]
            for label, cmd in (("le", ["le", str(a.out / "one_band_le.xml")] + src),
                               ("cats", ["cats", str(a.out / "one_band_cats.xml")] + src + ["--window", a.window])):
                t1, before = time.time(), dict(CALLS)
                rc = cli.run(cmd) or rc
                if CALLS != before:
                    print(f"one_band: {label} solved again (not from this run's cache); the phase totals include it",
                          file=sys.stderr)
                TIMES[label + " (whole command)"] = time.time() - t1
    except Stop:
        print(f"one_band: stopped at {a.seconds} s", file=sys.stderr)
    finally:
        signal.alarm(0)
        if prof:
            prof.disable()
            buf = io.StringIO()
            st = pstats.Stats(prof, stream=buf).sort_stats("cumulative")
            st.print_stats(60)
            st.sort_stats("tottime").print_stats(30)
            (a.out / "profile.txt").write_text(buf.getvalue())
        for k, v in TIMES.items():
            print(f"one_band: {k}: {v:.1f} s" + (f" ({CALLS[k]} calls)" if CALLS[k] else ""), file=sys.stderr)
        print(f"one_band: {time.time() - t:.1f} s, exit {rc}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
