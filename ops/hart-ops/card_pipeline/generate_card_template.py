#!/usr/bin/env python3
"""
Build HART equipment card mail-merge template on the Apostrophe poker sticker sheet.

Design source: train_card.prompt
  - Letterhead logo upper-left
  - Railroad name + division subtitle
  - Boxed title upper-right
  - Heavy outer card border
  - Large image area (~half the card)
  - Footer form number
  - Sans-serif, monochrome, subtle gray fills on header/footer only

Sticker sheet: Poker Size Sticker Sheet Template.docx (9 cards per 8.5x11 page)
"""

import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from car_paths import (
    ASSETS,
    DATA,
    OUTPUT_DIR,
    PIPELINE,
    ROOT as BASE,
    STICKER_SHEET,
    require_sticker_sheet,
)

LOGO = ASSETS / "Logo.png"
ICON_ROAD_NAME = ASSETS / "icon_railroad.png"   # tracks-in-a-circle line icon
ICON_ROAD_NUM  = ASSETS / "icon_number.png"     # circled # line icon
ICON_DESC      = ASSETS / "icon_pencil.png"     # circled pencil line icon
OUTPUT = OUTPUT_DIR / "HART_Equipment_Card_Template.docx"

# ── sticker-slot dimensions (twips) ─────────────────────────────────────────
# Page 4 of the sticker template (the 3×3 table): prints closer to the sticker
# edge — best for card fronts with text per Apostrophe's instructions.
SLOT_W = 3686   # ≈ 2.56"
SLOT_H = 5098   # ≈ 3.54"

CARD_SLOTS = [
    (0, 0), (0, 1), (0, 2),
    (1, 0), (1, 1), (1, 2),
    (2, 0), (2, 1), (2, 2),
]

# Page margins from the template's sectPr (page 4 grid).
PAGE_MAR_TOP = 202
PAGE_MAR_BOTTOM = 101
PAGE_MAR_LEFT = 418
PAGE_MAR_RIGHT = 360

# Column widths for the 3-column card grid (consistent across all rows)
COL_A = 900    # logo / icon
COL_B = 1000   # railroad name / label
COL_C = SLOT_W - COL_A - COL_B   # 1501 – badge / value

# Row heights (twips) – sized so the card fills the sticker top to bottom.
H_HEADER = 860     # tall enough for the logo + title
H_IMAGE  = 2004    # image row (taller for square/tall crops like IMG_9137)
H_DATA_SECTION = 1450  # data block; tuned with revision gap below data table
# Visual gap between image bordered box and data table (c_img bottom + c_data top).
DATA_TABLE_TOP_PAD = 140   # c_data top margin (gap below image box)
IMG_OUTER_PAD_TOP = 50
IMG_OUTER_PAD_BOTTOM = 80  # was 140; partial reclaim for taller image box
IMG_INNER_PAD = 20
WORK_FLOW_COMMODITY_GAP = 36  # space below INBOUND/OUTBOUND, before commodity
H_FOOTER = 110     # exact height for one 5.5pt revision line (was 323)
H_FOOTER_LINE_TWIPS = 110  # 5.5pt exact line in revision cell

# ── style constants ─────────────────────────────────────────────────────────
FONT        = "Arial"
GRAY_FILL   = "D9D9D9"
DIVIDER_CLR = "BFBFBF"
LABEL_CLR   = RGBColor(0, 0, 0)
VALUE_CLR   = RGBColor(70, 70, 70)
ICON        = "\u2630"   # consistent line-style icon

# Inner section boxes (image + data); the main container itself is borderless.
# Inner lines: heavier than before, still lighter than the outer card frame (2.25pt).
INNER_BORDER = 8         # 1pt in Word (sz is 1/8-pt units)
IMAGE_BORDER = INNER_BORDER

# Card art sized on the page-2 gutter grid; centered as a unit in page-4 slots.
PAGE2_SLOT_W = 3401
CONTENT_MARGIN = 110
FRAME_MARGIN = 140
TARGET_CARD_W = PAGE2_SLOT_W - 2 * CONTENT_MARGIN    # 3181 twips
TARGET_FRAME_W = PAGE2_SLOT_W - 2 * FRAME_MARGIN     # 3121 twips
CENTER_OFFSET = (SLOT_W - PAGE2_SLOT_W) // 2         # shift block into wider slot
CARD_DROP_TWIPS = 180                                # 1/8" — nudge card art down in each slot
CARD_TOP_PAD = 166 + CARD_DROP_TWIPS                 # frame origin below slot top

CARD_W = TARGET_CARD_W
SIDE_PAD = 160           # horizontal pad inside header / image / data sections
FRAME_STROKE_PT = 2.25   # heavier rounded frame
FRAME_GROW_TWIPS = 45      # 1/32" — expand outer rounded frame per side / downward
FRAME_GROW_PT = 72.0 / 32  # same in points
FRAME_ARCSIZE = 0.07     # corner rounding (fraction of shorter side)


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


# ── card builder ────────────────────────────────────────────────────────────

