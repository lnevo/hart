"""Bracket plumb shim: fills the 3/32 pocket under the bracket's flat leg so the upright leg
hangs plumb instead of leaning with the helix grade (user, 2026-10-14).

The pocket floor is parallel to the roadbed, which climbs along the track. The flat leg runs
radially, so the grade tilts it SIDEWAYS: the bracket leans about 1.3 deg along the post face.
This strip tapers across its width by grade x width, so its bottom face is level.

  * grade at the pocket's mid radius (r 27.85, between 26 and 29.7): 4 / (2 pi r) = 2.29 %
    (2.45 % at r 26, 2.14 % at 29.7; one uniform taper is within 0.001 in)
  * width 0.62 in (pocket 0.6625) -> taper 0.0141 in (0.36 mm)
  * thin edge = BASE (one first layer, 0.2 mm), thick edge = BASE + taper = 0.56 mm
    The pocket has 0.0137 in (0.35 mm) to spare under the 0.080 strap, so the bracket ends up
    about 0.03 mm below the underside on average. Negligible.
  * length 3.5 in from the 26 in edge, 0.2 in center slot for the bracket screws
  * a notch in the THICK edge marks it: thick edge goes UPHILL

Same part for every bracket. Prints flat as modeled, sloped face up. With 0.08-0.1 mm layers
the slope prints as 3-4 steps of about 0.1 mm.
"""
import numpy as np
import trimesh
from shapely.geometry import Polygon
import router_template_lattice as lat

IN = 25.4
W = 0.62
L = 3.5
R_MID = 27.85
GRADE = 4 / (2 * np.pi * R_MID)
BASE = 0.2 / IN                     # slicer first-layer height
TAPER = GRADE * W
SLOT_W, SLOT_END = 0.2, 0.3
NOTCH = 0.06


def build():
    # Cross-section: u = across the width, v = thickness. Thick edge at u = 0 (notched).
    prof = Polygon(np.array([(0, 0), (W, 0), (W, BASE), (0, BASE + TAPER)]) * IN)
    body = trimesh.creation.extrude_polygon(prof, L * IN)       # extruded along z = length
    # (u, v, z) -> (x = length, y = width, z = thickness), flat on the bed.
    perm = np.array([[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=float)
    body.apply_transform(perm)
    slot = trimesh.creation.box([(L - 2 * SLOT_END) * IN, SLOT_W * IN, 4])
    slot.apply_translation([L / 2 * IN, W / 2 * IN, 0])
    notch = trimesh.creation.box([NOTCH * IN, 2 * NOTCH * IN, 4])
    notch.apply_translation([L / 2 * IN, 0, 0])
    return trimesh.boolean.difference([body, slot, notch], engine="manifold")


if __name__ == "__main__":
    body = build()
    path = "/Users/lnevo/Downloads/stl/bracket_plumb_shim.stl"
    body.export(path)
    v = body.vertices
    thick_y = v[np.argmax(v[:, 2]), 1]
    print("watertight", body.is_watertight, "reload ok", lat.stl_roundtrip_ok(path),
          "bodies", len(body.split(only_watertight=False)), "size mm", np.round(body.extents, 3),
          f"grade {GRADE:.4f} taper {TAPER:.4f} in, thin {BASE * IN:.2f} thick {(BASE + TAPER) * IN:.2f} mm",
          "thick edge at y mm", round(thick_y, 2))
