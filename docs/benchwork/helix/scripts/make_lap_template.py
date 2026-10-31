"""Half-lap router template for the 93.75 deg helix roadbed blanks (26 / 31.75 in radii).

Registers on the blank's radial END face (lip) and its 26 in INNER arc (fence),
and gives a radial shoulder exactly 3.75 deg back from the end, so every lap
is identical. Router depth (1/4 in top lap or 1/2 in bottom lap) is set on the router.

Lattice plate + 100 % core modifier + two screw holes: see router_template_lattice.py.

GUIDE_OFFSET = 0     -> top-bearing pattern / flush-trim bit (bearing = cutter dia)
GUIDE_OFFSET = (bushing_OD - bit_dia) / 2  -> guide bushing
"""
from math import radians, degrees, cos, sin
import numpy as np
import trimesh
from shapely.geometry import Polygon, LineString
from shapely import affinity
from shapely.ops import unary_union
import router_template_lattice as lat
from stl_out import out_dir

IN = 25.4
GUIDE_OFFSET = 0.0          # inches, see docstring
RI, RO = 26.0, 31.75        # roadbed radii (nominal)
RO_MAX = 32.25              # widest outer edge the window must clear (blank may run to 32 in)
LAP_DEG = 3.75              # full adjacent overlap
PLATE_T = 0.5               # template thickness (bearing rides this edge)
BLOCK_H = 0.5               # lip / fence height (< plywood thickness)
BLOCK_W = 0.5               # lip / fence width
WIN_MARGIN = 0.5            # window runs past inner/outer edges so the bit runs off clean
RAIL = 2.4                  # plate width beyond each side of the window (router base support)
PLATE_RI, PLATE_RO = RI - WIN_MARGIN - 0.25, RO_MAX + WIN_MARGIN + 0.25
LIP_SPANS = [(25.75, 27.0), (30.25, 31.5)]   # lip pads; both inside every blank's end face (26 to 31.75+)
SCREW_R = (26.75, 31.0)     # #6 x 1 in flat head, 1/2 in into the blank


def sector(r0, r1, a0, a1, n=240):
    """Annular sector in inches, angles in degrees, end lines radial."""
    a = np.radians(np.linspace(a0, a1, n))
    outer = np.c_[r1 * np.cos(a), r1 * np.sin(a)]
    inner = np.c_[r0 * np.cos(a[::-1]), r0 * np.sin(a[::-1])]
    return Polygon(np.vstack([outer, inner]))


def band_past_line(r0, r1, width):
    """Strip lying on the negative-y side of the radial end line (the x-axis, y=0)."""
    return Polygon([(r0, 0), (r1, 0), (r1, -width), (r0, -width)])


# Local frame: blank's end face is the radial line along +x (angle 0);
# the blank body runs toward positive angles. Lap = angles 0..LAP_DEG.
mean_r = (PLATE_RI + PLATE_RO) / 2
rail_deg = degrees(RAIL / mean_r)

window = sector(RI - WIN_MARGIN, RO_MAX + WIN_MARGIN, 0.0, LAP_DEG)
if GUIDE_OFFSET:
    window = window.buffer(GUIDE_OFFSET, join_style=2)

# Plate: shoulder-side rail is a sector; end-side rail is a straight band past the end line
# (keeps the lip face and window end edge exactly on the radial end line).
plate = sector(PLATE_RI, PLATE_RO, 0.0, LAP_DEG + rail_deg).union(
    band_past_line(PLATE_RI, PLATE_RO, RAIL)).difference(window)

# Lip = two pads hooking the end face (inner and outer) instead of one full-length bar.
lip = unary_union([band_past_line(r0, r1, BLOCK_W) for r0, r1 in LIP_SPANS])
# Inner-arc fence under the shoulder-side rail, kept 0.15 in clear of the window.
fence = sector(RI - BLOCK_W, RI, LAP_DEG + degrees(0.15 / RI), LAP_DEG + rail_deg)
# Screws into the blank past the shoulder (outside the lap), clear of the solid core band.
screws = [(r * cos(radians(a)), r * sin(radians(a))) for r in SCREW_R
          for a in [LAP_DEG + degrees((lat.CORE_W + lat.BOSS_R + 0.4) / r)]]


def build(mirror, name=""):
    lines = [(f"HALF-LAP {name}", 1.0), ("LOWER 1/4  |  UPPER 1/2", 0.8),
             (f"PAIRS W/ POCKET {name}", 0.7), ("#6 x 1in FLAT HEAD", 0.7)] if name else None
    # Label on the rail past the end cut (beyond the lip pads).
    label_xy = ((PLATE_RI + PLATE_RO) / 2, -(BLOCK_W + RAIL) / 2 - 0.1)
    return lat.build(plate, window, lip, fence, screws, PLATE_T, BLOCK_H, lines, label_xy, 6.0, mirror)


if __name__ == "__main__":
    OUT = out_dir(__doc__)
    for name, mir in (("A", False), ("B", True)):
        body, core = build(mir, name)
        lat.export(f"{OUT}roadbed_halflap_template_{name}", body, core)
