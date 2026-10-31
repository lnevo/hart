"""Check / deposit-slip stamp jig: holds the stamper in a fixed spot relative to the slip's corner.

Use: lay the slip face up on the table. Set the jig on top of it and slide it up-and-left until
the slip's top edge and left edge both touch the two lips on the underside (the zero corner).
Drop the stamper into the pocket and stamp. The slip slides in under the jig through the
LIP_H gap on the open right and bottom sides.

  * Zero corner = inside faces of the top lip and left lip. A small relief hole at the inside
    corner keeps a rounded or dog-eared slip corner from holding the slip off either lip.
  * Pocket = stamper footprint + CLR per side, placed so a centred stamper's top-left corner
    is OFFSET_RIGHT right of the left lip and OFFSET_DOWN down from the top lip.
  * Logo window framing the slip's printed TD logo with an even LOGO_BORDER all round: an
    even margin means the slip is seated in the corner; a lopsided one means it isn't.
  * An L foot under the far (bottom-right) corner wall so the jig doesn't tip off the L of lips.
    It lands on the slip, which is fine.

v2 SIZES (2026-10-18): 3.36 x 1.62 in housing; lettering at 0.77 in right / 1.4 in down;
first character 0.4 in right and down from the housing corner, so the housing sits 0.37 right / 1.0 down.
v3: test print stamped 0.06 in too far left and 0.04 in too low; housing now 0.43 right / 0.96 down.
v4: 0.01 in more to the right; housing 0.44 right / 0.96 down.
v5: v4 stamped 0.1 in too high; housing 0.44 right / 1.06 down.

Model is in use orientation (x right, y up = toward the slip's top edge, corner at origin).
The exported STL is flipped for printing: the flat top face goes on the bed, lips and foot
point up. No supports.
"""
import os
import sys
import numpy as np
import trimesh
from shapely.geometry import box
from shapely import affinity

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../www/helix/scripts"))
import stl_text
import router_template_lattice as lat

IN = 25.4
STAMP_LONG = 3.36       # in, stamper housing left-to-right on the slip (2026-10-18)
STAMP_SHORT = 1.62      # in, stamper housing top-to-bottom on the slip
SLIP_H = 3.39           # in, check top-to-bottom (fit check only)
LETTER_RIGHT = 0.77     # in, slip left edge -> first character's left edge (target)
LETTER_DOWN = 1.4       # in, slip top edge -> first character's top edge (target)
IMG_RIGHT = 0.4         # in, housing left edge -> first character's left edge
IMG_DOWN = 0.4          # in, housing top edge -> first character's top edge
FIELD_RIGHT = 0.07      # in, 2026-10-18 test prints: 0.06 right, then 0.01 more
FIELD_DOWN = 0.06       # in, 0.04 up, then 0.1 down (net 0.06 down)
OFFSET_RIGHT = LETTER_RIGHT - IMG_RIGHT + FIELD_RIGHT   # in, slip left edge -> housing left (0.44)
OFFSET_DOWN = LETTER_DOWN - IMG_DOWN + FIELD_DOWN       # in, slip top edge -> housing top (1.06)
CLR = 0.4               # mm per side, stamper in pocket
GUIDE_H = 5.0           # mm, slab thickness = pocket wall height guiding the stamper
LIP_H = 2.0             # mm, lips below the slab = gap the slip slides through
LIP_T = 4.0             # mm, lip width
WALL = 5.0              # mm, slab beyond the pocket on the right and bottom
RELIEF_D = 2.0          # mm, corner relief hole
LOGO_RIGHT = 0.47       # in, slip left edge -> TD logo left edge
LOGO_DOWN = 0.27        # in, slip top edge -> TD logo top edge
LOGO_SIZE = 0.45        # in, logo is square
LOGO_BORDER = 1.5       # mm, window margin around the logo on every side
FOOT_L = 12.0           # mm, each leg of the L foot
LABEL_DEPTH = 0.6       # mm


