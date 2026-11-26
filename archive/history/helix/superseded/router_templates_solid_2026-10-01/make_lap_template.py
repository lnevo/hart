"""Half-lap router template for the 93.75 deg helix roadbed blanks (26 / 31.75 in radii).

Registers on the blank's radial END face (lip) and its 26 in INNER arc (fence),
and gives a radial shoulder exactly 3.75 deg back from the end, so every lap
is identical. Router depth (1/4 in top lap or 1/2 in bottom lap) is set on the router.

GUIDE_OFFSET = 0     -> top-bearing pattern / flush-trim bit (bearing = cutter dia)
GUIDE_OFFSET = (bushing_OD - bit_dia) / 2  -> guide bushing
"""
from math import radians, degrees
import numpy as np
import trimesh
from shapely.geometry import Polygon, LineString
from shapely import affinity
from stl_text import label_cutters

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

lip = band_past_line(PLATE_RI, PLATE_RO, BLOCK_W)
# Inner-arc fence under the shoulder-side rail, kept 0.15 in clear of the window.
fence = sector(RI - BLOCK_W, RI, LAP_DEG + degrees(0.15 / RI), LAP_DEG + rail_deg)


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
        lines = [(f"HALF-LAP {name}", 1.0), ("LOWER 1/4  |  UPPER 1/2", 0.8),
                 (f"PAIRS W/ POCKET {name}", 0.7)]
        m = trimesh.boolean.difference([m] + label_cutters(lines, c.x, cy, 6.0, -1, 1.6, mirror_x=True),
                                       engine="manifold")
    m.apply_translation(-m.bounds[0] * [1, 1, 0])
    return m


if __name__ == "__main__":
    for name, mir in (("A", False), ("B", True)):
        m = build(mir, name)
        out = f"/Users/lnevo/Downloads/stl/roadbed_halflap_template_{name}.stl"
        m.export(out)
        print(out, "watertight", m.is_watertight, "bodies", len(m.split(only_watertight=False)), "size mm", np.round(m.extents, 1))
