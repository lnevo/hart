"""Railhead layer spacer: the vase layer spacer, standing on the railheads of one track.

For checking the loop-to-loop pitch where there's no bare roadbed to stand on (the outside
track). It measures railhead to the underside of the loop above, which is the clearance that
matters: height = 4.000 pitch - 0.72 measured plywood - T, T = railhead above the roadbed top.

Same 1.5 in flared foot, fillet and gussets as layer_spacer_4in_pitch_vase_1line.stl. Two
open grooves across the bottom of the foot straddle the railheads, so it can't slide or tip
across the track. The groove roofs rest on the railheads, so the part is H_RAIL + GROOVE_D
tall. On the curve a 1.5 in groove is off the rail by ~0.2 mm; the groove play
covers it. The grooves (GROOVE_D) are shallower than the rail, so the foot stays off the ties.

T = 0.160 is the nominal Code 83 value (2026-10-18). Caliper the actual railhead height above
the roadbed top and change T.

Slicer (Creality Print, spiral vase): the grooves split the bottom of the foot into 3 strips,
which vase mode can't spiral. Vase mode prints the bottom shell layers as normal solid layers,
so BOTTOM_SOLID covers the grooves plus a roof over them and the spiral starts above that:
bottom shell layers 15 at 0.2 mm (check the bottom shell thickness reaches BOTTOM_SOLID),
slice gap closing radius 0.01 (keeps the gusset slits), elephant foot compensation on (keeps
the grooves open). Check the preview: solid layers with the grooves bridged, then the spiral.
"""
import numpy as np
import trimesh
import router_template_lattice as lat
from stl_out import out_dir
from make_layer_spacer import IN, PITCH, PLY_T, FLARE_OD
from make_layer_spacer_vase import build as build_vase

T = 0.160                       # in, railhead above the roadbed top (nominal Code 83; caliper it)
H_RAIL = PITCH - PLY_T - T      # 3.120 in
GAUGE = 16.5                    # mm, HO, between the inside faces of the railheads
HEAD_W = 1.0                    # mm, Code 83 railhead width (approx.)
GROOVE_W = 1.8                  # mm
GROOVE_D = 1.2                  # mm, rail is ~2.1 mm tall, so the foot is ~0.9 above the ties
BOTTOM_SOLID = 3.0              # mm, groove + roof, printed as normal bottom layers


def build():
    # the groove roofs sit on the railheads, so the top is H_RAIL above them
    body = build_vase(0, h=H_RAIL + GROOVE_D / IN, rib_z0=BOTTOM_SOLID)   # gussets stand on the solid floor
    c = GAUGE / 2 + HEAD_W / 2  # railhead centreline
    L = FLARE_OD * IN + 2
    cuts = []
    for x in (-c, c):
        g = trimesh.creation.box([GROOVE_W, L, GROOVE_D + 1])
        g.apply_translation([x, 0, (GROOVE_D - 1) / 2])
        cuts.append(g)
    return trimesh.boolean.difference([body] + cuts, engine="manifold")


if __name__ == "__main__":
    OUT = out_dir(__doc__)
    body = build()
    path = f"{OUT}rail_spacer_4in_pitch_vase.stl"
    body.export(path)
    print(path.split("/")[-1], "watertight", body.is_watertight, "reload ok", lat.stl_roundtrip_ok(path),
          "bodies", len(body.split(only_watertight=False)), "size mm", np.round(body.extents, 2),
          "railhead to top in", round((body.bounds[1][2] - GROOVE_D) / IN, 4))
    for z in (0.5, 1.4, 2, BOTTOM_SOLID + 0.1, 6, 12, 40, 78):
        sec = body.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1]).to_2D()[0]
        print("  z", z, "regions", len(sec.polygons_full), "holes", sum(len(p.interiors) for p in sec.polygons_full))
