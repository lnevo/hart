"""Piers under the first helix loop: -15 in deck to the UNDERSIDE of the 3/4 in roadbed (mm).

Post 1 (butt joint, bracket 0): P1 top = 1-1/32 in above the deck (template-fit), so the
underside is 1-1/32 - 3/4 = 9/32 in. Each later post is 45 deg on = +1/2 in. Post 1 already sits
on the cork-transition shim and Post 8 falls over the raised entry tongue, so piers are made for
POSTS (2..7) only; edit POSTS to add or drop any.

Frame: X radial (+ = outward), Y along the track (+ = uphill), Z up. The top is a plane sloped
at the helix grade at the pier's center radius R_C. Height is set at the pier center, which goes
on the post's radial line. The arrows engraved on the tabs point uphill.

Trellis, built to print fast with no supports: two thin webs run along the track joined by a
cross web (an H in plan), each web pierced with 45-degree diamond windows. Each long web carries
a 9 mm top flange flared out at 45 degrees; the plywood bears on the two flanges. Webs are
WEB_T thick so the slicer fills them with perimeters only (no infill). Every overhang is
45 degrees or steeper.

Screws: a tab on each radial side, 3/8 in thick, with a hole countersunk from the top for a
#6 drywall screw driven down into the deck. A 1 in screw goes 5/8 in into 3/4 in plywood;
a 1-1/4 in screw would come out the bottom. Screw the piers down before the roadbed goes on.
Prints feet-down as modeled.
"""
import numpy as np
import trimesh
from shapely.geometry import box, Polygon
from shapely import affinity
from make_height_spacers import IN, revolve, check
from stl_text import text_polys, centered

OUT = "/Users/lnevo/Downloads/stl/"

P1_TOP_IN, PLY_IN, RISE_PER_POST = 1.03125, 0.75, 0.5
POSTS = [2, 3, 4, 5, 6, 7]
R_C = (26.0 + 31.75) / 2                    # pier center radius, in
GRADE = 4.0 / (2 * np.pi * R_C)             # helix grade at R_C (rise/run)

PIER_W, PIER_L = 2.0 * IN, 1.5 * IN         # outside of the flanges: radial width, length along track
WEB_T = 2.4                                 # web thickness (3 perimeters at 0.4-0.45 mm)
FLANGE_W, FLANGE_T = 9.0, 1.6               # top flange width, min thickness (at the low end)
DIA_A, DIA_GAP, DIA_EDGE = 5.5, 2.0, 2.5    # diamond half-diagonal, tip-to-tip gap, min edge margin
FOOT_EXT, FOOT_T = 1.0 * IN, 0.375 * IN     # tab reach past the pier, thickness
TAB_L = 0.75 * IN                           # tab length along the track
HOLE_OFF = 0.6 * IN                         # hole center out from the pier's outer face
SHAFT_D, HEAD_D, CSK_ANGLE = 0.156 * IN, 0.340 * IN, 90.0
LABEL_SIZE, LABEL_DEPTH = 5.0, 0.6
CORNER_R = 3.0


def underside_in(post):
    return P1_TOP_IN - PLY_IN + RISE_PER_POST * (post - 1)


def prism_y(poly_xz, y0, y1):
    """Extrude a polygon drawn in (x, z) along Y from y0 to y1."""
    m = trimesh.creation.extrude_polygon(poly_xz, y1 - y0)       # local (x, z, y)
    m.apply_transform([[1, 0, 0, 0], [0, 0, 1, y0], [0, 1, 0, 0], [0, 0, 0, 1]])
    return m


def prism_x(poly_yz, x0, x1):
    """Extrude a polygon drawn in (y, z) along X from x0 to x1."""
    m = trimesh.creation.extrude_polygon(poly_yz, x1 - x0)       # local (y, z, x)
    m.apply_transform([[0, 0, 1, x0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]])
    return m


