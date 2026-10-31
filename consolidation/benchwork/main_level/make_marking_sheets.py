#!/usr/bin/env python3
"""Marking sheets for the main-level plywood: for each 4 x 8 sheet in the cut plan, every point to mark,
measured in from the sheet's left and top factory edges (the cut plan's orientation), with each edge read as a
straight line, a trammel arc (centre + radius) or a free curve (points to spring a batten through).

Needs shapely, numpy and reportlab. Run: python make_marking_sheets.py [out.pdf]
"""
import math
import os
import sys
import tempfile

import numpy as np
from shapely.geometry import LineString, Point
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "main_level_marking_sheets.pdf")
sys.argv = [sys.argv[0], tempfile.mkdtemp()]          # the cut plan writes its SVGs there on import
sys.path.insert(0, HERE)
import plywood_cut_plan as cp  # noqa: E402

PW, PH = landscape(letter)
INK, GREY, ACCENT = HexColor("#1f2326"), HexColor("#5f666b"), HexColor("#b4532a")
FILL = {"34": HexColor("#e3c48f"), "12": HexColor("#a9c6c0")}
CORNER_DEG = 20.0      # a turn sharper than this is a corner
FREE_STEP = 3.0        # spacing of points along a free curve
ARC_TOL = 1 / 16       # largest miss for an edge to count as a circular arc


def f16(v):
    """inches to the nearest 1/16 as text"""
    e = round(v * 16) / 16
    w = int(e)
    n = int(round((e - w) * 16))
    if n == 0:
        return f"{w}"
    d = 16
    while n % 2 == 0:
        n //= 2
        d //= 2
    return f"{w}-{n}/{d}" if w else f"{n}/{d}"


def turn(a, b, c):
    a1 = math.atan2(b[1] - a[1], b[0] - a[0])
    a2 = math.atan2(c[1] - b[1], c[0] - b[0])
    return abs(math.degrees((a2 - a1 + math.pi) % (2 * math.pi) - math.pi))


def fit_circle(pts):
    p = np.array(pts)
    A = np.c_[2 * p[:, 0], 2 * p[:, 1], np.ones(len(p))]
    b = (p ** 2).sum(1)
    cx, cy, k = np.linalg.lstsq(A, b, rcond=None)[0]
    r = math.sqrt(k + cx * cx + cy * cy)
    miss = max(abs(math.dist((cx, cy), q) - r) for q in pts)
    return (cx, cy), r, miss


def ring_edges(coords):
    """Split a closed ring at its corners into runs of points: [(kind, pts, extra)]."""
    pts = [coords[0]]
    for q in coords[1:-1]:
        if math.dist(q, pts[-1]) > 1e-3:
            pts.append(q)
    n = len(pts)
    corner = [turn(pts[i - 1], pts[i], pts[(i + 1) % n]) > CORNER_DEG for i in range(n)]
    if not any(corner):
        corner[0] = True
    start = corner.index(True)
    order = pts[start:] + pts[:start]
    flags = corner[start:] + corner[:start]
    runs, cur = [], [order[0]]
    for q, f in zip(order[1:] + [order[0]], flags[1:] + [True]):
        cur.append(q)
        if f:
            runs.append(cur)
            cur = [q]
    out = []
    for run in runs:
        out += split_run(run)
    return out


