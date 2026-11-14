#!/usr/bin/env python3
"""Draw the engine terminal as a placeholder on the staging level drawing.

    python3 engine_terminal.py > engine_terminal.svg

Switch 13 gets its turnout here but no label: levels_page.markers() already labels it.

The terminal is not in plan 5.3b. This lays it out in the plan's centimetres (y down, same
frame as staging_plan.svg) from the built topology in tables.xml and a photo of the benchwork
looking west along the Switch 7 straight (2026-11-13):

    Switch 13 (on the run's curve into the yard ladder) -> Switch 11 -> EH-1 (through leg)
                                                           Switch 11 -> Switch 9 -> EH-2 (through), EH-3

Taken from the photo: the three EH tracks lie south of the run, parallel to its straight, at
2.5 in centres (the track gauges in the photo); EH-3 is about 5 in from the run; Switch 9 sits
where the straights end, Switch 11 further round the curve, and the lead closes on the run
until it joins it at Switch 13. Taken from the drawing: the run and where Switch 13 sits on it
(levels_page.py LOCATE). Not measured: the stub lengths and the radii, so this is a placeholder.
"""
import math
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

sys.path.insert(0, str(paths.LAYOUT_SCRIPTS))
import layout_facts  # noqa: E402


def switch_hand(number):
    """L or R from switches.csv; this drawing cannot guess a hand nobody recorded."""
    hand = layout_facts.load_switches()[number].hand
    if hand not in ("L", "R"):
        raise SystemExit(f"switches.csv has no hand for Switch {number}; the engine terminal drawing needs it")
    return hand

RUN_C = (103.0, 442.8)      # centre of the run's curve from the Switch 7 straight up to Switch 15
RUN_R = 78.7
RUN_Y = 521.5               # the run's straight (Switch 7 is on it)
SW13 = (31.3, 475.3)        # Switch 13 from the loop 2 passes (levels_page.markers)
CC = 2.5 * 2.54             # EH track centres
GAP = 5.0 * 2.54            # run to EH-3
Y3, Y2, Y1 = RUN_Y + GAP, RUN_Y + GAP + CC, RUN_Y + GAP + 2 * CC
TO_LEN, TO_OFF = 23.4, 2.6  # turnout symbol, as the plan turnouts are drawn
LEAD_STRAIGHT = 0.0         # straight out of Switch 13's diverging leg before the lead curves
SW11_AT = 0.30              # Switch 11's points, as a share of the lead curve from Switch 13
STUB_END = 180.0            # x of the three end bumpers: lengths not measured


def on_run(deg):
    a = math.radians(deg)
    return (RUN_C[0] + RUN_R * math.cos(a), RUN_C[1] + RUN_R * math.sin(a))


def heading(deg):
    """Direction of travel on a curve centred like the run's, away from Switch 15, at this angle."""
    a = math.radians(deg)
    return (math.sin(a), -math.cos(a))


def arc_to_line(p, hdg_deg, y, end_deg=90.0):
    """Arc that leaves p on heading hdg_deg (as heading()) and reaches the line y on heading end_deg (90 is east)."""
    a = math.radians(hdg_deg)
    n = (-math.cos(a), -math.sin(a))                 # towards the centre
    r = (y - p[1]) / (math.sin(math.radians(end_deg)) + n[1])
    c = (p[0] + r * n[0], p[1] + r * n[1])
    return c, r


def arc_pts(c, r, deg0, deg1, step=3.0):
    k = max(2, int(abs(deg0 - deg1) / step) + 1)
    return [(c[0] + r * math.cos(math.radians(deg0 + (deg1 - deg0) * i / k)),
             c[1] + r * math.sin(math.radians(deg0 + (deg1 - deg0) * i / k))) for i in range(k + 1)]


def ease(p0, p1, n=12):
    """S-curve between two eastbound points (cubic with level end tangents at p1)."""
    d = (p1[0] - p0[0]) / 2
    s = 1 if p1[1] > p0[1] else -1
    q = [p0, (p0[0] + d, p0[1] + s * d * TO_OFF / TO_LEN), (p1[0] - d, p1[1]), p1]
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append(tuple(u ** 3 * q[0][j] + 3 * u * u * t * q[1][j] + 3 * u * t * t * q[2][j] + t ** 3 * q[3][j]
                         for j in range(2)))
    return out


