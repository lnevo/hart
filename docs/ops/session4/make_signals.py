"""Draft mock signal STLs for punch list item 6. Units are mm; one STL per colour per option; every part is far
over 9 mm3 and one piece. Each signal has a square peg to push into the benchwork foam, so no stick size is assumed.

Run: /Users/lnevo/hart/.venv/bin/python docs/ops/session4/make_signals.py   (needs trimesh and manifold3d)
Colours: body (black), lamp_red, lamp_yellow, lamp_green. The lamps sit in sockets cut in the body, flush with the
face and 0.6 mm proud, so a four-colour plate prints without supports when the face points up or the part lies back.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

OUT = Path(__file__).parent / "out" / "stl"
LAMP_COLOURS = ("red", "yellow", "green")


def box(x0, x1, y0, y1, z0, z1):
    return trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0),
                                transform=trimesh.transformations.translation_matrix(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)))


def lamp_cyl(cx, cz, dia, y0, y1):
    """A cylinder along +y from y0 to y1, centred at x=cx, z=cz."""
    m = trimesh.creation.cylinder(radius=dia / 2, height=y1 - y0, sections=48)
    m.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, (1, 0, 0)))   # cylinder axis z -> +y
    m.apply_translation((cx, (y0 + y1) / 2, cz))
    return m


def build(parts, lamps, lamp_dia, face_y):
    """parts: boxes unioned into the body; lamps: [(colour, cx, cz)] cut into the face at y=face_y (body spans y<=face_y)."""
    body = trimesh.boolean.union(parts, engine="manifold") if len(parts) > 1 else parts[0]
    cuts = [lamp_cyl(cx, cz, lamp_dia, face_y - 3, face_y + 1) for _, cx, cz in lamps]
    body = trimesh.boolean.difference([body] + cuts, engine="manifold")
    out = {"body": body}
    for colour, cx, cz in lamps:
        out[f"lamp_{colour}"] = lamp_cyl(cx, cz, lamp_dia, face_y - 3, face_y + 0.6)
    return out


def option_a():
    """A: block. 24 x 12 housing, three lamps stacked, on a 7 x 7 peg 25 mm long. Height 45 above the peg."""
    parts = [box(-12, 12, 0, 12, 0, 45), box(-3.5, 3.5, 2.5, 9.5, -25, 0.5)]
    return build(parts, [("red", 0, 36), ("yellow", 0, 23), ("green", 0, 10)], 10, 12)


def option_b():
    """B: mast. 7 x 7 pole 70 mm tall, a 30 x 5 backing plate and a 22 x 8 head with three lamps, on a 7 x 7 peg."""
    parts = [box(-3.5, 3.5, 0, 7, 0, 70), box(-15, 15, 0, 5, 70, 112), box(-12, 12, 5, 13, 74, 108), box(-3.5, 3.5, 0, 7, -25, 0.5)]
    return build(parts, [("red", 0, 100), ("yellow", 0, 91), ("green", 0, 82)], 7, 13)


def option_c():
    """C: dwarf. Low 22 x 10 housing, lamps in a triangle (red top), on a 30 x 24 x 4 foot with a 7 x 7 peg under it."""
    parts = [box(-15, 15, -2, 22, 0, 4), box(-11, 11, 6, 16, 4, 34), box(-3.5, 3.5, 8.5, 15.5, -25, 0.5)]
    return build(parts, [("red", 0, 27), ("yellow", -5.5, 14), ("green", 5.5, 14)], 8, 16)


OPTIONS = {"A-block": option_a, "B-mast": option_b, "C-dwarf": option_c}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in OPTIONS.items():
        for part, mesh in fn().items():
            mesh.export(OUT / f"signal-{name}-{part}.stl")


if __name__ == "__main__":
    main()
