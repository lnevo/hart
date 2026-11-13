"""labels.py: place labels so none sits on a line, a symbol or another label (rule R12, draw-time part).

Each label is asked for with an ordered list of allowed positions. Obstacles are known first (every drawn
line, every symbol); labels are then placed hardest first (fewest free positions), each taking its first
free position. A label with no free position takes the least bad one and is reported, so the layout can be
given more room there (the grid-room part of R12, still to do in the layout).

Positions are SVG text anchors: (x, baseline y, text-anchor).
"""
import math

from label_check import BELOW, CAP, boxes_overlap, seg_box_gap, text_width

PAD = 1.2


def text_box(x, y, anchor, s, size, weight, spacing=0.0):
    w = text_width(s, size, weight, spacing)
    x0 = x - (w / 2 if anchor == "middle" else w if anchor == "end" else 0)
    return (x0, y - CAP * size, x0 + w, y + BELOW * size)


class Placer:
    def __init__(self):
        self.lines = []       # (a, b, width)
        self.boxes = []       # symbols and placed labels
        self.asks = []
        self.unplaced = []

    def line(self, a, b, w):
        self.lines.append((a, b, w))

    def box(self, b):
        self.boxes.append(b)

    def clear(self, box, pad=PAD):
        if any(seg_box_gap(a, b, box) < w / 2 + pad for a, b, w in self.lines):
            return False
        return not any(boxes_overlap(box, o, pad) for o in self.boxes)

    def cost(self, box):
        c = sum(1 for a, b, w in self.lines if seg_box_gap(a, b, box) < w / 2 + PAD)
        return c + sum(1 for o in self.boxes if boxes_overlap(box, o, PAD))

    def ask(self, what, s, size, cands, weight="normal", extra="", spacing=0.0, emit=None):
        """cands: [(x, y, anchor)] in order of preference."""
        self.asks.append(dict(what=what, s=s, size=size, cands=cands, weight=weight, extra=extra,
                              spacing=spacing, emit=emit))

    def solve(self):
        """Place every label asked for; returns [(ask, (x, y, anchor))]."""
        def boxes(a):
            return [text_box(x, y, an, a["s"], a["size"], a["weight"], a["spacing"]) for x, y, an in a["cands"]]
        todo = list(self.asks)
        out = []
        while todo:
            free = [(sum(self.clear(b) for b in boxes(a)), i) for i, a in enumerate(todo)]
            _, i = min(free)
            a = todo.pop(i)
            bs = boxes(a)
            k = next((j for j, b in enumerate(bs) if self.clear(b)), None)
            if k is None:
                k = min(range(len(bs)), key=lambda j: (self.cost(bs[j]), j))
                self.unplaced.append(f"{a['what']} {a['s']}")
            self.boxes.append(bs[k])
            out.append((a, a["cands"][k]))
        return out


def around(x, y, size, dxs, dys, anchor="middle"):
    """Candidate anchors on a small grid around a point, in the order given."""
    return [(x + dx, y + dy, anchor) for dy in dys for dx in dxs]


def dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])
