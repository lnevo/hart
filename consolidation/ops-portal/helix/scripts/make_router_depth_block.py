"""Double-sided plunge-to-bottom router depth block for the half-lap and bracket-pocket templates.

Straight-sided stand-in for the end of a roadbed blank. The template's lip hooks the
END face; its 26 in fence touches the INNER edge, which is a straight line tangent to
the 26 in circle inside both fences' span. Set the router on the template, plunge
until the bit bottoms in a well, lock. Well depth = depth cut into the wood.

Flipping the block over (end face stays against the lip) mirrors it, so one face
serves lap-B / pocket-A and the other lap-A / pocket-B. Top and bottom wells are
interleaved so they never overlap, and each face reads the same way, ascending outward:
row 1 (joint line, reachable through the templates) 3/32 -> 1/4 -> 3/8;
row 2 (router directly on the block) 1/2 -> 5/8 -> 3/4.
"""
from math import radians, sin, cos
import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely import affinity
from make_lap_template import IN, RI
from stl_text import text_polys, centered
from stl_out import out_dir

JOINT_DEG = 1.875       # wells on the nominal joint line (under lap window and pocket slot)
TANGENT_DEG = 5.8       # inner edge touches r=26 here: inside lap fence (4.1-8.5) and pocket fence (2.9-7.6)
BLOCK_T = 1.0           # > 0.5 lip/fence drop; leaves 1/4 in under the 3/4 in through-cut wells
OUTER_X = 32.5
FAR_Y = 4.1
WELL_D = 0.75
ENGRAVE = 0.5           # mm

WELL_PITCH = 0.85       # centre spacing, alternating faces -> 0.10 in wall between neighbours
# (face, depth), outward from the inner edge. 3/32 wells must be at r <= 29.7 (pocket slot).
WELLS = [("top", 3 / 32), ("bottom", 3 / 32), ("top", 0.25), ("bottom", 0.25), ("top", 3 / 8), ("bottom", 3 / 8)]
FIRST_R = 27.1          # centres the 6-well row between the inner (tangent) edge and OUTER_X
# Second row: 1/2, 5/8, 3/4 (router base directly on the block, no template). These are
# outside the lap window; for the 1/2 in lap with the 1/2 in lap template, hang the bit off
# the block edge and plunge to the bench: block thickness 1.0 = template 0.5 + cut 0.5.
# Interleaved between faces and ascending outward like the first row.
ROW2_Y = 2.45
ROW2 = [(f, d, FIRST_R + i * WELL_PITCH) for i, (f, d) in enumerate(
    [("top", 0.5), ("bottom", 0.5), ("top", 5 / 8), ("bottom", 5 / 8), ("top", 0.75), ("bottom", 0.75)])]
LABEL = {3 / 32: "3/32", 0.25: "1/4", 3 / 8: "3/8", 0.5: "1/2", 5 / 8: "5/8", 0.75: "3/4"}
FACE_LABEL = {"top": ("LAP B", "PKT A"), "bottom": ("LAP A", "PKT B")}

t = radians(TANGENT_DEG)
x_at = lambda y: (RI - y * sin(t)) / cos(t)          # tangent line x cos t + y sin t = RI
outline = Polygon([(x_at(0), 0), (OUTER_X, 0), (OUTER_X, FAR_Y), (x_at(FAR_Y), FAR_Y)])


def mm(g):
    return affinity.scale(g, IN, IN, origin=(0, 0))


def prism(g, h, z0):
    out = []
    for poly in getattr(g, "geoms", [g]):
        m = trimesh.creation.extrude_polygon(poly, h)
        m.apply_translation([0, 0, z0])
        out.append(m)
    return out


top_z = BLOCK_T * IN
body = trimesh.creation.extrude_polygon(mm(outline), top_z)
cuts = []
well_list = [(f, d, (FIRST_R + i * WELL_PITCH) * cos(radians(JOINT_DEG)),
              (FIRST_R + i * WELL_PITCH) * sin(radians(JOINT_DEG))) for i, (f, d) in enumerate(WELLS)]
well_list += [(f, d, x, ROW2_Y) for f, d, x in ROW2]
for face, d, x, y in well_list:
    disk = mm(Point(x, y).buffer(WELL_D / 2, 128))
    ly = (y + WELL_D / 2 + 0.3) * IN
    label = centered(text_polys(LABEL[d], 3.4), x * IN, ly)
    if face == "top":
        cuts += prism(disk, d * IN + 1, top_z - d * IN)
        cuts += prism(label, ENGRAVE + 1, top_z - ENGRAVE)
    else:
        cuts += prism(disk, d * IN + 1, -1)
        # mirrored so it reads correctly once the block is flipped
        cuts += prism(affinity.scale(label, 1, -1, origin=(x * IN, ly)), ENGRAVE + 1, -1)
for face, z0 in (("top", top_z - ENGRAVE), ("bottom", -1)):
    for i, s in enumerate(FACE_LABEL[face]):
        cx, cy = (28.0 + 2.6 * i) * IN, 3.7 * IN
        g = centered(text_polys(s, 4.0), cx, cy)
        if face == "bottom":
            g = affinity.scale(g, 1, -1, origin=(cx, cy))
        cuts += prism(g, ENGRAVE + 1, z0)

block = trimesh.boolean.difference([body] + cuts, engine="manifold")

if __name__ == "__main__":
    OUT = out_dir(__doc__)
    # Print standing on the END face: well floors become vertical walls (no bridging sag)
    # and the registration face prints flat on the bed.
    printed = block.copy()
    printed.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    printed.apply_translation(-printed.bounds[0])
    out = OUT + "router_depth_block.stl"
    printed.export(out)
    print(out, "watertight", printed.is_watertight, "bodies", len(printed.split(only_watertight=False)),
          "size mm", np.round(printed.extents, 1), "vol cm3", round(printed.volume / 1000, 1))
