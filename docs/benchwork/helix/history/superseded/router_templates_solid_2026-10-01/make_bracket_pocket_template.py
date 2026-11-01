"""Bracket-pocket router template, registered like the half-lap template.

Routes the 3/32 in pocket for the 4x4 steel brace in the UNDERSIDE of the lower
member (the piece whose TOP was lapped), centered on the nominal 90 deg joint
line = 1.875 deg back from the end face, running radially off the 26 in inner edge.

Registers on the blank's radial END face (lip) and 26 in INNER arc (fence).
Pocket file letter matches the lap template letter that fit your blanks
(the pocket is cut on the opposite face, so its hand is mirrored internally).
"""
from math import radians, degrees
import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely import affinity
from make_lap_template import IN, GUIDE_OFFSET, RI, sector, band_past_line
from stl_text import label_cutters

JOINT_DEG = 1.875           # nominal joint line, measured from the end face
STRAP_W = 0.600             # measured brace strap width
SIDE_CLEAR = 1 / 32         # per side (PDF 9)
BRACKET_TIP_R = 29.7258     # 4 in leg tip radius (PDF 9)
TIP_CLEAR = 0.22            # past the tip so a 1/2 in bit's rounded end clears square strap corners
RUN_OFF = 0.5               # window runs past the 26 in inner edge
PLATE_T = 0.75              # thicker than the lap template: 3/32 depth keeps the bearing high
BLOCK_H = 0.5
BLOCK_W = 0.5
RAIL = 2.5                  # plate beyond the window on both sides (router base support)
PLATE_RI, PLATE_RO = RI - RUN_OFF - 0.25, BRACKET_TIP_R + TIP_CLEAR + 1.0

half_w = STRAP_W / 2 + SIDE_CLEAR
r0, r1 = RI - RUN_OFF, BRACKET_TIP_R + TIP_CLEAR

# Window = strip along the radial joint line (built along +x, then rotated to JOINT_DEG).
window = affinity.rotate(Polygon([(r0, -half_w), (r1, -half_w), (r1, half_w), (r0, half_w)]),
                         JOINT_DEG, origin=(0, 0))
if GUIDE_OFFSET:
    window = window.buffer(GUIDE_OFFSET, join_style=2)

mean_r = (PLATE_RI + PLATE_RO) / 2
far_deg = JOINT_DEG + degrees((half_w + RAIL) / mean_r)
plate = sector(PLATE_RI, PLATE_RO, 0.0, far_deg).union(
    band_past_line(PLATE_RI, PLATE_RO, RAIL)).difference(window)
lip = band_past_line(PLATE_RI, PLATE_RO, BLOCK_W)
fence = sector(RI - BLOCK_W, RI, JOINT_DEG + degrees((half_w + 0.15) / RI), far_deg)


def extrude(poly, h, z0):
    m = trimesh.creation.extrude_polygon(poly, h * IN)
    m.apply_translation([0, 0, z0 * IN])
    return m


def build(mirror, name=""):
    polys = [plate, lip, fence]
    if mirror:
        polys = [affinity.scale(p, xfact=1, yfact=-1, origin=(0, 0)) for p in polys]
    scaled = [affinity.scale(p, IN, IN, origin=(0, 0)) for p in polys]
    # Printed plate-down: plate z=0..T, lip/fence stick UP (flip over to use).
    parts = [extrude(scaled[0], PLATE_T, 0),
             extrude(scaled[1], PLATE_T + BLOCK_H, 0),
             extrude(scaled[2], BLOCK_H, PLATE_T)]
    m = trimesh.boolean.union(parts, engine="manifold")
    if name:
        # Engrave the router-side face (on the bed when printed), mirrored so it reads
        # correctly once flipped for use. Placed on the rail past the end cut.
        c = scaled[1].centroid
        cy = c.y + (-1 if not mirror else 1) * ((RAIL + BLOCK_W) / 2) * IN
        lines = [(f"BRACKET POCKET {name}", 1.0), ("3/32 DEEP - LOWER PC UNDERSIDE", 0.7),
                 (f"PAIRS W/ HALF-LAP {name}", 0.7)]
        m = trimesh.boolean.difference([m] + label_cutters(lines, c.x, cy, 5.5, -1, 1.6, mirror_x=True),
                                       engine="manifold")
    m.apply_translation(-m.bounds[0] * [1, 1, 0])
    return m


if __name__ == "__main__":
    # Opposite hand from the lap template with the same letter (routed on the other face).
    for name, mir in (("A", True), ("B", False)):
        m = build(mir, name)
        out = f"/Users/lnevo/Downloads/stl/bracket_pocket_template_{name}.stl"
        m.export(out)
        print(out, "watertight", m.is_watertight, "bodies", len(m.split(only_watertight=False)),
              "size mm", np.round(m.extents, 1))
