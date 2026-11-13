"""signal_reader.py <tables.xml> <switches.csv> <block_lengths.csv> <schematic graph.json> <plan_overrides.json> <out.json>

Layer 1 signals from the Layout Editor panel (rule R13 in docs/ops/SCHEMATIC_SPEC.md). Never typed by hand.

For every mast bound on the panel (at a turnout leg, an anchor or an end bumper) this finds the run of track
it stands on and the switch or track end its governed movement is heading for, then finds the same run in
the schematic graph (AnyRail plan plus the plan overrides), matched by the switch numbers at its ends and
the track names. Writes one entry per mast:

  {"mast": "24RA", "toward": "23", "run": ["23", "1"], "names": ["Main West"], "cm_from_toward": 0,
   "dir": "east", "kind": "field", "heads": 1, "source": "le_panel"}

kind: field (a mast with signal heads), virtual (exists for Dispatcher only; not drawn) or planned (named in
the overrides' "signals_planned": placeholders with no hardware). dir comes from the name's L or R; a mast
with neither takes the anchor's east or west binding. Masts that cannot be placed are listed and left out.
"""
import json
import re
import sys
import xml.etree.ElementTree as ET

import le_reader
import schem


def east_side(pp, segs, coords):
    """The segment on the east side of an anchor, by JMRI's own rule (LayoutEditorTools.isAtWestEndOfAnchor):
    compare the far ends of the two segments; mostly horizontal track: east is larger x; mostly vertical:
    east is larger y (south); otherwise horizontal."""
    s1, s2 = pp.get("connect1name"), pp.get("connect2name")
    far = []
    for s in (s1, s2):
        t = segs[s]
        other = t.get("connect2name") if t.get("connect1name") == pp.get("ident") else t.get("connect1name")
        typ = t.get("type2") if t.get("connect1name") == pp.get("ident") else t.get("type1")
        far.append(coords(other, typ))
    dx, dy = far[0][0] - far[1][0], far[0][1] - far[1][1]
    if abs(dy) > 2 * abs(dx):
        return s1 if dy > 0 else s2
    return s1 if dx > 0 else s2


