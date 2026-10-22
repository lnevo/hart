"""Redraw the construction plan's entry pages (2, 3, 8) from the as-built facts in BUILD_STATUS section 1
and splice them into the plan PDF in place of the stale ones.

As built: 5-3/8 in straight + 45 deg curve from 4:30 to the entry butt joint (bracket 0), bracket grid
from the butt joint, 0.72 in plywood, P1 top 1-1/32 in above the -15 deck (the height stack, not the
old grade chain). Needs reportlab and pymupdf.
Run: python scripts/make_entry_pages.py files/helix_construction_plan_FINAL_31p75_18p75_2026-09-23.pdf
"""
import io
import math
import sys

import fitz
from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

PW, PH = 792, 612
NAVY, GREY, INK, BLUE = HexColor("#17335e"), HexColor("#667085"), HexColor("#172033"), HexColor("#2563eb")
RED, ORANGE, PLY, RAIL = HexColor("#d92d20"), HexColor("#f08c00"), HexColor("#fde68a"), HexColor("#101828")
ROW, NOTE_BG, NOTE_FG, OK_BG = HexColor("#f2f4f7"), HexColor("#fff6ed"), HexColor("#93370d"), HexColor("#ecfdf3")
REV = "Entry pages rev. 2026-10-22"

# ---- as-built numbers (BUILD_STATUS section 1) ----
STRAIGHT = 5.375
R_IN, R_MEAN, R_OUT = 28.0, 29.25, 30.5           # inner track, planning radius, outer track
EDGE_IN, EDGE_OUT = 26.0, 31.75
PITCH, PLY_T, T_TRACK, CORK = 4.0, 0.72, 0.160, 0.236
P1_TOP = 1 + 1 / 32                               # above the -15 deck at bracket 0
RISE_45 = 0.5
HELIX_DEG, LAST_BRACKET_DEG, EXIT_STRAIGHT = 1290.0, 1260.0, 20 + 15 / 16


def arc45(r):
    return r * math.pi / 4


def grade(r):
    return PITCH / (2 * math.pi * r)


LIFT = P1_TOP - CORK                              # tongue plywood top above the deck at the butt joint
CLEAR = PITCH - PLY_T - T_TRACK
END_RAIL = -15 + LIFT + HELIX_DEG / 45 * RISE_45  # normalized railhead (upper corked track = 0)
G_MEAN = grade(R_MEAN)


def f3(v, sign=False):
    return f"{v:+.3f}" if sign else f"{v:.3f}"


def head(c, title, sub, page):
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(38, PH - 40, title)
    c.setFillColor(GREY)
    c.setFont("Helvetica", 9.8)
    c.drawString(38, PH - 61, sub)
    c.setStrokeColor(HexColor("#d0d5dd"))
    c.setLineWidth(0.8)
    c.line(38, PH - 76, PW - 37, PH - 76)
    c.setFont("Helvetica", 6.8)
    c.drawString(38, 22, "HART Railroad - Neville Island Helix Construction Plan")
    c.setFillColor(INK)
    c.drawRightString(PW - 37, 22, f"{REV} | Page {page}")


def h2(c, x, y, s, size=11.5):
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", size)
    c.drawString(x, y, s)


def para(c, x, y, s, w, size=7.4, color=INK, lead=None, bullet=None):
    lead = lead or size * 1.32
    c.setFillColor(color)
    c.setFont("Helvetica", size)
    for i, ln in enumerate(simpleSplit(s, "Helvetica", size, w - (9 if bullet else 0))):
        if bullet and i == 0:
            c.drawString(x, y, bullet)
        c.drawString(x + (9 if bullet else 0), y, ln)
        y -= lead
    return y


