"""system.py <staging.json> <staging_opts.json> <main.json> <main_opts.json> <out.svg>

Stage 0 spike: staging, main and upper level as three bands on one sheet, in route order from the bottom up.
"""
import json
import sys

import schem


def main(built, built_opts, main_graph, main_opts, out):
    bo = dict(schem.DEFAULTS, **json.load(open(built_opts)))
    mo = dict(schem.DEFAULTS, **json.load(open(main_opts)))
    bands = []

    g = json.load(open(main_graph))
    schem.apply_edits(g, mo["edits"])
    N = g["nodes"]
    for e in g["edges"]:                    # the main level's two helix tracks
        for a, b in ((e["u"], e["v"]), (e["v"], e["u"])):
            name = mo.get("helix", {}).get(N[a].get("label"))
            if name and N[b]["kind"] == "end" and e["cm"] > 300:
                e["names"], e["main"] = [name], True
                N[b].update(sub="helix", to="Staging")
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

    rank = {"Upper": 0, "Main": 1, "Staging": 2}       # route order from the bottom up: staging, main, upper
    bands.sort(key=lambda b: rank.get(b[0].split()[0], 9))
    schem.draw_page(bands, dict(mo, title=mo.get("system_title", mo["title"])), out)


if __name__ == "__main__":
    main(*sys.argv[1:6])
