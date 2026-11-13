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

TAU = {"A": -1, "B": 1, "C": 1}


# ---------------------------------------------------------------- orient
def colour(g, sw_edges, T):
    sig = {}
    adj = collections.defaultdict(list)
    for e in sw_edges:
        r = (1 if e["id"] in T else -1) * TAU[e["up"]] * TAU[e["vp"]]
        adj[e["u"]].append((e["v"], r))
        adj[e["v"]].append((e["u"], r))
    for start in (n for n, d in g["nodes"].items() if d["kind"] == "switch"):
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
        return sig[n] * TAU[p] if nodes[n]["kind"] == "switch" else None

    def add(sid, src, dst, e, name):
        strands[sid] = dict(src=src, dst=dst, edge=e["id"], name=name, cm=e["cm"],
                            main=e["main"], link=e["link"])
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


def orient(g, max_turnbacks=3):
    sw = [e for e in g["edges"] if all(g["nodes"][n]["kind"] == "switch" for n in (e["u"], e["v"]))]
    cand = [e for e in sw if not e["link"]]
    best = None
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
            if best is None or cost < best[0] - 1e-9:
                best = (cost, sig, ids)
        if best is not None and k > len(best[2]):
            break
    if best is None:
        raise SystemExit("no orientation found; raise max_turnbacks")
    return best[1], best[2]


# ---------------------------------------------------------------- sweep
def legs(nodes, n):
    """(upper strand, lower strand) of the frog side of switch n, in screen terms."""
    d = nodes[n]
    side = d["outs"] if d["sig"] == 1 else d["ins"]
    b, c = side["B"], side["C"]
    c_low = (d["hand"] == 1) == (d["sig"] == 1)
    return (b, c) if c_low else (c, b)


def sweep(nodes, strands, col, warn):
    L, alive, done, snaps, enclosed = [], set(), set(), [], {}

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
            if iu > il:
                warn(f"switch {d['label']}: legs arrive in the opposite order")
                iu, il = il, iu
            if any(s in alive for s in L[iu + 1:il]):
                warn(f"switch {d['label']}: a track lies between its two legs")
            alive.difference_update((up, lo))
            L.insert(il, d["outs"]["A"])
            alive.add(d["outs"]["A"])
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
        elif d["sig"] == 1:
            if d["ins"]["A"] not in alive:
                demand(d["ins"]["A"], hint)
            process(p)
        else:
            up, lo = legs(nodes, p)
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
        return (2 if d["sig"] == -1 else 3, col[n])

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
                up, lo = legs(nodes, n)
                if up in alive:
                    demand(lo, (up, "below"))
                else:
                    demand(up, (lo, "above"))
            continue
        src = [n for n, d in nodes.items() if n not in done and not d["ins"]]
        process(min(src, key=lambda n: -sum(strands[s]["cm"] for s in nodes[n]["outs"].values())))
    return L, snaps, enclosed


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


class Rows:
    def __init__(self, nodes, strands, snaps):
        self.nodes, self.strands, self.snaps = nodes, strands, snaps
        self.extra = set()
        self.flat = {n: "B" for n, d in nodes.items() if d["kind"] == "switch"}

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
        diag = {s for s, d in st.items() if self.sloped(s, "src") and self.sloped(s, "dst")
                and (d["link"] or (not d["name"] and d["cm"] < 40))}
        above = collections.defaultdict(set)
        pairs = set(self.extra)
        for snap in self.snaps:
            row = [s for s in snap if s not in diag]
            pairs.update(zip(row, row[1:]))
        for a, b in pairs:
            ca, cb = find(a), find(b)
            if ca == cb:
                return None
            above[ca].add(cb)
        classes = sorted({find(s) for s in st if s not in diag})
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
        bias = 0.05 * sum(f == "C" for f in self.flat.values())

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
        best = self.solve()
        if best is None:
            for n in self.flat:
                self.flat[n] = "C"
                best = self.solve()
                if best:
                    break
                self.flat[n] = "B"
        if best is None:
            raise SystemExit("rows: no consistent assignment")
        improved = True
        while improved:
            improved = False
            for n in self.flat:
                self.flat[n] = "C" if self.flat[n] == "B" else "B"
                r = self.solve()
                if r and r["cost"] < best["cost"] - 1e-9:
                    best, improved = r, True
                else:
                    self.flat[n] = "C" if self.flat[n] == "B" else "B"
        return best