def build_card(cell, *, advance_record: bool, idx: int,
               record: dict | None = None, image_path=None) -> None:
    """Place one prompt-styled card into a sticker-sheet slot.

    When ``record`` / ``image_path`` are given the card is filled with static
    values and an embedded photo (single-card output); otherwise it carries
    MERGEFIELD placeholders for a mail merge."""
    cell.text = ""
    # Shift the whole card block into the wider page-4 slot; internal 110/140
    # margins (content vs frame) stay as on the page-2 grid.
    side_gap = SLOT_W - PAGE2_SLOT_W - CENTER_OFFSET
    pad(cell, top=CARD_TOP_PAD, left=CENTER_OFFSET, right=side_gap)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP   # raise content to top

    # Leading anchor paragraph hosts the NEXT-record field and the rounded
    # frame shape. Keep it tiny so it doesn't shift the card down.
    lead = cell.paragraphs[0]
    para(lead, after=2)
    lead.paragraph_format.line_spacing = Pt(1)
    if advance_record:
        next_record(lead)
    for r in lead.runs:
        r.font.size = Pt(1)

    # Heavier rounded outer frame. Height must stay inside the 3.35" sticker
    # slot so the bottom row (with no card below to mask any overhang) doesn't
    # exceed the available space, while still clearing the footer line.
    frame_w_pt = (TARGET_FRAME_W + 2 * FRAME_GROW_TWIPS) / 20.0
    frame_h_pt = 3.16 * 72.0 + FRAME_GROW_PT          # 1/32" taller at bottom
    frame_left_pt = (FRAME_MARGIN - FRAME_GROW_TWIPS) / 20.0
    frame_top_pt = 1.0
    add_round_frame(
        lead,
        idx,
        width_pt=frame_w_pt,
        height_pt=frame_h_pt,
        left_pt=frame_left_pt,
        top_pt=frame_top_pt,
    )

    # ── main card container: single column, 4 stacked sections (borderless) ─
    t = cell.add_table(rows=4, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_width_dxa(t, CARD_W, center=True)
    grid(t, [CARD_W])
    borders(t, outer=0)   # no border; rounded frame is the only card outline

    # ── SECTION 0 · header · logo left, name upper-right (no fill) ────────
    row_h(t.rows[0], H_HEADER)
    c_head = t.rows[0].cells[0]
    width(c_head, CARD_W)
    pad(c_head, top=20, left=SIDE_PAD, bottom=20, right=SIDE_PAD)
    c_head.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    content_w = CARD_W - 2 * SIDE_PAD
    logo_w = 900
    title_w = content_w - logo_w
    head = c_head.add_table(rows=1, cols=2)
    tbl_width_dxa(head, content_w, center=False)
    grid(head, [logo_w, title_w])
    borders(head, outer=0)           # no border around the logo/title cells
    h_logo, h_title = head.rows[0].cells
    width(h_logo, logo_w)
    width(h_title, title_w)
    for c in (h_logo, h_title):
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # Logo (the rounded frame is baked into Logo.png, so no cell border needed).
    # Zero the default cell margins so the 0.56"-wide image isn't clipped on the
    # right; a small left margin keeps it off the card frame.
    pad(h_logo, left=40, right=0, top=0, bottom=0)
    p = h_logo.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
    if LOGO.exists():
        p.add_run().add_picture(str(LOGO), width=Inches(0.56))
    else:
        text(p.add_run(), "LOGO", bold=True, size=6, color=(100, 100, 100))

    # Right field: car type — centered, all-caps, inside a top+bottom rule that
    # hugs the text. A left cell margin keeps the rule off the logo frame.
    pad(h_title, left=150, right=0, top=0, bottom=0)
    inner_title = title_w - 150
    type_box = h_title.add_table(rows=1, cols=1)
    tbl_width_dxa(type_box, inner_title, center=False)
    grid(type_box, [inner_title])
    borders(type_box, outer=0)
    tc = type_box.rows[0].cells[0]
    width(tc, inner_title)
    pad(tc, top=36, bottom=36)
    hrule(tc, size=INNER_BORDER, color=DIVIDER_CLR)
    p = tc.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
    if record is not None:
        text(p.add_run(), record.get("Type", "").upper(), bold=True, size=12)
    else:
        merge_field(p, "Type", bold=True, size=12)
    tighten_cell(h_title)

    tighten_cell(c_head)

    # ── SECTION 1 · image area (~half the card) · own inset box ───────────
    row_h(t.rows[1], H_IMAGE)
    c_img = t.rows[1].cells[0]
    width(c_img, CARD_W)
    pad(c_img, top=IMG_OUTER_PAD_TOP, left=SIDE_PAD, bottom=IMG_OUTER_PAD_BOTTOM, right=SIDE_PAD)
    c_img.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    img_w = CARD_W - 2 * SIDE_PAD
    img = c_img.add_table(rows=1, cols=1)
    tbl_width_dxa(img, img_w, center=True)
    grid(img, [img_w])
    borders(img, outer=IMAGE_BORDER, color=DIVIDER_CLR)
    ic = img.rows[0].cells[0]
    width(ic, img_w)
    ic.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    pad(ic, top=IMG_INNER_PAD, bottom=IMG_INNER_PAD, left=40, right=40)
    p = ic.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
    if image_path is not None and Path(image_path).exists():
        p.add_run().add_picture(str(image_path), width=Inches(1.84))
    elif record is not None and record.get("Blank"):
        text(p.add_run(), "WORK ORDERS", bold=True, size=6, color=LABEL_CLR)
        orders = record.get("Orders") or []
        for line in orders:
            q = ic.add_paragraph()
            para(q, align=WD_ALIGN_PARAGRAPH.LEFT, before=3, after=0)
            text(q.add_run(), line, size=5.5, color=VALUE_CLR)
        for _ in range(max(1, 7 - len(orders))):
            q = ic.add_paragraph()
            para(q, align=WD_ALIGN_PARAGRAPH.LEFT, before=5, after=0)
            text(q.add_run(), "_" * 46, size=5.5, color=(170, 170, 170))
    else:
        text(p.add_run(), "EQUIPMENT IMAGE", size=7, color=(140, 140, 140))
        linebreak(p)
        merge_field(p, "ImagePath", size=6, color=VALUE_CLR)

    tighten_cell(c_img)

    # ── SECTION 2 · data fields · own inset box with soft dividers ────────
    row_h(t.rows[2], H_DATA_SECTION)
    c_data = t.rows[2].cells[0]
    width(c_data, CARD_W)
    pad(c_data, top=DATA_TABLE_TOP_PAD, left=SIDE_PAD, bottom=8, right=SIDE_PAD)
    c_data.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    # Icon column must fit 0.15" picture (216 twips) + horizontal cell padding.
    icon_w, label_w = 340, 1040
    data_w = content_w
    value_w = data_w - icon_w - label_w

    data = c_data.add_table(rows=3, cols=3)
    tbl_width_dxa(data, data_w, center=True)
    grid(data, [icon_w, label_w, value_w])
    # Complete soft box: top + bottom match the sides and the row dividers,
    # so the whole table is framed with one consistent light line.
    borders(data, outer=INNER_BORDER, inner_h=INNER_BORDER, inner_v=0, color=DIVIDER_CLR)

    # Matching circled line-art icons (image) for each field.
    fields = [
        ("ROAD NAME:",   "RoadName",   ICON_ROAD_NAME),
        ("ROAD NUMBER:", "RoadNumber", ICON_ROAD_NUM),
        ("DESCRIPTION:", "Description", ICON_DESC),
    ]
    for ri, (label, fname, icon_path) in enumerate(fields):
        row = data.rows[ri]
        c_icon, c_lbl, c_val = row.cells
        width(c_icon, icon_w)
        pad(c_icon, top=16, left=30, bottom=10, right=30)
        c_icon.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        width(c_lbl, label_w)
        pad(c_lbl, top=30, left=30, bottom=30, right=30)
        c_lbl.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        width(c_val, value_w)
        pad(c_val, top=30, left=30, bottom=30, right=30)
        c_val.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        p = c_icon.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.CENTER, after=1.5)
        if icon_path.exists():
            p.add_run().add_picture(str(icon_path), width=Inches(0.15))
        else:
            text(p.add_run(), "\u2630", size=8, color=(120, 120, 120))

        p = c_lbl.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        text(p.add_run(), label, bold=False, size=6, color=LABEL_CLR)

        p = c_val.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        if record is not None:
            val = record.get(fname, "")
            if fname == "Description":
                val_size = 5.5 if len(val) > 18 else 6.5
            else:
                val_size = 9
            text(p.add_run(), val, bold=True, size=val_size, color=VALUE_CLR)
        else:
            field_size = 9 if fname in ("RoadName", "RoadNumber") else 6.5
            merge_field(p, fname, bold=True, size=field_size, color=VALUE_CLR)

    tighten_cell(c_data)

    # ── SECTION 3 · footer (no fill) ──────────────────────────────────────
    row_h(t.rows[3], H_FOOTER)
    c_ftr = t.rows[3].cells[0]
    width(c_ftr, CARD_W)
    c_ftr.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    p = c_ftr.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    text(p.add_run(), "Form HART-CC-001    Rev A", size=5.5, color=(80, 80, 80))
    tighten_revision_cell(c_ftr)

    minimize_cell_tail(cell)   # keep all 9 cards on one page


