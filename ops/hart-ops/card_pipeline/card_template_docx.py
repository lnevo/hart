"""Low-level OOXML and text helpers shared by the HART card builders.

Split out of generate_card_template.py, which re-exports every name here.
"""

import re

from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from card_template_layout import (
    DIVIDER_CLR,
    FONT,
    FRAME_ARCSIZE,
    FRAME_STROKE_PT,
    H_FOOTER_LINE_TWIPS,
)


# ── low-level OOXML helpers ─────────────────────────────────────────────────

def _tc_pr(cell):
    return cell._tc.get_or_add_tcPr()


def shade(cell, color: str) -> None:
    el = OxmlElement("w:shd")
    el.set(qn("w:fill"), color)
    el.set(qn("w:val"), "clear")
    _tc_pr(cell).append(el)


def width(cell, twips: int) -> None:
    tc_pr = _tc_pr(cell)
    el = tc_pr.find(qn("w:tcW"))
    if el is None:
        el = OxmlElement("w:tcW")
        tc_pr.append(el)
    el.set(qn("w:w"), str(twips))
    el.set(qn("w:type"), "dxa")


def pad(cell, top=0, left=0, bottom=0, right=0) -> None:
    tc_pr = _tc_pr(cell)
    el = tc_pr.find(qn("w:tcMar"))
    if el is not None:
        tc_pr.remove(el)
    el = OxmlElement("w:tcMar")
    for side, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        s = OxmlElement(f"w:{side}")
        s.set(qn("w:w"), str(val))
        s.set(qn("w:type"), "dxa")
        el.append(s)
    tc_pr.append(el)


def row_h(row, twips: int) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    el = tr_pr.find(qn("w:trHeight"))
    if el is None:
        el = OxmlElement("w:trHeight")
        tr_pr.append(el)
    el.set(qn("w:val"), str(twips))
    el.set(qn("w:hRule"), "exact")


def grid(table, widths: list[int]) -> None:
    tbl = table._tbl
    old = tbl.find(qn("w:tblGrid"))
    if old is not None:
        tbl.remove(old)
    g = OxmlElement("w:tblGrid")
    for w in widths:
        c = OxmlElement("w:gridCol")
        c.set(qn("w:w"), str(w))
        g.append(c)
    tbl.insert(0, g)


def tbl_width_pct(table, pct: int = 100) -> None:
    pr = table._tbl.tblPr
    el = pr.find(qn("w:tblW"))
    if el is None:
        el = OxmlElement("w:tblW")
        pr.append(el)
    el.set(qn("w:w"), str(pct * 50))
    el.set(qn("w:type"), "pct")
    lay = pr.find(qn("w:tblLayout"))
    if lay is None:
        lay = OxmlElement("w:tblLayout")
        pr.append(lay)
    lay.set(qn("w:type"), "fixed")


def tbl_width_dxa(table, twips: int, *, center=True) -> None:
    pr = table._tbl.tblPr
    el = pr.find(qn("w:tblW"))
    if el is None:
        el = OxmlElement("w:tblW")
        pr.append(el)
    el.set(qn("w:w"), str(twips))
    el.set(qn("w:type"), "dxa")
    lay = pr.find(qn("w:tblLayout"))
    if lay is None:
        lay = OxmlElement("w:tblLayout")
        pr.append(lay)
    lay.set(qn("w:type"), "fixed")
    if center:
        jc = pr.find(qn("w:jc"))
        if jc is None:
            jc = OxmlElement("w:jc")
            pr.append(jc)
        jc.set(qn("w:val"), "center")


def add_round_frame(paragraph, idx, *, width_pt, height_pt, left_pt, top_pt) -> None:
    """Anchor a rounded-rectangle outline behind the card content (VML)."""
    z = -251650000 - idx          # behind text, unique-ish per card
    style = (
        "position:absolute;"
        f"margin-left:{left_pt:.2f}pt;margin-top:{top_pt:.2f}pt;"
        f"width:{width_pt:.2f}pt;height:{height_pt:.2f}pt;"
        f"z-index:{z};"
        "mso-position-horizontal-relative:text;"
        "mso-position-vertical-relative:text"
    )
    xml = (
        '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word">'
        '<w:rPr><w:noProof/></w:rPr>'
        '<w:pict>'
        f'<v:roundrect id="cardframe{idx}" o:spid="_x0000_s10{idx:02d}" '
        f'style="{style}" arcsize="{FRAME_ARCSIZE}" '
        'filled="f" stroked="t" strokecolor="#1F1F1F" '
        f'strokeweight="{FRAME_STROKE_PT}pt" '
        'xmlns:o="urn:schemas-microsoft-com:office:office">'
        '<v:stroke joinstyle="round"/>'
        '<w10:wrap type="none"/>'
        '</v:roundrect>'
        '</w:pict>'
        '</w:r>'
    )
    paragraph._p.append(parse_xml(xml))


