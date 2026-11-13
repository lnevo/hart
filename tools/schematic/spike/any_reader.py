"""any_reader.py <parts.json> <graph.json> <component index> <out.json>

AnyRail track graph (from the prototype reader) -> logical graph (stage 0 spike).
Turnouts are numbered T<part index>; track has no names yet. A four-ended part is read as a
plain crossing: each route runs straight through it.
"""
import json
import math
import sys


def unit(dx, dy):
    n = math.hypot(dx, dy) or 1.0
    return [dx / n, dy / n]


def main(parts_file, graph_file, comp, out):
    parts = json.load(open(parts_file))
    G = json.load(open(graph_file))
    members = G["comps"][int(comp)]
    nbr = {}
    for a, ka, b, kb in G["links"]:
        nbr[(a, ka)] = (b, kb)
        nbr[(b, kb)] = (a, ka)

    nodes, port, through = {}, {}, {}
    for i in members:
        p = parts[i]
        e = p["eps"]
        pts = [(q["x"], q["y"]) for q in e]
        if len(e) == 3:
            toe = max(range(3), key=lambda k: min(math.dist(pts[k], pts[j]) for j in range(3) if j != k))
            rest = [k for k in range(3) if k != toe]

            def bend(k):  # how far leg k is from straight ahead of the toe
                d = (e[k]["a"] - e[toe]["a"]) % (2 * math.pi)
                return abs(min(d, 2 * math.pi - d) - math.pi)

            rest.sort(key=bend)
            a, b, c = pts[toe], pts[rest[0]], pts[rest[1]]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            nid = f"T{i}"
            nodes[nid] = dict(kind="switch", hand=1 if cross > 0 else -1, label=str(i), xy=list(mid),
                              z=round(e[toe]["z"], 1),
                              dirs={"A": unit(a[0] - mid[0], a[1] - mid[1]), "B": unit(b[0] - mid[0], b[1] - mid[1]),
                                    "C": unit(c[0] - mid[0], c[1] - mid[1])})
            for k, name in zip((toe, rest[0], rest[1]), "ABC"):
                port[(i, k)] = (nid, name)
        elif len(e) == 2:
            through[(i, 0)], through[(i, 1)] = (i, 1), (i, 0)
        elif len(e) == 4:      # crossing: pair each end with the one most nearly opposite
            for k in range(4):
                j = max((j for j in range(4) if j != k), key=lambda j: math.dist(pts[k], pts[j]))
                through[(i, k)] = (i, j)
        else:
            sys.exit(f"part {i} ({p['name']}) has {len(e)} ends")

    def length(i, k):
        p = parts[i]
        if "len" in p:
            return p["len"]
        j = through[(i, k)][1]
        return math.dist((p["eps"][k]["x"], p["eps"][k]["y"]), (p["eps"][j]["x"], p["eps"][j]["y"]))

    edges, seen, ends = [], set(), 0
    for (i, k), (nid, name) in sorted(port.items()):
        if (nid, name) in seen:
            continue
        cm, cur, zs = 0.0, (i, k), [parts[i]["eps"][k]["z"]]
        while True:
            if cur not in nbr:
                ends += 1
                far = (f"END:{ends}", "E")
                nodes[far[0]] = dict(kind="end", sub="open", label="", z=round(zs[-1], 1))
                break
            j, kj = nbr[cur]
            if (j, kj) in port:
                far = port[(j, kj)]
                break
            cm += length(j, kj)
            cur = through[(j, kj)]
            zs.append(parts[j]["eps"][cur[1]]["z"])
        seen.add((nid, name))
        seen.add(far)
        edges.append(dict(id=f"e{len(edges)}", u=nid, up=name, v=far[0], vp=far[1], names=[], cm=round(cm, 1),
                          main=False, link=False, dz=round(max(zs) - min(zs), 1)))
    json.dump(dict(nodes=nodes, edges=edges), open(out, "w"), indent=1)
    print(len(nodes), "nodes", len(edges), "edges", ends, "open ends")


if __name__ == "__main__":
    main(*sys.argv[1:5])