def _via_interchange_label(rail: str) -> str:
    """Format a RouteChain token as ``Via CSX Interchange`` / ``Via POHC Interchange``."""
    rail = (rail or "").strip()
    if not rail:
        return ""
    if rail.lower().startswith("via "):
        return rail
    if rail.endswith("Interchange"):
        return f"Via {rail}"
    return f"Via {rail} Interchange"


def build_waybill_card(cell, *, idx: int, record: dict) -> None:
    """Place one spot waybill card into a sticker-sheet slot.

    Same rounded-frame layout as equipment cards, but the header carries the
    industry name (no HART logo) and the body holds spot/load details."""
    cell.text = ""
    side_gap = SLOT_W - PAGE2_SLOT_W - CENTER_OFFSET
    pad(cell, top=CARD_TOP_PAD, left=CENTER_OFFSET, right=side_gap)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    lead = cell.paragraphs[0]
    para(lead, after=2)
    lead.paragraph_format.line_spacing = Pt(1)
    for r in lead.runs:
        r.font.size = Pt(1)

    frame_w_pt = (TARGET_FRAME_W + 2 * FRAME_GROW_TWIPS) / 20.0
    frame_h_pt = 3.16 * 72.0 + FRAME_GROW_PT
    frame_left_pt = (FRAME_MARGIN - FRAME_GROW_TWIPS) / 20.0
    add_round_frame(
        lead,
        idx,
        width_pt=frame_w_pt,
        height_pt=frame_h_pt,
        left_pt=frame_left_pt,
        top_pt=1.0,
    )

    t = cell.add_table(rows=4, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_width_dxa(t, CARD_W, center=True)
    grid(t, [CARD_W])
    borders(t, outer=0)

    commodity = record.get("Commodity", "")
    route_from = record.get("RouteFrom", record.get("Route", "")).strip()
    route_to = record.get("RouteTo", "").strip()
    route_chain = record.get("RouteChain", record.get("RouteVia", "")).strip()
    flow = record.get("Flow", "")
    is_interchange = record.get("CardKind") == "interchange"
    is_empty = commodity == "EMPTY"
    is_outbound_empty = record.get("CardKind") == "outbound_empty" or (
        is_empty and not record.get("Spots") and flow == "OUT"
    )
    is_inbound_empty = record.get("CardKind") == "inbound_empty" or (
        is_empty and bool(record.get("Spots")) and flow == "IN"
    )

    # ── SECTION 0 · industry name across the top ─────────────────────────
    row_h(t.rows[0], H_HEADER)
    c_head = t.rows[0].cells[0]
    width(c_head, CARD_W)
    pad(c_head, top=24, left=SIDE_PAD, bottom=24, right=SIDE_PAD)
    c_head.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    inner_w = CARD_W - 2 * SIDE_PAD
    title_box = c_head.add_table(rows=1, cols=1)
    tbl_width_dxa(title_box, inner_w, center=False)
    grid(title_box, [inner_w])
    borders(title_box, outer=0)
    tc = title_box.rows[0].cells[0]
    width(tc, inner_w)
    pad(tc, top=36, bottom=36)
    hrule(tc, size=INNER_BORDER, color=DIVIDER_CLR)
    p = tc.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
    industry = record.get("Industry", "")
    title = "EMPTY" if is_outbound_empty else industry.upper()
    title_size = 9 if len(title) > 22 else 11
    text(p.add_run(), title, bold=True, size=title_size)
    tighten_cell(c_head)

    # ── SECTION 1 · flow + commodity work-order block ────────────────────
    row_h(t.rows[1], H_IMAGE)
    c_work = t.rows[1].cells[0]
    width(c_work, CARD_W)
    pad(c_work, top=IMG_OUTER_PAD_TOP, left=SIDE_PAD, bottom=IMG_OUTER_PAD_BOTTOM, right=SIDE_PAD)
    c_work.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    work_w = CARD_W - 2 * SIDE_PAD
    work = c_work.add_table(rows=1, cols=1)
    tbl_width_dxa(work, work_w, center=True)
    grid(work, [work_w])
    borders(work, outer=IMAGE_BORDER, color=DIVIDER_CLR)

    # Each entry: (kind, text, size, bold, color) — kind is load, gap, or line
    work_lines: list[tuple] = []
    if is_outbound_empty:
        yard = route_to or "Interchange"
        return_line = f"Return to {yard}"
        ret_size = 6 if len(return_line) > 28 else 7
        work_lines.append(("line", return_line, ret_size, False, VALUE_CLR))
        if route_chain:
            work_lines.append(("gap", "", 0, False, VALUE_CLR))
            via_label = _via_interchange_label(route_chain)
            via_size = 5.5 if len(via_label) > 24 else 6.5
            work_lines.append(("line", via_label, via_size, True, LABEL_CLR))
    elif is_inbound_empty:
        work_lines.append(("load", "EMPTY", 10, True, VALUE_CLR))
        if route_chain:
            work_lines.append(("gap", "", 0, False, VALUE_CLR))
            via_label = _via_interchange_label(route_chain)
            via_size = 5.5 if len(via_label) > 24 else 6.5
            work_lines.append(("line", via_label, via_size, True, LABEL_CLR))
    else:
        comm_size = 8 if len(commodity) > 28 else 9.5
        work_lines.append(("load", commodity, comm_size, True, VALUE_CLR))
        work_lines.append(("gap", "", 0, False, VALUE_CLR))
        if is_interchange:
            if route_from:
                from_size = 5.5 if len(route_from) > 36 else 6.5
                work_lines.append(("line", f"From: {route_from}", from_size, False, VALUE_CLR))
            if route_to:
                to_size = 5.5 if len(route_to) > 36 else 6.5
                work_lines.append(("line", f"To: {route_to}", to_size, False, VALUE_CLR))
            if route_from or route_to:
                work_lines.append(("gap", "", 0, False, VALUE_CLR))
            if route_chain:
                via_label = _via_interchange_label(route_chain)
                via_size = 5.5 if len(via_label) > 24 else 6.5
                work_lines.append(("line", via_label, via_size, True, LABEL_CLR))
        elif flow == "IN" and route_from:
            from_size = 5.5 if len(route_from) > 36 else 6.5
            work_lines.append(("line", f"From: {route_from}", from_size, False, VALUE_CLR))
            if route_chain:
                work_lines.append(("gap", "", 0, False, VALUE_CLR))
                via_label = _via_interchange_label(route_chain)
                via_size = 5.5 if len(via_label) > 24 else 6.5
                work_lines.append(("line", via_label, via_size, True, LABEL_CLR))
        elif flow == "OUT" and route_to:
            to_size = 5.5 if len(route_to) > 36 else 6.5
            work_lines.append(("line", f"To: {route_to}", to_size, False, VALUE_CLR))
            if route_chain:
                work_lines.append(("gap", "", 0, False, VALUE_CLR))
                via_label = _via_interchange_label(route_chain)
                via_size = 5.5 if len(via_label) > 24 else 6.5
                work_lines.append(("line", via_label, via_size, True, LABEL_CLR))

    inner = work.rows[0].cells[0]
    width(inner, work_w)
    inner.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    pad(inner, top=4, bottom=4, left=8, right=8)
    inner_tbl = inner.add_table(rows=len(work_lines), cols=1)
    tbl_width_dxa(inner_tbl, work_w - 80, center=True)
    grid(inner_tbl, [work_w - 80])
    borders(inner_tbl, outer=0)

    for i, (kind, line, size, bold, color) in enumerate(work_lines):
        row_cell = inner_tbl.rows[i].cells[0]
        width(row_cell, work_w - 80)
        if kind == "load":
            top_pad, bottom_pad = 6, WORK_FLOW_COMMODITY_GAP if not is_empty else 8
        elif kind == "gap":
            top_pad, bottom_pad = 6, WORK_FLOW_COMMODITY_GAP
        else:
            top_pad, bottom_pad = 8, 8
        pad(row_cell, top=top_pad, bottom=bottom_pad, left=40, right=40)
        row_cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        if kind == "load" and not is_empty:
            bottom_rule(row_cell, size=4, color=DIVIDER_CLR)
        elif kind == "line" and i + 1 < len(work_lines):
            next_kind = work_lines[i + 1][0]
            if next_kind == "line":
                bottom_rule(row_cell, size=4, color=DIVIDER_CLR)
        p = row_cell.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
        if line:
            text(p.add_run(), line, bold=bold, size=size, color=color)

    tighten_cell(inner)
    tighten_cell(c_work)

    # ── SECTION 2 · spot / car type / load table ─────────────────────────
    row_h(t.rows[2], H_DATA_SECTION)
    c_data = t.rows[2].cells[0]
    width(c_data, CARD_W)
    pad(c_data, top=DATA_TABLE_TOP_PAD, left=SIDE_PAD, bottom=8, right=SIDE_PAD)
    c_data.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    content_w = CARD_W - 2 * SIDE_PAD
    icon_w, label_w = 340, 1040
    value_w = content_w - icon_w - label_w

    if is_outbound_empty:
        fields = [("LOAD:", "Commodity", ICON_DESC)]
    else:
        fields = [
            ("SPOT(S):", "Spots", ICON_ROAD_NUM),
            ("CAR TYPE:", "CarType", ICON_ROAD_NAME),
            ("LOAD:", "LoadSummary", ICON_DESC),
        ]

    data = c_data.add_table(rows=len(fields), cols=3)
    tbl_width_dxa(data, content_w, center=True)
    grid(data, [icon_w, label_w, value_w])
    borders(data, outer=INNER_BORDER, inner_h=INNER_BORDER, inner_v=0, color=DIVIDER_CLR)

    for ri, (label, key, icon_path) in enumerate(fields):
        row = data.rows[ri]
        c_icon, c_lbl, c_val = row.cells
        width(c_icon, icon_w)
        pad(c_icon, top=16, left=30, bottom=10, right=30)
        c_icon.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        width(c_lbl, label_w)
        pad(c_lbl, top=30, left=30, bottom=30, right=30)
        c_lbl.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        width(c_val, value_w)
        pad(c_val, top=30, left=30, bottom=30, right=30)
        c_val.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        p = c_icon.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.CENTER, after=1.5)
        if icon_path.exists():
            p.add_run().add_picture(str(icon_path), width=Inches(0.15))
        else:
            text(p.add_run(), "\u2630", size=8, color=(120, 120, 120))

        p = c_lbl.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        text(p.add_run(), label, bold=False, size=6, color=LABEL_CLR)

        p = c_val.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        if key == "LoadSummary":
            val = record.get("LoadSummary") or record.get("Commodity", "")
        else:
            val = record.get(key, "")
        if key in ("Commodity", "LoadSummary"):
            val_size = 5.5 if len(val) > 22 else 6.5
        elif key == "Spots":
            val_size = 9
        else:
            val_size = 7 if len(val) > 16 else 8
        text(p.add_run(), val, bold=True, size=val_size, color=VALUE_CLR)

    tighten_cell(c_data)

    # ── SECTION 3 · footer ─────────────────────────────────────────────
    row_h(t.rows[3], H_FOOTER)
    c_ftr = t.rows[3].cells[0]
    width(c_ftr, CARD_W)
    c_ftr.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    p = c_ftr.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    text(p.add_run(), "Form HART-WB-001    Rev A", size=5.5, color=(80, 80, 80))
    tighten_revision_cell(c_ftr)

    minimize_cell_tail(cell)