# ---------------------------------------------------------------- columns
def name_cells(name, opts):
    return 0 if not name else math.ceil((len(name) * opts["name_px"] * 0.62 + 10) / opts["cell"])


def place(nodes, strands, R, enclosed, opts):
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
        h = name_cells(s["name"], opts)
        if nodes[u]["kind"] == "end" or nodes[v]["kind"] == "end":
            h = max(h, 1) + 1
        w = max(1, su + sv + h)
        need[sid] = (su, sv, w)
        cons.append((u, v, w))
        cm = s["cm"] / (2 if "." in sid else 1)
        weight.append((u, v, 100.0 / (cm + 25.0)))     # long tracks take up the slack
    for t, inside in enclosed.items():
        for sid in inside:
            cons.append((strands[sid]["dst"][0], t, 1))
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
        raise SystemExit("columns: constraints do not settle")

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
        spans.append((R["srow"][sid], x[s["src"][0]] + su, x[s["dst"][0]] - sv, sid))
    found = set()
    for (r1, a1, b1, s1), (r2, a2, b2, s2) in itertools.combinations(spans, 2):
        if r1 == r2 and a1 < b2 and a2 < b1:
            found.add((s1, s2) if rank[s1] < rank[s2] else (s2, s1))
    return found


# ---------------------------------------------------------------- draw
def draw(nodes, strands, R, x, need, spine, opts, out):
    cell, rowh = opts["cell"], opts["rowh"]
    srow, nrow, diag = R["srow"], R["nrow"], R["diag"]
    rows = list(srow.values())
    x0, y0 = min(x.values()), min(rows)
    W = (max(x.values()) - x0) * cell + 90
    H = (max(rows) - y0) * rowh
    pw, ph, m = 1056, 816, 48
    top = 110

    def X(c):
        return m + (c - x0) * cell

    def Y(r):
        return top + (r - y0) * rowh

    scale = min(1.0, (pw - 2 * m) / max(W, 1))
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pw} {ph}" width="{pw}" height="{ph}" '
           f'font-family="\'Helvetica Neue\',Helvetica,Arial,sans-serif">',
           f'<rect width="{pw}" height="{ph}" fill="#fff"/>',
           f'<rect x="24" y="24" width="{pw - 48}" height="{ph - 48}" fill="none" stroke="#000" stroke-width="1.5"/>',
           f'<g transform="translate({m * (1 - scale)},0) scale({scale})" fill="none" stroke="#000" '
           f'stroke-linecap="round" stroke-linejoin="round">']
    text = []

    def label(xp, yp, s, size, anchor="middle", weight="normal", extra=""):
        text.append(f'<text x="{xp:.1f}" y="{yp:.1f}" font-size="{size}" text-anchor="{anchor}" '
                    f'font-weight="{weight}" fill="#000" stroke="none" {extra}>{s}</text>')

    turn_rows = collections.defaultdict(list)
    for sid, s in strands.items():
        (u, _), (v, _) = s["src"], s["dst"]
        heavy = sid in spine or s["main"]
        wd = opts["main_w"] if heavy else opts["side_w"]
        if sid in diag:
            pts = [(X(x[u]), Y(nrow[u])), (X(x[v]), Y(nrow[v]))]
        else:
            su, sv, _ = need[sid]
            r = srow[sid]
            pts = []
            if u in nrow:
                pts.append((X(x[u]), Y(nrow[u])))
            pts += [(X(x[u] + su), Y(r)), (X(x[v] - sv), Y(r))]
            if v in nrow:
                pts.append((X(x[v]), Y(nrow[v])))
            for t in (u, v):
                if nodes[t]["kind"].startswith("turn"):
                    turn_rows[t].append((r, wd))
            if s["name"]:
                label((X(x[u] + su) + X(x[v] - sv)) / 2, Y(r) - 5, s["name"].upper(), opts["name_px"], extra='letter-spacing="0.4"')
        d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in dedupe(pts))
        svg.append(f'<path d="{d}" stroke-width="{wd}"/>')
    for t, rs in turn_rows.items():
        (r1, w1), (r2, w2) = sorted(rs)
        xt = X(x[t])
        k = min(cell, rowh * (r2 - r1)) / 2
        dirx = -1 if nodes[t]["kind"] == "turnR" else 1
        svg.append(f'<path d="M{xt:.1f},{Y(r1):.1f} L{xt - dirx * k:.1f},{Y(r1) + k:.1f} '
                   f'L{xt - dirx * k:.1f},{Y(r2) - k:.1f} L{xt:.1f},{Y(r2):.1f}" stroke-width="{max(w1, w2)}"/>')
    for n, d in nodes.items():
        if d["kind"] == "switch":
            up, lo = legs(nodes, n)
            a_row = nrow[n]
            low = lo in diag and nrow[other_end(strands, lo, n)] > a_row or lo not in diag and srow[lo] > a_row
            high = up in diag and nrow[other_end(strands, up, n)] < a_row or up not in diag and srow[up] < a_row
            dy = -7 if low and not high else 13     # the side away from the sloped leg
            label(X(x[n]) - 7 * d["sig"], Y(a_row) + dy, d["label"], opts["num_px"], weight="bold")
        elif d["kind"] == "end":
            xe, ye = X(x[n]), Y(nrow[n])
            if d.get("sub") == "open":
                dirx = 1 if d["ins"] else -1
                svg.append(f'<path d="M{xe:.1f},{ye:.1f} m{-6 * dirx},-5 l{6 * dirx},5 l{-6 * dirx},5" stroke-width="1.6"/>')
                if d.get("label"):
                    label(xe + 8 * dirx, ye + 3, d["label"].upper(), opts["name_px"],
                          anchor="start" if dirx == 1 else "end", weight="bold")
            else:
                svg.append(f'<path d="M{xe:.1f},{ye - 5:.1f} L{xe:.1f},{ye + 5:.1f}" stroke-width="2.4"/>')
    ybar = Y(max(rows)) + 34
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
        yb = ybar + lane * 30
        svg.append(f'<path d="M{a:.1f},{yb - 6} L{a:.1f},{yb} L{b:.1f},{yb} L{b:.1f},{yb - 6}" stroke-width="1.4"/>')
        label((a + b) / 2, yb + 14, name.upper(), 12, weight="bold", extra='letter-spacing="1"')
    svg += text
    svg.append("</g>")
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
                title=["Schematic diagram"], stations={}, left_end=None, ends={}, flip_vertical=False)