def split_run(run):
    """Break a smooth run into straight lines and circular arcs where it can (greedy, longest first);
    whatever is left is a free curve."""
    out, free, i, n = [], [], 0, len(run)

    def flush():
        if len(free) > 1:
            out.append(("free", free[:], None))
        free.clear()

    while i < n - 1:
        jl = i + 1                                  # straight: every point within tolerance of the chord
        while jl + 1 < n and all(LineString([run[i], run[jl + 1]]).distance(Point(q)) <= ARC_TOL / 4
                                 for q in run[i + 1:jl + 1]):
            jl += 1
        ja, arc_fit, j = None, None, i + 3          # arc: grow while it stays on one circle
        while j < n:
            c, r, miss = fit_circle(run[i:j + 1])
            if miss > ARC_TOL or r > 200:
                break
            ja, arc_fit = j, (c, r)
            j += 1
        if ja is not None and ja > jl and math.dist(run[i], run[ja]) >= 1.0:
            if free:
                free.append(run[i])
                flush()
            out.append(("arc", run[i:ja + 1], arc_fit))
            i = ja
        elif math.dist(run[i], run[jl]) >= 1.0 or jl == n - 1:
            if free:
                free.append(run[i])
                flush()
            out.append(("line", [run[i], run[jl]], None))
            i = jl
        else:
            free.append(run[i])
            i += 1
    if free:
        free.append(run[-1])
        flush()
    return out


def along(run, step):
    """Points every `step` along a polyline, plus its end."""
    d = [0.0]
    for a, b in zip(run, run[1:]):
        d.append(d[-1] + math.dist(a, b))
    out, s, i = [], step, 0
    while s < d[-1] - step / 3:
        while d[i + 1] < s:
            i += 1
        t = (s - d[i]) / (d[i + 1] - d[i])
        out.append((run[i][0] + t * (run[i + 1][0] - run[i][0]), run[i][1] + t * (run[i + 1][1] - run[i][1])))
        s += step
    return out


def on_edge(p):
    x, y = p
    return min(x, y, cp.SW - x, cp.SH - y) < 0.02