def build():
    ox, oy = OFFSET_RIGHT * IN, OFFSET_DOWN * IN
    sl, ss = STAMP_LONG * IN, STAMP_SHORT * IN
    # pocket, y negative = down the slip
    px0, px1 = ox - CLR, ox + sl + CLR
    py0, py1 = -(oy + ss + CLR), -(oy - CLR)
    x0, x1 = -LIP_T, px1 + WALL
    y0, y1 = py0 - WALL, LIP_T
    z_slab = LIP_H

    slab = box(x0, y0, x1, y1).difference(box(px0, py0, px1, py1))
    assert -y0 < SLIP_H * IN, "jig hangs past the bottom of the slip"
    # logo window: the logo square plus an even border
    wx0, wx1 = LOGO_RIGHT * IN - LOGO_BORDER, (LOGO_RIGHT + LOGO_SIZE) * IN + LOGO_BORDER
    wy1, wy0 = -LOGO_DOWN * IN + LOGO_BORDER, -(LOGO_DOWN + LOGO_SIZE) * IN - LOGO_BORDER
    assert min(wx0, -wy1) >= 3 and (wy0 - py1 >= 3 or px0 - wx1 >= 3), "logo window too close"
    slab = slab.difference(box(wx0, wy0, wx1, wy1))
    band_top = py1 if wx0 >= px0 else min(py1, wy0 - 3)
    body = trimesh.creation.extrude_polygon(slab, GUIDE_H)
    body.apply_translation([0, 0, z_slab])

    parts = [body]
    top_lip = trimesh.creation.extrude_polygon(box(x0, 0, x1, y1), LIP_H + 0.01)
    left_lip = trimesh.creation.extrude_polygon(box(x0, y0, 0, y1), LIP_H + 0.01)
    # L-shaped foot kept under the corner wall so it can't reach into the pocket
    foot_g = box(x1 - FOOT_L, y0, x1, py0 - 0.5).union(box(px1 + 0.5, y0, x1, y0 + FOOT_L))
    foot = trimesh.creation.extrude_polygon(foot_g, LIP_H + 0.01)
    parts += [top_lip, left_lip, foot]
    jig = trimesh.boolean.union(parts, engine="manifold")

    relief = trimesh.creation.cylinder(radius=RELIEF_D / 2, height=LIP_H * 2 + 1, sections=32)
    cuts = [relief]

    # label on the top face, in the left band under the sight window, reading bottom-to-top
    label = f"{LETTER_RIGHT:g}R {LETTER_DOWN:g}D"
    g = stl_text.text_polys(label, 3.5)
    g = affinity.rotate(g, 90, origin=(0, 0))
    band_cx = (x0 + px0) / 2
    band_cy = (band_top + y0) / 2
    g = stl_text.centered(g, band_cx, band_cy)
    for poly in getattr(g, "geoms", [g]):
        m = trimesh.creation.extrude_polygon(poly, LABEL_DEPTH + 0.5)
        m.apply_translation([0, 0, z_slab + GUIDE_H - LABEL_DEPTH])
        cuts.append(m)
    jig = trimesh.boolean.difference([jig] + cuts, engine="manifold")
    return jig, (px0, px1, py0, py1)


if __name__ == "__main__":
    jig, pocket = build()
    # flip for printing: top face on the bed
    jig.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    jig.apply_translation(-jig.bounds[0])
    jig = lat.clean(jig)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_stamp_jig_v5.stl")
    jig.export(out)
    print("watertight", jig.is_watertight, "reload ok", lat.stl_roundtrip_ok(out),
          "bodies", len(jig.split(only_watertight=False)), "size mm", np.round(jig.extents, 1),
          "vol cm3", round(jig.volume / 1000, 1))
    print("pocket mm  x", np.round(pocket[:2], 2), " y", np.round(pocket[2:], 2))
