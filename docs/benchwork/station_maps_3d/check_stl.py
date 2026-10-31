#!/usr/bin/env python3
"""Fail if an ASCII STL is open or small enough for the slicer to take for inches."""

from __future__ import annotations

import re
import sys

MIN_VOLUME_MM3 = 18.0  # twice the slicer's 9 mm^3 limit
VERTEX = re.compile(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)")


def check(path: str) -> bool:
    with open(path) as f:
        pts = [tuple(float(c) for c in m.groups()) for m in VERTEX.finditer(f.read())]
    tris = [pts[i : i + 3] for i in range(0, len(pts), 3)]
    edges: dict = {}
    volume = 0.0
    for a, b, c in tris:
        volume += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        ) / 6
        for e in ((a, b), (b, c), (c, a)):
            edges[e] = edges.get(e, 0) + 1
    open_edges = sum(1 for (a, b), n in edges.items() if edges.get((b, a), 0) != n)
    ok = volume >= MIN_VOLUME_MM3 and open_edges == 0
    print(f"{'ok ' if ok else 'BAD'} {path}: {volume:.0f} mm3, {open_edges} open edges")
    return ok


if __name__ == "__main__":
    results = [check(p) for p in sys.argv[1:]]
    sys.exit(0 if all(results) else 1)
