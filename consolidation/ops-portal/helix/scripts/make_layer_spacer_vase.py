"""Spiral-vase version of the layer spacer (see make_layer_spacer.py for the height rationale).

Same envelope: 3.280 in tall (4.000 pitch - 0.72 plywood), 1 in OD, bottom 1/4 in flared at
45 deg to 1.5 in. Vase mode prints one line per layer, so the extra walls are modeled: the part
is solid with one thin SPIRAL slit winding in from the outside (user, 2026-10-13: "more
walls"). The single outline runs in along the slit and back out, so every band between turns
gets a line on each side: TURNS x 2 lines of solid wall from one continuous path. A short
radial lead takes the slit out through the flare, so every layer is one outline.

Band = 2 x LINE_W, so the two lines fill it. If you change the slicer's outer-wall line width,
set LINE_W to match and re-run.

Also writes a 1-line version (TURNS = 0: the plain solid, no slit), the cheapest and fastest.

Slicer: spiral vase on, bottom shell layers 3-4, "slice gap closing radius" 0.01 (the default
0.049 can close the 0.1 mm slit). Check the preview shows the coiled wall.
"""
import numpy as np
import trimesh
from shapely.geometry import LineString
from shapely.ops import unary_union
import router_template_lattice as lat
from make_layer_spacer import IN, H, OD, FLARE_OD, FLARE_H

LINE_W = 0.45                   # mm, slicer outer-wall line width
SLIT = 0.1                      # mm
TURNS = 1                       # user 2026-10-13: middle ground (was 4, then 2)
PITCH = 2 * LINE_W + SLIT       # mm between slit turns


def build(turns=TURNS):
    ro, rb = OD / 2 * IN, FLARE_OD / 2 * IN
    solid = trimesh.creation.revolve(np.array([(0, 0), (rb, 0), (ro, FLARE_H * IN), (ro, H * IN), (0, H * IN)]),
                                     sections=96)
    solid.fix_normals()
    if turns == 0:
        return solid
    r0 = ro - 2 * LINE_W - SLIT / 2
    t = np.linspace(0, turns * 2 * np.pi, turns * 180 + 1)
    r = r0 - PITCH * t / (2 * np.pi)
    spiral = LineString(np.c_[r * np.cos(t), r * np.sin(t)])
    lead = LineString([(r0, 0), (rb + 1, 0)])
    slit = unary_union([spiral.buffer(SLIT / 2, cap_style="flat", join_style="mitre"),
                        lead.buffer(SLIT / 2, cap_style="flat")])
    cut = trimesh.creation.extrude_polygon(slit, H * IN + 2)
    cut.apply_translation([0, 0, -1])
    return trimesh.boolean.difference([solid, cut], engine="manifold")


if __name__ == "__main__":
    for turns, path in ((TURNS, "/Users/lnevo/Downloads/stl/layer_spacer_4in_pitch_vase.stl"),
                        (0, "/Users/lnevo/Downloads/stl/layer_spacer_4in_pitch_vase_1line.stl")):
        body = build(turns)
        body.export(path)
        print(path.split("/")[-1], "watertight", body.is_watertight, "reload ok", lat.stl_roundtrip_ok(path),
              "bodies", len(body.split(only_watertight=False)), "size mm", np.round(body.extents, 2))
        for z in (1, 40, 83):
            sec = body.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1]).to_2D()[0]
            print("  z", z, "regions", len(sec.polygons_full), "holes", sum(len(p.interiors) for p in sec.polygons_full),
                  "outline mm", round(sum(p.exterior.length for p in sec.polygons_full), 1))