def marks_for(g):
    """Marks for one placed piece: [(label, x, y, note)], plus drawing hints."""
    rows, arcs, frees = [], [], []
    polys = g.geoms if hasattr(g, "geoms") else [g]
    for poly in polys:
        edges = ring_edges(list(poly.exterior.coords))
        for kind, run, extra in edges:
            p0 = run[0]
            if kind == "line":
                rows.append(("corner", p0, ""))
            elif kind == "arc":
                (cx, cy), r = extra
                on = 0 <= cx <= cp.SW and 0 <= cy <= cp.SH
                rows.append(("arc start", p0, f"arc R {f16(r)} · "
                             + (f"ctr {f16(cx)}, {f16(cy)}" if on else "ctr off sheet")))
                arcs.append(((cx, cy), r, run, on, len(rows)))
                if not on or r > 60:
                    for q in along(run, FREE_STEP * 2):
                        if not on_edge(q):
                            rows.append(("arc check", q, ""))
                else:
                    mid = run[len(run) // 2]
                    rows.append(("arc check", mid, "mid-arc check"))
            else:
                rows.append(("curve start", p0, "free curve: batten"))
                for q in along(run, FREE_STEP):
                    if not on_edge(q):          # points on a factory edge need no mark
                        rows.append(("curve", q, ""))
                frees.append(run)
    return rows, arcs, frees


def header(c, title, sub, page, pages):
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(36, PH - 40, title)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(GREY)
    c.drawString(36, PH - 54, sub)
    c.drawRightString(PW - 36, PH - 40, f"HART main level | marking sheets | page {page} of {pages}")
    c.setStrokeColor(HexColor("#d0d5dd"))
    c.line(36, PH - 62, PW - 36, PH - 62)


def draw_sheet(c, s, marks, k, ox, oy):
    """Sheet at k pt/in, top-left corner of the sheet at (ox, oy) in page points."""
    P = lambda x, y: (ox + x * k, oy - y * k)
    c.setFillColor(HexColor("#fbfaf6"))
    c.setStrokeColor(INK)
    c.setLineWidth(0.8)
    c.rect(ox, oy - cp.SH * k, cp.SW * k, cp.SH * k, stroke=1, fill=1)
    c.setStrokeColor(HexColor("#e7e3d8"))
    c.setLineWidth(0.4)
    for gx in range(12, 96, 12):
        c.line(*P(gx, 0), *P(gx, cp.SH))
    for gy in range(12, 48, 12):
        c.line(*P(0, gy), *P(cp.SW, gy))
    for pid, g, _ in s["placed"]:
        polys = g.geoms if hasattr(g, "geoms") else [g]
        for poly in polys:
            path = c.beginPath()
            cs = list(poly.exterior.coords)
            path.moveTo(*P(*cs[0]))
            for q in cs[1:]:
                path.lineTo(*P(*q))
            path.close()
            c.setFillColor(FILL[s["level"]])
            c.setStrokeColor(GREY)
            c.setLineWidth(0.6)
            c.drawPath(path, stroke=1, fill=1)
        rp = g.representative_point()
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(*P(rp.x, rp.y - 0.5), pid)
    for (cx, cy), r, run, on, n in marks["arcs"]:
        if on:
            x, y = P(cx, cy)
            c.setStrokeColor(ACCENT)
            c.setLineWidth(1)
            c.line(x - 5, y, x + 5, y)
            c.line(x, y - 5, x, y + 5)
            c.setFillColor(ACCENT)
            c.setFont("Helvetica", 5.6)
            c.drawString(x + 3, y + 2.5, f"c{n}")
    for n, (lab, (x, y), note, pid) in enumerate(marks["rows"], 1):
        if lab in ("corner", "arc start", "curve start", "arc check", "curve"):
            px, py = P(x, y)
            c.setFillColor(ACCENT if lab in ("corner", "arc start", "curve start") else GREY)
            c.circle(px, py, 1.6 if lab in ("corner", "arc start", "curve start") else 1.0, stroke=0, fill=1)
            if lab not in ("curve", "arc check") or n % 2 == 0:
                c.setFont("Helvetica", 5.6)
                dx = 3 if x < cp.SW - 3 else -3
                dy = -7 if y < 3 else 2.5
                (c.drawString if dx > 0 else c.drawRightString)(px + dx, py + dy, str(n))
    c.setFillColor(GREY)
    c.setFont("Helvetica", 7)
    c.drawString(ox, oy + 5, "TOP factory edge")
    c.drawRightString(ox + cp.SW * k, oy - cp.SH * k - 10, "96 in  |  grid 12 in")
    c.saveState()
    c.translate(ox - 5, oy - cp.SH * k / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, "LEFT factory edge")
    c.restoreState()


def build():
    sheets = [s for s in cp.SHEETS]
    pages = []
    for s in sheets:
        rows, arcs = [], []
        for pid, g, _ in s["placed"]:
            r, a, _ = marks_for(g)
            arcs += [(cc, rr, run, on, n + len(rows)) for cc, rr, run, on, n in a]
            rows += [(lab, p, note, pid) for lab, p, note in r]
        pages.append((s, dict(rows=rows, arcs=arcs)))
    # the drawing page takes the first FIRST rows (3 columns); the rest go on table pages of 3 x 40
    k, FIRST, per = 6.6, 3 * 13, 3 * 40
    total = 1 + sum(1 + math.ceil(max(len(m["rows"]) - FIRST, 0) / per) for _, m in pages)
    c = canvas.Canvas(OUT, pagesize=(PW, PH))
    c.setTitle("HART main level - plywood marking sheets")
    page = 1
    header(c, "Main-level plywood marking sheets", "Every point to mark on each 4 x 8 sheet, measured in from the "
           "LEFT and TOP factory edges, in the cut plan's orientation.", page, total)
    y = PH - 90
    c.setFillColor(INK)
    for s in [
        "How to use: lay the sheet good face up with the same edge at the top as the cut-plan sheet. Measure each "
        "mark along the top edge (from left) and down (from top) with a square or a story stick; tick it, then "
        "join the marks.",
        "Straight edges: join the two corner marks with a straightedge or a snapped line.",
        "Arcs: the table gives the radius and the centre. If the centre is on the sheet, mark it and swing a "
        "trammel (or the router on a trammel arm) from the arc start to the next mark; the mid-arc check should "
        "fall on the line. If the centre is off the sheet, spring a batten through the check points instead.",
        "Free curves (eased edges, the board's S-curve, the turnback): mark the points every 3 in and spring a thin "
        "batten through them.",
        "Marks on the sheet edge need no measuring in that direction. Points are to the nearest 1/16 in, and an edge is read as an arc when it stays within 1/16 in of one; cut on "
        "the waste side of the line. Pieces drawn flipped in the cut plan are marked as drawn.",
        "Check before cutting: measure one long diagonal of each rectangle-like piece against the drawing, and "
        "confirm the piece sizes in the cut plan (the bounding sizes are listed there).",
    ]:
        from reportlab.lib.utils import simpleSplit
        for i, ln in enumerate(simpleSplit(s, "Helvetica", 10, PW - 90)):
            c.setFont("Helvetica", 10)
            c.drawString(50 if i else 40, y, ("- " if i == 0 else "") + ln)
            y -= 14
        y -= 6
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y - 6, "Sheets: " + "   ".join(f"{s['id']} ({'3/4' if s['level'] == '34' else '1/2'}): "
                                                      f"{s['title']}" for s, _ in pages[:5]))
    c.drawString(40, y - 20, "        " + "   ".join(f"{s['id']} ({'3/4' if s['level'] == '34' else '1/2'}): "
                                                    f"{s['title']}" for s, _ in pages[5:]))
    c.showPage()
    for s, m in pages:
        page += 1
        th = "3/4 in" if s["level"] == "34" else "1/2 in"
        header(c, f"Sheet {s['id']} ({th}): {s['title']}", "Orange dots = corners / arc and curve starts "
               "(numbered); grey = check points along arcs and curves; orange cross = trammel centre on the sheet.",
               page, total)
        draw_sheet(c, s, m, k, (PW - cp.SW * k) / 2, PH - 84)
        rows = m["rows"]
        table(c, rows[:FIRST], 0, PH - 84 - cp.SH * k - 26, 13)
        c.showPage()
        for start in range(FIRST, len(rows), per):
            page += 1
            header(c, f"Sheet {s['id']} ({th}): marks, continued", "From left = along the top edge; from top = "
                   "down from the top edge. Inches, nearest 1/16.", page, total)
            table(c, rows[start:start + per], start, PH - 80, 40)
            c.showPage()
    c.save()
    print(OUT, total, "pages")


