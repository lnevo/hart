"""system.py <staging.json> <staging_opts.json> <main.json> <main_opts.json> <out.svg>

Stage 0 spike: staging, main and upper level as three bands on one sheet, in route order from the bottom up.
"""
import json
import sys

import schem


def main(built, built_opts, main_graph, main_opts, out, helix_style="coil"):
    bo = dict(schem.DEFAULTS, **json.load(open(built_opts)), helix_style=helix_style)
    mo = dict(schem.DEFAULTS, **json.load(open(main_opts)), helix_style=helix_style)
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
    main(*sys.argv[1:7])
