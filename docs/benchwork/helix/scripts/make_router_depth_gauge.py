"""Stepped router depth gauge for the half-lap and bracket-pocket templates.

Each step height = the depth cut into the wood (template thickness NOT included).

Setting: router upside down, lay the template you'll use on the router base with the
bit poking up through its window, stand the gauge ON THE TEMPLATE next to the bit,
and raise the bit until its tip is flush with the step. Also drops into a finished
cut to check it.

LOWER piece: cut 1/4 in off the top  -> 1/2 in left; pocket 3/32 in in its underside.
UPPER piece: cut 1/2 in off the bottom -> 1/4 in left.
"""
import numpy as np
import trimesh
from shapely.geometry import box
from shapely.ops import unary_union
from stl_text import text_polys, centered
from stl_out import out_dir

IN = 25.4
STEP_W, DEPTH = 1.0, 1.25     # inches
ENGRAVE = 0.5                 # mm

# (height in, line 1, line 2)
STEPS = [
    (3 / 32, "POCKET", "3/32 CUT"),
    (0.25,   "LOWER",  "1/4 CUT"),
    (0.5,    "UPPER",  "1/2 CUT"),
]


parts, cuts = [], []
for i, (h, l1, l2) in enumerate(STEPS):
    x0 = i * STEP_W * IN
    w, d, hz = STEP_W * IN, DEPTH * IN, h * IN
    parts.append(trimesh.creation.extrude_polygon(box(x0, 0, x0 + w, d), hz))
    cx = x0 + w / 2
    lines = [l1, l2, f'{h:.3f}"'] if l2 else [l1, f'{h:.3f}"']
    ys = np.linspace(d * 0.75, d * 0.25, len(lines))
    for s, y in zip(lines, ys):
        g = text_polys(s, 3.6 if '"' not in s else 3.0)
        g = centered(g, cx, y)
        for poly in getattr(g, "geoms", [g]):
            m = trimesh.creation.extrude_polygon(poly, ENGRAVE + 0.2)
            m.apply_translation([0, 0, hz - ENGRAVE])
            cuts.append(m)

block = trimesh.boolean.union(parts, engine="manifold")
block = trimesh.boolean.difference([block] + cuts, engine="manifold")

if __name__ == "__main__":
    OUT = out_dir(__doc__)
    out = OUT + "router_depth_gauge.stl"
    block.export(out)
    print(out, "watertight", block.is_watertight, "bodies", len(block.split(only_watertight=False)),
          "size mm", np.round(block.extents, 2))
    for h, l1, l2 in STEPS:
        print(f"{l1} {l2}: {h:.5f} in = {h * IN:.3f} mm")
