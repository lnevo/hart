"""Mid-piece bracket-pocket router template (odd-n brackets, 45 deg from each joint line).

Same 3/32 in pocket slot as the joint pocket template (0.6625 in wide, r 25.5 -> 29.95,
1/2 in top-bearing bit, 3/4 in plate), but for the middle of a piece:
  * NO end lip. The template rides the 26 in INSIDE edge only (two fence segments,
    one each side of the slot) and is positioned along the arc by its centerline:
    pencil line visible through both ends of the slot + a V-notch in the outer edge.
  * Two #6 countersunk screw holes (one each side) pin it once it's centered.
  * Symmetric about the slot centerline, so ONE template serves every piece (no A/B hand).
  * Solid plate, no lattice. Proportions match the joint pocket template: inner arc
    r 25.25, outer r 30.95, 2.5 in rails, 1/2 x 1/2 in fence on the 26 in arc.

Printed router face down (fence up), no supports.
Template + 100 % core modifier 3MF via router_template_lattice.export().
"""
from math import degrees, sqrt
import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union
import router_template_lattice as lat
from make_lap_template import IN, RI, sector
from make_bracket_pocket_template import (STRAP_W, SIDE_CLEAR, BRACKET_TIP_R, TIP_CLEAR, RUN_OFF, PLATE_T,
                                          BLOCK_H, BLOCK_W, RAIL, PLATE_RI, PLATE_RO)
from stl_text import label_cutters
from stl_out import out_dir

SCREWS_R = 27.0             # #6 x 1-1/4 in flat head, 1/2 in into the blank
NOTCH_DEPTH, NOTCH_W = 0.3, 0.3
FENCE_CLEAR = 0.15          # fence stays this far from the slot (as on the joint templates)

half_w = STRAP_W / 2 + SIDE_CLEAR
r0, r1 = RI - RUN_OFF, BRACKET_TIP_R + TIP_CLEAR

# Local frame: slot centerline on +x (helix centre at origin), plate symmetric in y.
window = Polygon([(r0, -half_w), (r1, -half_w), (r1, half_w), (r0, half_w)])
theta = degrees((half_w + RAIL) / ((PLATE_RI + PLATE_RO) / 2))
notch = Polygon([(PLATE_RO + 0.1, -NOTCH_W / 2 - 0.1 * NOTCH_W / NOTCH_DEPTH), (PLATE_RO - NOTCH_DEPTH, 0),
                 (PLATE_RO + 0.1, NOTCH_W / 2 + 0.1 * NOTCH_W / NOTCH_DEPTH)])
plate = sector(PLATE_RI, PLATE_RO, -theta, theta).difference(window).difference(notch)
fence_deg = degrees((half_w + FENCE_CLEAR) / RI)
fence = unary_union([sector(RI - BLOCK_W, RI, fence_deg, theta), sector(RI - BLOCK_W, RI, -theta, -fence_deg)])
screw_dy = half_w + lat.CORE_W + lat.BOSS_R + 0.45
screws = [(sqrt(SCREWS_R ** 2 - screw_dy ** 2), s * screw_dy) for s in (-1, 1)]


def build():
    t, h = PLATE_T * IN, BLOCK_H * IN
    core = window.buffer(lat.CORE_W, join_style=2).intersection(plate).difference(window)
    parts = lat._prisms(lat._mm(plate), t, 0) + lat._prisms(lat._mm(fence), h, t)
    cuts = []
    for x, y in screws:
        cuts += lat._countersunk_hole(x * IN, y * IN, t)
    # Underside label (wood face, top as printed), read from the underside, text along the slot.
    side = [("MID-PIECE POCKET", 1.0), ('3/32" DEEP - UNDERSIDE', 0.75)]
    other = [("CENTER ON 46.875° LINE", 0.75), ('#6 x 1-1/4" FLAT HEAD', 0.75)]
    for lines, sy in ((side, 1), (other, -1)):
        cuts += label_cutters(lines, 28.9 * IN, sy * 1.85 * IN, 5.0, t - lat.ENGRAVE, lat.ENGRAVE + 1)
    body = trimesh.boolean.union(parts, engine="manifold")
    body = trimesh.boolean.difference([body] + cuts, engine="manifold")
    core_m = trimesh.boolean.union(lat._prisms(lat._mm(core), t, 0), engine="manifold")
    shift = -body.bounds[0] * [1, 1, 0]
    body.apply_translation(shift)
    core_m.apply_translation(shift)
    return body, core_m


if __name__ == "__main__":
    OUT = out_dir(__doc__)
    body, core = build()
    lat.export(OUT + "bracket_pocket_template_MID", body, core)
    print("plate half-angle deg", round(theta, 3), "screws", np.round(screws, 3))
