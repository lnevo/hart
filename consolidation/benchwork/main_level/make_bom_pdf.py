#!/usr/bin/env python3
"""Render HART_main_level_BOM.md to HART_main_level_BOM.pdf (letter, ReportLab).

Handles only what the BOM uses: # / ## headings, paragraphs, - bullets (with indented continuation lines),
pipe tables, **bold** and `code`.
    python3 make_bom_pdf.py [out.pdf]
"""
import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).resolve().parent
SRC = HERE / "HART_main_level_BOM.md"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "HART_main_level_BOM.pdf"

ss = getSampleStyleSheet()
BODY = ss["BodyText"].clone("b", fontSize=9, leading=11.5)
CELL = BODY.clone("c", fontSize=8.5, leading=10)
H1, H2 = ss["Title"].clone("h1", fontSize=16, alignment=0), ss["Heading2"].clone("h2", fontSize=12, spaceBefore=10)


def inline(t):
    t = html.escape(t.strip(), quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", t)


def table(rows):
    rows = [r for r in rows if not re.fullmatch(r"[\s|:-]+", r)]
    cells = [[Paragraph(inline(c), CELL) for c in r.strip().strip("|").split("|")] for r in rows]
    widths = [26, 246, 62, 84, 58, 64] if len(cells[0]) == 6 else None   # shopping list: give the item room
    t = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6e6e6")),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def main():
    flow, lines, i = [], SRC.read_text().splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            flow += [table(lines[i:j]), Spacer(0, 6)]
            i = j
            continue
        if ln.startswith("# "):
            flow.append(Paragraph(inline(ln[2:]), H1))
        elif ln.startswith("## "):
            flow.append(Paragraph(inline(ln[3:]), H2))
        elif ln.startswith("- "):
            text = ln[2:]
            while i + 1 < len(lines) and lines[i + 1].startswith("  "):
                i += 1
                text += " " + lines[i].strip()
            flow.append(Paragraph(inline(text), BODY, bulletText="•"))
        elif ln.strip():
            flow.append(Paragraph(inline(ln), BODY))
        i += 1
    SimpleDocTemplate(str(OUT), pagesize=letter, title="HART main level BOM",
                      leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36).build(flow)
    print(OUT)


if __name__ == "__main__":
    main()
