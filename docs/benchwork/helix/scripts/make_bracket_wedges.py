"""Bracket pocket wedges: tapered shims under the bracket's flat leg, so the upright leg sits
flat on the post (user, 2026-10-14: brackets "a bit out of whack").

The bracket is screwed to the roadbed through the flat leg in the 3/32 pocket. If the bend
isn't exactly 90 deg, the upright leg tips toward or away from the 2x4. A wedge between the
flat leg and the pocket floor rotates the bracket. Both legs are 4 in, so a gap g at the
bottom of the 4 in upright leg needs a taper of g x (wedge length / 4) along the flat leg.
The wedge is named by the GAP it fixes.

Orientation (flip the wedge end for end to correct the other way):
  * bottom of the upright leg stands OFF the post -> thick end toward the bracket tip (outer)
  * bottom of the leg hits the post, top stands off -> thick end toward the post (inner)

  * width 0.62 in (pocket 0.6625), length 3.5 in, from the 26 in edge toward the tip
  * thin end 0.5 mm; thick end = thin + taper
  * 0.2 in center slot (0.3 in from each end) so the bracket screws pass wherever its holes are
  * notches on one long edge at the thick end: count = gap in 64ths

Printed standing on the un-notched long edge, so the taper is drawn in XY (smooth, no layer
steps) and the slot is a short bridge. No supports.
"""
import numpy as np
import trimesh
from shapely.geometry import Polygon
import router_template_lattice as lat
from stl_out import out_dir

IN = 25.4
W = 0.62
L = 3.5
LEG = 4.0
T0 = 0.5 / IN
SLOT_W, SLOT_END = 0.2, 0.3
NOTCH_W, NOTCH_D, NOTCH_GAP = 0.04, 0.06, 0.1
GAPS = (1, 2, 3, 4)                 # in 64ths


def build(g64):
    t1 = T0 + g64 / 64 * L / LEG
    # Wedge profile in the print XY plane: x = length, y = thickness; z = width (standing on edge).
    prof = Polygon([(0, 0), (L, 0), (L, t1), (0, T0)])
    body = trimesh.creation.extrude_polygon(Polygon(np.array(prof.exterior.coords) * IN), W * IN)
    cuts = []
    slot = trimesh.creation.box([(L - 2 * SLOT_END) * IN, 1 * IN, SLOT_W * IN])
    slot.apply_translation([L / 2 * IN, 0, W / 2 * IN])
    cuts.append(slot)
    for i in range(g64):
        n = trimesh.creation.box([NOTCH_W * IN, 1 * IN, 2 * NOTCH_D * IN])
        n.apply_translation([(L - 0.15 - i * NOTCH_GAP) * IN, 0, W * IN])
        cuts.append(n)
    return trimesh.boolean.difference([body] + cuts, engine="manifold"), t1


if __name__ == "__main__":
    OUT = out_dir(__doc__)
    for g in GAPS:
        body, t1 = build(g)
        path = f"{OUT}bracket_wedge_gap_{g}_64.stl"
        body.export(path)
        print(path.split("/")[-1], "watertight", body.is_watertight, "reload ok", lat.stl_roundtrip_ok(path),
              "bodies", len(body.split(only_watertight=False)), "size mm", np.round(body.extents, 2),
              f"thin {T0:.4f} thick {t1:.4f} in")