# STS location color names → hex (matches build_cc_waybill.php palette).
STS_COLOR_HEX = {
    "pink": "FFC0CB",
    "red": "FF0000",
    "orange": "FFA500",
    "yellow": "FFFF00",
    "green": "008000",
    "lightblue": "ADD8E6",
    "mediumblue": "0000CD",
    "purple": "800080",
    "lightgrey": "D3D3D3",
    "black": "000000",
    "white": "FFFFFF",
}


def build_cc_waybill_label(cell, *, idx: int, record: dict) -> None:
    """One slim CC/WB shipment label (empty or freight) in a poker sticker slot.

    Mirrors STS ``printable_ccwaybill.php`` / ``build_cc_*.php`` fields, but
    sized for the same Apostrophe card template as equipment cards — one bill
    per label (empty and freight are separate cards).
    """
    cell.text = ""
    side_gap = SLOT_W - PAGE2_SLOT_W - CENTER_OFFSET
    pad(cell, top=CARD_TOP_PAD, left=CENTER_OFFSET, right=side_gap)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    lead = cell.paragraphs[0]
    para(lead, after=2)
    lead.paragraph_format.line_spacing = Pt(1)
    for r in lead.runs:
        r.font.size = Pt(1)

    frame_w_pt = (TARGET_FRAME_W + 2 * FRAME_GROW_TWIPS) / 20.0
    frame_h_pt = 3.16 * 72.0 + FRAME_GROW_PT
    frame_left_pt = (FRAME_MARGIN - FRAME_GROW_TWIPS) / 20.0
    add_round_frame(
        lead,
        idx,
        width_pt=frame_w_pt,
        height_pt=frame_h_pt,
        left_pt=frame_left_pt,
        top_pt=1.0,
    )

    kind = (record.get("BillKind") or "freight").lower()
    is_empty = kind == "empty"
    accent = STS_COLOR_HEX.get(
        (record.get("Color") or "").strip().lower(), DIVIDER_CLR
    )

    t = cell.add_table(rows=8, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_width_dxa(t, CARD_W, center=True)
    grid(t, [CARD_W])
    borders(t, outer=0)

    h_header = H_HEADER - 40
    h_accent = 90
    h_dest = 1180
    h_body = H_DATA_SECTION + 80
    h_ship = 160
    # Fixed band between shipment ID and form (anchor shipment from the bottom).
    h_ship_to_form = 280
    h_form = 120
    # Fill remaining frame height so the form sits as a true bottom footer.
    # Small clearance above the rounded frame stroke (avoid border overlap).
    frame_content_twips = int(round((3.16 * 72.0 + FRAME_GROW_PT) * 20)) - 160

    # ── header: logo + EMPTY / FREIGHT ───────────────────────────────────
    row_h(t.rows[0], h_header)
    c_head = t.rows[0].cells[0]
    width(c_head, CARD_W)
    pad(c_head, top=16, left=SIDE_PAD, bottom=8, right=SIDE_PAD)
    c_head.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    content_w = CARD_W - 2 * SIDE_PAD
    logo_w, title_w = 820, content_w - 820
    head = c_head.add_table(rows=1, cols=2)
    tbl_width_dxa(head, content_w, center=False)
    grid(head, [logo_w, title_w])
    borders(head, outer=0)
    h_logo, h_title = head.rows[0].cells
    width(h_logo, logo_w)
    width(h_title, title_w)
    pad(h_logo, left=30, right=0, top=0, bottom=0)
    h_logo.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = h_logo.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
    party_logo = Path(record.get("LogoPath") or "")
    if party_logo.is_file():
        p.add_run().add_picture(str(party_logo), width=Inches(0.52))
    elif LOGO.exists():
        p.add_run().add_picture(str(LOGO), width=Inches(0.48))
    else:
        text(p.add_run(), "HART", bold=True, size=7)

    pad(h_title, left=80, right=0, top=0, bottom=0)
    h_title.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    title_box = h_title.add_table(rows=1, cols=1)
    inner_title = title_w - 80
    tbl_width_dxa(title_box, inner_title, center=False)
    grid(title_box, [inner_title])
    borders(title_box, outer=0)
    tc = title_box.rows[0].cells[0]
    width(tc, inner_title)
    pad(tc, top=28, bottom=28)
    hrule(tc, size=INNER_BORDER, color=DIVIDER_CLR)
    p = tc.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
    bill_title = "EMPTY" if is_empty else "FREIGHT"
    text(p.add_run(), bill_title, bold=True, size=11)
    tighten_cell(c_head)

    # ── STS color accent bar ─────────────────────────────────────────────
    row_h(t.rows[1], h_accent)
    c_bar = t.rows[1].cells[0]
    width(c_bar, CARD_W)
    pad(c_bar, top=0, bottom=0, left=SIDE_PAD, right=SIDE_PAD)
    shade(c_bar, accent)
    c_bar.paragraphs[0].paragraph_format.space_after = Pt(0)

    # ── destination block ────────────────────────────────────────────────
    row_h(t.rows[2], h_dest)
    c_dest = t.rows[2].cells[0]
    width(c_dest, CARD_W)
    pad(c_dest, top=40, left=SIDE_PAD, bottom=20, right=SIDE_PAD)
    dest_w = CARD_W - 2 * SIDE_PAD
    dest = c_dest.add_table(rows=1, cols=1)
    tbl_width_dxa(dest, dest_w, center=True)
    grid(dest, [dest_w])
    borders(dest, outer=IMAGE_BORDER, color=DIVIDER_CLR)
    inner = dest.rows[0].cells[0]
    width(inner, dest_w)
    pad(inner, top=50, bottom=50, left=60, right=60)
    inner.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    to_loc = record.get("ToLocation", "")
    station_lines = split_on_commas(record.get("Station", ""))
    track = record.get("Track", "")
    spot = record.get("Spot", "")
    flow = (record.get("Flow") or "").strip().upper()
    if track.lower() == "staging" and flow in {"IN", "OUT"}:
        track_spot = f"STAGING  ·  {flow}"
    elif track and spot:
        track_spot = f"{track}  ·  {spot}"
    else:
        track_spot = track or spot or "—"

    # Extra room when station wraps after a comma (e.g. Chemical Unload)
    if len(station_lines) > 1:
        h_dest = 1320
        row_h(t.rows[2], h_dest)

    p = inner.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=1, after=1)
    text(p.add_run(), "TO: ", bold=True, size=6, color=LABEL_CLR)
    text(p.add_run(), to_loc or "—", bold=True, size=9, color=VALUE_CLR)

    p = inner.add_paragraph()
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=1, after=1)
    text(p.add_run(), "STATION: ", bold=True, size=6, color=LABEL_CLR)
    if station_lines:
        text(p.add_run(), station_lines[0], bold=False, size=7, color=VALUE_CLR)
        for cont in station_lines[1:]:
            p.add_run().add_break()
            text(p.add_run(), cont, bold=False, size=7, color=VALUE_CLR)
    else:
        text(p.add_run(), "—", bold=False, size=7, color=VALUE_CLR)

    p = inner.add_paragraph()
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=1, after=1)
    text(p.add_run(), "TRACK / SPOT: ", bold=True, size=6, color=LABEL_CLR)
    text(p.add_run(), track_spot, bold=False, size=7, color=VALUE_CLR)
    tighten_cell(c_dest)

    # ── contents / routing ───────────────────────────────────────────────
    row_h(t.rows[3], h_body)
    c_body = t.rows[3].cells[0]
    width(c_body, CARD_W)
    pad(c_body, top=30, left=SIDE_PAD, bottom=10, right=SIDE_PAD)

    if is_empty:
        fields = [
            ("ASSIGNMENT", ["Empty car to load"]),
            ("CAR TYPE", [record.get("CarCode", "") or "—"]),
            ("LOADS", [record.get("Consignment", "") or "—"]),
            ("SHIPMENT", split_on_commas(record.get("Description", "")) or ["—"]),
        ]
    else:
        fields = [
            ("CONTENTS", [record.get("Consignment", "") or "—"]),
            ("CAR TYPE", [record.get("CarCode", "") or "—"]),
            ("FROM", [record.get("FromLocation", "") or "—"]),
            (
                "FROM STA.",
                split_on_commas(record.get("FromStation", "")) or ["—"],
            ),
        ]

    body_w = CARD_W - 2 * SIDE_PAD
    label_w, value_w = 1100, body_w - 1100
    data = c_body.add_table(rows=len(fields), cols=2)
    tbl_width_dxa(data, body_w, center=True)
    grid(data, [label_w, value_w])
    borders(data, outer=INNER_BORDER, inner_h=INNER_BORDER, inner_v=0, color=DIVIDER_CLR)

    for ri, (label, value_lines) in enumerate(fields):
        c_lbl, c_val = data.rows[ri].cells
        width(c_lbl, label_w)
        width(c_val, value_w)
        pad(c_lbl, top=24, bottom=24, left=40, right=20)
        pad(c_val, top=24, bottom=24, left=30, right=30)
        c_lbl.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        c_val.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = c_lbl.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        text(p.add_run(), label, bold=False, size=6, color=LABEL_CLR)
        p = c_val.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        measure = " ".join(value_lines)
        val_size = 5.5 if len(measure) > 28 else (6.5 if len(measure) > 18 else 7.5)
        write_label_lines(p, value_lines, bold=True, size=val_size, color=VALUE_CLR)
    tighten_cell(c_body)

    # ── flex spacer: absorbs variable dest height so shipment stays bottom-anchored
    used = h_header + h_accent + h_dest + h_body + h_ship + h_ship_to_form + h_form
    h_spacer = max(40, frame_content_twips - used)
    row_h(t.rows[4], h_spacer)
    c_gap = t.rows[4].cells[0]
    width(c_gap, CARD_W)
    pad(c_gap, top=0, bottom=0, left=0, right=0)
    _tighten_paragraph(c_gap.paragraphs[0], 20)

    # ── shipment ID (fixed distance above form footer) ────────────────────
    row_h(t.rows[5], h_ship)
    c_ship = t.rows[5].cells[0]
    width(c_ship, CARD_W)
    pad(c_ship, top=0, bottom=0, left=SIDE_PAD, right=SIDE_PAD)
    c_ship.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    code = (record.get("ShipmentCode") or "").strip()
    p = c_ship.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    if code:
        text(p.add_run(), code, bold=True, size=7.5, color=VALUE_CLR)
    else:
        text(p.add_run(), "—", bold=True, size=7.5, color=(120, 120, 120))

    # ── fixed gap between shipment ID and form ────────────────────────────
    row_h(t.rows[6], h_ship_to_form)
    c_mid = t.rows[6].cells[0]
    width(c_mid, CARD_W)
    pad(c_mid, top=0, bottom=0, left=0, right=0)
    _tighten_paragraph(c_mid.paragraphs[0], 20)

    # ── form ID footer at bottom of card ──────────────────────────────────
    row_h(t.rows[7], h_form)
    c_form = t.rows[7].cells[0]
    width(c_form, CARD_W)
    pad(c_form, top=0, bottom=6, left=SIDE_PAD, right=SIDE_PAD)
    c_form.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM
    p = c_form.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    text(p.add_run(), "Form HART-CCWB-001", size=5, color=(100, 100, 100))

    minimize_cell_tail(cell)


