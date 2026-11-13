"""label_check.py <drawing.svg> [--list]

Check 5 of the specification (docs/ops/SCHEMATIC_SPEC.md): no label may overlap a drawn line, a symbol or
another label. Works on the finished SVG, so it judges what the reader sees, whatever placed the labels.

Text boxes are measured with the drawing's own font (Helvetica Neue, from the system font files) and its
letter-spacing; a box runs from the cap height above the baseline to a small margin below it. Lines are
the drawn path segments widened by half their stroke. Prints one fault per pair, naming both items.
"""
import math
import re
import sys
import xml.etree.ElementTree as ET

from PIL import ImageFont

NS = "{http://www.w3.org/2000/svg}"
FONT = "/System/Library/Fonts/HelveticaNeue.ttc"
FACES = {"normal": 0, "bold": 1}                     # face index in the .ttc
CAP, BELOW, PAD = 0.72, 0.06, 0.6                  # cap height and margin below the baseline (em); clearance (px)
_fonts = {}


def font(weight, size):
    key = (weight, round(size * 4))
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(FONT, 400, index=FACES.get(weight, 0))
    return _fonts[key]


def text_width(s, size, weight, spacing):
    return font(weight, size).getlength(s) * size / 400 + spacing * max(len(s) - 1, 0)


def parse_transform(t):
    """translate(x,y) scale(s) only, which is all the drawing uses. Returns (tx, ty, s)."""
    tx = ty = 0.0
    s = 1.0
    if t:
        m = re.search(r"translate\(([-\d.]+)[ ,]+([-\d.]+)\)", t)
        if m:
            tx, ty = float(m.group(1)), float(m.group(2))
        m = re.search(r"scale\(([-\d.]+)\)", t)
        if m:
            s = float(m.group(1))
    return tx, ty, s


def compose(outer, inner):
    ox, oy, os_ = outer
    ix, iy, is_ = inner
    return ox + os_ * ix, oy + os_ * iy, os_ * is_


def walk(el, tf, out):
    tf = compose(tf, parse_transform(el.get("transform")))
    tag = el.tag.replace(NS, "")
    tx, ty, s = tf
    P = lambda x, y: (tx + s * x, ty + s * y)
    if tag == "path":
        w = float(el.get("stroke-width", 1)) * s
        pts, cur = [], None
        for cmd, x, y in re.findall(r"([ML])\s*([-\d.]+)[ ,]([-\d.]+)", el.get("d", "")):
            p = P(float(x), float(y))
            if cmd == "L" and cur is not None:
                out["lines"].append((cur, p, w))
            cur = p
    elif tag in ("circle", "ellipse"):
        cx, cy = P(float(el.get("cx")), float(el.get("cy")))
        rx = float(el.get("r") or el.get("rx")) * s
        ry = float(el.get("r") or el.get("ry")) * s
        out["shapes"].append(("circle", (cx - rx, cy - ry, cx + rx, cy + ry)))
    elif tag == "text":
        size = float(el.get("font-size", 10)) * s
        spacing = float(el.get("letter-spacing", 0)) * s
        txt = "".join(el.itertext())
        w = text_width(txt, size, el.get("font-weight", "normal"), spacing)
        x, y = P(float(el.get("x")), float(el.get("y")))
        a = el.get("text-anchor", "start")
        x0 = x - (w / 2 if a == "middle" else w if a == "end" else 0)
        out["texts"].append((txt, (x0, y - CAP * size, x0 + w, y + BELOW * size)))
    for c in el:
        walk(c, tf, out)


def seg_box_gap(a, b, box):
    """Distance from segment ab to an axis-aligned box (0 if they touch)."""
    x0, y0, x1, y1 = box
    if any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in (a, b)):
        return 0.0
    edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    if any(_cross(a, b, c, d) for c, d in edges):
        return 0.0
    best = min(_pt_seg(p, a, b) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
    return min(best, *(_pt_seg(p, c, d) for p in (a, b) for c, d in edges))


def _pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _cross(a, b, c, d):
    o = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def boxes_overlap(p, q, pad=0.0):
    return p[0] < q[2] + pad and q[0] < p[2] + pad and p[1] < q[3] + pad and q[1] < p[3] + pad


def check(svg):
    out = {"lines": [], "shapes": [], "texts": []}
    walk(ET.parse(svg).getroot(), (0.0, 0.0, 1.0), out)
    lines = [l for l in out["lines"] if not _frame(l)]
    faults = []
    T = out["texts"]
    for i, (t, box) in enumerate(T):
        for a, b, w in lines:
            if seg_box_gap(a, b, box) < w / 2 + PAD:
                faults.append(("track", t, f"line {a[0]:.0f},{a[1]:.0f}-{b[0]:.0f},{b[1]:.0f}", box))
                break
        for kind, sb in out["shapes"]:
            inside = sb[0] <= box[0] and box[2] <= sb[2] and sb[1] <= box[1] and box[3] <= sb[3]
            if boxes_overlap(box, sb) and not inside:      # a letter inside its own circle is the symbol
                faults.append(("symbol", t, f"{kind} at {(sb[0] + sb[2]) / 2:.0f},{(sb[1] + sb[3]) / 2:.0f}", box))
        for u, ub in T[i + 1:]:
            if boxes_overlap(box, ub, PAD):
                faults.append(("label", t, u, box))
    return faults, len(T)


def _frame(l):
    """Sheet border and title-block rules are not track."""
    return False


if __name__ == "__main__":
    faults, n = check(sys.argv[1])
    kinds = {}
    for f in faults:
        kinds[f[0]] = kinds.get(f[0], 0) + 1
    print(f"{sys.argv[1]}: {n} labels, {len(faults)} label faults", kinds)
    if "--list" in sys.argv:
        for kind, t, other, box in faults:
            print(f"  {kind:6} {t!r:28} vs {other}  at {box[0]:.0f},{box[1]:.0f}")
