#!/usr/bin/env python3
"""The run from Switch 5 to Switch 15 on the staging level drawing (staging_plan.svg), read from the drawing, and
where the timed passes put Switch 7 and 13 on it.

Nothing about the drawing is typed here: the run is the chain of `sw7` polylines in the SVG, starting at the one end
nearest the "Sw 5" label and continuing from the toe of Switch 5's turnout symbol (the corner of its three `to`
lines that lies furthest from the run). Where Switch 7 and 13 sit comes from loop2_locate.csv (the timed passes of
2026-11-13: mm from Switch 5's points along the run), checked against block_lengths.csv. A drawing that does not
chain into one run, or a data file that disagrees with the block lengths, stops with the reason.
"""
import csv
import math
import re
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, railroad  # noqa: E402

sys.path.insert(0, str(paths.LAYOUT_SCRIPTS))
import infer_block_lengths as infer  # noqa: E402  the plan's turnout centres along the run (PLAN_LOOP2_TURNOUT_MM)

LOCATE_CSV = paths.LAYOUT_DATA / "loop2_locate.csv"
BLOCK_CSV = paths.LAYOUT_DATA / "block_lengths.csv"
MM_PER_IN = 25.4
TOLERANCE_MM = 1.5          # the recorded means are rounded to the mm, so the sums may differ by that
LENGTH_TOLERANCE_IN = 0.06  # block_lengths.csv holds one decimal
FIT_CM = 0.15               # how far a drawn arc point may lie from the circle fitted to it (the SVG is rounded to 0.1)

PIN_5 = infer.PLAN_LOOP2_TURNOUT_MM["Switch 5"]     # Switch 5 and Switch 15 centres, mm from Switch 5's points
PIN_15 = infer.PLAN_LOOP2_TURNOUT_MM["Switch 15"]


class RunError(ValueError):
    """The drawing or the locate data cannot give the run."""


def _num(row, field, line):
    try:
        return float(row[field])
    except (KeyError, TypeError, ValueError):
        raise RunError(f"{LOCATE_CSV.name} line {line}: {field!r} is not a number ({row.get(field)!r})")


def load_locate(path=LOCATE_CSV):
    """{"7": dict(mean, step24, step48, before), "13": ..., "7b": mean mm} from loop2_locate.csv, mm from Switch 5's
    points. Checks each mean against its two passes and each 'before' against the Switch 15 pin."""
    out = {}
    with open(path, newline="") as f:
        for line, row in enumerate(csv.DictReader(f), 2):
            sec = (row.get("section") or "").strip()
            if sec in out or sec not in ("Switch 7", "Switch 13", "Switch 7b"):
                raise RunError(f"{path.name} line {line}: section {sec!r} is not Switch 7, Switch 13 or Switch 7b, "
                               "or it repeats")
            key = sec[len("Switch "):]
            if sec == "Switch 7b":     # the loop 1 estimate: a mean and nothing else
                out[key] = _num(row, "mean_mm", line)
                continue
            rec = {f: _num(row, f, line) for f in ("mean_mm", "step24_mm", "step48_mm", "before_sw15_mm")}
            if abs(rec["mean_mm"] - (rec["step24_mm"] + rec["step48_mm"]) / 2) > TOLERANCE_MM:
                raise RunError(f"{path.name} line {line}: the mean {rec['mean_mm']:.0f} mm is not the mean of its "
                               f"passes {rec['step24_mm']:.0f} and {rec['step48_mm']:.0f} mm")
            if abs(PIN_15 - rec["mean_mm"] - rec["before_sw15_mm"]) > TOLERANCE_MM:
                raise RunError(f"{path.name} line {line}: {rec['before_sw15_mm']:.0f} mm before Switch 15 does not "
                               f"match its mean {rec['mean_mm']:.0f} mm and the Switch 15 pin at {PIN_15} mm")
            out[key] = {"mean": rec["mean_mm"], "step24": rec["step24_mm"], "step48": rec["step48_mm"],
                        "before": rec["before_sw15_mm"]}
    missing = {"7", "13", "7b"} - set(out)
    if missing:
        raise RunError(f"{path.name} has no row for Switch {', Switch '.join(sorted(missing))}")
    return out