def build():
    # Switch 9's hand from switches.csv. "L" (the owner's Switch 9): tilted so its diverging leg runs parallel
    # to the EH tracks (through leg to EH-2); "R" (the first build): through leg EH-3, diverging leg EH-2.
    sw9_hand = switch_hand(9)
    trk, to, lb, rl = [], [], [], []
    frog = math.degrees(math.atan2(TO_OFF, TO_LEN))
    step = math.degrees(TO_LEN / RUN_R)

    # Switch 13: points towards Switch 15, through leg along the run, diverging leg outside the curve
    a13 = math.degrees(math.atan2(SW13[1] - RUN_C[1], SW13[0] - RUN_C[0]))
    a_toe = a13 + step / 2
    toe13, thru13 = on_run(a_toe), on_run(a_toe - step)
    h = heading(a_toe - step / 2 + frog)
    div13 = (toe13[0] + TO_LEN * h[0], toe13[1] + TO_LEN * h[1])
    to.append((toe13, thru13, div13))

    # the lead: one curve from Switch 13 that ends on the EH-2 line, at Switch 9's points
    # Left-hand Switch 9: its diverging leg must leave parallel to the EH tracks (east), so the lead arrives
    # one frog angle south of east and the through leg, straight on, carries that tilt before it eases to EH-2.
    end = 90.0 + (frog if sw9_hand == "L" else 0.0)
    hd = a_toe - step / 2 + frog
    p = (div13[0] + LEAD_STRAIGHT * h[0], div13[1] + LEAD_STRAIGHT * h[1])
    c, r = arc_to_line(p, hd, Y3, end)
    a11 = hd + (end - hd) * SW11_AT                  # Switch 11's points on the lead
    st11 = math.degrees(TO_LEN / r)

    def at(deg):
        return (c[0] + r * math.cos(math.radians(deg)), c[1] + r * math.sin(math.radians(deg)))
    toe11, in11 = at(a11), at(a11 - st11)             # inner leg stays on the lead, towards Switch 9
    hd1 = a11 - st11 / 2 + frog                       # outer leg leaves the curve, towards EH-1
    h11 = heading(hd1)
    out11 = (toe11[0] + TO_LEN * h11[0], toe11[1] + TO_LEN * h11[1])
    trk.append([div13] + arc_pts(c, r, hd, a11))
    to.append((toe11, in11, out11))
    lb.append((toe11[0] - 1, toe11[1] + 44, "Sw 11"))
    trk.append(arc_pts(c, r, a11 - st11, end))                           # Switch 11 to Switch 9
    c1, r1 = arc_to_line(out11, hd1, Y1)
    trk.append(arc_pts(c1, r1, hd1, 90.0) + [(STUB_END, Y1)])            # EH-1, the outer track
    toe9 = at(end)
    if sw9_hand == "L":
        # through leg straight on along the arrival heading, diverging leg east along EH-3
        thru9 = (toe9[0] + TO_LEN * math.cos(math.radians(frog)), toe9[1] + TO_LEN * math.sin(math.radians(frog)))
        div9 = (toe9[0] + TO_LEN, toe9[1])
        to.append((toe9, thru9, div9))
        trk.append([div9, (STUB_END, Y3)])                               # EH-3
        trk.append(ease(thru9, (thru9[0] + 30, Y2)) + [(STUB_END, Y2)])  # EH-2, the normal route
    else:
        thru9, div9 = (toe9[0] + TO_LEN, Y3), (toe9[0] + TO_LEN, Y3 + TO_OFF)
        to.append((toe9, thru9, div9))
        trk.append([thru9, (STUB_END, Y3)])                              # EH-3
        trk.append(ease(div9, (div9[0] + 30, Y2)) + [(STUB_END, Y2)])    # EH-2
    lb.append((toe9[0] - 6, Y3 - 5, "Sw 9"))
    for y, name in ((Y3, "EH-3"), (Y2, "EH-2"), (Y1, "EH-1")):
        to.append(((STUB_END, y - 1.6), (STUB_END, y + 1.6), None))      # end bumper
        rl.append((STUB_END + 3, y + 1.8, name))
    rl.append((toe9[0] + 34, Y1 + 9, "Engine terminal: placeholder, not in plan 5.3b"))
    rl.append((toe9[0] + 34, Y1 + 15, "Switch 9 is left hand: its normal route goes to EH-2"
               if sw9_hand == "L" else "Switch 9's normal route goes to EH-2"))
    run = lambda P: sum(math.dist(P[k], P[k + 1]) for k in range(len(P) - 1)) / 2.54
    # trk order: Switch 13 to 11, Switch 11 to 9, EH-1, EH-3, EH-2
    lengths_in = {"13 to 11": run(trk[0]), "11 to 9": run(trk[1]), "EH-1": run(trk[2]), "EH-3": run(trk[3]), "EH-2": run(trk[4])}
    info = dict(lengths_in=lengths_in, lead_radius=r, eh1_radius=r1, sw13_toe=toe13, sw11_toe=toe11, sw9_toe=toe9,
                eh=dict(y1=Y1, y2=Y2, y3=Y3), eh1_tangent_x=c1[0])
    return trk, to, lb, rl, info


def svg():
    trk, to, lb, rl, info = build()
    out = []
    for pts in trk:
        out.append('<polyline class="trk" points="%s"/>' % " ".join("%.1f,%.1f" % p for p in pts))
    for a, b, c in to:
        for p, q in ((a, b), (a, c), (b, c)):
            if p and q:
                out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (p + q))
    for x, y, t in lb:
        out.append('<text class="lb" x="%.1f" y="%.1f">%s</text>' % (x, y, t))
    for x, y, t in rl:
        out.append('<text class="rl" x="%.1f" y="%.1f">%s</text>' % (x, y, t))
    return "\n".join(out) + "\n", info


if __name__ == "__main__":
    s, info = svg()
    sys.stdout.write(s)
    print(info, file=sys.stderr)
