"""schem.py <graph.json> <out.svg> [options.json]

Stage 0 spike: logical graph -> schematic on a whole-cell grid -> SVG.

Steps: orient (which way each switch faces, which runs are drawn as turnbacks),
sweep (top-to-bottom order of the tracks), rows, columns, draw.
"""
import collections
import itertools
import json
import math
import sys

TAU = {"A": -1, "B": 1, "C": 1, "D": -1}
JUNCTION = ("switch", "dx")
TURN_SIGN = 1


# ---------------------------------------------------------------- orient
def colour(g, sw_edges, T):
    sig = {}
    adj = collections.defaultdict(list)
    for e in sw_edges:
        r = (1 if e["id"] in T else -1) * TAU[e["up"]] * TAU[e["vp"]]
        adj[e["u"]].append((e["v"], r))
        adj[e["v"]].append((e["u"], r))
    for start in (n for n, d in g["nodes"].items() if d["kind"] in JUNCTION):
        if start in sig:
            continue
        sig[start] = 1
        todo = [start]
        while todo:
            u = todo.pop()
            for v, r in adj[u]:
                if v not in sig:
                    sig[v] = r * sig[u]
                    todo.append(v)
                elif sig[v] != r * sig[u]:
                    return None
    return sig


def build(g, sig, T):
    """Strands (drawn pieces of track) and the left-to-right graph."""
    nodes = {n: dict(d, ins={}, outs={}) for n, d in g["nodes"].items()}
    strands = {}

    def side(n, p):
        return sig[n] * TAU[p] if nodes[n]["kind"] in JUNCTION else None

    def add(sid, src, dst, e, name):
        strands[sid] = dict(src=src, dst=dst, edge=e["id"], ends=(e["u"], e["v"]), name=name, cm=e["cm"],
                            main=e["main"], link=e["link"], hidden=e.get("hidden", False))
        nodes[src[0]]["outs"][src[1]] = sid
        nodes[dst[0]]["ins"][dst[1]] = sid

    for e in g["edges"]:
        u, v = (e["u"], e["up"]), (e["v"], e["vp"])
        su, sv = side(*u), side(*v)
        names = tidy(e["names"])
        if su is None and sv is None:
            raise SystemExit("edge between two track ends")
        if su is None:
            su = -sv
        if sv is None:
            sv = -su
        if su != sv:
            a, b = (u, v) if su == 1 else (v, u)
            add(e["id"], a, b, e, " / ".join(names))
        else:
            t = "turn:" + e["id"]
            nodes[t] = dict(kind="turnR" if su == 1 else "turnL", ins={}, outs={}, label="")
            n0 = names[0] if names else ""
            n1 = names[-1] if len(names) > 1 else ""
            if su == 1:
                add(e["id"] + ".0", u, (t, 0), e, n0)
                add(e["id"] + ".1", v, (t, 1), e, n1)
            else:
                add(e["id"] + ".0", (t, 0), u, e, n0)
                add(e["id"] + ".1", (t, 1), v, e, n1)
    for n, d in nodes.items():
        d["sig"] = sig.get(n, 0)
    return nodes, strands


def tidy(names):
    """Block names to track names: drop "Track ", and "S-4 East" when "S-4" is there too."""
    short = [n[6:] if n.startswith("Track ") else n for n in names]
    out = []
    for n in short:
        base = n.rsplit(" ", 1)[0] if n.endswith((" East", " West")) else n
        n = base if base in short else n
        if n not in out:
            out.append(n)
    return out


def columns(nodes, strands):
    """Longest-path column per node, or None when the left-to-right graph has a cycle."""
    indeg = {n: len(d["ins"]) for n, d in nodes.items()}
    col = {n: 0 for n in nodes}
    todo = [n for n, k in indeg.items() if k == 0]
    seen = 0
    while todo:
        n = todo.pop()
        seen += 1
        for sid in nodes[n]["outs"].values():
            m = strands[sid]["dst"][0]
            col[m] = max(col[m], col[n] + 1)
            indeg[m] -= 1
            if indeg[m] == 0:
                todo.append(m)
    return col if seen == len(nodes) else None


def udot(g, e):
    du = g["nodes"][e["u"]].get("dirs", {}).get(e["up"])
    dv = g["nodes"][e["v"]].get("dirs", {}).get(e["vp"])
    return du[0] * dv[0] + du[1] * dv[1] if du and dv else 0.0


def orient(g, max_turnbacks=3, keep=10):
    """The cheapest ways to face every switch, best first: (facing, turnback edges)."""
    sw = [e for e in g["edges"] if all(g["nodes"][n]["kind"] in JUNCTION for n in (e["u"], e["v"]))]
    cand = [e for e in sw if not e["link"]]
    if len(cand) > 40:      # big plan: only runs that bend back on the layout may be turnbacks
        cand = [e for e in cand if udot(g, e) > -0.5]
        max_turnbacks = 5
    best, found = None, []
    for k in range(max_turnbacks + 1):
        for T in itertools.combinations(cand, k):
            ids = {e["id"] for e in T}
            sig = colour(g, sw, ids)
            if sig is None:
                continue
            nodes, strands = build(g, sig, ids)
            col = columns(nodes, strands)
            if col is None:
                continue
            width = max(col.values())
            cost = 10 * k + 0.2 * width
            for e in T:
                cost += 6 * (1 - udot(g, e))   # a turnback should be a U-turn on the layout too
            found.append((cost, sorted(ids), sig, ids))
            if best is None or cost < best[0] - 1e-9:
                best = (cost, sig, ids)
        if best is not None and k > len(best[2]):
            break
    if best is None:
        raise SystemExit("no orientation found; raise max_turnbacks")
    found.sort(key=lambda f: (f[0], f[1]))
    return [(sig, ids) for _, _, sig, ids in found[:keep]]


# ---------------------------------------------------------------- sweep
def legs(nodes, n):
    """(upper strand, lower strand) of the frog side of switch n, in screen terms."""
    d = nodes[n]
    side = d["outs"] if d["sig"] == 1 else d["ins"]
    b, c = side["B"], side["C"]
    c_low = (d["hand"] == 1) == (d["sig"] == 1)
    return (b, c) if c_low else (c, b)


def dx_tracks(nodes, n):
    """Double crossover: ((upper in, upper out), (lower in, lower out))."""
    d = nodes[n]
    if d["sig"] == 1:
        ab, dc = (d["ins"]["A"], d["outs"]["B"]), (d["ins"]["D"], d["outs"]["C"])
    else:
        ab, dc = (d["ins"]["B"], d["outs"]["A"]), (d["ins"]["C"], d["outs"]["D"])
    return (ab, dc) if (d["hand"] == 1) == (d["sig"] == 1) else (dc, ab)


