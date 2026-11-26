"""Layer spacer: checks the 4.000 in roadbed-to-roadbed pitch past the first loop.

Stands on the top of the lower loop's roadbed and carries the underside of the loop above:
height = 4.000 pitch - 0.72 measured plywood = 3.280 in. (Height datum: the stack sets the
roadbed TOP; underside = top - 0.72. See HART_Neville_Helix_BUILD_STATUS.md section 1.)

Cheap and fast: an open tube (no top, bottom or infill), so the slicer prints only walls.
Stiffened 2026-10-13 (user: "a little bit stronger"): 2.0 mm wall plus an internal + of
1.6 mm ribs running full height. The ribs keep the tube from ovaling or buckling and still
print as walls only.
1 in OD fits between the 26 in inside edge and the track's ties (about 1.6 in of room). The
bottom 1/4 in flares out at 45 deg to 1.5 in OD so the spacer doesn't tip while you place
it. The flare leans inward going up, so no supports.

Grade across the 1 in footprint is about 0.02 in; ignore it.
Prints as modeled, flare down. Not spiral vase (the ribs need normal mode).
"""
import numpy as np
import trimesh
import router_template_lattice as lat
from stl_out import out_dir

IN = 25.4
PITCH = 4.000
PLY_T = 0.72                    # measured
H = PITCH - PLY_T               # 3.280 in
OD = 1.0
WALL = 2.0 / IN                 # 2.0 mm: ~5 slicer lines, no infill
RIB = 1.6 / IN                  # internal + ribs
FLARE_OD = 1.5
FLARE_H = (FLARE_OD - OD) / 2   # 45 deg


def build():
    ro, rb = OD / 2, FLARE_OD / 2
    # (radius, z) profile of the wall, counterclockwise, revolved about z.
    prof = np.array([
        (rb - WALL, 0), (rb, 0), (ro, FLARE_H), (ro, H),
        (ro - WALL, H), (ro - WALL, FLARE_H), (rb - WALL, 0),
    ]) * IN
    tube = trimesh.creation.revolve(prof, sections=96)
    tube.fix_normals()
    # + ribs, clipped to the solid outer profile so they reach the flare too.
    solid = trimesh.creation.revolve(np.array([(0, 0), (rb, 0), (ro, FLARE_H), (ro, H), (0, H)]) * IN,
                                     sections=96)
    solid.fix_normals()
    ribs = [trimesh.creation.box([FLARE_OD * IN, RIB * IN, H * IN]),
            trimesh.creation.box([RIB * IN, FLARE_OD * IN, H * IN])]
    for r in ribs:
        r.apply_translation([0, 0, H / 2 * IN])
    cross = trimesh.boolean.intersection([trimesh.boolean.union(ribs, engine="manifold"), solid],
                                         engine="manifold")
    return trimesh.boolean.union([tube, cross], engine="manifold")


if __name__ == "__main__":
    OUT = out_dir(__doc__)
    body = build()
    path = OUT + "layer_spacer_4in_pitch.stl"
    body.export(path)
    print("watertight", body.is_watertight, "reload ok", lat.stl_roundtrip_ok(path),
          "bodies", len(body.split(only_watertight=False)), "size mm", np.round(body.extents, 2),
          "H in", round(H, 4), "vol cm3", round(body.volume / 1000, 2))
