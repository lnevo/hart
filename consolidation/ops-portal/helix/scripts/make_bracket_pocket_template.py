"""Bracket-pocket router template, registered like the half-lap template.

Routes the 3/32 in pocket for the 4x4 steel brace in the UNDERSIDE of the lower
member (the piece whose TOP was lapped), centered on the nominal 90 deg joint
line = 1.875 deg back from the end face, running radially off the 26 in inner edge.

Registers on the blank's radial END face (lip) and 26 in INNER arc (fence).
Pocket file letter matches the lap template letter that fit your blanks
(the pocket is cut on the opposite face, so its hand is mirrored internally).

Lattice plate + 100 % core modifier + two screw holes: see router_template_lattice.py.
"""
from math import radians, degrees, cos, sin
import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely import affinity
from make_lap_template import IN, GUIDE_OFFSET, RI, sector, band_past_line
from shapely.ops import unary_union
import router_template_lattice as lat

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
LIP_SPANS = [(25.75, 27.0), (29.5, 30.75)]    # lip pads on the end face
SCREW_R = (26.75, 30.0)     # #6 x 1-1/4 in flat head, 1/2 in into the blank

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
# Lip = two pads hooking the end face (inner and outer) instead of one full-length bar.
lip = unary_union([band_past_line(a, b, BLOCK_W) for a, b in LIP_SPANS])
fence = sector(RI - BLOCK_W, RI, JOINT_DEG + degrees((half_w + 0.15) / RI), far_deg)
# Screws into the full-thickness blank past the lap (> 3.75 deg), clear of the solid core band.
screws = [(r * cos(radians(a)), r * sin(radians(a))) for r in SCREW_R
          for a in [JOINT_DEG + degrees((half_w + lat.CORE_W + lat.BOSS_R + 0.45) / r)]]


def build(mirror, name=""):
    lines = [(f"BRACKET POCKET {name}", 1.0), ("3/32 DEEP - LOWER PC UNDERSIDE", 0.7),
             (f"PAIRS W/ HALF-LAP {name}", 0.7), ("#6 x 1-1/4in FLAT HEAD", 0.7)] if name else None
    # Label on the rail past the end cut (beyond the lip pads).
    label_xy = ((PLATE_RI + PLATE_RO) / 2, -(BLOCK_W + RAIL) / 2 - 0.1)
    return lat.build(plate, window, lip, fence, screws, PLATE_T, BLOCK_H, lines, label_xy, 5.5, mirror)


if __name__ == "__main__":
    # Opposite hand from the lap template with the same letter (routed on the other face).
    for name, mir in (("A", True), ("B", False)):
        body, core = build(mir, name)
        lat.export(f"/Users/lnevo/Downloads/stl/bracket_pocket_template_{name}", body, core)