def main(graph, out, optfile=None):
    g = json.load(open(graph))
    opts = dict(DEFAULTS, **(json.load(open(optfile)) if optfile else {}))
    for e in g["edges"]:                       # owner's notes on track ends
        for n in (e["u"], e["v"]):
            for nm in e["names"]:
                if nm in opts["ends"] and g["nodes"][n]["kind"] == "end":
                    g["nodes"][n].update(opts["ends"][nm])
    if opts["flip_vertical"]:
        for d in g["nodes"].values():
            if d["kind"] == "switch":
                d["hand"] = -d["hand"]
    warnings = []
    sig, T = orient(g)
    nodes, strands = build(g, sig, T)
    col = columns(nodes, strands)
    if opts["left_end"]:
        e = next(e for e in g["edges"] if opts["left_end"] in e["names"])
        if col[e["v"]] > max(col.values()) / 2:
            sig = {n: -s for n, s in sig.items()}
            nodes, strands = build(g, sig, T)
            col = columns(nodes, strands)
    order, snaps, enclosed = sweep(nodes, strands, col, warnings.append)
    spine = spine_path(nodes, strands, col)
    rows = Rows(nodes, strands, snaps)
    for _ in range(6):
        R = rows.optimise()
        x, need = place(nodes, strands, R, enclosed, opts)
        clash = overlaps(nodes, strands, R, x, need, order)
        if not clash - rows.extra:
            break
        rows.extra |= clash
    else:
        warnings.append("tracks still overlap after 6 passes")
    draw(nodes, strands, R, x, need, set(spine), opts, out)
    print("turnbacks:", sorted(T), "| spine:", [strands[s]["name"] or s for s in spine])
    print("size:", max(x.values()) - min(x.values()), "cells x", max(R["srow"].values()) - min(R["srow"].values()) + 1, "rows")
    for w in warnings:
        print("WARNING:", w)


if __name__ == "__main__":
    main(*sys.argv[1:4])
