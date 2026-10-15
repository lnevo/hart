"""Bracket-height spacer set and P1 height template (all geometry in mm).

Use: the TEMPLATE stands on the -15 in deck at a post; its top = top of the first roadbed
piece (P1, 3/4 in plywood) at Post 1 / bracket 0. Stack spacers on the template to add the
rise for that post (+1/2 in per 45 deg post). Any subset stacks in any order:
1/4 + 1/2 + 3/4 + 1 + 1-1/2 = 4.000 in, every 1/4 in step from 0 to 4 in is reachable.

Registration: two tapered pegs on the BOTTOM of each spacer press into sockets on the TOP of
whatever is below (pegs are shorter than the sockets are deep, so only the flat faces bear and
the pegs add no height). Three crush ribs in each socket grip the peg, so pieces snap together
like Lego; stored as one stack on the template there is no case. The template has the same
footprint, a flat bottom and sockets on top. The stack's top face stays flat for a level.

Spacers export upside down (reference top face on the bed, pegs up). Use TRIM_MM to correct
any spacer that measures off with calipers after printing.
"""
import numpy as np
import trimesh
from shapely.geometry import box
from stl_text import text_polys, centered

IN = 25.4
OUT = "/Users/lnevo/Downloads/stl/"

# Template height = -15 deck to TOP of P1 at Post 1. Tongue and P1 are both 3/4 in plywood, so
# top-to-top it is the entry riser step (as printed in entry_wedge_riser_inside/outside.stl:
# 5.375*0.02176 + 0.500 + 0.247 = 0.864 in = 21.946 mm, measured off the mesh) plus the 6.000 mm
# step of cork_to_plywood_transition_shim.stl (also measured off the mesh). Set None to skip.
RISER_STEP_MM, CORK_STEP_MM = 21.946, 6.000
# That math gives 1.100 in, but P1 measured lower on the bench; the user set 1-1/16 in, test-fit too high, now 1-1/32 in.
TEMPLATE_H_IN, TEMPLATE_LABEL = 1.03125, '1-1/32"'   # calc: (RISER_STEP_MM + CORK_STEP_MM) / IN

FOOT_W, FOOT_L = 1.5 * IN, 2.0 * IN   # spacer / template column footprint
CORNER_R = 3.0
EDGE_CH = 0.5                 # edge chamfer (also hides elephant foot on the bed face)
PEG_D, PEG_H, PEG_TIP = 8.0, 3.0, 0.8
SOCK_D, SOCK_DEPTH, SOCK_CH = 8.5, 3.6, 0.5
RIB_R, RIB_IN = 0.6, 3.95    # crush-rib radius; rib inner face radius (peg r = 4.0 -> 0.05 grip)
PEG_Y = 14.0                  # pegs at (0, +/-PEG_Y)
ENGRAVE = 0.8

SPACERS = [  # (height in, label)
    (0.25, '1/4"'),
    (0.50, '1/2"'),
    (0.75, '3/4"'),
    (1.00, '1"'),
    (1.50, '1-1/2"'),
]
TRIM_MM = {0.25: 0.0, 0.50: 0.0, 0.75: 0.0, 1.00: 0.0, 1.50: 0.0}
BASES = [(0.25, 'BASE 1/4"')]   # flat-bottom, sockets-on-top blocks (start a stack without the template)


def rrect(w, l, r=CORNER_R, cx=0.0, cy=0.0):
    return box(cx - w / 2, cy - l / 2, cx + w / 2, cy + l / 2).buffer(-r).buffer(r, resolution=16)


def chamfered_prism(w, l, h, c=EDGE_CH):
    """Rounded-rect prism z=[0,h] with chamfered top and bottom edges (convex hull of slabs)."""
    inner = rrect(w - 2 * c, l - 2 * c, max(CORNER_R - c, 0.5))
    outer = rrect(w, l)
    pts = []
    for poly, zs in ((inner, (0.0, h)), (outer, (c, h - c))):
        xy = np.array(poly.exterior.coords)
        for z in zs:
            pts.append(np.column_stack([xy, np.full(len(xy), z)]))
    return trimesh.convex.convex_hull(np.vstack(pts))


def revolve(profile, x, y, z):
    m = trimesh.creation.revolve(np.array(profile), sections=48)
    m.apply_translation([x, y, z])
    return m


def peg(x, y):
    r = PEG_D / 2
    return revolve([(0, -PEG_H), (r - PEG_TIP, -PEG_H), (r, -PEG_H + PEG_TIP), (r, 0.2), (0, 0.2)], x, y, 0)


