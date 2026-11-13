"""baseline_report.py <staging.json> <main.json> [--no-preferences] [--no-hints] [--without KEY ...]

Checks of a drawing beyond the spike's own crossing test (stream A2): per band, every crossing or overlap
the self-check prints, every switch on the main route where the main is not level, and every switch whose
level leg is a short link while a long track slopes (a yard ladder with the yard track not level).
--without removes single hint entries (a level_leg switch, "keep_close", "shorten", "min_cells") to find out which
one was covering a fault.
"""
import argparse
import io
import sys

import layers
import schem
import system


def label(nodes, n):
    d = nodes[n]
    return d.get("label") or ("end" if d["kind"] == "end" else d["kind"])


def tag(nodes, n):
    d = nodes[n]
    lab = label(nodes, n)
    return f"{lab} ({d['alias']})" if d.get("alias") and d["alias"] != lab else lab


def leg_rows(band):
    """For each switch: {port: (strand, sloped at this switch)}."""
    nodes, strands, R = band["nodes"], band["strands"], band["R"]
    srow, nrow, diag = R["srow"], R["nrow"], R["diag"]
    out = {}
    for n, d in nodes.items():
        if d["kind"] != "switch":
            continue
        legs = {}
        for p in "ABC":
            sid = d["outs"].get(p) or d["ins"].get(p)
            if sid is None:
                continue
            legs[p] = (sid, sid in diag or srow[sid] != nrow[n])
        out[n] = legs
    return out


def analyse(band):
    nodes, strands = band["nodes"], band["strands"]
    found = {"faults": schem.check(band), "main": [], "ladder": []}
    for n, legs in leg_rows(band).items():
        s = {p: strands[sid] for p, (sid, _) in legs.items()}
        if "A" in s and s["A"]["main"]:
            via = [p for p in "BC" if p in s and s[p]["main"]]
            if len(via) == 1 and legs[via[0]][1]:
                found["main"].append((tag(nodes, n), f"main enters the common end and leaves by leg {via[0]}, which is drawn "
                                      f"sloped (the level leg is {'C' if via[0] == 'B' else 'B'}, "
                                      f"{s['C' if via[0] == 'B' else 'B']['name'] or 'unnamed'})"))
            elif len(via) == 2:
                found["main"].append((tag(nodes, n), "main on all three legs"))
        elif "A" in s and not s["A"]["main"]:
            via = [p for p in "BC" if p in s and s[p]["main"]]
            if via:
                found["main"].append((tag(nodes, n), f"main on leg {via[0]} but not on the common end"))
        # ladder: the level leg is a short link while the sloped leg is a long track
        lv = [p for p in "BC" if p in legs and not legs[p][1]]
        sl = [p for p in "BC" if p in legs and legs[p][1]]
        if len(lv) == 1 and len(sl) == 1:
            L, S = s[lv[0]], s[sl[0]]
            far = L["dst"][0] if L["src"][0] == n else L["src"][0]
            if nodes[far]["kind"] in ("switch", "dx") and not L["main"] and L["cm"] <= 40 and S["cm"] > 2 * L["cm"] + 20 and not S["main"]:
                found["ladder"].append((tag(nodes, n), f"level leg {lv[0]} is {L['name'] or 'a link'} ({L['cm']:.0f} cm), "
                                        f"sloped leg {sl[0]} is {S['name'] or 'a track'} ({S['cm']:.0f} cm)"))
        elif not lv:
            found["ladder"].append((tag(nodes, n), "neither leg is level"))
    # main strands drawn on a diagonal (not level between two switches)
    diag = band["R"]["diag"]
    for sid in diag:
        if strands[sid]["main"]:
            u, v = strands[sid]["src"][0], strands[sid]["dst"][0]
            found["main"].append((f"{tag(nodes, u)} to {tag(nodes, v)}", "main strand drawn as a diagonal"))
    return found


def run(staging, main_graph, preferences, hints, without=()):
    bo, mo = system.options(preferences, hints)
    for o in (bo, mo):
        for key in without:
            if key == "keep_close":
                o.pop("keep_close", None)
            elif key == "shorten":
                o.pop("shorten", None)
            elif key == "min_cells":
                o.pop("min_cells", None)
            else:
                o["level_leg"] = {k: v for k, v in o.get("level_leg", {}).items() if k != key}
    stdout, sys.stdout = sys.stdout, io.StringIO()
    try:
        bands = system.build_bands(staging, main_graph, bo, mo)
        printed = sys.stdout.getvalue().splitlines()
    finally:
        sys.stdout = stdout
    res = {t.split()[0]: analyse(b) for t, b, _ in bands}
    for line in printed:                # the layout's own warnings (rules dropped, clearance that could not be met)
        res[line.split()[0]]["printed"] = line
    return res


def show(res):
    for title, f in res.items():
        print(f"== {title}")
        print(f"  layout says: {f.get('printed')}")
        print(f"  self-check faults: {len(f['faults'])}")
        for x in f["faults"]:
            print("   ", x)
        print(f"  main not level: {len(f['main'])}")
        for a, b in f["main"]:
            print(f"    {a}: {b}")
        print(f"  ladder, yard track not level: {len(f['ladder'])}")
        for a, b in f["ladder"]:
            print(f"    {a}: {b}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("staging_graph")
    ap.add_argument("main_graph")
    ap.add_argument("--no-preferences", action="store_true")
    ap.add_argument("--no-hints", action="store_true")
    ap.add_argument("--without", nargs="*", default=[])
    a = ap.parse_args()
    show(run(a.staging_graph, a.main_graph, not a.no_preferences, not a.no_hints, a.without))