def diamonds(s0, s1, z0, z1):
    """45-degree diamond windows (2D polys) filling [s0, s1] x [z0, z1] on a square grid."""
    a, pitch = DIA_A, 2 * DIA_A + DIA_GAP
    ncol = max(0, int((s1 - s0 + DIA_GAP) // pitch))
    nrow = max(0, int((z1 - z0 + DIA_GAP) // pitch))
    out = []
    for i in range(ncol):
        u = s0 + (s1 - s0 - (ncol * pitch - DIA_GAP)) / 2 + a + i * pitch
        for j in range(nrow):
            v = z0 + (z1 - z0 - (nrow * pitch - DIA_GAP)) / 2 + a + j * pitch
            out.append(Polygon([(u, v - a), (u + a, v), (u, v + a), (u - a, v)]))
    return out


def countersink(x, y, top):
    r_s, r_h = SHAFT_D / 2, HEAD_D / 2
    depth = (r_h - r_s) / np.tan(np.radians(CSK_ANGLE / 2))
    return revolve([(0, -top - 1), (r_s, -top - 1), (r_s, -depth), (r_h, 0), (r_h, 5), (0, 5)], x, y, top)


def tab_label(s, x, rot_deg):
    """Engraving cutters on a tab's top face; rot_deg turns the text so it runs along Y."""
    g = centered(text_polys(s, LABEL_SIZE), 0, 0)
    g = affinity.translate(affinity.rotate(g, rot_deg, origin=(0, 0)), x, 0)
    cuts = []
    for poly in getattr(g, "geoms", [g]):
        m = trimesh.creation.extrude_polygon(poly, LABEL_DEPTH + 0.3)
        m.apply_translation([0, 0, FOOT_T - LABEL_DEPTH])
        cuts.append(m)
    return cuts


def pier(post):
    hc = underside_in(post) * IN
    low = hc - GRADE * PIER_L / 2
    high = hc + GRADE * PIER_L / 2
    ztop = high + 1.0                         # build tall, then cut to the sloped plane
    flare = (FLANGE_W - WEB_T) / 2            # 45-degree flare: height = horizontal reach
    z_flare = low - FLANGE_T - flare          # where the flange flare starts
    assert z_flare > FOOT_T, (post, z_flare)
    ys = (-PIER_L / 2, PIER_L / 2)

    parts, cuts = [], []
    xw = PIER_W / 2 - FLANGE_W / 2            # web centerline: flange flush with the pier's outside
    for sx in (1, -1):
        c = sx * xw
        prof = Polygon([(c - WEB_T / 2, 0), (c + WEB_T / 2, 0), (c + WEB_T / 2, z_flare),
                        (c + FLANGE_W / 2, z_flare + flare), (c + FLANGE_W / 2, ztop),
                        (c - FLANGE_W / 2, ztop), (c - FLANGE_W / 2, z_flare + flare), (c - WEB_T / 2, z_flare)])
        parts.append(prism_y(prof, *ys))
        # windows in the long web, one field each side of the cross web, clear of the tab and flare
        zw0, zw1 = FOOT_T + DIA_EDGE, z_flare - DIA_EDGE
        for s0, s1 in ((-PIER_L / 2 + DIA_EDGE, -WEB_T / 2 - DIA_EDGE), (WEB_T / 2 + DIA_EDGE, PIER_L / 2 - DIA_EDGE)):
            for d in diamonds(s0, s1, zw0, zw1):
                cuts.append(prism_x(d, c - WEB_T, c + WEB_T))
    # cross web along X at y = 0, between the long webs, up to the sloped top
    xi = xw - WEB_T / 2
    parts.append(prism_x(box(-WEB_T / 2, 0, WEB_T / 2, ztop), -xi - 0.1, xi + 0.1))
    for d in diamonds(-xi + DIA_EDGE, xi - DIA_EDGE, DIA_EDGE + 1.0, low - 2 * DIA_EDGE):
        cuts.append(prism_y(d, -WEB_T, WEB_T))
    # screw tabs from the web out past the hole
    for sx in (1, -1):
        x0, x1 = sorted((sx * (xw - WEB_T / 2), sx * (PIER_W / 2 + FOOT_EXT)))
        parts.append(trimesh.creation.extrude_polygon(
            box(x0, -TAB_L / 2, x1, TAB_L / 2).buffer(-CORNER_R).buffer(CORNER_R, resolution=16), FOOT_T))
        cuts.append(countersink(sx * (PIER_W / 2 + HOLE_OFF), 0, FOOT_T))
        # label between the pier and the hole, running uphill (+Y), readable from that side
        lx = sx * (PIER_W / 2 + (HOLE_OFF - HEAD_D / 2) / 2)
        cuts += tab_label(f"P{post} →" if sx > 0 else f"← P{post}", lx, 90 if sx > 0 else -90)

    m = trimesh.boolean.union(parts, engine="manifold")
    # sloped top: remove everything above z = hc + GRADE*y
    big = 4 * PIER_W
    above = trimesh.convex.convex_hull(np.array(
        [[x, y, hc + GRADE * y + dz] for x in (-big, big) for y in (-big, big) for dz in (0, 200)]))
    m = trimesh.boolean.difference([m, above] + cuts, engine="manifold")
    return m, hc


if __name__ == "__main__":
    print(f"grade at r={R_C:.3f} in: {GRADE * 100:.3f}%  (top drops/rises {GRADE * PIER_L / IN:.4f} in end to end)")
    for p in POSTS:
        m, hc = pier(p)
        name = f"first_loop_pier_post{p}.stl"
        check(m, name)
        print(f"   underside at center {hc / IN:.5f} in = {hc:.3f} mm, volume {m.volume / 1000:.1f} cm3")
        m.export(OUT + name)