# ── sticker-sheet assembly ────────────────────────────────────────────────────

def _ensure_sect_pr_last(body) -> None:
    """sectPr must be the final body child; mid-document sectPr causes blank pages."""
    sect = body.find(qn("w:sectPr"))
    if sect is not None:
        body.remove(sect)
        body.append(sect)


def _insert_before_sect(body, element) -> None:
    sect = body.find(qn("w:sectPr"))
    if sect is not None:
        sect.addprevious(element)
    else:
        body.append(element)


def _minimal_body_paragraph() -> OxmlElement:
    """Tiny paragraph (no page break) for Word's body tail requirement."""
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
    return p


def _add_document_tail(body) -> None:
    """One minimal paragraph before sectPr — no page break (avoids blank trailing page)."""
    _ensure_sect_pr_last(body)
    sect = body.find(qn("w:sectPr"))
    if sect is None:
        return
    prev = sect.getprevious()
    if prev is not None and prev.tag == qn("w:p"):
        for br in prev.findall(".//" + qn("w:br")):
            if br.get(qn("w:type")) == "page":
                parent = br.getparent()
                if parent is not None:
                    parent.remove(br)
        return
    sect.addprevious(_minimal_body_paragraph())
    _ensure_sect_pr_last(body)


def _page4_grid(body):
    """Return the page-4 sticker sheet table (3×3, no gutters)."""
    for tbl in body.findall(qn("w:tbl")):
        grid = tbl.find(qn("w:tblGrid"))
        if grid is not None and len(grid.findall(qn("w:gridCol"))) == 3:
            return tbl
    raise ValueError("page 4 sticker grid (3×3 table) not found in template")


