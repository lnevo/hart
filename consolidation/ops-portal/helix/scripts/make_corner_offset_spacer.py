"""Corner offset spacers: full barrels under the wing corners at the bracket-0 butt joint.

The cork-to-plywood transition shim (2 in along the track x 3.5 in radial) sits in a cutout in
the deck under the seam. The subroadbed is 6 in wide, so 1.25 in wings overhang the shim on the
inside and outside. A barrel goes under each wing corner, and a screw passes down through the
roadbed and the barrel into the deck. The barrel holds the roadbed at height, so the screw
clamps against it instead of pulling the wing down.

  * P1 barrels = P1 underside above the deck at bracket 0 = 1-1/32 (P1 top, p1_height_template)
    - 0.72 measured plywood = 0.311 in, plus a 1.65 mm field correction (2026-10-15: the
    0.311 prints came out 1.65 mm short of the gap) = 0.376 in (9.56 mm). The height stack
    (p1_height_template + spacers) is the definitive roadbed TOP; underside = top - 0.72.
  * 5/8 in OD, 1/4 in hole (user, 2026-10-13: narrower to fit where it can, wider hole so the
    #6 screw has play). Print 100% infill to make up for the thin wall.
  * P1 corners only: the tongue is already held by entry_wedge_riser_inside/outside.stl.

Print 2. MEASURE both gaps first and change P1_GAP if they differ.

Prints as modeled, flat on the bed. No supports.
"""
import numpy as np
import trimesh
import router_template_lattice as lat
from stl_out import out_dir

IN = 25.4
FIELD_ADD = 1.65 / IN           # 2026-10-15: 0.311 prints were 1.65 mm too short
P1_GAP = 1 + 1 / 32 - 0.72 + FIELD_ADD   # 0.376 in (9.56 mm), deck top to P1 underside
OD = 5 / 8
HOLE = 1 / 4                    # #6 screw with play


def build(h):
    barrel = trimesh.creation.cylinder(radius=OD / 2 * IN, height=h * IN, sections=96)
    hole = trimesh.creation.cylinder(radius=HOLE / 2 * IN, height=h * IN + 2, sections=48)
    body = trimesh.boolean.difference([barrel, hole], engine="manifold")
    body.apply_translation(-body.bounds[0])
    return body


if __name__ == "__main__":
    OUT = out_dir(__doc__)
    for h in (P1_GAP,):
        body = build(h)
        path = OUT + "corner_spacer_P1.stl"
        body.export(path)
        print("watertight", body.is_watertight, "reload ok", lat.stl_roundtrip_ok(path),
              "bodies", len(body.split(only_watertight=False)), "size mm", np.round(body.extents, 3),
              "h in", round(h, 4))