def table(c, x, y, w, rows, cols, size=7.4, rh=15, bold_last=True, header=None):
    """rows of strings; cols = right edges (fractions of w) for columns after the first."""
    if header:
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", size)
        c.drawString(x + 4, y, header[0])
        for s, f in zip(header[1:], cols):
            c.drawRightString(x + w * f - 4, y, s)
        y -= rh
    for i, r in enumerate(rows):
        if i % 2 == 0:
            c.setFillColor(ROW)
            c.rect(x, y - (rh - 1) / 2 + 2.5, w, rh - 1, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont("Helvetica", size)
        c.drawString(x + 4, y, r[0])
        for j, (s, f) in enumerate(zip(r[1:], cols)):
            c.setFont("Helvetica-Bold" if bold_last and j == len(cols) - 1 else "Helvetica", size)
            c.drawRightString(x + w * f - 4, y, s)
        y -= rh
    return y


# ---------------------------------------------------------------- page 2
def page2(c):
    head(c, "ENTRY / EASEMENT GEOMETRY",
         "As built: 5-3/8 in straight + 45 deg curve from 4:30 to the entry butt joint (bracket 0). "
         "Heights come from the height stack, not the old grade chain.", 2)

    # plan view: helix centre off to the left; 6:00 = straight down, 4:30 = 45 deg toward the right
    h2(c, 44, PH - 104, "PLAN VIEW - 4:30 TO THE BUTT JOINT", 10)
    k, cx, cy = 8.0, 70, PH - 23

    def pt(r, a):
        return cx + k * r * math.cos(math.radians(a)), cy + k * r * math.sin(math.radians(a))

    def track(r, color, lw, dash=None):
        c.setStrokeColor(color)
        c.setLineWidth(lw)
        c.setDash(*(dash or ()))
        p = c.beginPath()
        x, y = pt(r, -45)
        tx, ty = math.cos(math.radians(45)), math.sin(math.radians(45))
        p.moveTo(x + k * STRAIGHT * tx, y + k * STRAIGHT * ty)
        p.lineTo(x, y)
        for i in range(1, 46):
            p.lineTo(*pt(r, -45 - i))
        c.drawPath(p, stroke=1, fill=0)
        c.setDash()

    track(EDGE_IN, GREY, 0.8)
    track(EDGE_OUT, GREY, 0.8)
    track(R_IN, BLUE, 1.4)
    track(R_OUT, BLUE, 1.4)
    c.setStrokeColor(RED)
    c.setLineWidth(1.6)
    c.line(*pt(EDGE_IN - 1, -90), *pt(EDGE_OUT + 1, -90))
    c.setStrokeColor(GREY)
    c.setLineWidth(0.6)
    c.setDash(3, 2)
    c.line(*pt(EDGE_IN - 1, -45), *pt(EDGE_OUT + 1.5, -45))
    c.setDash()
    x, y = pt(EDGE_OUT, -45)
    s = k * STRAIGHT * math.cos(math.radians(45))
    c.setStrokeColor(RAIL)
    c.setLineWidth(1.2)
    a, b = pt(EDGE_IN, -45)
    c.line(a + s, b + s, x + s, y + s)
    c.setFillColor(INK)
    c.setFont("Helvetica", 7.2)
    c.drawString(x + s + 4, y + s - 2, "start of the straight (tongue hinge)")
    c.drawString(x + 6, y - 13, "4:30, curve starts")
    lx, ly = pt(EDGE_OUT + 0.5, -45)
    c.drawString(lx + s / 2 + 10, ly + s / 2 - 2, "5-3/8 in straight")
    mx, my = pt(EDGE_OUT + 1.5, -68)
    c.drawString(mx + 2, my - 4, "45 deg curve on the 26 in radius")
    bx, by = pt(EDGE_OUT + 1, -90)
    c.setFillColor(RED)
    c.drawString(bx - 30, by - 10, "butt joint = bracket 0")
    c.setFillColor(GREY)
    c.setFont("Helvetica-Oblique", 6.4)
    c.drawString(44, PH - 312, "To scale (1:9). Grey = roadbed edges r 26 / 31.75; blue = tracks r 28 / 30.5. "
                 "The helix is rotated so its grid starts here.")

    h2(c, 44, PH - 336, "ENTRY CONSTRUCTION")
    y = PH - 352
    for s in [
        "The tongue is cookie-cut from the existing deck with its track and 6 mm cork: the 5-3/8 in straight "
        "(the same on both tracks), then the 45 deg curve from 4:30. It is a liftout.",
        "It rises from the deck at the start of the straight to the butt joint, held by entry_wedge_riser_inside / "
        f"outside. At the butt joint its plywood top is {CORK:.3f} in below P1 and the cork makes the railheads "
        "continuous. Don't force the two plywood tops flush.",
        "P1 is a butt start with no lap: trim 1.875 deg radially off its entry end (0.851 in, about 27/32, on the "
        "26 in edge; 1.039 at 31.75). That leaves a 91.875 deg piece, inside chord 37.366 in.",
        f"P1 top is 1-1/32 in above the -15 deck at bracket 0 (p1_height_template, set by test fit); underside "
        f"{P1_TOP - PLY_T:.3f}. P1 sits on the cork-to-plywood transition shim in a pocket in the deck, with the "
        "0.376 in corner spacers under its two wing corners.",
        "Bracket 0 sits under the butt joint: keep its whole 0.600 strap on the helix side of the cork step. The "
        "bracket grid counts from here (page 6 / page 8 step 9).",
    ]:
        y = para(c, 50, y, s, 360, bullet="•") - 3

    # profile
    h2(c, 430, PH - 104, "PROFILE ALONG THE MEAN TRACK")
    c.setFillColor(GREY)
    c.setFont("Helvetica-Oblique", 6.4)
    c.drawString(430, PH - 117, "Vertical exaggerated. Brown = plywood, orange = cork, black = railhead.")
    x0, x1, x2 = 440, 690, 745
    L = STRAIGHT + arc45(R_MEAN)
    sx = (x1 - x0) / L
    yb, vy = PH - 225, 60
    xs = x0 + STRAIGHT * sx

    def yy(h):
        return yb + vy * h

    c.setStrokeColor(HexColor("#9a3412"))
    c.setLineWidth(4)
    c.line(x0, yy(0) - 2, x1, yy(LIFT) - 2)                  # tongue plywood
    c.line(x1, yy(P1_TOP) - 2, x2, yy(P1_TOP + G_MEAN * (x2 - x1) / sx) - 2)   # helix plywood
    c.setStrokeColor(ORANGE)
    c.setLineWidth(3)
    c.line(x0, yy(CORK) - 1.5, x1, yy(P1_TOP) - 1.5)         # cork on the tongue
    c.setStrokeColor(RAIL)
    c.setLineWidth(1.2)
    c.line(x0, yy(CORK) + 6, x1, yy(P1_TOP) + 6)
    c.line(x1, yy(P1_TOP) + 6, x2, yy(P1_TOP + G_MEAN * (x2 - x1) / sx) + 6)
    c.setStrokeColor(GREY)
    c.setLineWidth(0.5)
    c.line(x0 - 10, yb - 4, x2, yb - 4)
    c.setFillColor(GREY)
    c.setFont("Helvetica", 6.4)
    c.drawString(x0 - 10, yb - 13, "-15 deck")
    c.setStrokeColor(RED)
    c.setLineWidth(0.8)
    c.line(x1, yb - 20, x1, yy(P1_TOP) + 22)
    c.setFillColor(RED)
    c.setFont("Helvetica", 7)
    c.drawCentredString(x1, yy(P1_TOP) + 26, "butt joint / bracket 0")
    c.setStrokeColor(GREY)
    c.setLineWidth(0.5)
    c.line(xs, yb - 20, xs, yb + 4)
    c.line(x0, yb - 20, x0, yb + 4)
    c.setFillColor(INK)
    c.setFont("Helvetica", 6.8)
    c.drawCentredString((x0 + xs) / 2, yb - 28, f"{STRAIGHT:.3f}")
    c.drawCentredString((xs + x1) / 2, yb - 28, f"{arc45(R_MEAN):.3f} mean 45 deg arc")
    c.drawCentredString(xs, yb - 38, "4:30")
    c.drawString(x1 + 4, yy(P1_TOP) - 14, f"P1 top {P1_TOP:.3f}")
    c.drawString((x0 + x1) / 2 + 10, yy(LIFT / 2) - 16, f"tongue ply up {LIFT:.3f}")

    # local stack
    h2(c, 430, PH - 292, "LOCAL STACK AT THE BUTT JOINT")
    sy, sv, xa, xm, xc = PH - 400, 60, 440, 590, 745
    c.setFillColor(PLY)
    c.setStrokeColor(HexColor("#b54708"))
    c.setLineWidth(0.6)
    c.rect(xa, sy + sv * (LIFT - 0.75), xm - xa, sv * 0.75, stroke=1, fill=1)
    c.rect(xm, sy + sv * (P1_TOP - PLY_T), xc - xm, sv * PLY_T, stroke=1, fill=1)
    c.setFillColor(ORANGE)
    c.rect(xa, sy + sv * LIFT, xm - xa, sv * CORK, stroke=1, fill=1)
    c.setStrokeColor(RAIL)
    c.setLineWidth(1.6)
    c.line(xa, sy + sv * P1_TOP + 10, xc, sy + sv * P1_TOP + 10)
    c.setFillColor(INK)
    c.setFont("Helvetica", 7)
    c.drawCentredString((xa + xm) / 2, sy + sv * (LIFT - 0.4), "3/4 tongue plywood (on risers)")
    c.drawCentredString((xa + xm) / 2, sy + sv * (LIFT + 0.07), "6 mm / 0.236 cork")
    c.drawCentredString((xm + xc) / 2, sy + sv * (P1_TOP - 0.4), "0.72 helix plywood (P1)")
    c.drawCentredString((xa + xc) / 2, sy + sv * P1_TOP + 15, "continuous railhead")
    c.setStrokeColor(RED)
    c.setLineWidth(0.8)
    c.line(xm, sy - 12, xm, sy + sv * P1_TOP + 22)
    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(xm, sy - 22, "plywood top steps +0.236 in; railhead stays continuous")

    # planning values
    x, y, w = 430, 150, 320
    c.setFillColor(HexColor("#eff6ff"))
    c.roundRect(x - 8, 40, w + 16, 128, 6, stroke=0, fill=1)
    h2(c, x, 155, "AS-BUILT VALUES TO THE BUTT JOINT", 9.5)
    table(c, x, 140, w, [
        ("Straight (both tracks)", f"{STRAIGHT:.3f} in"),
        ("45 deg arc: inner r 28 / mean 29.25 / outer r 30.5",
         f"{arc45(R_IN):.3f} / {arc45(R_MEAN):.3f} / {arc45(R_OUT):.3f}"),
        ("Mean path, straight start to butt joint", f"{L:.3f} in"),
        ("P1 top / underside above the deck at bracket 0", f"{P1_TOP:.3f} / {P1_TOP - PLY_T:.3f}"),
        ("Tongue plywood lift at the butt joint", f"{LIFT:.3f} in"),
        ("Tongue grade as a straight ramp: inner / outer",
         f"{LIFT / (STRAIGHT + arc45(R_IN)):.2%} / {LIFT / (STRAIGHT + arc45(R_OUT)):.2%}"),
        (f"Clearance under loop 1 at the butt joint (T {T_TRACK:.3f})", f"{CLEAR:.2f} in"),
    ], [1.0], rh=13.5, size=7)


# ---------------------------------------------------------------- page 3
def page3(c):
    head(c, "VERTICAL GEOMETRY, CLEARANCE, AND EXIT",
         "The curved helix is fixed by the height stack; the exit straight is the vertical easing and "
         "cork-restoration zone.", 3)
    h2(c, 44, PH - 104, "HELIX GRADES")
    table(c, 44, PH - 124, 330, [
        ("28 in inner track", f"{grade(R_IN):.3%}"),
        ("30.5 in outer track", f"{grade(R_OUT):.3%}"),
        ("29.25 in planning radius", f"{grade(R_MEAN):.3%}"),
        ("Rise per 45 deg (bracket to bracket)", "0.500 in"),
        ("Rise per full turn", "4.000 in"),
    ], [1.0], rh=18, size=8)

    h2(c, 44, PH - 230, "OVERHEAD CLEARANCE")
    y = PH - 248
    for s in [
        "Railhead-to-railhead pitch is 4.000 in throughout the overlapping helix.",
        f"Clearance = 4.000 - 0.72 (measured plywood, not a nominal 3/4) - T. Nominal Atlas Code 83, "
        f"T about 0.160, gives {CLEAR:.2f} in. Caliper the actual track before sign-off.",
        f"Over the entry tongue the least clearance is at the butt joint ({CLEAR:.2f} in). The tongue climbs "
        "faster than the helix, so the gap opens up toward 4:30. Field check: loop-1 underside above the deck = "
        "4.311 - (degrees back from the butt joint / 90) in; subtract the railhead height measured there.",
        "The 0.080 in brace is recessed; check that no screw tip, washer or hardware projects below.",
    ]:
        y = para(c, 50, y, s, 320, size=7.8, bullet="-") - 4

    h2(c, 420, PH - 104, "RAILHEAD PROFILE")
    c.setFillColor(GREY)
    c.setFont("Helvetica", 6.6)
    c.drawString(420, PH - 117, "Normalized railheads: lower corked track = -15.000, upper corked track = 0.000 "
                 "(both carry 6 mm cork).")
    c.drawString(420, PH - 126, "The helix has no cork, so its railhead is the plywood top less 0.236 on this scale.")
    rows = [
        ("Start of the 5-3/8 in straight (existing track)", "-", "0.000", "-15.000"),
        ("Butt joint, bracket 0", f3(LIFT, True), f3(LIFT), f3(-15 + LIFT)),
        ("Bracket 28 (1260 deg), last regular bracket", "+14.000", f3(LIFT + 14), f3(-15 + LIFT + 14)),
        ("End of the 1290 deg helix", f3(HELIX_DEG / 45 * RISE_45 - 14, True), f3(END_RAIL + 15),
         f3(END_RAIL, True)),
        ("6 in into the exit straight, full grade", f3(6 * G_MEAN, True), f3(END_RAIL + 15 + 6 * G_MEAN),
         f3(END_RAIL + 6 * G_MEAN, True)),
        ("End of the 20-15/16 in straight, full grade*", f3((EXIT_STRAIGHT - 6) * G_MEAN, True),
         f3(END_RAIL + 15 + EXIT_STRAIGHT * G_MEAN), f3(END_RAIL + EXIT_STRAIGHT * G_MEAN, True)),
    ]
    table(c, 420, PH - 146, 335, rows, [0.62, 0.79, 1.0], rh=24, size=7.4,
          header=("Point", "Increment", "Rise", "Railhead"))

    c.setFillColor(NOTE_BG)
    c.roundRect(414, 120, 347, 150, 7, stroke=0, fill=1)
    h2(c, 426, 250, "EXIT INTERPRETATION", 10.5)
    y = 233
    for s in [
        f"The helix finishes {END_RAIL:.3f} in above the upper corked track. That is about 0.03 in lower than "
        "the earlier 3/4-based estimate, because the plywood is 0.72.",
        f"If the cork comes back about 6 in into the exit straight, the helix railhead there is "
        f"{END_RAIL + 6 * G_MEAN:+.2f} in at full grade, or {END_RAIL:+.2f} if the grade flattens at the end of "
        "the curve. Ease it in the exit straight and the curve under D01; easing early never reduces clearance, "
        "because the loop below is fixed.",
        "* Reference only: the exit doesn't carry full grade to its end. Don't change the 4 in pitch to force a "
        "zero. The exit straight's direction against the loop below still needs a field answer.",
    ]:
        y = para(c, 426, y, s, 325, size=7.2, color=NOTE_FG) - 5


# ---------------------------------------------------------------- page 8
STEPS = [
    ("Cut the flat 1x3 frame ties", "Cut 16 required ties with an 18.000 in outside/long edge and mirrored 22.5 deg "
     "ends. Short edge is 15.929 in (check only). Cut 8 more only if using the optional middle frame."),
    ("Prepare the eight posts", "Cut 8 x 2x4 uprights to 18.750 in. Orient every post 3.5 in RADIAL x 1.5 in "
     "TANGENTIAL. With post bottoms at the -15.000 in benchwork datum, 1/2 in D01 plywood on top places the D01 "
     "plywood surface at +4.250 in. Mark each 3.5 in side-face center at 1.750 in."),
    ("Assemble the lower and upper flat frames", "Lay the 1x3s flat. Center the 2.706 in mitered end contact on "
     "each 3.5 in post side. Lower frame occupies 0-0.75 in; upper frame 18.00-18.75 in. Optional middle frame "
     "centers at 9.375 in."),
    ("Place / verify the frame against the existing 26 in circle", "At each 45 deg station set BOTH outside "
     "corners of the 2x4 0.263 in inside the 26 in circle (bracket_edge_shim is the go/no-go gauge). Small errors "
     "along the circle need no frame change: the 0.600 strap slides +/-0.45 in on the post face."),
    ("Establish / verify the eight 45 deg stations", "The grid counts from the entry butt joint, and the frame is "
     "rotated to suit. Opposite stations are 52.000 in apart on the 26 in circle; adjacent ones 19.8995 in. "
     "Dry-fit the roadbed and fix any misfit by rotate, translate, then scale (build status section 2)."),
    ("Cookie-cut the entry", "Free the 5-3/8 in straight and the 45 deg curve from 4:30, keeping the track and "
     "6 mm cork. The tongue is a liftout on entry_wedge_riser_inside / outside."),
    ("Dry-fit the butt joint", "Trim P1 1.875 deg radially at its entry end. Set P1's top 1-1/32 in above the "
     "deck with p1_height_template, on the transition shim with the 0.376 in corner spacers. Raise the tongue until "
     "the railheads align, keeping the 0.236 in plywood step."),
    ("Test one bracket assembly", "Bench-test one actual 4x4 brace with a 3/32 in pocket and a piece of the "
     "0.72 in roadbed plywood under load before batch-routing."),
    ("Route pockets and install braces", "Bracket n sits n x 45 deg past the butt joint and n x 0.500 in above "
     "bracket 0; measure every height from bracket 0. Keep bracket 0's whole strap on the helix side of the cork "
     "step. Brackets stay square and radial; the plumb shim takes the 1.3 deg lean."),
    ("Assemble the roadbed spiral", "Use verified P1-P15 blanks. Half-laps in 0.72 ply: upper piece keeps 0.26, "
     "lower 0.46; six #6 x 5/8 screws per lap from the page 13 template. Check 26 / 31.75 radii and the 4.000 in "
     "pitch continuously. P1 entry and P15 exit are the only planned trims."),
    ("Fit the final 30 deg and exit", "The regular grid stops at bracket 28 (1260 deg, +14.000). Independently "
     "support the last 30 deg and the 20-15/16 in exit straight once they clear the loop below."),
    ("Restore cork and tie into D02", "Use the exit straight plus the following curve under D01 to ease the "
     "profile and reintroduce 6 mm cork. Do not alter the 4 in/turn helix pitch. Dry-fit the 1/2 in D01 deck over "
     "this easing zone before permanent attachment."),
]


def page8(c):
    head(c, "BUILD SEQUENCE / PRE-CUT AND PRE-TRACK CHECKS",
         "Use this order so the flat frame, the entry butt joint, brace fit and the final exit are verified before "
         "permanent track installation.", 8)
    y = PH - 96
    for i, (t, s) in enumerate(STEPS, 1):
        c.setFillColor(BLUE)
        c.circle(54, y - 7, 10, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 7.8)
        c.drawCentredString(54, y - 10, str(i))
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 9.2)
        c.drawString(74, y, f"{i}. {t}")
        yy = para(c, 74, y - 13, s, 600, size=6.7, lead=8.4)
        y = min(yy - 6, y - 34)
    c.setFillColor(OK_BG)
    c.roundRect(44, 36, 704, 38, 7, stroke=0, fill=1)
    c.setFillColor(HexColor("#067647"))
    c.setFont("Helvetica-Bold", 8.4)
    c.drawString(58, 61, "FINAL CHECK BEFORE TRACK")
    para(c, 58, 47, f"Confirm about {CLEAR:.2f} in overhead clearance (4.000 - 0.72 - measured track height), no "
         "protruding hardware, smooth transitions, half-lap seating, frame clearance, and D01/D02 clearance.",
         680, size=6.8)


def main(path):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PW, PH))
    for fn in (page2, page3, page8):
        fn(c)
        c.showPage()
    c.save()
    new = fitz.open("pdf", buf.getvalue())
    doc = fitz.open(path)
    for src, page in ((0, 2), (1, 3), (2, 8)):
        doc.delete_page(page - 1)
        doc.insert_pdf(new, from_page=src, to_page=src, start_at=page - 1)
    doc.save(path + ".tmp", garbage=3, deflate=True)
    doc.close()
    import os
    os.replace(path + ".tmp", path)
    print(path)


if __name__ == "__main__":
    main(sys.argv[1])
