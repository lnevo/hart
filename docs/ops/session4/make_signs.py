"""Draft printables for punch list items 4 and 5 (SVG in mm, then PDF).

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


def sign_b(x, y, cp):
    """Tall flag 40 x 60 with the level along a coloured band at the left and a stick strip below."""
    w, h = 40, 60
    sw = ", ".join(cp["switches"])
    return [rect(x, y, w, h, "#fff", sw=0.4), rect(x, y, 9, h, LEVEL_FILL[cp["level"]], stroke="none"),
            t(x + 6.2, y + h / 2, cp["level"].upper(), 4, "#fff", rot=-90),
            t(x + 24, y + 12, "CP", 7), t(x + 24, y + 30, cp["name"].replace("CP ", ""), fit(cp["name"].replace("CP ", ""), 28, 14)),
            t(x + 24, y + 42, "Switch" if len(cp["switches"]) == 1 else "Switches", 3.4, weight="normal"),
            t(x + 24, y + 48, sw, fit(sw, 28, 4)),
            rect(x + 17, y + h + 1, 12, 8, "none", "#888", 0.2, "1,1")]


def sign_c(x, y, cp):
    """Tent: a face 56 x 36 and the same face upside down above it; fold on the dashed line over the stick top."""
    w, h = 56, 36
    out = []
    for flip in (0, 1):
        oy = y + (0 if flip else h)
        cx, cy = x + w / 2, oy + h / 2
        g = [rect(x, oy, w, h, "#fff", sw=0.4), rect(x, oy, w, 6, LEVEL_FILL[cp["level"]], stroke="none"),
             t(cx, oy + 4.4, "CONTROL POINT", 3.2, "#fff"),
             t(cx, oy + 21, cp["name"], fit(cp["name"], 50, 13)), t(cx, oy + 31, sw_text(cp), 3.6, weight="normal")]
        out.append(f'<g transform="rotate({180 if flip else 0} {cx:.2f} {cy:.2f})">' + "".join(g) + "</g>")
    out.append(f'<line x1="{x}" y1="{y + h}" x2="{x + w}" y2="{y + h}" stroke="#c00" stroke-width="0.3" stroke-dasharray="2,1"/>')
    return out


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


def board_a(jobs):
    """Table: sign-up number, job, name, destination colours, a long line for the crew member."""
    w, h = TABLOID_L
    body = [t(w / 2, 24, "CREW BOARD", 20), t(w / 2, 33, "Sign up in order, one name per line", 6, weight="normal")]
    for i, j in enumerate(jobs):
        y = 46 + i * 30
        body += [rect(15, y, w - 30, 30, "#fff", sw=0.5), t(30, y + 20, str(i + 1), 18),
                 t(65, y + 15, j["code"], 16, anchor="start"), t(65, y + 24, j["name"], 6, anchor="start", weight="normal"),
                 rect(165, y + 5, 240, 20, "none", "#888", 0.3)] + chips(112, y + 4, j["colors"], 9, 2)
    return page(w, h, body)


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


def board_c(jobs, key):
    """Sign-up table at left, the destination colour key at right."""
    w, h = TABLOID_L
    body = [t(15, 24, "CREW BOARD", 16, anchor="start"), t(15, 32, "Sign up in order", 6, anchor="start", weight="normal")]
    for i, j in enumerate(jobs):
        y = 42 + i * 28
        body += [rect(15, y, 250, 25, "#fff", sw=0.5), t(25, y + 17, str(i + 1), 14), t(45, y + 12, j["code"], 12, anchor="start"),
                 t(45, y + 20, j["name"], 5, anchor="start", weight="normal"), rect(115, y + 4, 145, 17, "none", "#888", 0.3)]
    body.append(t(280, 42, "Destination colours", 8, anchor="start"))
    for k, c in enumerate(key):
        y = 50 + k * 19
        body += [rect(280, y, 24, 15, c["hex"], "#000", 0.3), t(310, y + 6.5, c["label"], 5, anchor="start"),
                 t(310, y + 12.5, c["dest"], 4.2, anchor="start", weight="normal")]
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
    write("cp-signs-A-plate", sheets(cps, sign_a, (66, 56), "Control point signs, option A plate", 3, 4))
    write("cp-signs-B-flag", sheets(cps, sign_b, (46, 72), "Control point signs, option B flag", 4, 3))
    write("cp-signs-C-tent", sheets(cps, sign_c, (62, 78), "Control point signs, option C tent", 3, 3))
    by_id = {c["id"]: c for c in key}
    jobs = [{**j, "colors": [by_id[c] for c in j["colors"]]} for j in facts.board_jobs()]
    write("crew-board-A-table", [board_a(jobs)])
    write("crew-board-B-columns", [board_b(jobs)])
    write("crew-board-C-key", [board_c(jobs, key)])


if __name__ == "__main__":
    main()