def borders(table, *, outer=18, inner_h=0, inner_v=0, color="000000") -> None:
    """Set table borders. Sizes in 1/8-point units."""
    pr = table._tbl.tblPr
    old = pr.find(qn("w:tblBorders"))
    if old is not None:
        pr.remove(old)
    b = OxmlElement("w:tblBorders")
    specs = {
        "top": outer, "left": outer, "bottom": outer, "right": outer,
        "insideH": inner_h, "insideV": inner_v,
    }
    for edge, sz in specs.items():
        el = OxmlElement(f"w:{edge}")
        if sz:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(sz))
            el.set(qn("w:color"), color)
            el.set(qn("w:space"), "0")
        else:
            el.set(qn("w:val"), "nil")
        b.append(el)
    pr.append(b)


def bottom_rule(cell, size=4, color=DIVIDER_CLR) -> None:
    """Soft divider line under a cell."""
    tc_pr = _tc_pr(cell)
    old = tc_pr.find(qn("w:tcBorders"))
    if old is not None:
        tc_pr.remove(old)
    b = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        b.append(el)
    el = OxmlElement("w:bottom")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:color"), color)
    el.set(qn("w:space"), "0")
    b.append(el)
    tc_pr.append(b)


def box(cell, size=8, color="808080") -> None:
    """Thin border box around a cell (all four sides)."""
    tc_pr = _tc_pr(cell)
    old = tc_pr.find(qn("w:tcBorders"))
    if old is not None:
        tc_pr.remove(old)
    b = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:color"), color)
        el.set(qn("w:space"), "0")
        b.append(el)
    tc_pr.append(b)


def hrule(cell, size=6, color="808080") -> None:
    """Top + bottom borders only; left/right defer to the card's outer border.

    Used for full-width cells so their side edges don't sit on top of the
    heavy outer border (which made the frame look inconsistent)."""
    tc_pr = _tc_pr(cell)
    old = tc_pr.find(qn("w:tcBorders"))
    if old is not None:
        tc_pr.remove(old)
    b = OxmlElement("w:tcBorders")
    for edge in ("left", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        b.append(el)
    for edge in ("top", "bottom"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:color"), color)
        el.set(qn("w:space"), "0")
        b.append(el)
    tc_pr.append(b)


def para(p, *, align=None, before=0, after=0):
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.0
    if align is not None:
        p.alignment = align


def text(run, s, *, bold=False, size=8, color=None):
    run.text = s
    run.bold = bold
    run.font.name = FONT
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = color if isinstance(color, RGBColor) else RGBColor(*color)


_NBSP = "\u00a0"


def keep_address_together(s: str) -> str:
    """Keep parenthetical city/state from wrapping mid-address (NBSP inside)."""
    if not s:
        return s

    def _paren(m: re.Match[str]) -> str:
        return "(" + m.group(1).replace(" ", _NBSP) + ")"

    return re.sub(r"\(([^)]+)\)", _paren, str(s))


def split_on_commas(s: str) -> list[str]:
    """Split display text on commas outside parentheses.

    Example: ``Aristech Plastics, Chemical Unload`` → two lines.
    ``Dow Chemical (Midland, MI)`` stays one line.
    """
    if not s:
        return []
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in str(s):
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            part = "".join(buf).strip()
            if part:
                parts.append(keep_address_together(part))
            buf = []
        else:
            buf.append(ch)
    part = "".join(buf).strip()
    if part:
        parts.append(keep_address_together(part))
    return parts or [keep_address_together(str(s))]


def write_label_lines(
    p,
    lines: list[str],
    *,
    bold: bool = False,
    size: float = 7,
    color=None,
) -> None:
    """Write one or more lines into a paragraph (soft line breaks between)."""
    if not lines:
        text(p.add_run(), "—", bold=bold, size=size, color=color)
        return
    for i, line in enumerate(lines):
        if i:
            p.add_run().add_break()
        text(p.add_run(), line, bold=bold, size=size, color=color)


def merge_field(p, name, *, bold=False, size=8, color=None):
    r = p.add_run()
    r.font.name = FONT
    r.font.size = Pt(size)
    r.bold = bold
    if color:
        r.font.color.rgb = color

    for kind, payload in (
        ("begin", None),
        ("instr", f" MERGEFIELD {name} "),
        ("separate", None),
        ("text", f"«{name}»"),
        ("end", None),
    ):
        if kind == "instr":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = payload
            r._r.append(el)
        elif kind == "text":
            el = OxmlElement("w:t")
            el.text = payload
            r._r.append(el)
        else:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
            r._r.append(el)


def linebreak(p):
    """Insert a real line break (Word ignores literal newlines in a run)."""
    p.add_run().add_break()


def tighten_cell(cell) -> None:
    """Remove the empty paragraph python-docx leaves around a nested table.

    That stray paragraph adds a blank line above the table (a gap, and it
    pushes content down so exact-height rows clip it). We drop empty
    paragraphs and leave one minimal trailing paragraph (Word requires a
    cell to end in a paragraph)."""
    tc = cell._tc
    if not tc.findall(qn("w:tbl")):
        return
    for child in list(tc):
        if child.tag == qn("w:p") and not child.findall(qn("w:r")):
            tc.remove(child)
    if len(tc) and list(tc)[-1].tag == qn("w:tbl"):
        p = OxmlElement("w:p")
        pPr = OxmlElement("w:pPr")
        spacing = OxmlElement("w:spacing")
        spacing.set(qn("w:before"), "0")
        spacing.set(qn("w:after"), "0")
        spacing.set(qn("w:line"), "20")
        spacing.set(qn("w:lineRule"), "exact")
        pPr.append(spacing)
        rPr = OxmlElement("w:rPr")
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), "2")
        rPr.append(sz)
        pPr.append(rPr)
        p.append(pPr)
        tc.append(p)