def clear_cell_borders(cell) -> None:
    """Remove printable borders from a sticker-slot cell."""
    tc_pr = _tc_pr(cell)
    old = tc_pr.find(qn("w:tcBorders"))
    if old is not None:
        tc_pr.remove(old)
    b = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        b.append(el)
    tc_pr.append(b)
    shd = tc_pr.find(qn("w:shd"))
    if shd is not None:
        tc_pr.remove(shd)


def strip_grid_guides(table) -> None:
    """Hide the Apostrophe template's gray slot grid when printing."""
    borders(table, outer=0, inner_h=0, inner_v=0)
    pr = table._tbl.tblPr
    for tag in ("w:tblStyle",):
        el = pr.find(qn(tag))
        if el is not None:
            pr.remove(el)
    look = pr.find(qn("w:tblLook"))
    if look is None:
        look = OxmlElement("w:tblLook")
        pr.append(look)
    look.set(qn("w:val"), "0000")
    look.set(qn("w:firstRow"), "0")
    look.set(qn("w:lastRow"), "0")
    look.set(qn("w:firstColumn"), "0")
    look.set(qn("w:lastColumn"), "0")
    look.set(qn("w:noHBand"), "0")
    look.set(qn("w:noVBand"), "0")
    for row in table.rows:
        for cell in row.cells:
            clear_cell_borders(cell)