def sweep(nodes, strands, col, warn):
    L, alive, done, snaps, enclosed, free, ev = [], set(), set(), [], {}, set(), {}

    def snap():
        snaps.append([s for s in L if s in alive])

    def where(hint):
        if hint is None:
            return len(L)
        i = L.index(hint[0])
        return i if hint[1] == "above" else i + 1

    def process(n, hint=None):
        d = nodes[n]
        k = d["kind"]
        if k == "switch" and d["sig"] == 1:
            a = d["ins"]["A"]
            up, lo = legs(nodes, n)
            i = L.index(a)
            alive.discard(a)
            L[i:i + 1] = [up, a, lo]
            alive.update((up, lo))
        elif k == "switch":
            up, lo = legs(nodes, n)
            iu, il = L.index(up), L.index(lo)
            if iu > il or any(s in alive for s in L[min(iu, il) + 1:max(iu, il)]):
                # the layout is not flat here (one track passes over another): let the shorter leg cross
                f = min((up, lo), key=lambda s: strands[s]["cm"])
                free.add(f)
                warn(f"switch {d['label']}: one leg has to cross other track to reach it")
                iu, il = min(iu, il), max(iu, il)
            alive.difference_update((up, lo))
            L.insert(il, d["outs"]["A"])
            alive.add(d["outs"]["A"])
        elif k == "dx":
            (iu_, ou), (il_, ol) = dx_tracks(nodes, n)
            if L.index(iu_) > L.index(il_):
                warn(f"double crossover {d['label']}: tracks arrive in the opposite order")
                (iu_, ou), (il_, ol) = (il_, ol), (iu_, ou)
            if any(s in alive for s in L[L.index(iu_) + 1:L.index(il_)]):
                warn(f"double crossover {d['label']}: a track lies between its two tracks")
            alive.difference_update((iu_, il_))
            L.insert(L.index(il_), ol)
            L.insert(L.index(iu_) + 1, ou)
            alive.update((ou, ol))
        elif k == "end" and d["outs"]:
            s = d["outs"]["E"]
            L.insert(where(hint), s)
            alive.add(s)
        elif k == "end":
            alive.discard(d["ins"]["E"])
        elif k == "turnL":
            s0, s1 = d["outs"][0], d["outs"][1]
            want = hint[2] if hint and len(hint) > 2 else s0
            other = s1 if want == s0 else s0
            if hint is None:        # nothing to sit beside: take the order from which way the loop bends on the layout
                (u, pu), (v, _) = strands[s0]["dst"], strands[s1]["dst"]
                du = nodes[u].get("dirs", {}).get(pu)
                if du and "xy" in nodes[u] and "xy" in nodes[v]:
                    px, py = TURN_SIGN * -du[1], TURN_SIGN * du[0]
                    if nodes[v]["xy"][0] * px + nodes[v]["xy"][1] * py > nodes[u]["xy"][0] * px + nodes[u]["xy"][1] * py:
                        want, other = s1, s0
            pair = [want, other] if (hint is None or hint[1] == "below") else [other, want]
            i = where(hint)
            L[i:i] = pair
            alive.update(pair)
        elif k == "turnR":
            i0, i1 = sorted((L.index(d["ins"][0]), L.index(d["ins"][1])))
            inside = [s for s in L[i0 + 1:i1] if s in alive]
            if inside:
                warn(f"turnback {n}: tracks still open inside it")
            enclosed[n] = [s for s in L[i0 + 1:i1]]
            alive.difference_update(d["ins"].values())
        ev[n] = len(done)
        done.add(n)
        snap()

    def demand(s, hint):
        p = strands[s]["src"][0]
        d = nodes[p]
        if p in done:
            return
        if d["kind"] == "end":
            process(p, hint)
        elif d["kind"] == "turnL":
            process(p, (hint[0], hint[1], s))
        elif d["kind"] == "switch" and d["sig"] == 1:
            if d["ins"]["A"] not in alive:
                demand(d["ins"]["A"], hint)
            process(p)
        else:
            up, lo = legs(nodes, p) if d["kind"] == "switch" else [t[0] for t in dx_tracks(nodes, p)]
            have = [x for x in (up, lo) if x in alive]
            if not have:
                demand(up, hint)
                have = [up]
            if up not in alive:
                demand(up, (lo, "above"))
            if lo not in alive:
                demand(lo, (up, "below"))
            process(p)

    def prio(n):
        d = nodes[n]
        if d["kind"] == "end":
            return (0, col[n])
        if d["kind"] == "turnR":
            i0, i1 = sorted((L.index(d["ins"][0]), L.index(d["ins"][1])))
            return (1 if not any(s in alive for s in L[i0 + 1:i1]) else 9, col[n])
        return (2 if d["sig"] == -1 or d["kind"] == "dx" else 3, col[n])

    while len(done) < len(nodes):
        ready = [n for n, d in nodes.items() if n not in done and d["ins"]
                 and all(s in alive for s in d["ins"].values())]
        if ready:
            process(min(ready, key=prio))
            continue
        part = [n for n, d in nodes.items() if n not in done and d["ins"]
                and any(s in alive for s in d["ins"].values())]
        if part:
            n = min(part, key=lambda n: col[n])
            d = nodes[n]
            if d["kind"] == "turnR":
                have = next(s for s in d["ins"].values() if s in alive)
                miss = next(s for s in d["ins"].values() if s not in alive)
                demand(miss, (have, "below"))
            else:
                up, lo = legs(nodes, n) if d["kind"] == "switch" else [t[0] for t in dx_tracks(nodes, n)]
                if up in alive:
                    demand(lo, (up, "below"))
                else:
                    demand(up, (lo, "above"))
            continue
        src = [n for n, d in nodes.items() if n not in done and not d["ins"]]
        process(min(src, key=lambda n: -sum(strands[s]["cm"] for s in nodes[n]["outs"].values())))
    return L, snaps, enclosed, free, ev


# ---------------------------------------------------------------- rows
def spine_path(nodes, strands, col):
    """Heaviest left-to-right path: the main line."""
    order = sorted(nodes, key=lambda n: col[n])
    best = {n: (0.0, []) for n in nodes}
    for n in order:
        for sid in nodes[n]["outs"].values():
            s = strands[sid]
            w = (s["cm"] or 30.0) * (4 if s["main"] else 1)
            m = s["dst"][0]
            if best[n][0] + w > best[m][0]:
                best[m] = (best[n][0] + w, best[n][1] + [sid])
    return max(best.values(), key=lambda b: b[0])[1]


def descend(start, items, push, cost):
    """Local search: move one item a step, pushing whatever it would collide with; keep it if cheaper."""
    cur, best = start, cost(start)
    improved = True
    while improved:
        improved = False
        for it in items:
            for step in (1, -1):
                new = push(cur, it, step)
                c = cost(new)
                if c < best - 1e-9:
                    cur, best, improved = new, c, True
    return cur, best


def find_cycle(classes, above):
    """One directed cycle as a list of (from, to), or None."""
    state, stack = {}, []

    def visit(c):
        state[c] = 1
        stack.append(c)
        for d in sorted(above[c]):
            if state.get(d) == 1:
                i = stack.index(d)
                path = stack[i:] + [d]
                return list(zip(path, path[1:]))
            if d not in state:
                r = visit(d)
                if r:
                    return r
        stack.pop()
        state[c] = 2
        return None

    for c in classes:
        if c not in state:
            r = visit(c)
            if r:
                return r
    return None


