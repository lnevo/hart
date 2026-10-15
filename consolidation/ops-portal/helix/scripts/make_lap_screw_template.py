"""Full-size paper template for the half-lap glue screws (prints on US Letter at 100%).

Top view of a lap. The lap is a 3.75 deg wedge between two radial seams; the nominal joint
line is in its middle (1.875 deg from each seam). The bracket pocket (0.6625 in wide, 3/32 deep,
r 26 -> 29.95) is centered on the joint line in the lower piece's underside, hidden from the top.

As-built lap (user, 2026-10-14): upper 0.26 in, lower 0.46 in. #6 x 5/8 flat head, flush:
tip 0.095 in above the underside, but under the pocket the lower piece is only 0.366, so a
screw there would reach the pocket floor. Screws stay POCKET_CLEAR from the pocket edge and
SEAM_CLEAR from both seams. The pattern is symmetric about the joint line, so one template
fits both hands: put either seam line on the visible top seam and the arc on the 26 in edge.
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly, Circle, Rectangle

PAGE_W, PAGE_H = 8.5, 11.0
RI, RO, RO2 = 26.0, 31.75, 32.0
HALF = np.radians(1.875)            # seam to joint line
POCKET_W = 0.6625
POCKET_R = 29.95                    # pocket outer end
POCKET_CLEAR = 3 / 16               # screw center to pocket edge, minimum
SEAM_CLEAR = 0.25                   # screw center to seam, minimum
# (radius, tangential offset from the joint line), mirrored to both sides
SCREWS = [(26.75, 0.56), (29.25, 0.62), (30.85, 0.60)]

CX, CY = PAGE_W / 2, 2.6 - RI        # helix center (off the page); r 26 lands at y = 2.6


def xy(r, phi):
    return CX + r * np.sin(phi), CY + r * np.cos(phi)


def arc(r, a0, a1, n=60):
    p = np.linspace(a0, a1, n)
    return np.c_[CX + r * np.sin(p), CY + r * np.cos(p)]


def check():
    for r, off in SCREWS:
        seam = r * np.sin(HALF) - off            # tangential distance to the seam (near enough)
        pocket = off - POCKET_W / 2 if r < POCKET_R + POCKET_CLEAR else 99
        assert seam >= SEAM_CLEAR - 1e-9, (r, seam)
        assert pocket >= POCKET_CLEAR - 1e-9, (r, pocket)
        print(f"r {r}: offset {off}, to seam {seam:.3f}, to pocket edge {pocket if pocket < 99 else 'past end'}")


def draw(path):
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, PAGE_W)
    ax.set_ylim(0, PAGE_H)
    ax.set_aspect("equal")
    ax.axis("off")

    lap = np.vstack([arc(RI, -HALF, HALF), arc(RO2, HALF, -HALF)])
    ax.add_patch(MPoly(lap, closed=True, fc="#f4f4f4", ec="none"))
    # Seams (radial), extended past both edges as registration lines.
    for s in (-HALF, HALF):
        ax.plot(*np.array([xy(RI - 0.6, s), xy(RO2 + 0.4, s)]).T, color="k", lw=1.2)
    # Inside edge (registration), outer edges.
    a = np.radians(6)
    ax.plot(*arc(RI, -a, a).T, color="k", lw=1.6)
    ax.plot(*arc(RO, -HALF, HALF).T, color="k", lw=0.8, ls="--")
    ax.plot(*arc(RO2, -HALF, HALF).T, color="k", lw=0.8, ls=":")
    # Joint line.
    ax.plot(*np.array([xy(RI - 0.3, 0), xy(RO2 + 0.2, 0)]).T, color="0.4", lw=0.8, ls="-.")
    # Bracket pocket keep-out (pocket + POCKET_CLEAR), hatched.
    w = POCKET_W / 2
    ax.add_patch(Rectangle((CX - w, CY + RI), POCKET_W, POCKET_R - RI, fc="none", ec="r", lw=1,
                           hatch="///", alpha=0.6))
    k = w + POCKET_CLEAR
    ax.add_patch(Rectangle((CX - k, CY + RI), 2 * k, POCKET_R + POCKET_CLEAR - RI, fc="none", ec="r",
                           lw=0.6, ls="--"))
    # Screws: crosshair + #6 head circle (0.262 in).
    for r, off in SCREWS:
        for sgn in (-1, 1):
            phi = sgn * np.arcsin(off / r)
            x, y = xy(r, phi)
            ax.add_patch(Circle((x, y), 0.131, fc="none", ec="b", lw=1))
            ax.plot([x - 0.2, x + 0.2], [y, y], color="b", lw=0.6)
            ax.plot([x, x], [y - 0.2, y + 0.2], color="b", lw=0.6)
            ax.plot(x, y, "o", color="b", ms=1.5)

    t = dict(ha="center", va="center", fontsize=7)
    ax.text(CX, CY + RI - 0.25, "INSIDE EDGE  r 26  (align to plywood edge)", **t)
    ax.text(CX, CY + RO + 0.12, "outer edge r 31.75", fontsize=6, ha="center")
    ax.text(CX, CY + RO2 + 0.12, "r 32", fontsize=6, ha="center")
    for s, lbl in ((-HALF, "SEAM"), (HALF, "SEAM")):
        x, y = xy(RO2 + 0.6, s)
        ax.text(x, y, lbl, rotation=-np.degrees(s), **t)
    ax.text(CX, CY + RI + 1.6, "BRACKET\nPOCKET\n(below)\nno screws", color="r", fontsize=6.5,
            ha="center", va="center", bbox=dict(fc="white", ec="none", pad=1))
    x, y = xy(RO2 + 0.45, 0)
    ax.text(x, y, "joint line", fontsize=6, ha="center", color="0.4")

    ax.text(0.5, 10.5, "HALF-LAP SCREW TEMPLATE — print at 100% / Actual size (no scaling)",
            fontsize=10, weight="bold", va="top")
    ax.text(0.5, 10.2, "\n".join([
        "1. Check the scale bars below.  2. Cut along the inside-edge arc and one seam line.",
        "3. Put the arc on the 26 in inside edge and the seam line on the visible top seam (either side: symmetric).",
        "4. Tape down, poke each crosshair with an awl, drill: countersink bit, 9/64 clearance thru upper,",
        "   7/64 pilot into lower.  #6 x 5/8 flat head, flush.  Glue first.",
        "Lap: upper 0.26 / lower 0.46 in.  Screws stay 3/16+ from the pocket and 1/4+ from both seams.",
    ]), fontsize=7.5, va="top", family="monospace")

    # Scale bars.
    ax.add_patch(Rectangle((0.5, 0.5), 2.0, 0.08, fc="k"))
    ax.text(1.5, 0.65, "2.000 in", ha="center", fontsize=7)
    ax.add_patch(Rectangle((4.0, 0.5), 50 / 25.4, 0.08, fc="k"))
    ax.text(4.0 + 25 / 25.4, 0.65, "50 mm", ha="center", fontsize=7)
    ax.text(PAGE_W - 0.5, 0.5, "make_lap_screw_template.py  2026-10-14", fontsize=5.5, ha="right",
            color="0.5")
    fig.savefig(path)
    fig.savefig(path.replace(".pdf", "_preview.png"), dpi=110)


if __name__ == "__main__":
    check()
    draw("/Users/lnevo/Downloads/stl/lap_screw_template.pdf")