def minimize_cell_tail(cell) -> None:
    """Shrink the default paragraph python-docx leaves after a cell's table.

    cell.add_table() appends an empty Normal-style paragraph (~11pt) after the
    card table. Left alone it inflates each card past the sticker-slot height,
    so 9 filled cards overflow onto a second page. Force it to a 1pt line."""
    tc = cell._tc
    children = list(tc)
    if not children or children[-1].tag != qn("w:p"):
        return
    p = children[-1]
    if p.findall(qn("w:r")):
        return
    pPr = p.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p.insert(0, pPr)
    old = pPr.find(qn("w:spacing"))
    if old is not None:
        pPr.remove(old)
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:before"), "0")
    spacing.set(qn("w:after"), "0")
    spacing.set(qn("w:line"), "20")
    spacing.set(qn("w:lineRule"), "exact")
    pPr.append(spacing)
    rPr = pPr.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        pPr.append(rPr)
    sz = rPr.find(qn("w:sz"))
    if sz is None:
        sz = OxmlElement("w:sz")
        rPr.append(sz)
    sz.set(qn("w:val"), "2")


def _tighten_paragraph(p, line_twips: int = 110) -> None:
    """Zero paragraph spacing; exact line height for a single tight line."""
    pPr = p._p.get_or_add_pPr()
    old = pPr.find(qn("w:spacing"))
    if old is not None:
        pPr.remove(old)
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:before"), "0")
    spacing.set(qn("w:after"), "0")
    spacing.set(qn("w:line"), str(line_twips))
    spacing.set(qn("w:lineRule"), "exact")
    pPr.append(spacing)


def tighten_revision_cell(cell, line_twips: int = H_FOOTER_LINE_TWIPS) -> None:
    """Strip all slack from the footer cell so the revision line cannot overlap."""
    pad(cell, top=0, left=0, bottom=0, right=0)
    tc = cell._tc
    paragraphs = tc.findall(qn("w:p"))
    for extra in paragraphs[1:]:
        if not extra.findall(qn("w:r")):
            tc.remove(extra)
    if paragraphs:
        _tighten_paragraph(cell.paragraphs[0], line_twips)


def next_record(p):
    r = p.add_run()
    for kind in ("begin",):
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), kind)
        r._r.append(el)
    el = OxmlElement("w:instrText")
    el.set(qn("xml:space"), "preserve")
    el.text = " NEXT "
    r._r.append(el)
    for kind in ("separate", "end"):
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), kind)
        r._r.append(el)