def main(tables, switches_csv, lengths_csv, graph, overrides, out):
    root = ET.parse(tables).getroot()
    panel = next(p for p in root.iter("LayoutEditor") if p.get("name") != "Dispatcher System")
    le = le_reader.read(tables, switches_csv, lengths_csv)
    LN = le["nodes"]
    tos = {t.get("ident"): t for t in panel.iter("layoutturnout")}
    segs = {s.get("ident"): s for s in panel.iter("tracksegment")}
    pps = {p.get("ident"): p for p in panel.iter("positionablepoint")}

    def coords(ident, typ):
        if typ.startswith("TURNOUT"):
            t = tos[ident]
            leg = typ[-1].lower()
            return float(t.get("x" + leg)), float(t.get("y" + leg))
        p = pps[ident]
        return float(p.get("x")), float(p.get("y"))

    # what each mast is
    masts = {}
    for m in root.iter("signalmast"):
        name = m.findtext("userName")
        masts[name] = dict(kind="field", heads=max(1, len(re.findall(r"\(IH", m.findtext("systemName") or ""))))
    for m in root.iter("virtualsignalmast"):
        masts[m.findtext("userName")] = dict(kind="virtual", heads=1)

    ov = json.load(open(overrides))
    planned = set(ov.get("signals_planned", []))

    # where each mast is on the panel's graph: (edge, toward node, cm from that node)
    edge_at = {}
    for e in le["edges"]:
        edge_at[(e["u"], e["up"])] = e
        edge_at[(e["v"], e["vp"])] = e
    portmap = {}
    for ident, t in tos.items():
        if t.get("type") in ("RH_XOVER", "LH_XOVER"):
            rh = t.get("type") == "RH_XOVER"
            top, bot = (("A", "B"), ("C", "D")) if rh else (("B", "A"), ("D", "C"))
            for half, (pl, nl) in (("a", top), ("b", bot)):
                portmap[(ident, pl)] = (ident + half, "A")
                portmap[(ident, nl)] = (ident + half, "B")
        else:
            for leg in "ABC":
                portmap[(ident, leg)] = (ident, leg)

    found, problems = [], []
    for ident, t in tos.items():
        for leg in "ABCD":
            name = t.findtext(f"signal{leg}Mast")
            if not name:
                continue
            node, port = portmap[(ident, leg)]
            e = edge_at.get((node, port))
            if e is None:
                problems.append(f"{name}: no track at {ident} leg {leg}")
                continue
            found.append((name, e, node, 0.0, None))
    anchor_edge = {}
    for e in le["edges"]:
        for a, cm, seg_u, seg_v in e.get("anchors", []):
            anchor_edge[a] = (e, cm, seg_u, seg_v)
    for ident, p in pps.items():
        for slot in ("east", "west"):
            name = p.get(slot + "boundsignalmast")
            if not name:
                continue
            if p.get("type") == "END_BUMPER":     # a mast at a buffer stop governs the move away from it
                e = next((x for x in le["edges"] if x["v"] == "END:" + ident or x["u"] == "END:" + ident), None)
                if e is None:
                    problems.append(f"{name}: bumper {ident} not on the graph")
                    continue
                toward = e["u"] if e["v"] == "END:" + ident else e["v"]
                found.append((name, e, toward, e["cm"], slot))
                continue
            if ident not in anchor_edge:
                problems.append(f"{name}: anchor {ident} not on the graph")
                continue
            e, cm, seg_u, seg_v = anchor_edge[ident]
            east = east_side(p, segs, coords)
            going_east = slot == "east"
            heading_v = (east == seg_v) == going_east       # travel toward v's side of the anchor
            toward = e["v"] if heading_v else e["u"]
            found.append((name, e, toward, (e["cm"] - cm) if heading_v else cm, slot))

    # the same runs on the schematic graph
    g = json.load(open(graph))
    schem.apply_edits(g, ov["edits"])
    SN = g["nodes"]
    lab = lambda N, n: (N[n].get("label") or "") if N[n]["kind"] != "end" else ""
    clean = lambda names: {re.sub(r"^Track ", "", x).replace("Main Ext", "Ext").replace(" East", "").replace(" West", "")
                           for x in names}

    def match(e, toward):
        want = sorted((lab(LN, e["u"]), lab(LN, e["v"])))
        names = clean(e["names"])
        best = None
        for s in g["edges"]:
            have = sorted((lab(SN, s["u"]), lab(SN, s["v"])))
            if have != want:
                continue
            score = len(names & clean(s["names"])) - abs(s["cm"] - e["cm"]) / 1000
            if best is None or score > best[0]:
                best = (score, s)
        if best is None:
            return None, None
        s = best[1]
        t = lab(LN, toward)
        tn = s["u"] if lab(SN, s["u"]) == t else s["v"]
        if lab(SN, s["u"]) == lab(SN, s["v"]):      # both ends carry the same number: keep the panel's sense
            tn = s["u"] if toward == e["u"] else s["v"]
        return s, tn

    rows = []
    for name, e, toward, cm, slot in found:
        short = name.replace("Mast ", "")
        info = masts.get(name, dict(kind="field", heads=1))
        kind = "planned" if short in planned else info["kind"]
        m = re.match(r"\d+([LR])", short)
        d = {"R": "east", "L": "west"}[m.group(1)] if m else slot
        if m and slot and d != slot:
            problems.append(f"{short}: name says {d}, binding says {slot}")
        s, tn = match(e, toward)
        if s is None:
            problems.append(f"{short}: run {lab(LN, e['u']) or 'end'}-{lab(LN, e['v']) or 'end'} not in the schematic")
            continue
        far = s["v"] if tn == s["u"] else s["u"]
        rows.append(dict(mast=short, toward=lab(SN, tn) or SN[tn].get("label", ""), run=[lab(SN, tn), lab(SN, far)],
                         names=s["names"], edge_cm=s["cm"], cm_from_toward=round(min(cm, s["cm"]), 1), dir=d,
                         kind=kind, heads=info["heads"], source="le_panel", _edge=s["id"], _toward_node=tn))
    rows.sort(key=lambda r: (int(re.match(r"\d+", r["mast"]).group()), r["mast"]))
    json.dump(dict(schema="schematic.signals/1", source=tables.split("/")[-1], signals=rows, unplaced=problems),
              open(out, "w"), indent=1)
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(len(rows), "masts placed", kinds, "|", len(problems), "problems")
    for p in problems:
        print("  ", p)


if __name__ == "__main__":
    main(*sys.argv[1:7])
