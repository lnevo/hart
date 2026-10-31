"""Shared helpers for engraving text into the helix jig STLs (all geometry in mm)."""
import trimesh
from shapely.geometry import Polygon
from shapely import affinity
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties


def text_polys(s, size_mm):
    """Text outline as shapely geometry (mm), holes handled by even-odd XOR."""
    path = TextPath((0, 0), s, size=size_mm, prop=FontProperties(family="DejaVu Sans", weight="bold"))
    geom = Polygon()
    for ring in path.to_polygons():
        if len(ring) >= 3:
            geom = geom.symmetric_difference(Polygon(ring).buffer(0))
    return geom


def centered(g, cx, cy):
    b = g.bounds
    return affinity.translate(g, cx - (b[0] + b[2]) / 2, cy - (b[1] + b[3]) / 2)


def label_cutters(lines, cx, cy, size_mm, z0, depth, mirror_x=False, spacing=1.6):
    """Prisms for a centred block of text lines, for boolean subtraction.

    mirror_x: mirror each line so it reads correctly from the other side of the part.
    """
    cuts = []
    n = len(lines)
    for i, (s, scale) in enumerate(lines if isinstance(lines[0], tuple) else [(l, 1.0) for l in lines]):
        y = cy + ((n - 1) / 2 - i) * size_mm * spacing
        g = centered(text_polys(s, size_mm * scale), cx, y)
        if mirror_x:
            g = affinity.scale(g, -1, 1, origin=(cx, y))
        for poly in getattr(g, "geoms", [g]):
            m = trimesh.creation.extrude_polygon(poly, depth)
            m.apply_translation([0, 0, z0])
            cuts.append(m)
    return cuts
