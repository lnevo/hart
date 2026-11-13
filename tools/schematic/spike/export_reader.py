"""export_reader.py <AnyRail JMRI export .xml> <out.json> [skip-block-substring]

AnyRail's "export to JMRI" file -> logical graph (stage 0 spike). Keeps the largest connected
group of turnouts once blocks whose name contains the skip text are left out.
Switch labels are running numbers; the district is the export's block (AnyRail section) name.
"""
import collections
import json
import math
import sys
import xml.etree.ElementTree as ET

PX_PER_CM = 96 / 25.4   # AnyRail exports 1 px = 1/96 in at 1:10


def unit(dx, dy):
    n = math.hypot(dx, dy) or 1.0
    return [dx / n, dy / n]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def main(path, out, skip=None):
    panel = ET.parse(path).getroot().find("LayoutEditor")
    tos = {t.get("ident"): t for t in panel.iter("layoutturnout")}
    segs = {s.get("ident"): s for s in panel.iter("tracksegment")}
    pps = {p.get("ident"): p for p in panel.iter("positionablepoint")}
    nodes, portmap, edges = {}, {}, []

    def pt(t, leg):
        cx, cy = float(t.get("xcen")), float(t.get("ycen"))
        if leg == "B":
            return float(t.get("xb")), float(t.get("yb"))
        if leg == "C":
            return float(t.get("xc")), float(t.get("yc"))
        o = pt(t, "B" if (leg == "A" and "XOVER" not in t.get("type")) else ("C" if leg == "A" else "B"))
        return 2 * cx - o[0], 2 * cy - o[1]

    for ident, t in tos.items():
        ty = t.get("type")
        district = (t.get("blockname") or "").split("_", 2)[-1]
        if ty in ("LH_TURNOUT", "RH_TURNOUT", "WYE_TURNOUT"):
            a, b, c = pt(t, "A"), pt(t, "B"), pt(t, "C")
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            nodes[ident] = dict(kind="switch", label="", xy=list(mid), district=district,
                                hand=1 if cross((b[0] - a[0], b[1] - a[1]), (c[0] - a[0], c[1] - a[1])) > 0 else -1,
                                dirs={k: unit(p[0] - mid[0], p[1] - mid[1]) for k, p in zip("ABC", (a, b, c))})
            for leg in "ABC":
                portmap[(ident, leg)] = (ident, leg)
        elif ty == "DOUBLE_XOVER":      # tracks A-B and D-C, both crossings
            a, b, c, d = (pt(t, leg) for leg in "ABCD")
            mid = (float(t.get("xcen")), float(t.get("ycen")))
            nodes[ident] = dict(kind="dx", label="", xy=list(mid), district=district,
                                hand=1 if cross((b[0] - a[0], b[1] - a[1]), (d[0] - a[0], d[1] - a[1])) > 0 else -1,
                                dirs={k: unit(p[0] - mid[0], p[1] - mid[1]) for k, p in zip("ABCD", (a, b, c, d))})
            for leg in "ABCD":
                portmap[(ident, leg)] = (ident, leg)
        else:
            sys.exit(f"unsupported turnout type {ty} at {ident}")

    def where(name, ty):
        if ty.startswith("TURNOUT"):
            return pt(tos[name], ty[-1])
        p = pps[name]
        return float(p.get("x")), float(p.get("y"))

    def seg_cm(s):
        pts = [where(s.get("connect1name"), s.get("type1"))]
        pts += [(float(c.get("x")), float(c.get("y"))) for c in s.iter("controlpoint")]
        pts.append(where(s.get("connect2name"), s.get("type2")))
        chord = math.dist(pts[0], pts[-1])
        poly = sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
        return (chord + poly) / 2 / PX_PER_CM      # a Bezier lies between its chord and its control polygon

    def ends_of(s):
        return [(s.get("connect1name"), s.get("type1")), (s.get("connect2name"), s.get("type2"))]

    def follow(seg, frm):
        cm, blocks, dashed = seg_cm(seg), [seg.get("blockname")], seg.get("dashed") == "yes"
        while True:
            n, ty = next(e for e in ends_of(seg) if e[0] != frm)
            if ty.startswith("TURNOUT"):
                return portmap[(n, ty[-1])], cm, blocks, dashed
            pp = pps[n]
            nxt = [x for x in (pp.get("connect1name"), pp.get("connect2name")) if x and x != seg.get("ident")]
            if pp.get("type") == "END_BUMPER" or not nxt:
                return ("END:" + n, "E"), cm, blocks, dashed
            frm, seg = n, segs[nxt[0]]
            cm += seg_cm(seg)
            dashed = dashed or seg.get("dashed") == "yes"
            if seg.get("blockname") != blocks[-1]:
                blocks.append(seg.get("blockname"))

    seen = set()
    for s in segs.values():
        for n, ty in ends_of(s):
            if not ty.startswith("TURNOUT") or portmap[(n, ty[-1])] in seen:
                continue
            start = portmap[(n, ty[-1])]
            (v, vp), cm, blocks, dashed = follow(s, n)
            seen.update((start, (v, vp)))
            if v.startswith("END:"):
                nodes[v] = dict(kind="end", sub="bumper", label="")
            district = collections.Counter(b for b in blocks if b).most_common(1)
            district = district[0][0].split("_", 2)[-1] if district else ""
            edges.append(dict(u=start[0], up=start[1], v=v, vp=vp, names=[], cm=round(cm, 1), link=False,
                              main="Mainline" in district, district=district, hidden=dashed))

    if skip:
        drop = {n for n, d in nodes.items() if skip in d.get("district", "")}
        edges = [e for e in edges if e["u"] not in drop and e["v"] not in drop and skip not in e["district"]]
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        parent[find(e["u"])] = find(e["v"])
    size = collections.Counter(find(n) for n, d in nodes.items() if d["kind"] != "end")
    keep = size.most_common(1)[0][0]
    nodes = {n: d for n, d in nodes.items() if find(n) == keep}
    edges = [e for e in edges if e["u"] in nodes]
    order = sorted((n for n, d in nodes.items() if d["kind"] != "end"), key=lambda n: (nodes[n]["xy"][1], nodes[n]["xy"][0]))
    for i, n in enumerate(order, 1):
        nodes[n]["label"] = str(i)
    for i, e in enumerate(edges):
        e["id"] = f"e{i}"
    json.dump(dict(nodes=nodes, edges=edges), open(out, "w"), indent=1)
    kinds = collections.Counter(d["kind"] for d in nodes.values())
    print(dict(kinds), len(edges), "edges; districts:",
          dict(collections.Counter(e["district"] for e in edges).most_common()))


if __name__ == "__main__":
    main(*sys.argv[1:4])
