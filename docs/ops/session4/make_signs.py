"""Control point signs (plate) and the crew board (columns): punch list items 4 and 5 (SVG in mm, then PDF).

Run: /Users/lnevo/hart/.venv/bin/python docs/ops/session4/make_signs.py
The PDF step needs PyMuPDF (the root .venv has it); without it only the SVGs are written.
"""
from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).parent))
import facts

OUT = Path(__file__).parent / "out"
LETTER = (215.9, 279.4)
TABLOID_L = (431.8, 279.4)
FONT = "Helvetica, Arial, sans-serif"
LEVEL_FILL = {"Staging": "#6b7280", "Main": "#1d4ed8", "Upper": "#b45309"}


def t(x, y, s, size, fill="#000", anchor="middle", weight="bold", rot=0):
    r = f' transform="rotate({rot} {x} {y})"' if rot else ""
    return (f'<text x="{x:.2f}" y="{y:.2f}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}"{r}>{escape(s)}</text>')


def rect(x, y, w, h, fill="none", stroke="#000", sw=0.3, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'


def page(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">'
            f'<rect width="{w}" height="{h}" fill="#fff"/>' + "".join(body) + "</svg>")


def fit(s, width, top):
    """Font size so that bold text of this length fits the width (mm), at most top."""
    return round(min(top, width / (0.62 * len(s))), 1)


def sw_text(cp):
    return ("Switch " if len(cp["switches"]) == 1 else "Switches ") + ", ".join(cp["switches"])


def sign_a(x, y, cp):
    """Plate 62 x 42, level colour band on top; a dashed strip below marks where the stick is glued on the back."""
    w, h = 62, 42
    return [rect(x, y, w, h, "#fff", sw=0.4), rect(x, y, w, 8, LEVEL_FILL[cp["level"]], stroke="none"),
            t(x + w / 2, y + 5.6, f"CONTROL POINT  -  {cp['level'].upper()}", 3.6, "#fff"),
            t(x + w / 2, y + 26, cp["name"], fit(cp["name"], 56, 15)),
            t(x + w / 2, y + 36, sw_text(cp), 4, weight="normal"),
            rect(x + w / 2 - 6, y + h + 2, 12, 8, "none", "#888", 0.2, "1,1"),
            t(x + w / 2, y + h + 7, "stick", 3, "#888", weight="normal")]


def sheets(cps, draw, cell, title, cols, rows):
    per, pages = cols * rows, []
    for p in range(0, len(cps), per):
        body = [t(10, 8, f"{title}: print at 100 percent, cut on the outline", 3.5, anchor="start", weight="normal")]
        for i, cp in enumerate(cps[p:p + per]):
            body += draw(10 + (i % cols) * cell[0], 14 + (i // cols) * cell[1], cp)
        pages.append(page(*LETTER, body))
    return pages


def chips(x, y, colours, size=9, gap=2, per_row=4):
    return [rect(x + (k % per_row) * (size + gap), y + (k // per_row) * (size + gap), size, size, c["hex"], "#000", 0.2)
            for k, c in enumerate(colours)]


def board_b(jobs):
    """Columns: one tall card per job with the order number on top, colour chips and a name box at the bottom."""
    w, h = TABLOID_L
    body = [t(w / 2, 20, "CREW BOARD: sign up left to right", 14)]
    cw = (w - 20 - 4 * (len(jobs) - 1)) / len(jobs)
    for i, j in enumerate(jobs):
        x = 10 + i * (cw + 4)
        body += [rect(x, 30, cw, 235, "#fff", sw=0.5), rect(x, 30, cw, 16, "#111", stroke="none"),
                 t(x + cw / 2, 42, str(i + 1), 11, "#fff"), t(x + cw / 2, 66, j["code"], 12 if len(j["code"]) < 8 else 9),
                 t(x + cw / 2, 78, j["name"], 4.2, weight="normal"), rect(x + 5, 215, cw - 10, 40, "none", "#888", 0.3),
                 t(x + cw / 2, 222, "name", 3.5, "#888", weight="normal")] + chips(x + 6, 90, j["colors"], 7, 1)
    return page(w, h, body)


def write(name, svgs):
    OUT.mkdir(exist_ok=True)
    paths = []
    for n, svg in enumerate(svgs, 1):
        p = OUT / (f"{name}.svg" if len(svgs) == 1 else f"{name}-p{n}.svg")
        p.write_text(svg)
        paths.append(p)
    try:
        import pymupdf
    except ImportError:
        return
    pdf = pymupdf.open()
    for p in paths:
        pdf.insert_pdf(pymupdf.open("pdf", pymupdf.open(str(p)).convert_to_pdf()))
    pdf.save(str(OUT / f"{name}.pdf"))


def main():
    cps, key = facts.control_points(), facts.colour_key()
    write("cp-signs-A-plate", sheets(cps, sign_a, (66, 56), "Control point signs", 3, 4))
    by_id = {c["id"]: c for c in key}
    jobs = [{**j, "colors": [by_id[c] for c in j["colors"]]} for j in facts.board_jobs()]
    write("crew-board-B-columns", [board_b(jobs)])


if __name__ == "__main__":
    main()