def keep_sticker_grid(doc: Document) -> None:
    """Keep only page 4's sticker grid (the 3×3 table) + section props.

    Uses the template's page margins and slot dimensions so the printed sheet
    aligns with Apostrophe's edge-to-edge poker sticker layout."""
    body = doc.element.body
    sheet = _page4_grid(body)
    sect = body.find(qn("w:sectPr"))
    for el in list(body):
        if el is not sheet and el is not sect:
            body.remove(el)

    # The template ships the grid as a floating (page-centered) table. Once the
    # cells are filled, the renderer can't center the taller table on one page
    # and splits it across two. Make it in-flow instead, with fixed row heights
    # and the template's page margins, so all 9 cards stay on one page.
    tblPr = sheet.find(qn("w:tblPr"))
    tp = tblPr.find(qn("w:tblpPr"))
    if tp is not None:
        tblPr.remove(tp)
    jc = tblPr.find(qn("w:jc"))
    if jc is None:
        jc = OxmlElement("w:jc")
        tblPr.append(jc)
    jc.set(qn("w:val"), "center")
    for tr in sheet.findall(qn("w:tr")):
        trPr = tr.find(qn("w:trPr"))
        h = trPr.find(qn("w:trHeight")) if trPr is not None else None
        if h is not None:
            h.set(qn("w:val"), str(SLOT_H))
            h.set(qn("w:hRule"), "exact")

    section = doc.sections[0]
    section.top_margin = Inches(PAGE_MAR_TOP / 1440)
    section.bottom_margin = Inches(PAGE_MAR_BOTTOM / 1440)
    section.left_margin = Inches(PAGE_MAR_LEFT / 1440)
    section.right_margin = Inches(PAGE_MAR_RIGHT / 1440)

    # Template slot gridlines must not print — strip table style + cell borders.
    strip_grid_guides(doc.tables[0])
    if body.find(qn("w:sectPr")) is None:
        body.append(OxmlElement("w:sectPr"))
    _ensure_sect_pr_last(body)


def main() -> None:
    require_sticker_sheet()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STICKER_SHEET, OUTPUT)
    doc = Document(OUTPUT)
    keep_sticker_grid(doc)

    sheet = doc.tables[0]
    for i, (r, c) in enumerate(CARD_SLOTS):
        build_card(sheet.rows[r].cells[c], advance_record=(i > 0), idx=i)

    _add_document_tail(doc.element.body)
    doc.save(OUTPUT)
    print(f"Wrote {OUTPUT}")
    print(f"  9 cards · 3×3 sticker grid · mail-merge ready")
    if LOGO.exists():
        print(f"  Logo: {LOGO.name}")


if __name__ == "__main__":
    main()