def socket(x, y, top):
    r = SOCK_D / 2
    cut = revolve([(0, -SOCK_DEPTH), (r, -SOCK_DEPTH), (r, -SOCK_CH), (r + SOCK_CH, 0), (r + SOCK_CH, 0.3), (0, 0.3)],
                  x, y, top)
    ribs = []
    for a in (np.pi / 2, np.pi / 2 + 2 * np.pi / 3, np.pi / 2 + 4 * np.pi / 3):
        rib = trimesh.creation.cylinder(radius=RIB_R, height=SOCK_DEPTH - SOCK_CH, sections=16)
        rc = RIB_IN + RIB_R
        rib.apply_translation([x + rc * np.cos(a), y + rc * np.sin(a), top - (SOCK_DEPTH + SOCK_CH) / 2])
        ribs.append(rib)
    return trimesh.boolean.difference([cut] + ribs, engine="manifold")


def side_text(s, size, face_x, zc, yc=0.0, depth=ENGRAVE):
    """Engraving cutters on the +X (face_x>0) or -X face, reading upright from outside."""
    g = centered(text_polys(s, size), 0, 0)
    sign = 1 if face_x > 0 else -1
    cuts = []
    for poly in getattr(g, "geoms", [g]):
        m = trimesh.creation.extrude_polygon(poly, depth + 0.3)   # local (u, v, w)
        # u -> sign*Y, v -> Z, w -> into the part along -sign*X
        T = np.array([[0, 0, -sign, face_x + sign * 0.3],
                      [sign, 0, 0, yc],
                      [0, 1, 0, zc],
                      [0, 0, 0, 1]], dtype=float)
        m.apply_transform(T)
        cuts.append(m)
    return cuts


def check(mesh, name):
    bodies = len(mesh.split(only_watertight=False))
    assert mesh.is_watertight and bodies == 1, (name, mesh.is_watertight, bodies)
    print(f"{name}: watertight, 1 body, extents mm {np.round(mesh.extents, 2)}")


def spacer(h_in, label):
    h = h_in * IN + TRIM_MM[h_in]
    body = chamfered_prism(FOOT_W, FOOT_L, h)
    adds = [peg(0, PEG_Y), peg(0, -PEG_Y)]
    cuts = [socket(0, PEG_Y, h), socket(0, -PEG_Y, h)]
    size = min(0.55 * h, 10.0)
    for fx in (FOOT_W / 2, -FOOT_W / 2):
        cuts += side_text(label, size, fx, h / 2)
    m = trimesh.boolean.union([body] + adds, engine="manifold")
    m = trimesh.boolean.difference([m] + cuts, engine="manifold")
    return m, h


def base(h_in, label):
    """Flat bottom, sockets on top: starts a stack on any flat surface. Prints as modeled."""
    h = h_in * IN
    m = chamfered_prism(FOOT_W, FOOT_L, h)
    cuts = [socket(0, PEG_Y, h), socket(0, -PEG_Y, h)]
    for fx in (FOOT_W / 2, -FOOT_W / 2):
        cuts += side_text(label, min(0.55 * h, 10.0), fx, h / 2)
    return trimesh.boolean.difference([m] + cuts, engine="manifold"), h


def template(h_in, label):
    h = h_in * IN
    m = chamfered_prism(FOOT_W, FOOT_L, h)
    cuts = [socket(0, PEG_Y, h), socket(0, -PEG_Y, h)]
    size = min(0.22 * h, 6.0)
    for fx in (FOOT_W / 2, -FOOT_W / 2):
        cuts += side_text("P1 TOP", size, fx, h / 2 + 0.65 * size)
        cuts += side_text(label, size * 0.85, fx, h / 2 - 0.65 * size)
    return trimesh.boolean.difference([m] + cuts, engine="manifold"), h


if __name__ == "__main__":
    flip = trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
    total = 0.0
    for h_in, label in SPACERS:
        m, h = spacer(h_in, label)
        total += h
        name = "height_spacer_" + label.replace('"', "in").replace("/", "_").replace("-", "_") + ".stl"
        m.apply_transform(flip)                       # reference top face onto the bed
        m.apply_translation(-np.array([0, 0, m.bounds[0][2]]))
        check(m, name)
        print(f"   height {h_in:.3f} in = {h:.3f} mm (body), pegs add {PEG_H} mm below")
        m.export(OUT + name)
    print(f"full stack {total / IN:.3f} in")

    for h_in, label in BASES:
        b, h = base(h_in, label)
        name = "height_base_" + label.split()[1].replace('"', "in").replace("/", "_") + ".stl"
        check(b, name)
        print(f"   height {h_in:.3f} in = {h:.3f} mm")
        b.export(OUT + name)

    if TEMPLATE_H_IN is not None:
        t, th = template(TEMPLATE_H_IN, TEMPLATE_LABEL)
        check(t, "p1_height_template.stl")
        t.export(OUT + "p1_height_template.stl")
        print(f"   template {th / IN:.3f} in = {th:.3f} mm; stored stack incl. template {(th + total) / IN:.3f} in")
    else:
        print("TEMPLATE_H_IN not set: template skipped")