def check_block_lengths(locate, csv_path=BLOCK_CSV):
    """Scale, Barn, OS Switch 13 and OS Switch 15 in block_lengths.csv must follow from the timed centres: blocks
    tile the run, so Scale is Switch 5 to Switch 7 less half of OS Switch 5 and OS Switch 7, OS Switch 13 and 15
    split the gap between their centres, and Barn is what is left between Switch 7 and 13. Raises RunError."""
    inches = {name: b.jmri_in for name, b in railroad.read_block_lengths(csv_path).items()}   # all four are timed
    l7, l13 = locate["7"]["mean"], locate["13"]["mean"]
    gap = PIN_15 - l13
    half = lambda name: inches[name] * MM_PER_IN / 2
    want = {"Track Scale": (l7 - PIN_5) - half("OS Switch 5") - half("OS Switch 7"),
            "Track Barn": (l13 - l7) - half("OS Switch 7") - gap / 2,
            "OS Switch 13": gap, "OS Switch 15": gap}
    bad = [f"{n} is {inches[n]:.1f} in, the timed passes give {mm / MM_PER_IN:.1f} in"
           for n, mm in want.items() if abs(inches[n] - mm / MM_PER_IN) > LENGTH_TOLERANCE_IN]
    if bad:
        raise RunError("block_lengths.csv and " + LOCATE_CSV.name + " disagree: " + "; ".join(bad))


def _points(s):
    return [tuple(map(float, p.split(","))) for p in s.split()]


def _key(p):
    return "%.1f,%.1f" % p


def run_path(staging):
    """The run from Switch 5's points to its far end, read from the drawing: (path, pieces). path is one list of
    points (cm, y down); pieces are the drawn polylines it is made of, in order and oriented along it (the first,
    the turnout symbol's route, is a straight line)."""
    polys = [_points(m.group(1)) for m in re.finditer(r'<polyline class="sw7" points="([^"]+)"', staging)]
    if not polys:
        raise RunError("the staging drawing has no sw7 polylines (the run from Switch 5 to Switch 15)")
    at = {}
    for i, q in enumerate(polys):
        for end in (q[0], q[-1]):
            at.setdefault(_key(end), []).append(i)
    ends = [k for k, v in at.items() if len(v) == 1]
    if len(ends) != 2 or any(len(v) > 2 for v in at.values()):
        raise RunError(f"the sw7 polylines do not chain into one run: {len(ends)} loose end(s), "
                       f"joins {sorted(len(v) for v in at.values())}")
    label = re.search(r'<text class="lb" x="([\d.]+)" y="([\d.]+)">Sw 5</text>', staging)
    if not label:
        raise RunError('the staging drawing has no "Sw 5" label to tell which end of the run is Switch 5')
    lab = (float(label.group(1)), float(label.group(2)))
    start = min(ends, key=lambda k: math.dist(tuple(map(float, k.split(","))), lab))
    # the toe of Switch 5's turnout symbol: of the three corners of its `to` lines, the one furthest from the run
    tos = [tuple(map(float, m.groups())) for m in
           re.finditer(r'<line class="to" x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"', staging)]
    tri = [t for t in tos if start in (_key(t[:2]), _key(t[2:]))]
    corners = {c for t in tri for c in (t[:2], t[2:])}
    if len(tri) != 2 or len(corners) != 3:
        raise RunError(f"the run's first end {start} is not a corner of one turnout symbol (3 corners, 2 lines on it)")
    here = tuple(map(float, start.split(",")))
    toe = max(corners, key=lambda c: math.dist(c, here))
    path, pieces, used, cur = [toe, here], [[toe, here]], set(), start
    while True:
        nxt = [i for i in at[cur] if i not in used]
        if not nxt:
            break
        used.add(nxt[0])
        q = polys[nxt[0]]
        if _key(q[0]) != cur:
            q = q[::-1]
        path += q[1:]
        pieces.append(q)
        cur = _key(q[-1])
    if len(used) != len(polys):
        raise RunError(f"the run chain covers {len(used)} of {len(polys)} sw7 polylines")
    return path, pieces


