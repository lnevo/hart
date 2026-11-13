"""system.py <staging.json> <main.json> <out.svg> [--no-preferences] [--no-hints] [--data DIR]

Stage 0 spike: staging, main and upper level as three bands on one sheet, in route order from the bottom up.
Inputs are the graphs from export_reader.py and the layered option files in
jmri/layouts/hart/data/schematic/ (see layers.py). All layers are on by default; --no-preferences draws
without the owner's look, --no-hints without the temporary hand hints. Layer 1 is always read.
"""
import argparse
import json

import layers
import schem


def main(built, main_graph, out, preferences=True, hints=True, data=layers.DATA):
    bo = dict(schem.DEFAULTS, **layers.load("staging", preferences, hints, data))
    mo = dict(schem.DEFAULTS, **layers.load("main_upper", preferences, hints, data))
    bo["helix_style"] = mo["helix_style"] = mo.get("helix_style", "box")
    bands = []
    tracks = sorted(set(mo.get("helix", {}).values()))      # H1, H2 ... mean the same track on every band
    bo["helix_tracks"] = mo["helix_tracks"] = tracks

    g = json.load(open(main_graph))
    schem.apply_edits(g, mo["edits"])
    N = g["nodes"]
    for e in g["edges"]:                    # the main level's two helix tracks
        for a, b in ((e["u"], e["v"]), (e["v"], e["u"])):
            name = mo.get("helix", {}).get(N[a].get("label"))
            if name and N[b]["kind"] == "end" and e["cm"] > 300:
                e["names"], e["main"] = [name], True
                N[b].update(sub="helix", to="Staging", side=mo.get("helix_side", "west"))
    if mo.get("main_route"):
        keep = {e["id"] for e in g["edges"] if e["names"]}
        schem.mark_main(g, mo["main_route"])
        for e in g["edges"]:
            e["main"] = e["main"] or e["id"] in keep
    for title, sub in schem.split_levels(g, mo["levels"]):
        w = []
        band = schem.layout(sub, mo, w)
        bands.append((title, band, mo))
        print(title, len(schem.faults(band)), "drawing faults", w)

    g = json.load(open(built))              # staging: the plan's own track with the as-built edits
    schem.apply_edits(g, bo["edits"])
    w = []
    band = schem.layout(g, bo, w)
    bands.append(("Staging level", band, bo))
    print("Staging level", len(schem.faults(band)), "drawing faults", w)

    rank = {w: i for i, w in enumerate(mo.get("band_order", ["Upper", "Main", "Staging"]))}   # top to bottom
    bands.sort(key=lambda b: rank.get(b[0].split()[0], 9))
    schem.draw_page(bands, dict(mo, title=mo.get("system_title", mo["title"])), out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("staging_graph")
    ap.add_argument("main_graph")
    ap.add_argument("out")
    ap.add_argument("--no-preferences", action="store_true")
    ap.add_argument("--no-hints", action="store_true")
    ap.add_argument("--data", default=layers.DATA)
    a = ap.parse_args()
    main(a.staging_graph, a.main_graph, a.out, not a.no_preferences, not a.no_hints, a.data)
