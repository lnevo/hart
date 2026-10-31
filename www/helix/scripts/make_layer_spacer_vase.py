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

Reinforced 2026-10-18 (user: cracking where the flare joins the cylinder; flare OD/height
can't grow):
  * FILLET_R rounds the inside corner where the 45 deg flare meets the cylinder. It only adds
    material inside the old envelope (base OD and flare height unchanged), removes the sharp
    corner the crack started at, and every layer along the curve is steeper than 45 deg, so
    the layers overlap more.
  * 1-line version only: RIBS radial slits through the flare, extending RIB_UP above the
    blend and in to RIB_IN from the axis. The single outline runs in and back out along each
    slit, so each becomes a 2-line gusset tying the flare skin to the cylinder wall across
    the joint. (The 3-line version's spiral leaves no room for them; it has 3 walls there.)

Slicer: spiral vase on, bottom shell layers 3-4, "slice gap closing radius" 0.01 (the default
0.049 can close the 0.1 mm slit). Check the preview shows the coiled wall, and for the 1-line
version the 4 gussets in the flare (the 0.01 setting is now needed for it too).
"""
import numpy as np
import trimesh
from stl_out import out_dir
from shapely.geometry import LineString
from shapely.ops import unary_union
import router_template_lattice as lat
from make_layer_spacer import IN, H, OD, FLARE_OD, FLARE_H

LINE_W = 0.45                   # mm, slicer outer-wall line width
SLIT = 0.1                      # mm
TURNS = 1                       # user 2026-10-13: middle ground (was 4, then 2)
PITCH = 2 * LINE_W + SLIT       # mm between slit turns
FILLET_R = 10.0                 # mm, flare-to-cylinder blend
RIBS = 4                        # gussets in the 1-line version
RIB_UP = 5.0                    # mm, gussets run this far above the top of the blend
RIB_IN = 8.0                    # mm from the axis, inner end of each gusset


def profile(h=H):
    """(r, z) mm: 45 deg flare, FILLET_R blend into the cylinder, closed through the axis."""
    ro, rb, hf = OD / 2 * IN, FLARE_OD / 2 * IN, FLARE_H * IN
    d = FILLET_R * np.tan(np.pi / 8)            # corner to tangent point, 45 deg turn
    c = np.array([ro + FILLET_R, hf + d])        # blend centre, outside the part
    a = np.linspace(np.pi + np.pi / 4, np.pi, 24)  # slope tangent -> cylinder tangent
    arc = c + FILLET_R * np.c_[np.cos(a), np.sin(a)]
    return np.vstack([[(0, 0), (rb, 0)], arc, [(ro, h * IN), (0, h * IN)]]), hf + d


def build(turns=TURNS, h=H, rib_z0=0.0):
    """rib_z0: mm, gussets start here (above a solid floor)."""
    ro, rb = OD / 2 * IN, FLARE_OD / 2 * IN
    prof, blend_top = profile(h)
    solid = trimesh.creation.revolve(prof, sections=96)
    solid.fix_normals()
    if turns == 0:
        cuts = []
        z0 = rib_z0 if rib_z0 else -1.0      # -1: through the bottom face
        for k in range(RIBS):
            t = (k + 0.5) * 2 * np.pi / RIBS     # clear of the 3-line version's lead angle
            rib = LineString([(RIB_IN * np.cos(t), RIB_IN * np.sin(t)), ((rb + 1) * np.cos(t), (rb + 1) * np.sin(t))])
            cut = trimesh.creation.extrude_polygon(rib.buffer(SLIT / 2, cap_style="flat"), blend_top + RIB_UP - z0)
            cut.apply_translation([0, 0, z0])
            cuts.append(cut)
        return trimesh.boolean.difference([solid] + cuts, engine="manifold")
    r0 = ro - 2 * LINE_W - SLIT / 2
    t = np.linspace(0, turns * 2 * np.pi, turns * 180 + 1)
    r = r0 - PITCH * t / (2 * np.pi)
    spiral = LineString(np.c_[r * np.cos(t), r * np.sin(t)])
    lead = LineString([(r0, 0), (rb + 1, 0)])
    slit = unary_union([spiral.buffer(SLIT / 2, cap_style="flat", join_style="mitre"),
                        lead.buffer(SLIT / 2, cap_style="flat")])
    cut = trimesh.creation.extrude_polygon(slit, h * IN + 2)
    cut.apply_translation([0, 0, -1])
    return trimesh.boolean.difference([solid, cut], engine="manifold")


if __name__ == "__main__":
    OUT = out_dir(__doc__)
    for turns, path in ((TURNS, f"{OUT}layer_spacer_4in_pitch_vase.stl"),
                        (0, f"{OUT}layer_spacer_4in_pitch_vase_1line.stl")):
        body = build(turns)
        body.export(path)
        print(path.split("/")[-1], "watertight", body.is_watertight, "reload ok", lat.stl_roundtrip_ok(path),
              "bodies", len(body.split(only_watertight=False)), "size mm", np.round(body.extents, 2))
        for z in (1, 4, 7, 10, 14, 40, 83):
            sec = body.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1]).to_2D()[0]
            print("  z", z, "regions", len(sec.polygons_full), "holes", sum(len(p.interiors) for p in sec.polygons_full),
                  "outline mm", round(sum(p.exterior.length for p in sec.polygons_full), 1))