def table(c, chunk, start, top, nrow):
    colw = (PW - 72) / 3
    for i, (lab, (x, y), note, pid) in enumerate(chunk):
        col, row = divmod(i, nrow)
        tx, ty = 36 + col * colw, top - row * 11
        if row == 0:
            c.setFont("Helvetica-Bold", 7.2)
            c.setFillColor(GREY)
            c.drawString(tx, ty + 2, "#")
            c.drawString(tx + 18, ty + 2, "piece")
            c.drawRightString(tx + 84, ty + 2, "from left")
            c.drawRightString(tx + 128, ty + 2, "from top")
        ty -= 10
        strong = lab in ("corner", "arc start", "curve start")
        c.setFillColor(INK if strong else GREY)
        c.setFont("Helvetica-Bold" if strong else "Helvetica", 7.4)
        c.drawString(tx, ty, str(start + i + 1))
        c.setFont("Helvetica", 7.4)
        c.drawString(tx + 18, ty, pid)
        c.drawRightString(tx + 84, ty, "edge" if x < 0.02 else ("96" if x > cp.SW - 0.02 else f16(x)))
        c.drawRightString(tx + 128, ty, "edge" if y < 0.02 else ("48" if y > cp.SH - 0.02 else f16(y)))
        tag = note or ("" if lab == "corner" else lab)
        c.setFont("Helvetica", 5.8)
        c.setFillColor(ACCENT if "arc R" in tag or "free" in tag else GREY)
        c.drawString(tx + 134, ty, tag)


if __name__ == "__main__":
    build()