class Rows:
    def __init__(self, nodes, strands, snaps, free=(), pins=None, close=()):
        self.nodes, self.strands, self.snaps, self.free = nodes, strands, snaps, set(free)
        # owner's hints: which leg of a switch runs level, by switch label or plan part number
        find_ref = lambda ref: [n for n, d in nodes.items() if d["kind"] == "switch"
                                and ref in (d.get("alias"), d.get("label"))]
        # owner's hints: pairs of switches to keep on neighbouring rows
        self.close = [(a[0], b[0]) for a, b in ((find_ref(p), find_ref(q)) for p, q in close) if a and b]
        self.pins = {n: port for n, d in nodes.items() if d["kind"] == "switch"
                     for ref, port in (pins or {}).items() if ref in (d.get("alias"), d.get("label"))}
        self.extra = set()
        self.flat = {n: "B" for n, d in nodes.items() if d["kind"] == "switch"}
        self.tolerant = bool(free)
        self.dropped = 0

    def frog(self, n):
        d = self.nodes[n]
        return d["outs"] if d["sig"] == 1 else d["ins"]

    def a_strand(self, n):
        d = self.nodes[n]
        return (d["ins"] if d["sig"] == 1 else d["outs"])["A"]

    def sloped(self, sid, end):
        n, p = self.strands[sid][end]
        return self.nodes[n]["kind"] == "switch" and p in "BC" and self.flat[n] != p

    def solve(self):
        st = self.strands
        parent = {s: s for s in st}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for n, f in self.flat.items():
            parent[find(self.a_strand(n))] = find(self.frog(n)[f])
        for n, d in self.nodes.items():
            if d["kind"] == "dx":
                for a, b in dx_tracks(self.nodes, n):
                    parent[find(a)] = find(b)
        diag = {s for s, d in st.items() if self.sloped(s, "src") and self.sloped(s, "dst")
                and (d["link"] or (not d["name"] and d["cm"] < 40))}
        above = collections.defaultdict(set)
        pairs = set(self.extra)
        for snap in self.snaps:
            row = [s for s in snap if s not in diag and s not in self.free]
            pairs.update(zip(row, row[1:]))
        self.dropped = 0
        for a, b in pairs:
            if a in diag or b in diag:
                continue
            ca, cb = find(a), find(b)
            if ca == cb:
                if not self.tolerant:
                    return None
                self.dropped += 1
                continue
            above[ca].add(cb)
        classes = sorted({find(s) for s in st if s not in diag})
        while self.tolerant:            # break "A over B over ... over A" loops, one rule at a time
            cyc = find_cycle(classes, above)
            if not cyc:
                break
            a, b = cyc[0]
            above[a].discard(b)
            self.dropped += 1
        below = collections.defaultdict(set)
        indeg = {c: 0 for c in classes}
        for c in classes:
            for d in above[c]:
                indeg[d] += 1
                below[d].add(c)
        row = {c: 0 for c in classes}
        todo = [c for c in classes if indeg[c] == 0]
        seen = 0
        while todo:
            c = todo.pop()
            seen += 1
            for d in above[c]:
                row[d] = max(row[d], row[c] + 1)
                indeg[d] -= 1
                if indeg[d] == 0:
                    todo.append(d)
        if seen != len(classes):
            return None
        terms = []                      # (class, class, weight): slope length between two rows
        for n, f in self.flat.items():
            s = self.frog(n)["C" if f == "B" else "B"]
            me = find(self.a_strand(n))
            if s in diag:
                o = st[s]["src"][0] if st[s]["dst"][0] == n else st[s]["dst"][0]
                terms.append((me, find(self.a_strand(o)), 0.5))
            else:
                terms.append((me, find(s), 1.0))
        for a, b in self.close:
            terms.append((find(self.a_strand(a)), find(self.a_strand(b)), 5.0))
        for n, d in self.nodes.items():     # a double crossover wants its two tracks on neighbouring rows
            if d["kind"] == "dx":
                (a, _), (b, _) = dx_tracks(self.nodes, n)
                terms.append((find(a), find(b), 9.0))
        bias = 0.0
        for n, f in self.flat.items():      # a long track should run level and the short link slope
            level = st[self.frog(n)[f]]["cm"]
            other = st[self.frog(n)["C" if f == "B" else "B"]]["cm"]
            bias += (0.2 if other > 2 * level + 20 else 0.0) + (0.01 if f == "C" else 0.0)

        def cost(r):
            return (sum(w * abs(r[a] - r[b]) for a, b, w in terms) + bias
                    + 0.3 * (max(r.values()) - min(r.values())))

        def push(r, c, step):
            new = dict(r)
            new[c] += step
            todo = [c]
            while todo:
                k = todo.pop()
                if step > 0:
                    for d in above[k]:
                        if new[d] < new[k] + 1:
                            new[d] = new[k] + 1
                            todo.append(d)
                else:
                    for d in below[k]:
                        if new[d] > new[k] - 1:
                            new[d] = new[k] - 1
                            todo.append(d)
            return new

        row, c = descend(row, classes, push, cost)
        lo = min(row.values())
        srow = {s: row[find(s)] - lo for s in st if s not in diag}
        nrow = {}
        for n, d in self.nodes.items():
            if d["kind"] == "switch":
                nrow[n] = srow[self.a_strand(n)]
            elif d["kind"] == "end":
                nrow[n] = srow[next(iter(list(d["ins"].values()) + list(d["outs"].values())))]
        return dict(srow=srow, nrow=nrow, diag=diag, cost=c)

    def optimise(self):
        """Best of several starts, since the step-by-step search can stop at a poor arrangement."""
        import random
        rng = random.Random(7)
        keys = sorted(self.flat)
        starts = [dict(self.flat), {n: "B" for n in keys}, {n: "C" for n in keys}]
        starts += [{n: rng.choice("BC") for n in keys} for _ in range(5)]
        for st_ in starts:
            st_.update(self.pins)
        best = None
        for start in starts:
            self.flat = dict(start)
            r = self.optimise_from_here()
            sc = (self.dropped, r["cost"])
            if best is None or sc < best[0]:
                best = (sc, r, dict(self.flat))
        self.flat = best[2]
        self.dropped = best[0][0]
        return best[1]

    def optimise_from_here(self):
        """Choose each switch's level leg: first so that no above/below rule is broken, then for short slopes."""
        self.tolerant = True

        def score(r):
            return (self.dropped, r["cost"])

        best = self.solve()
        best_score = score(best)
        improved = True
        while improved:
            improved = False
            for n in self.flat:
                if n in self.pins:
                    continue
                self.flat[n] = "C" if self.flat[n] == "B" else "B"
                r = self.solve()
                sc = score(r)
                if sc[0] < best_score[0] or (sc[0] == best_score[0] and sc[1] < best_score[1] - 1e-9):
                    best, best_score, improved = r, sc, True
                else:
                    self.flat[n] = "C" if self.flat[n] == "B" else "B"
            if improved:
                continue
            # stuck on single changes: try two neighbouring switches together
            pairs = {tuple(sorted((d["src"][0], d["dst"][0]))) for d in self.strands.values()
                     if d["src"][0] in self.flat and d["dst"][0] in self.flat}
            for a, b in sorted(pairs):
                if a in self.pins or b in self.pins:
                    continue
                for n in (a, b):
                    self.flat[n] = "C" if self.flat[n] == "B" else "B"
                r = self.solve()
                sc = score(r)
                if sc[0] < best_score[0] or (sc[0] == best_score[0] and sc[1] < best_score[1] - 1e-9):
                    best, best_score, improved = r, sc, True
                    break
                for n in (a, b):
                    self.flat[n] = "C" if self.flat[n] == "B" else "B"
        self.dropped = best_score[0]
        return best


# ---------------------------------------------------------------- columns
def name_cells(name, opts):
    return 0 if not name else math.ceil((len(name) * opts["name_px"] * 0.62 + 10) / opts["cell"])


class Unsettled(Exception):
    pass


