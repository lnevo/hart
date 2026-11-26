"""Bracket edge shim: fills the gap between the 26 in inside edge and the 2x4 face.

For screwing the 4x4 brackets to the roadbed underside BEFORE the roadbed goes on the posts.
The bracket's flat leg sits in the 3/32 in pocket and its upright leg hangs down along the
2x4. Above the bracket's bend, between the plywood edge (r 26) and the 2x4 face (r 25.7258),
is an open gap. This shim fills it: curved face (r 26) against the plywood edge, flat face
coplanar with the back of the bracket's upright leg, bottom resting on the flat leg.
Align the bracket's back flush with the shim's flat face, screw the flat leg into the pocket,
and later the bracket back + shim bear flat on the 2x4 face.

  * height = 0.72 in plywood - 3/32 in pocket = 0.62625 in (pocket floor to roadbed top)
  * width  = 1.5 in on the flat face (user, 2026-10-13)
  * thickness = 26 - 25.7258 = 0.2742 in on the centerline, 0.2634 at the ends (r 26 sag 0.011 in)
  * bracket notch in the flat face (user, 2026-10-13): the bracket's upright leg rides the 2x4
    face up through the shim, so the shim straddles it and still bears on the 2x4 both sides.
    0.6625 in wide (0.600 strap + 1/32 per side, like the pocket), 0.085 in deep (0.080 steel
    + 0.005), full height, with a 0.10 in x 45 deg chamfer at its bottom back edge for the
    bracket's inside bend

No labels (removed at the user's request, 2026-10-13).

Printed standing on its bottom edge (38 x 7 mm footprint), so the notch runs straight up. No supports.
"""
import numpy as np
import trimesh
from shapely.geometry import Polygon
import router_template_lattice as lat
from make_lap_template import IN, RI
from stl_out import out_dir

PLY_T = 0.72                    # measured plywood
POCKET = 3 / 32
H = PLY_T - POCKET              # 0.62625 in
WIDTH = 1.5                     # flat (2x4) face width, user 2026-10-13
POST_FACE_R = 25.7258           # 2x4 face = back of the bracket's upright leg (PDF 9)
NOTCH_W = 0.600 + 2 / 32
NOTCH_D = 0.080 + 0.005
BEND = 0.10                     # chamfer leg for the bracket's inside bend


def build():
    y = np.linspace(-WIDTH / 2, WIDTH / 2, 61)
    arc = np.c_[np.sqrt(RI ** 2 - y ** 2), y]
    top = Polygon(np.vstack([[(POST_FACE_R, WIDTH / 2), (POST_FACE_R, -WIDTH / 2)], arc]))
    body = lat._prisms(lat._mm(top), H * IN, 0)[0]
    # Bracket notch, full height, in the flat face.
    notch = trimesh.creation.box([NOTCH_D * IN + 1, NOTCH_W * IN, H * IN + 2])
    notch.apply_translation([(POST_FACE_R + NOTCH_D / 2) * IN - 0.5, 0, H * IN / 2])
    # Inside-bend chamfer along the bottom back edge of the notch.
    c = BEND * IN * np.sqrt(2)
    bar = trimesh.creation.box([c, NOTCH_W * IN, c])
    bar.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 4, [0, 1, 0]))
    bar.apply_translation([(POST_FACE_R + NOTCH_D) * IN, 0, 0])
    body = trimesh.boolean.difference([body, notch, bar], engine="manifold")
    # Stands on its bottom edge as built (z = 0 on the bed).
    body.apply_translation(-body.bounds[0])
    return body


if __name__ == "__main__":
    OUT = out_dir(__doc__)
    body = build()
    base = OUT + "bracket_edge_shim"
    body.export(base + ".stl")
    print("watertight", body.is_watertight, "reload ok", lat.stl_roundtrip_ok(base + ".stl"),
          "bodies", len(body.split(only_watertight=False)), "size mm", np.round(body.extents, 3),
          "H in", H, "thick in", round(RI - POST_FACE_R, 4), round(np.sqrt(RI ** 2 - (WIDTH / 2) ** 2) - POST_FACE_R, 4))