def point_at(path, d_cm):
    run = 0.0
    for i in range(1, len(path)):
        seg = math.dist(path[i - 1], path[i])
        if run + seg >= d_cm:
            t = (d_cm - run) / seg
            return [path[i - 1][j] + t * (path[i][j] - path[i - 1][j]) for j in range(2)]
        run += seg
    return list(path[-1])


def tangent_circle(join, heading, points):
    """The circle that touches the line through `join` along `heading` at `join` and passes through the last of the
    points (the drawn points are rounded to 0.1 cm, so a free fit would put the centre a mm or two off; the join and
    the far end are the two points the drawing fixes). Returns the centre and radius."""
    hx, hy = heading
    norm = math.hypot(hx, hy)
    if norm < 1e-9:
        raise RunError("the straight before the run's curve has no direction")
    n = (-hy / norm, hx / norm)
    a, b = points[-1][0] - join[0], points[-1][1] - join[1]
    side = a * n[0] + b * n[1]
    if abs(side) < 1e-9:
        raise RunError("the run's curve ends on its straight")
    if side < 0:
        n = (-n[0], -n[1])
        side = -side
    r = (a * a + b * b) / (2 * side)
    return (join[0] + r * n[0], join[1] + r * n[1]), r


def piece_at(pieces, p):
    """The drawn polyline of the run that passes through point p."""
    best = min(pieces, key=lambda q: min(math.dist(p, v) for v in q))
    if min(math.dist(p, v) for v in best) > 3.0:
        raise RunError(f"no drawn piece of the run lies near ({p[0]:.1f}, {p[1]:.1f})")
    return best


def curve_at(pieces, p):
    """Centre and radius (cm, to 0.1) of the circle the run's piece through p is drawn on. The piece leaves the
    straight before it tangent to it; every drawn point must lie on the circle."""
    seg = piece_at(pieces, p)
    k = next(i for i, q in enumerate(pieces) if q is seg)
    if k == 0 or len(seg) < 5:
        raise RunError(f"the run's piece at ({p[0]:.1f}, {p[1]:.1f}) is not a drawn curve after a straight")
    before = pieces[k - 1]
    if before[-1] != seg[0]:
        raise RunError("the run's pieces do not join end to end")
    c, r = tangent_circle(seg[0], (before[-1][0] - before[-2][0], before[-1][1] - before[-2][1]), seg)
    off = max(abs(math.dist(q, c) - r) for q in seg)
    if off > FIT_CM:
        raise RunError(f"the run's curve at ({p[0]:.1f}, {p[1]:.1f}) is not a circle: points lie {off:.2f} cm off the fit")
    return (round(c[0], 1), round(c[1], 1)), round(r, 1)


def straight_at(staging, pieces, p, loop_class="loop"):
    """y of the run at p, where it must be a straight, and how far the loop's own straight lies above it (the
    Switch 7 crossover joins the two), both read from the drawing."""
    seg = piece_at(pieces, p)
    ys = [y for _, y in seg]
    if max(ys) - min(ys) > 0.05:
        raise RunError(f"the run is not straight at ({p[0]:.1f}, {p[1]:.1f}), where Switch 7 sits")
    above = []
    for m in re.finditer(r'<polyline class="%s" points="([^"]+)"' % loop_class, staging):
        q = _points(m.group(1))
        qy = [y for _, y in q]
        if max(qy) - min(qy) < 0.3 and min(x for x, _ in q) <= p[0] <= max(x for x, _ in q) \
                and 0 < p[1] - sum(qy) / len(qy) < 20:
            above.append(q)
    if len(above) != 1:
        raise RunError(f"{len(above)} straight loop tracks lie just above the run at Switch 7 (x {p[0]:.1f} cm); "
                       "expected one")
    return ys[0], round(ys[0] - sum(y for _, y in above[0]) / len(above[0]), 1)