def place(nodes, strands, R, enclosed, opts, extra=()):
    srow, nrow, diag = R["srow"], R["nrow"], R["diag"]
    cons, need, weight = [], {}, []
    for sid, s in strands.items():
        u, v = s["src"][0], s["dst"][0]
        if sid in diag:
            w = abs(nrow[u] - nrow[v])
            cons += [(u, v, w), (v, u, -w)]
            need[sid] = (0, 0, w)
            continue
        su = abs(srow[sid] - nrow[u]) if u in nrow else 0
        sv = abs(srow[sid] - nrow[v]) if v in nrow else 0
        h = max(name_cells(s["name"], opts), min(4, int(s["cm"] // 120)))   # a long track shows as a level run
        ends_ = {r for t in (u, v) for r in (nodes[t].get("alias"), nodes[t].get("label")) if r}
        tight = any(a in ends_ and b in ends_ for a, b in opts.get("shorten", ()))     # owner's hint: draw this run short
        if tight:
            h = 0
        refs = lambda n: {nodes[n].get("alias"), nodes[n].get("label")} - {None}
        for a, b, cells in opts.get("min_cells", ()):       # owner's hint: give this run at least so many cells
            e0, e1 = s["ends"]
            if (a in refs(e0) and b in refs(e1)) or (a in refs(e1) and b in refs(e0)):
                if "." not in sid or b in refs(u) | refs(v):  # of a folded run, the half that reaches b
                    h = max(h, cells)
        if nodes[u]["kind"] == "end" or nodes[v]["kind"] == "end":
            h = max(h, 1) + 1
        if nodes[u].get("sub") == "link" or nodes[v].get("sub") == "link":
            h, tight = 1, True          # a connector gets one short level cell, never more
        w = max(1, su + sv + h) + sum(nodes[t]["kind"] == "dx" for t in (u, v))
        need[sid] = (su, sv, w)
        cons.append((u, v, w))
        cm = s["cm"] / (2 if "." in sid else 1)
        weight.append((u, v, 20.0 if tight else 100.0 / (cm + 25.0)))     # long tracks take up the slack
    for t, inside in enclosed.items():
        for sid in inside:
            n = strands[sid]["dst"][0]
            cons.append((n, t, 4 if nodes[n].get("sub") == "helix" else 1))     # room for the helix box
    cons += list(extra)
    fwd, back = collections.defaultdict(list), collections.defaultdict(list)
    for u, v, w in cons:
        fwd[u].append((v, w))
        back[v].append((u, w))
    x = {n: 0 for n in nodes}
    for _ in range(4 * len(nodes) + 10):
        changed = False
        for u, v, w in cons:
            if x[v] < x[u] + w:
                x[v], changed = x[u] + w, True
        if not changed:
            break
    else:
        raise Unsettled("columns: constraints do not settle")

    def cost(xs):
        return sum(w * (xs[v] - xs[u]) for u, v, w in weight)

    def push(xs, n, step):
        new = dict(xs)
        new[n] += step
        todo = [n]
        while todo:
            k = todo.pop()
            if step > 0:
                for v, w in fwd[k]:
                    if new[v] < new[k] + w:
                        new[v] = new[k] + w
                        todo.append(v)
            else:
                for u, w in back[k]:
                    if new[u] > new[k] - w:
                        new[u] = new[k] - w
                        todo.append(u)
        return new

    x, _ = descend(x, sorted(nodes), push, cost)
    return x, need


def overlaps(nodes, strands, R, x, need, order):
    rank = {s: i for i, s in enumerate(order)}
    spans = []
    for sid, s in strands.items():
        if sid in R["diag"]:
            continue
        su, sv, _ = need[sid]
        room = lambda n: 1 if nodes[n].get("sub") in ("link", "helix") else 0     # a connector circle needs a cell
        spans.append((R["srow"][sid], x[s["src"][0]] + su - room(s["src"][0]),
                      x[s["dst"][0]] - sv + room(s["dst"][0]), sid))
    found = set()
    for (r1, a1, b1, s1), (r2, a2, b2, s2) in itertools.combinations(spans, 2):
        if r1 == r2 and a1 < b2 and a2 < b1:
            found.add((s1, s2) if rank[s1] < rank[s2] else (s2, s1))
    return found


# ---------------------------------------------------------------- edits, levels
def by_label(g, ref):
    """A junction by its plan part number (kept as alias) or its label."""
    hits = [n for n, d in g["nodes"].items() if d.get("alias") == ref]
    hits = hits or [n for n, d in g["nodes"].items() if d.get("label") == ref and d["kind"] != "end"]
    if len(hits) != 1:
        raise SystemExit(f"{len(hits)} junctions answer to {ref}")
    return hits[0]


def edge_at(g, n, port):
    return next(e for e in g["edges"] if (e["u"], e["up"]) == (n, port) or (e["v"], e["vp"]) == (n, port))


def far(e, n, port):
    return (e["v"], e["vp"]) if (e["u"], e["up"]) == (n, port) else (e["u"], e["up"])


def edge_between(g, a, b, port=None):
    n0, n1 = by_label(g, a), by_label(g, b)
    hits = [e for e in g["edges"] if {e["u"], e["v"]} == {n0, n1}
            and (port is None or (e["u"], e["up"]) == (n0, port) or (e["v"], e["vp"]) == (n0, port))]
    if not hits:
        raise SystemExit(f"no track between {a} and {b}")
    return max(hits, key=lambda e: e["cm"]), n0, n1


def lift(g, x, p1, p2):
    """Take switch x out of the run through ports p1 and p2, leaving plain track there."""
    e1, e2 = edge_at(g, x, p1), edge_at(g, x, p2)
    a, b = far(e1, x, p1), far(e2, x, p2)
    g["edges"] = [e for e in g["edges"] if e is not e1 and e is not e2]
    g["edges"].append(dict(e1, id=e1["id"] + "+" + e2["id"], u=a[0], up=a[1], v=b[0], vp=b[1],
                           cm=round(e1["cm"] + e2["cm"], 1), names=e1["names"] or e2["names"]))


def set_in(g, x, t, n0, cm_from_first, points_toward_first, names=(None, None)):
    """Set switch x into track t (between n0 and its other end): A toward one end, B toward the other."""
    end0 = (t["u"], t["up"]) if t["u"] == n0 else (t["v"], t["vp"])
    end1 = (t["v"], t["vp"]) if t["u"] == n0 else (t["u"], t["up"])
    at = max(5.0, min(cm_from_first, t["cm"] - 5))
    g["edges"].remove(t)
    p0, p1 = ("A", "B") if points_toward_first else ("B", "A")
    g["edges"].append(dict(t, id=t["id"] + "a", u=end0[0], up=end0[1], v=x, vp=p0, cm=round(at, 1),
                           names=[names[0]] if names[0] else t["names"]))
    g["edges"].append(dict(t, id=t["id"] + "b", u=x, up=p1, v=end1[0], vp=end1[1], cm=round(t["cm"] - at, 1),
                           names=[names[1]] if names[1] else t["names"]))


def new_switch(g, label, alias, hand):
    nid = "NEW:" + alias
    g["nodes"][nid] = dict(kind="switch", label=label, alias=alias, hand=1 if hand == "R" else -1,
                           dirs={"A": [-1.0, 0.0], "B": [1.0, 0.0], "C": [1.0, 0.0]})
    return nid


def grow(g, n, port, spec, template, count=[0]):
    """Build what hangs off a new switch's leg: a track end, or another switch with its own legs."""
    count[0] += 1
    if "end" in spec:
        end = f"END:new{count[0]}"
        g["nodes"][end] = dict(kind="end", sub=spec.get("sub", "bumper"), label="")
        g["edges"].append(dict(template, id=f"n{count[0]}", u=n, up=port, v=end, vp="E", names=[spec["end"]],
                               cm=spec.get("cm", 60.0), link=False, main=False))
        return
    x = new_switch(g, spec["switch"], spec.get("alias", spec["switch"]), spec["hand"])
    g["edges"].append(dict(template, id=f"n{count[0]}", u=n, up=port, v=x, vp="A", names=[], cm=25.0,
                           link=False, main=False))
    grow(g, x, "B", spec["b"], template)
    grow(g, x, "C", spec["c"], template)


def apply_edits(g, edits):
    """As-built changes and names on top of the plan."""
    N = g["nodes"]
    for ed in edits:
        op = ed["op"]
        if op == "relabel":         # plan part number -> the railroad's switch number
            for old, new in ed["map"].items():
                n = by_label(g, old)
                N[n]["alias"], N[n]["label"] = old, new
        elif op == "remove":        # switches that were not built: their straight route stays as track
            gone = [by_label(g, r) for r in ed["switches"]]
            for x in gone:
                c = next((e for e in g["edges"] if (e["u"], e["up"]) == (x, "C") or (e["v"], e["vp"]) == (x, "C")), None)
                if c is not None:
                    g["edges"].remove(c)
                    o = far(c, x, "C")[0]
                    if N[o]["kind"] == "end":
                        del N[o]
            for x in gone:
                lift(g, x, "A", "B")
                del N[x]
        elif op == "move":          # lift a switch out of one run and set it into another
            x = by_label(g, ed["switch"])
            p1, p2 = ed["through"]
            leg = next(p for p in "ABC" if p not in (p1, p2))
            e3 = edge_at(g, x, leg)
            lift(g, x, p1, p2)
            if (e3["u"], e3["up"]) == (x, leg):
                e3["up"] = "C"
            else:
                e3["vp"] = "C"
            t, n0, _ = edge_between(g, *ed["onto"])
            set_in(g, x, t, n0, ed["cm_from_first"], False)
            d = N[x]
            d["hand"] = {"R": 1, "L": -1}.get(ed.get("hand"), d["hand"])
            d["z"] = ed.get("z", d.get("z"))
            d["dirs"] = {"A": [-1.0, 0.0], "B": [1.0, 0.0], "C": [1.0, 0.0]}
            d["label"] += "*"
        elif op == "switch":        # a switch that is not in the plan, with whatever hangs off its diverging leg
            x = new_switch(g, ed["label"], ed.get("alias", ed["label"]), ed["hand"])
            t, n0, _ = edge_between(g, *ed["on"], ed.get("port"))
            set_in(g, x, t, n0, ed["cm_from_first"], ed["points_toward"] == ed["on"][0], ed.get("names", (None, None)))
            grow(g, x, "C", ed["c"], t)
        elif op == "crossover":     # two new switches joined by their diverging legs
            ids = []
            for k, side in enumerate(ed["sides"]):
                x = new_switch(g, ed["label"], ed["label"] + "ab"[k], ed["hand"])
                t, n0, _ = edge_between(g, *side["on"], side.get("port"))
                set_in(g, x, t, n0, side["cm_from_first"], side["points_toward"] == side["on"][0],
                       side.get("names", (None, None)))
                ids.append(x)
            g["edges"].append(dict(id="x" + ed["label"], u=ids[0], up="C", v=ids[1], vp="C", names=[], cm=0.0,
                                   main=False, link=True))
        elif op == "name":          # track names, and which tracks are main
            for a, b, name, *rest in ed["tracks"]:
                t, n0, _ = edge_between(g, a, b, rest[0] if rest and rest[0] in "ABC" else None)
                names = name if isinstance(name, list) else ([name] if name else [])
                t["names"] = names if t["u"] == n0 else names[::-1]
                t["main"] = "main" in rest
        elif op == "end":           # what a track end is: found from the switch and port it hangs off
            for ref, port, name, sub, to in ed["ends"]:
                n = by_label(g, ref)
                t = edge_at(g, n, port)
                e = far(t, n, port)[0]
                t["names"], t["main"] = [name], sub == "helix"
                N[e].update(sub=sub, to=to)
        else:
            raise SystemExit(f"unknown edit {op}")


def mark_main(g, routes):
    """Main track is what lies on the given routes (shortest way between each pair); everything else is secondary."""
    import heapq
    N = g["nodes"]

    def node(ref):
        for e in g["edges"]:
            for n in (e["u"], e["v"]):
                if N[n]["kind"] == "end" and (ref in e["names"] or N[n].get("label") == ref):
                    return n
        return by_label(g, ref)

    adj = collections.defaultdict(list)
    for e in g["edges"]:
        adj[e["u"]].append((e["v"], e))
        adj[e["v"]].append((e["u"], e))
        e["main"] = False
    for a, b, *how in routes:
        a, b = node(a), node(b)
        if how:                 # "direct": every track that runs straight between the two, however long
            for e in g["edges"]:
                if {e["u"], e["v"]} == {a, b}:
                    e["main"] = True
            continue
        dist, prev, heap = {a: 0.0}, {}, [(0.0, a)]
        while heap:
            d, n = heapq.heappop(heap)
            if n == b:
                break
            if d > dist[n]:
                continue
            for m, e in adj[n]:
                nd = d + e["cm"] + 1
                if nd < dist.get(m, 1e18):
                    dist[m], prev[m] = nd, (n, e)
                    heapq.heappush(heap, (nd, m))
        while b in prev:
            b, e = prev[b]
            e["main"] = True


def split_levels(g, spec):
    """Cut every run that joins two levels; each cut end becomes a lettered connector."""
    N = g["nodes"]
    z = {n: d.get("z") for n, d in N.items() if d["kind"] != "end"}
    for ref, to in spec.get("assign", {}).items():      # owner's choice of band for a junction
        z[by_label(g, ref)] = to
    for lo, hi, to in spec.get("treat", []):
        for n, v in z.items():
            if v is not None and lo <= v < hi:
                z[n] = to
    while any(v is None for v in z.values()):       # unknown height: take the nearest neighbour's
        progress = False
        for e in sorted(g["edges"], key=lambda e: e["cm"]):
            for a, b in ((e["u"], e["v"]), (e["v"], e["u"])):
                if a in z and b in z and z[a] is None and z[b] is not None:
                    z[a], progress = z[b], True
        if not progress:
            break
    names = spec["bands"]
    level = {n: next(i for i, b in enumerate(names) if (v if v is not None else 0) < b["below"]) for n, v in z.items()}
    letters = iter("ABCDEFGHJKLMNPQRSTUVWXYZ")
    for e in list(g["edges"]):
        if e["u"] in level and e["v"] in level and level[e["u"]] != level[e["v"]]:
            L = next(letters)
            g["edges"].remove(e)
            for k, (n, p) in enumerate(((e["u"], e["up"]), (e["v"], e["vp"]))):
                end = f"LINK:{L}{k}"
                other = e["v"] if k == 0 else e["u"]
                N[end] = dict(kind="end", sub="link", label=L, to=names[level[other]]["name"].split(",")[0])
                g["edges"].append(dict(e, id=f"{e['id']}{'xy'[k]}", u=n, up=p, v=end, vp="E", cm=round(e["cm"] / 2, 1)))
    parent = {n: n for n in N}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in g["edges"]:
        parent[find(e["u"])] = find(e["v"])
    groups = collections.defaultdict(list)
    for n in N:
        groups[find(n)].append(n)
    bands = []
    for members in groups.values():
        lv = collections.Counter(level[n] for n in members if n in level).most_common(1)[0][0]
        keep = set(members)
        bands.append((lv, len(members), names[lv]["name"],
                      dict(nodes={n: N[n] for n in members}, edges=[e for e in g["edges"] if e["u"] in keep])))
    bands.sort(key=lambda b: (b[0], -b[1]))
    return [(name, sub) for _, _, name, sub in bands]


# ---------------------------------------------------------------- lay out one band
def layout(g, opts, warnings):
    """Try the cheapest few orientations and keep the drawing with the fewest faults."""
    best = None
    for sig, T in orient(g):
        w = []
        band = layout_one(g, sig, T, opts, w)
        score = (len(faults(band)) + 3 * len(w), len(T))
        if best is None or score < best[0]:
            best = (score, band, w)
        if score[0] == 0:
            break
    warnings.extend(best[2])
    return best[1]


def layout_one(g, sig, T, opts, warnings):
    nodes, strands = build(g, sig, T)
    col = columns(nodes, strands)
    if opts["left_end"]:
        hit = [e for e in g["edges"] if opts["left_end"] in e["names"]]
        if hit and col[hit[0]["v"]] > max(col.values()) / 2:
            sig = {n: -s for n, s in sig.items()}
            nodes, strands = build(g, sig, T)
            col = columns(nodes, strands)
    sided = [(d["side"], bool(d["outs"])) for d in nodes.values() if d["kind"] == "end" and d.get("side")]
    wrong = sum((side == "west") != starts for side, starts in sided)     # an end marked west should be a left-hand start
    if sided and wrong * 2 > len(sided):
        sig = {n: -s for n, s in sig.items()}
        nodes, strands = build(g, sig, T)
        col = columns(nodes, strands)
    order, snaps, enclosed, free, ev = sweep(nodes, strands, col, warnings.append)
    rows = Rows(nodes, strands, snaps, free, opts.get("level_leg"), opts.get("keep_close", ()))
    xcons, refused = set(), set()
    for _ in range(12):
        R = rows.optimise()
        try:
            x, need = place(nodes, strands, R, enclosed, opts, xcons)
        except Unsettled:               # a clearance rule that cannot hold with the new rows: keep the ones that can
            kept = set()
            for rule in sorted(xcons):
                try:
                    place(nodes, strands, R, enclosed, opts, kept | {rule})
                    kept.add(rule)
                except Unsettled:
                    refused.add(rule)
            xcons = kept
            x, need = place(nodes, strands, R, enclosed, opts, xcons)
        band = dict(nodes=nodes, strands=strands, R=R, x=x, need=need, turnbacks=T)
        clash, apart = set(), set()
        for a, b in overlaps(nodes, strands, R, x, need, order) - rows.extra:
            (sa, da), (sb, db) = ((strands[k]["src"][0], strands[k]["dst"][0]) for k in (a, b))
            stub = lambda p, q: nodes[p]["kind"] == "end" or nodes[q]["kind"] == "end"
            gap = lambda p, q: 1 + sum(nodes[t].get("sub") in ("link", "helix") for t in (p, q))    # room for the circles
            if ev[da] < ev[sb] and stub(da, sb):    # a ends before b starts and one is a stub: slide it along the row
                apart.add((da, sb, gap(da, sb)))
            elif ev[db] < ev[sa] and stub(db, sa):
                apart.add((db, sa, gap(db, sa)))
            else:
                clash.add((a, b))
        more = (slope_rules(band, ev) | apart) - xcons - refused
        if not clash and not more:
            break
        rows.extra |= clash
        xcons |= more
    if rows.dropped:
        warnings.append(f"{rows.dropped} above/below rules dropped where the layout is not flat")
    return band


def slope_rules(band, ev):
    """Where a sloped leg cuts through another track, keep that track clear of the slope's columns."""
    strands = band["strands"]
    rules = set()
    for _, k1, s1, k2, s2 in faults(band):
        for (ka, (a, b)), kb in (((k1, s1), k2), ((k2, s2), k1)):
            if ka not in strands or kb not in strands or a[0] == b[0] or a[1] == b[1]:
                continue
            pts = paths(band)[ka]
            src, dst = strands[ka]["src"][0], strands[ka]["dst"][0]
            k = int(round(abs(b[1] - a[1])))
            bs, bd = strands[kb]["src"][0], strands[kb]["dst"][0]
            if (a, b) == (pts[0], pts[1]):          # slope leaves switch src
                n, before, after = src, 0, k
            elif (a, b) == (pts[-2], pts[-1]):      # slope arrives at switch dst
                n, before, after = dst, k, 0
            else:
                continue
            if ev[bd] < ev[n] and bd != n:
                rules.add((bd, n, before))
            elif ev[bs] > ev[n] and bs != n:
                rules.add((n, bs, after))
    return rules


def paths(band):
    """Every drawn line in grid units: id -> list of (column, row)."""
    nodes, strands, R, x, need = (band[k] for k in ("nodes", "strands", "R", "x", "need"))
    srow, nrow, diag = R["srow"], R["nrow"], R["diag"]
    out, turns = {}, collections.defaultdict(list)
    for sid, s in strands.items():
        u, v = s["src"][0], s["dst"][0]
        if sid in diag:
            out[sid] = [(x[u], nrow[u]), (x[v], nrow[v])]
            continue
        su, sv, _ = need[sid]
        r = srow[sid]
        pts = [(x[u], nrow[u])] if u in nrow else []
        pts += [(x[u] + su, r), (x[v] - sv, r)]
        if v in nrow:
            pts.append((x[v], nrow[v]))
        out[sid] = dedupe(pts)
        for t in (u, v):
            if nodes[t]["kind"].startswith("turn"):
                turns[t].append(r)
    for t, rs in turns.items():
        r1, r2 = sorted(rs)
        k = min(1.0, r2 - r1) / 2
        dx = -k if nodes[t]["kind"] == "turnR" else k
        out[t] = [(x[t], r1), (x[t] - dx, r1 + k), (x[t] - dx, r2 - k), (x[t], r2)]
    return out


def faults(band):
    """Lines that lie on top of each other or cross: (kind, id, segment, id, segment)."""
    strands = band["strands"]
    P = paths(band)

    def ends(k):
        return {strands[k]["src"][0], strands[k]["dst"][0]} if k in strands else {k}

    segs = [(k, a, b) for k, pts in P.items() for a, b in zip(pts, pts[1:]) if a != b]
    found = []
    for (k1, a, b), (k2, c, d) in itertools.combinations(segs, 2):
        if k1 == k2 or (k1 not in strands and k2 in strands and k1 in ends(k2)) or \
                (k2 not in strands and k1 in strands and k2 in ends(k1)):
            continue
        d1, d2 = (b[0] - a[0], b[1] - a[1]), (d[0] - c[0], d[1] - c[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        w = (c[0] - a[0], c[1] - a[1])
        if abs(den) < 1e-9:
            if abs(w[0] * d1[1] - w[1] * d1[0]) > 1e-9:
                continue
            L = d1[0] ** 2 + d1[1] ** 2
            t0, t1 = sorted(((p[0] - a[0]) * d1[0] + (p[1] - a[1]) * d1[1]) / L for p in (c, d))
            if min(t1, 1) - max(t0, 0) > 1e-6:
                found.append(("on top of each other", k1, (a, b), k2, (c, d)))
            continue
        t = (w[0] * d2[1] - w[1] * d2[0]) / den
        u = (w[0] * d1[1] - w[1] * d1[0]) / den
        if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
            at_end = (t < 1e-6 or t > 1 - 1e-6) and (u < 1e-6 or u > 1 - 1e-6)
            if at_end and ends(k1) & ends(k2):
                continue
            found.append(("cross", k1, (a, b), k2, (c, d)))
    return found


def check(band):
    nodes, strands = band["nodes"], band["strands"]

    def name(k):
        if k not in strands:
            return "turnback"
        s = strands[k]
        return (s["name"] or "track") + " " + "-".join(nodes[n].get("label") or "end" for n in (s["src"][0], s["dst"][0]))

    return sorted({f"{kind}: {name(k1)} and {name(k2)} near column {a[0]:.0f}, row {a[1]:.0f}"
                   for kind, k1, (a, _), k2, _ in faults(band)})


# ---------------------------------------------------------------- draw
def draw_band(band, title, opts, top, left):
    cell, rowh = opts["cell"], opts["rowh"]
    cell = opts.get("band_cell", {}).get((title or " ").split()[0], cell)      # a band can be stretched along its length
    nodes, strands, R, x = band["nodes"], band["strands"], band["R"], band["x"]
    srow, nrow, diag = R["srow"], R["nrow"], R["diag"]
    x0, y0 = min(x.values()), min(srow.values())
    svg, text = [], []

    def X(c):
        return left + (c - x0) * cell

    def Y(r):
        return top + 30 + (r - y0) * rowh

    # a band can be turned end for end (180 degrees): the line work is rotated, the lettering stays upright
    turned = (title or " ").split()[0] in opts.get("rotate_bands", ())
    cx = (X(x0) + X(max(x.values()))) / 2
    cy = (Y(y0) + Y(max(srow.values()))) / 2

    def label(xp, yp, s, size, anchor="middle", weight="normal", extra="", fixed=False):
        if turned and not fixed:
            xp, yp = 2 * cx - xp, 2 * cy - yp + size * 0.7
            anchor = {"start": "end", "end": "start"}.get(anchor, anchor)
        text.append(f'<text x="{xp:.1f}" y="{yp:.1f}" font-size="{size}" text-anchor="{anchor}" '
                    f'font-weight="{weight}" fill="#000" stroke="none" {extra}>{s}</text>')

    helix = []
    if title:
        label(left, top + 4, title.upper(), 12, anchor="start", weight="bold", extra='letter-spacing="1.5"', fixed=True)
    for k, pts in paths(band).items():
        s = strands.get(k)
        wd = opts["main_w"] if (s is None or s["main"]) else opts["side_w"]
        if s is None:
            wd = max(opts["main_w"] if strands[q]["main"] else opts["side_w"] for q in strands
                     if k in (strands[q]["src"][0], strands[q]["dst"][0]))
        d = "M" + " L".join(f"{X(px):.1f},{Y(py):.1f}" for px, py in pts)
        dash = ' stroke-dasharray="7 5"' if s and s["hidden"] else ""
        svg.append(f'<path d="{d}" stroke-width="{wd}"{dash}/>')
        if s and s["name"] and k not in diag:
            su, sv, _ = band["need"][k]
            label((X(x[s["src"][0]] + su) + X(x[s["dst"][0]] - sv)) / 2, Y(srow[k]) - 5, s["name"].upper(),
                  opts["name_px"], extra='letter-spacing="0.4"')
    for n, d in nodes.items():
        if d["kind"] == "switch":
            up, lo = legs(nodes, n)
            a_row = nrow[n]
            low = lo in diag and nrow[other_end(strands, lo, n)] > a_row or lo not in diag and srow[lo] > a_row
            high = up in diag and nrow[other_end(strands, up, n)] < a_row or up not in diag and srow[up] < a_row
            dy = -7 if low and not high else 13
            label(X(x[n]) - 7 * d["sig"], Y(a_row) + dy, d["label"], opts["num_px"], weight="bold")
        elif d["kind"] == "dx":
            (iu_, _), (il_, _) = dx_tracks(nodes, n)
            r1, r2 = sorted((srow[iu_], srow[il_]))
            h = (Y(r2) - Y(r1)) / 2
            svg.append(f'<path d="M{X(x[n]) - h:.1f},{Y(r1):.1f} L{X(x[n]) + h:.1f},{Y(r2):.1f} '
                       f'M{X(x[n]) - h:.1f},{Y(r2):.1f} L{X(x[n]) + h:.1f},{Y(r1):.1f}" stroke-width="{opts["side_w"]}"/>')
            label(X(x[n]), Y(r1) - 6, d["label"], opts["num_px"], weight="bold")
        elif d["kind"] == "end":
            xe, ye = X(x[n]), Y(nrow[n])
            dirx = 1 if d["ins"] else -1
            style = opts.get("helix_style", "box")
            if d.get("sub") == "helix" and style == "box":
                helix.append((xe, ye, d.get("to", "")))
            elif d.get("sub") == "helix" and style == "coil":       # three turns of a coil on the track itself
                for k in range(3):
                    svg.append(f'<ellipse cx="{xe + 7 + 7 * k:.1f}" cy="{ye:.1f}" rx="6" ry="9" stroke-width="1.6"/>')
                label(xe + 34, ye + 3, "HELIX", 7, anchor="start", weight="bold", extra='letter-spacing="1"')
            elif d.get("sub") == "helix" and style == "letters":    # a lettered connector, like the rise
                tracks = opts.get("helix_tracks") or sorted(
                    {strands[q]["name"] for q in strands for e_ in (strands[q]["src"][0], strands[q]["dst"][0])
                     if nodes[e_].get("sub") == "helix"})                  # same letter for the same track on every level
                mine = next(strands[q]["name"] for q in strands if n in (strands[q]["src"][0], strands[q]["dst"][0]))
                tag = "H" + str(1 + tracks.index(mine))
                svg.append(f'<circle cx="{xe + 9:.1f}" cy="{ye:.1f}" r="8" stroke-width="1.4" fill="#fff"/>')
                label(xe + 9, ye + 3, tag, 8, weight="bold")
                label(xe + 21, ye + 3, "HELIX TO " + d.get("to", "").upper(), 6.5, anchor="start")
            elif d.get("sub") == "helix":                           # arrow: plain arrowhead and words
                svg.append(f'<path d="M{xe - 6:.1f},{ye - 5:.1f} L{xe:.1f},{ye:.1f} L{xe - 6:.1f},{ye + 5:.1f}" stroke-width="1.8"/>')
                label(xe + 6, ye + 3, "HELIX TO " + d.get("to", "").upper(), 6.5, anchor="start", weight="bold")
            elif d.get("sub") == "link":
                svg.append(f'<circle cx="{xe + 9 * dirx:.1f}" cy="{ye:.1f}" r="8" stroke-width="1.4" fill="#fff"/>')
                label(xe + 9 * dirx, ye + 3.5, d["label"], 10, weight="bold")
                label(xe + 9 * dirx, ye + 19, "TO " + d["to"].upper(), 6)      # under the circle, clear of the track
            elif d.get("sub") == "open":
                svg.append(f'<path d="M{xe:.1f},{ye:.1f} m{-6 * dirx},-5 l{6 * dirx},5 l{-6 * dirx},5" stroke-width="1.6"/>')
                if d.get("label"):
                    label(xe + 8 * dirx, ye + 3, d["label"].upper(), opts["name_px"],
                          anchor="start" if dirx == 1 else "end", weight="bold")
            else:
                svg.append(f'<path d="M{xe:.1f},{ye - 5:.1f} L{xe:.1f},{ye + 5:.1f}" stroke-width="2.4"/>')
    if helix:          # one box where this band's helix tracks end
        bx = max(h[0] for h in helix) + 6
        y1, y2 = min(h[1] for h in helix) - 12, max(h[1] for h in helix) + 12
        for xe, ye, _ in helix:
            svg.append(f'<path d="M{xe:.1f},{ye:.1f} L{bx:.1f},{ye:.1f}" stroke-width="{opts["main_w"]}"/>')
        svg.append(f'<rect x="{bx:.1f}" y="{y1:.1f}" width="58" height="{y2 - y1:.1f}" rx="5" fill="#fff" stroke-width="1.8"/>')
        label(bx + 29, (y1 + y2) / 2 + 1, "HELIX", 10, weight="bold", extra='letter-spacing="1.5"')
        label(bx + 29, (y1 + y2) / 2 + 11, "TO " + helix[0][2].upper(), 5.5)
    bottom = Y(max(srow.values()))
    lanes = []
    for name, members in opts.get("stations", {}).items():
        xs = [X(x[n]) for n, d in nodes.items() if d["kind"] == "switch" and d["label"] in members]
        if not xs:
            continue
        a, b = min(xs) - 10, max(xs) + 10
        lane = next((i for i, taken in enumerate(lanes) if all(b < p or a > q for p, q in taken)), len(lanes))
        if lane == len(lanes):
            lanes.append([])
        lanes[lane].append((a - 30, b + 30))
        yb = bottom + 34 + lane * 30
        svg.append(f'<path d="M{a:.1f},{yb - 6} L{a:.1f},{yb} L{b:.1f},{yb} L{b:.1f},{yb - 6}" stroke-width="1.4"/>')
        label((a + b) / 2, yb + 14, name.upper(), 12, weight="bold", extra='letter-spacing="1"')
    bottom += 34 + len(lanes) * 30 if lanes else 0
    if turned:
        svg = [f'<g transform="rotate(180 {cx:.1f} {cy:.1f})">'] + svg + ["</g>"]
    return svg + text, X(max(x.values())) + 110, bottom - top + 14


def draw_page(bands, opts, out):
    pw, ph, m = 1056, 816, 48
    top, foot = 96, 100                       # clear of the direction legend and the title block
    sized = []
    for title, band, *own in bands:           # measure first, so every band can be centred
        o = own[0] if own else opts
        _, w, bottom = draw_band(band, title, o, 0, 0)
        sized.append([title, band, o, w - 110, bottom])
    if opts.get("equal_width"):               # stretch the narrower bands along their length to match the widest
        widest = max(w for *_, w, _ in sized)
        for item in sized:
            title, band, o, w, _ = item
            key = (title or " ").split()[0]
            cell = o.get("band_cell", {}).get(key, o["cell"])
            factor = min(2.5, widest / max(w, 1))
            item[2] = dict(o, band_cell=dict(o.get("band_cell", {}), **{key: cell * factor}))
            _, w2, bottom = draw_band(band, title, item[2], 0, 0)
            item[3], item[4] = w2 - 110, bottom
    gap = 78
    total_h = sum(h for *_, h in sized) + gap * (len(sized) - 1) + 30
    total_w = max(w for *_, w, _ in sized) + 120
    scale = min(1.0, (pw - 2 * m) / total_w, (ph - top - foot) / total_h)
    body, y = [], 30
    for title, band, o, w, h in sized:
        part, _, _ = draw_band(band, title, o, y, (total_w - w) / 2 - 20)
        body += part
        y += h + gap
    ox = (pw - total_w * scale) / 2
    oy = top + ((ph - top - foot) - total_h * scale) / 2
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pw} {ph}" width="{pw}" height="{ph}" '
           f'font-family="\'Helvetica Neue\',Helvetica,Arial,sans-serif">',
           f'<rect width="{pw}" height="{ph}" fill="#fff"/>',
           f'<rect x="24" y="24" width="{pw - 48}" height="{ph - 48}" fill="none" stroke="#000" stroke-width="1.5"/>',
           f'<g transform="translate({ox:.1f},{oy:.1f}) scale({scale:.4f})" fill="none" '
           f'stroke="#000" stroke-linecap="round" stroke-linejoin="round">'] + body + ["</g>"]
    cx = pw / 2
    svg.append(f'<text x="{cx - 20}" y="62" font-size="15" text-anchor="end" font-weight="bold" letter-spacing="2">'
               f'&#8592; {opts["left"].upper()}</text>')
    svg.append(f'<text x="{cx + 20}" y="62" font-size="15" text-anchor="start" font-weight="bold" letter-spacing="2">'
               f'{opts["right"].upper()} &#8594;</text>')
    bx, by = 24, ph - 24 - 64
    svg.append(f'<rect x="{bx}" y="{by}" width="330" height="64" fill="#fff" stroke="#000" stroke-width="1.5"/>')
    for i, line in enumerate(opts["title"]):
        svg.append(f'<text x="{bx + 10}" y="{by + 20 + i * 18}" font-size="{14 if i == 0 else 11}" '
                   f'font-weight="{"bold" if i == 0 else "normal"}" letter-spacing="1">{line.upper()}</text>')
    svg.append("</svg>")
    open(out, "w").write("\n".join(svg))


def other_end(strands, sid, n):
    s = strands[sid]
    return s["src"][0] if s["dst"][0] == n else s["dst"][0]


def dedupe(pts):
    out = []
    for p in pts:
        if not out or abs(out[-1][0] - p[0]) > 0.01 or abs(out[-1][1] - p[1]) > 0.01:
            out.append(p)
    return out


# ---------------------------------------------------------------- main
DEFAULTS = dict(cell=28, rowh=28, name_px=8.5, num_px=8, main_w=3.2, side_w=1.4, left="West", right="East",
                title=["Schematic diagram"], stations={}, left_end=None, ends={}, edits=[], levels=None)


def main(graph, out, optfile=None):
    g = json.load(open(graph))
    opts = dict(DEFAULTS, **(json.load(open(optfile)) if optfile else {}))
    for e in g["edges"]:                       # owner's notes on track ends
        for n in (e["u"], e["v"]):
            for nm in e["names"]:
                if nm in opts["ends"] and g["nodes"][n]["kind"] == "end":
                    g["nodes"][n].update(opts["ends"][nm])
    apply_edits(g, opts["edits"])
    parts = split_levels(g, opts["levels"]) if opts["levels"] else [("", g)]
    bands, problems = [], 0
    for title, sub in parts:
        if sum(d["kind"] != "end" for d in sub["nodes"].values()) == 0:
            continue
        warnings = []
        band = layout(sub, opts, warnings)
        bands.append((title, band))
        found = check(band)
        problems += len(found) + len(warnings)
        cols = max(band["x"].values()) - min(band["x"].values())
        rows = max(band["R"]["srow"].values()) - min(band["R"]["srow"].values()) + 1
        print(f"{title or 'band'}: {sum(d['kind'] in JUNCTION for d in band['nodes'].values())} junctions, "
              f"{cols} x {rows} cells, {len(band['turnbacks'])} turnbacks, {len(found)} drawing faults")
        for w in warnings:
            print("  WARNING:", w)
        for f in found:
            print("  FAULT:", f)
    draw_page(bands, opts, out)
    print("total problems:", problems)


if __name__ == "__main__":
    main(*sys.argv[1:4])
