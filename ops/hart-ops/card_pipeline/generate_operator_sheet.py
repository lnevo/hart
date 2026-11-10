#!/usr/bin/env python3
"""Generate an operator reference sheet for HART industries and yards."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

import csv

import generate_waybill_cards as gw

OUTPUT = gw.BASE.parents[1] / "docs/ops/HART_Operator_Sheet.docx"
LOGO_DIR = gw.BASE / "operator_logos"
SPUR_FILE = gw.BASE / "sts-docker-helpers" / "seed" / "inputs" / "spurs"
EMPTY = gw.EMPTY

PAGE_W = Inches(5)
PAGE_H = Inches(8)
MARGIN = Inches(0.4)

FONT_BODY = Pt(8.5)
FONT_HEADING = Pt(13)
FONT_SECTION = Pt(7.5)
FONT_TABLE = Pt(7.5)
FONT_TABLE_HEAD = Pt(7)
FONT_BULLET = Pt(8)

COLOR_BODY = RGBColor(0x44, 0x44, 0x44)
COLOR_MUTED = RGBColor(0x66, 0x66, 0x66)
COLOR_INK = RGBColor(0x22, 0x22, 0x22)
COLOR_BORDER = "BBBBBB"
COLOR_PANEL = "FAFAFA"

TABLE_COLS_IN = (0.32, 0.88, 0.82, 0.95, 0.95)
TABLE_COLS_TRACK = (1.05, 0.55, 1.15, 1.15)  # Track, Cars, In, Out (no spots)

USAGE_LABELS: dict[str, str] = {
    "pellet unload": "Pellet Unloading",
    "chemical unload": "Chemical Unloading",
    "shipping door": "Shipping",
    "coal unload": "Coal Unloading",
    "carbon load": "Carbon Loading",
    "cement unload": "Cement Unloading",
    "aggregate unload": "Aggregate Unloading",
    "lpg unload": "LPG Unloading",
    "crane track": "Steel Unloading",
    "team track": "Team Track",
    "off spot": "Off Spot",
    "storage": "Storage",
}

# Spur accent colors from layout `spurs` → STS location color names.
# Hex values match sts/build_cc_mtybill.php ($color_palette).
SPUR_PALETTE: dict[str, dict[str, str]] = {
    # Richer than pure #FFFF00 so the Aristech band reads yellow on screen/print
    # (pure neon yellow washes out as a thin rule).
    "yellow": {"accent": "FFD400", "text": "000000"},
    "green": {"accent": "008000", "text": "008000"},
    "blue": {"accent": "0000CD", "text": "0000CD"},
    "red": {"accent": "FF0000", "text": "FF0000"},
    "orange": {"accent": "FFA500", "text": "000000"},
    "purple": {"accent": "800080", "text": "800080"},
    "pink": {"accent": "FFC0CB", "text": "000000"},
    "lightblue": {"accent": "ADD8E6", "text": "000000"},
    "mediumblue": {"accent": "0000CD", "text": "0000CD"},
    "lightgrey": {"accent": "D3D3D3", "text": "000000"},
    "black": {"accent": "000000", "text": "000000"},
}

INDUSTRY_LOGOS: dict[str, tuple[str, float]] = {
    "Aristech Plastics": ("aristech.png", 1.95),
    "A Stucki Co": ("stucki.png", 1.55),
    "Calgon Carbon": ("calgon.png", 2.05),
    "Ferrel Gas": ("ferrellgas.png", 1.05),
    "Kosmos Cement": ("kosmos.png", 1.45),
    "Shenango Coke Works": ("shenango.png", 0.55),
}

# Local page order for island industries (includes Shenango; not in waybill INDUSTRY_ORDER).
SHEET_INDUSTRY_ORDER: dict[str, int] = {
    "Aristech Plastics": 0,
    "A Stucki Co": 1,
    "Calgon Carbon": 2,
    "Ferrel Gas": 3,
    "Kosmos Cement": 4,
    "Shenango Coke Works": 5,
}

# Historical notes (through 1990s) plus a short traffic line for the operator.
INDUSTRY_SUMMARIES: dict[str, list[str]] = {
    "Aristech Plastics": [
        "Founded 1986 as Aristech Chemical, spun off from U.S. Steel's USS Chemicals "
        "division with headquarters in Pittsburgh.",
        "Major producer of acrylic sheet, molded plastics, and synthetic resins for "
        "bathtubs, spas, architectural panels, and packaging.",
        "Continuous-cast acrylic sheet production began in 1969; chemical operations "
        "draw on the former USS Chemicals heritage dating to the 1960s.",
        "Traffic: plastic pellets (HC) and process chemicals (TA) in; plastic resins (XM) "
        "out. NVL serves the plant.",
    ],
    "A Stucki Co": [
        "Founded 1911 by Swiss engineer Arnold Stucki in the Pittsburgh area.",
        "Stucki's roller side-bearing design stabilized freight cars and became a "
        "North American industry standard by the 1950s.",
        "Grew through the 20th century as a supplier of railcar components, springs, "
        "bearings, and machined steel.",
        "Traffic: steel (FM/GA/XM) on the crane; general freight (XM/FM/GA) on the team "
        "track. Empties and outbound parts leave after spotting. NVL serves the plant.",
    ],
    "Calgon Carbon": [
        "Traces to 1942, when Pittsburgh Coke & Chemical developed coal-based activated "
        "carbon for U.S. military gas masks during World War II.",
        "Pioneered granular activated carbon for municipal drinking-water treatment in "
        "the 1960s; headquartered in the Pittsburgh area.",
        "Became an independent public company in 1987; one of the world's leading "
        "activated-carbon producers by the 1990s.",
        "Traffic: coal (HM) and process chemicals (TA) in; activated carbon (HC) out. "
        "NVL serves the plant.",
    ],
    "Ferrel Gas": [
        "Founded 1939 as A.C. Ferrell Butane Gas Company in Atchison, Kansas.",
        "James E. Ferrell took over in 1965 when the business had just four employees, "
        "then rebuilt it through Midwest propane dealer acquisitions.",
        "Bulk propane storage and rail deliveries expanded through the 1970s and 1980s "
        "as residential and farm demand grew.",
        "Traffic: LPG (TA) in at the unload racks; empty tanks out. NVL serves the plant.",
    ],
    "Kosmos Cement": [
        "Portland cement plant at Kosmosdale, Kentucky, shipping from the same site since "
        "1905; founded by Samuel Horner Jr. as Kosmos Portland Cement Company.",
        "Supplied cement for early Ohio River lock and dam construction; a fleet of "
        "company towboats with names beginning in \"K\" moved cement and quarry stone.",
        "The company town of Kosmosdale grew around the mill; Horner heirs sold the "
        "operation in 1957 and the plant was rebuilt in the early 1970s.",
        "Traffic: cement (HC) and aggregate (HM/GA) in; empty hoppers out. NVL serves "
        "the plant.",
    ],
    "Shenango Coke Works": [
        "Pittsburgh Coke & Chemical (PC&C) was making coke and pig iron on the "
        "eastern end of Neville Island by 1929. The coke ovens and chemical works "
        "that later became Shenango date to about 1930.",
        "PC&C was more than a coke plant: on the island it also made cement, "
        "industrial chemicals, and activated carbon. Those other branches became "
        "the Kosmos, Aristech, and Calgon operations still switched today.",
        "In 1962 Shenango Furnace purchased PC&C. The coke-and-iron division became "
        "Shenango Inc. and kept making coke and coke by-products on the same site "
        "for decades after the PC&C name disappeared.",
        "Traffic: HM coke on Shipping 1 and Shipping 2 (no numbered spots). CK1 lifts "
        "for South Yard scale. Loads to U.S. Steel Edgar Thomson Works (Braddock, PA) "
        "via CSX and LTV Steel Cleveland Works (Cleveland, OH) via POHC. NVL may set "
        "out deliveries; no Shenango empty pickup on the NVL return.",
    ],
}

SHENANGO_TRACK_ROWS: list[dict[str, str]] = [
    {
        "track": "Shipping 1",
        "cars": "HM",
        "inbound": "Empty / reload coke",
        "outbound": "Coke",
    },
    {
        "track": "Shipping 2",
        "cars": "HM",
        "inbound": "Empty / reload coke",
        "outbound": "Coke",
    },
]

# Yard / desk reference pages (after island industries).
# Offline company lists from hart_scully_nville_shipping_map_proposed.csv
# (party tracks at McKees Rocks-PA / Mckeesport-PA — not Neville Island plants).
YARD_PAGES: list[dict] = [
    {
        "title": "Scully Yard",
        "subtitle": "POHC interchange · McKees Rocks offline",
        "accent": "FFA500",  # STS orange
        "text": "000000",
        "logo": "pohc.png",
        "logo_width": 1.25,
        "role": [
            "POHC gateway. NVL takes its session-start block here. McKees Rocks-PA "
            "party tracks hold offline suppliers and customers.",
            "Connections beyond the offline tracks are typically POHC and NS.",
        ],
        "sections": [
            (
                "McKees Rocks — inbound (suppliers)",
                [
                    "Allegheny Ludlum (Brackenridge, PA)",
                    "Exxon Chemical (Bayonne, NJ)",
                    "Ferrellgas Co (Taneytown, MD)",
                    "General Chemical (Parsippany, NJ)",
                    "Hillman Coal (Canton Twp, PA)",
                    "Houghton Chemical (Allston, MA)",
                    "Kosmos Cement (Canton, OH)",
                    "Lehigh Cement (Mitchell, IN)",
                    "McConway & Torley (Pittsburgh, PA)",
                    "Michigan Limestone (Rogers City, MI)",
                    "Novacor (Indian Orchard, MA)",
                    "Republic Steel (Cleveland, OH)",
                ],
            ),
            (
                "McKees Rocks — outbound (customers)",
                [
                    "LTV Steel Cleveland Works (Cleveland, OH) — coke",
                    "Owens-Illinois (Toledo, OH)",
                    "Bemis Company (Flemington, NJ)",
                    "Pittsburgh Forge (McKees Rocks, PA)",
                    "Univar (Salem, MA)",
                ],
            ),
        ],
        "jobs": [
            "NVL — assign/pickup session block at Scully, then run to South Yard.",
        ],
    },
    {
        "title": "Demmler Yard",
        "subtitle": "CSX interchange · Mckeesport offline",
        "accent": "0000CD",  # STS mediumblue
        "text": "0000CD",
        "logo": "csx.png",
        "logo_width": 1.55,
        "role": [
            "CSX gateway. D749 lifts its inbound block here at session start. "
            "Mckeesport-PA party tracks hold offline suppliers and customers.",
            "Connections beyond the offline tracks are typically CSX "
            "(URR territory historically adjacent at Mckeesport).",
        ],
        "sections": [
            (
                "Mckeesport — inbound (suppliers)",
                [
                    "BASF (Wyandotte, MI)",
                    "Consol Energy (Pittsburgh, PA)",
                    "Dow Chemical (Midland, MI)",
                    "Ferrellgas pipeline terminal",
                    "Martin Marietta (Clairton, PA)",
                    "Medusa Cement (Charlevoix, MI)",
                    "Metal Service Co. (Apollo, PA)",
                    "R&P Coal (Brady Twp, PA)",
                    "Ryerson Steel Service",
                    "US Aggregates (Indianapolis, IN)",
                    "Washington Steel (Washington, PA)",
                    "Calgon Corp (Columbus, OH)",
                ],
            ),
            (
                "Mckeesport — outbound (customers)",
                [
                    "U.S. Steel Edgar Thomson Works (Braddock, PA) — coke",
                    "Calgon Corp (Columbus, OH)",
                    "Houghton Chemical (Allston, MA)",
                    "Metal Service Co. (Apollo, PA)",
                    "Owens-Illinois (Ottawa, IL)",
                    "Ryerson Steel Service",
                ],
            ),
        ],
        "jobs": [
            "D749 — pickup Demmler block → South Yard setout to open the session; "
            "later return from McKeesport side and terminate West Yard.",
        ],
    },
    {
        "title": "South Yard",
        "subtitle": "Classification hub · session start",
        "accent": "D3D3D3",  # STS lightgrey
        "text": "000000",
        "logo": "hart.png",
        "logo_width": 0.72,
        "role": [
            "Session open / class yard. West Lead = SOUTH-SCALE (CK1 weigh at 4 MPH, "
            "stretch, no brakes). Exchange: Demmler/CSX off; Island/Shenango on.",
        ],
        "trains": [
            {
                "name": "D749 — CSX turn",
                "lines": [
                    "Lift West Yard consist → Demmler pickup → South setout to open ops; "
                    "interchange per YM; west when cleared.",
                    "Return from McKeesport; YM spots West or South; engine to terminal.",
                ],
            },
            {
                "name": "NVL — POHC Island local",
                "lines": [
                    "Scully → South; interchange per YM; work Island industries + "
                    "Shenango setouts.",
                    "Finish Island/Shenango deliveries before return homebound. Final "
                    "South interchange → Scully. Shenango deliver-only on return.",
                ],
            },
            {
                "name": "CK1 — Coke transfer",
                "lines": [
                    "Calibrate scale. Shenango: set out reloads, lift Shipping 1/2 coke → "
                    "weigh West Lead → class. Imbalanced → reload orders.",
                    "Same session: reloads South → Shenango when authorized.",
                ],
            },
        ],
        "blocking": [
            "1. D749 Demmler → South setout opens the session.",
            "2. NVL South exchange before Island work.",
            "3. Island/Shenango setouts before NVL return homebound assigns.",
            "4. CK1 weigh/resort; reloads to Shenango when ready.",
            "5. D749 return → West Yard.",
        ],
    },
    {
        "title": "Dispatcher",
        "subtitle": "HART Railroad · session control",
        "accent": "000000",
        "text": "000000",
        "logo": "hart.png",
        "logo_width": 0.72,
        "role": [
            "Authorize road moves, keep train order, and protect the South Yard block "
            "exchange. Crews work from switch lists; yardmaster owns South class tracks.",
        ],
        "sections": [
            (
                "Territory",
                [
                    "Scully Yard — POHC interchange (NVL start).",
                    "Neville Island / Shenango — NVL local; CK1 coke plant.",
                    "South Yard — class hub, session open, track scale (West Lead).",
                    "Demmler Yard — CSX interchange (D749 start / return).",
                    "West Yard — D749 overnight / terminate.",
                ],
            ),
            (
                "Session sequence",
                [
                    "D749: Demmler pickup → South setout opens ops; then west as cleared.",
                    "NVL: Scully block → South exchange → Island / Shenango work → return "
                    "to Scully (Shenango deliver-only on return).",
                    "CK1: Shenango shipping → South scale → class; reloads back when ready.",
                    "D749 return from McKeesport → West Yard.",
                ],
            ),
        ],
        "blocking": [
            "1. Hold NVL Island work until South has taken the D749 inbound setout "
            "and completed the block exchange.",
            "2. Island / Shenango deliveries before NVL builds the homebound.",
            "3. CK1 scale string clear of West Lead conflicts during weigh (4 MPH).",
            "4. One road move at a time across shared leads when crews meet at South.",
        ],
    },
]


def _load_industry_styles() -> dict[str, dict]:
    """Merge spur colors from `spurs` with optional logo paths."""
    styles: dict[str, dict] = {}
    with SPUR_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "-" not in line:
                continue
            industry, _, color_name = [part.strip() for part in line.split("-", 2)]
            palette = SPUR_PALETTE.get(color_name.lower())
            if not palette:
                continue
            entry = dict(palette)
            logo_info = INDUSTRY_LOGOS.get(industry)
            if logo_info:
                entry["logo"] = logo_info[0]
                entry["logo_width"] = logo_info[1]
            else:
                entry["logo"] = None
                entry["logo_width"] = 0.0
            styles[industry] = entry
    return styles


INDUSTRY_STYLE = _load_industry_styles()


def _configure_page(section) -> None:
    section.page_width = PAGE_W
    section.page_height = PAGE_H
    section.left_margin = MARGIN
    section.right_margin = MARGIN
    section.top_margin = MARGIN
    section.bottom_margin = MARGIN
    section.header_distance = Inches(0)
    section.footer_distance = Inches(0)


def _configure_document(doc: Document) -> None:
    _configure_page(doc.sections[0])
    normal = doc.styles["Normal"]
    normal.font.size = FONT_BODY
    normal.font.name = "Georgia"
    normal.font.color.rgb = RGBColor(0x33, 0x33, 0x33)


def _set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _set_cell_margins(cell, top=40, bottom=40, left=60, right=60) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for tag, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        node = OxmlElement(f"w:{tag}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tc_pr.append(mar)


def _set_table_borders(
    table,
    *,
    color: str = COLOR_BORDER,
    outer_size: int = 6,
    inner_size: int = 4,
) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(outer_size))
        element.set(qn("w:color"), color)
        borders.append(element)
    for edge in ("insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(inner_size))
        element.set(qn("w:color"), color)
        borders.append(element)
    tbl_pr.append(borders)


def _set_cell_border(cell, *, bottom_size: int = 0, bottom_color: str = COLOR_BORDER) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "right"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "nil")
        borders.append(element)
    bottom = OxmlElement("w:bottom")
    if bottom_size:
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), str(bottom_size))
        bottom.set(qn("w:color"), bottom_color)
    else:
        bottom.set(qn("w:val"), "nil")
    borders.append(bottom)
    tc_pr.append(borders)


def _accent_rule(doc: Document, accent: str) -> None:
    rule = doc.add_table(rows=1, cols=1)
    rule.autofit = False
    cell = rule.rows[0].cells[0]
    cell.width = PAGE_W - 2 * MARGIN
    _set_cell_shading(cell, accent)
    _set_cell_margins(cell, top=0, bottom=0, left=0, right=0)
    cell.paragraphs[0].paragraph_format.space_after = Pt(0)
    rule.rows[0].height = Pt(4)
    _set_table_borders(rule, color=accent, outer_size=0, inner_size=0)


def _keep_with_next(paragraph) -> None:
    paragraph.paragraph_format.keep_with_next = True


def _set_row_cant_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        tr_pr.append(OxmlElement("w:cantSplit"))


def _set_table_column_widths(table, widths_in: tuple[float, ...]) -> None:
    table.autofit = False
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            if idx < len(widths_in):
                cell.width = Inches(widths_in[idx])


def _add_banner(doc: Document, title: str, style: dict) -> None:
    logo_name = style.get("logo")
    logo_path = LOGO_DIR / logo_name if logo_name else None
    has_logo = bool(logo_path and logo_path.exists())
    banner = doc.add_table(rows=1, cols=1)
    banner.autofit = False
    cell = banner.rows[0].cells[0]
    cell.width = PAGE_W - 2 * MARGIN
    _set_cell_shading(cell, COLOR_PANEL)
    _set_cell_margins(cell, top=90, bottom=90, left=100, right=100)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    _set_cell_border(cell, bottom_size=8, bottom_color=style["accent"])
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if has_logo:
        run = p.add_run()
        run.add_picture(str(logo_path), width=Inches(style["logo_width"]))
    else:
        run = p.add_run(title)
        run.bold = True
        run.font.size = FONT_HEADING
        run.font.name = "Georgia"
        run.font.color.rgb = RGBColor.from_string(style["text"])
    _keep_with_next(p)
    banner.rows[0].height = Inches(0.72 if has_logo else 0.52)
    _set_table_borders(banner, color=COLOR_BORDER, outer_size=4, inner_size=0)


def _add_title_heading(doc: Document, title: str, accent: str, *, subtitle: str = "") -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2 if subtitle else 6)
    run = p.add_run(title)
    run.bold = True
    run.font.size = FONT_HEADING
    run.font.name = "Georgia"
    run.font.color.rgb = RGBColor.from_string(accent if accent != "D3D3D3" else "222222")
    _keep_with_next(p)
    if subtitle:
        s = doc.add_paragraph()
        s.paragraph_format.space_before = Pt(0)
        s.paragraph_format.space_after = Pt(6)
        r = s.add_run(subtitle)
        r.font.size = FONT_SECTION
        r.font.name = "Georgia"
        r.font.color.rgb = COLOR_MUTED
        _keep_with_next(s)


def _add_section_label(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = FONT_SECTION
    run.font.name = "Georgia"
    run.font.color.rgb = COLOR_MUTED
    _keep_with_next(p)


def _add_body_paragraph(doc: Document, text: str, *, keep: bool = True) -> None:
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    for run in p.runs:
        run.font.size = FONT_BODY
        run.font.name = "Georgia"
        run.font.color.rgb = COLOR_BODY
    if keep:
        _keep_with_next(p)


def _add_bullet(doc: Document, text: str, *, keep: bool = True) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.15)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.space_before = Pt(0)
    run = p.add_run(f"• {text}")
    run.font.size = FONT_BULLET
    run.font.name = "Georgia"
    run.font.color.rgb = COLOR_BODY
    if keep:
        _keep_with_next(p)


def _style_data_table(table, accent: str, *, center_first: bool = True) -> None:
    header = table.rows[0]
    for idx, cell in enumerate(header.cells):
        _set_cell_margins(cell, top=35, bottom=35, left=45, right=45)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _set_cell_border(cell, bottom_size=8, bottom_color=accent)
        for p in cell.paragraphs:
            p.alignment = (
                WD_ALIGN_PARAGRAPH.CENTER if center_first and idx == 0 else WD_ALIGN_PARAGRAPH.LEFT
            )
            for run in p.runs:
                run.bold = True
                run.font.size = FONT_TABLE_HEAD
                run.font.name = "Georgia"
                run.font.color.rgb = COLOR_INK

    for row in table.rows[1:]:
        for idx, cell in enumerate(row.cells):
            _set_cell_margins(cell, top=28, bottom=28, left=45, right=45)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            for p in cell.paragraphs:
                p.alignment = (
                    WD_ALIGN_PARAGRAPH.CENTER
                    if center_first and idx == 0
                    else WD_ALIGN_PARAGRAPH.LEFT
                )
                for run in p.runs:
                    run.font.size = FONT_TABLE
                    run.font.name = "Georgia"
                    run.font.color.rgb = COLOR_BODY
        _set_row_cant_split(row)


def _usage_label(usage: str) -> str:
    return USAGE_LABELS.get(usage.lower(), usage).lstrip()


def _format_inbound(spec: dict) -> str:
    return gw.inbound_commodity_label(spec)


def _format_outbound(spec: dict) -> str:
    load = spec["outbound_load"]
    return "Empty cars" if load == EMPTY else load


def _add_spot_table(doc: Document, rows: list[dict], accent: str) -> None:
    table = doc.add_table(rows=1, cols=5)
    for i, text in enumerate(("Spot", "Track", "Cars", "In", "Out")):
        table.rows[0].cells[i].text = text
    for row in rows:
        cells = table.add_row().cells
        cells[0].text = row["spot"]
        cells[1].text = row["usage"]
        cells[2].text = row["cars"]
        cells[3].text = row["inbound"]
        cells[4].text = row["outbound"]
    _set_table_column_widths(table, TABLE_COLS_IN)
    _set_table_borders(table)
    _style_data_table(table, accent)


def _add_track_table(doc: Document, rows: list[dict], accent: str) -> None:
    table = doc.add_table(rows=1, cols=4)
    for i, text in enumerate(("Track", "Cars", "In", "Out")):
        table.rows[0].cells[i].text = text
    for row in rows:
        cells = table.add_row().cells
        cells[0].text = row["track"]
        cells[1].text = row["cars"]
        cells[2].text = row["inbound"]
        cells[3].text = row["outbound"]
    _set_table_column_widths(table, TABLE_COLS_TRACK)
    _set_table_borders(table)
    _style_data_table(table, accent, center_first=False)


def _add_industry_section(
    doc: Document, industry: str, rows: list[dict], *, page_break: bool
) -> None:
    if page_break:
        doc.add_page_break()

    style = INDUSTRY_STYLE[industry]
    logo_path = LOGO_DIR / style["logo"] if style.get("logo") else None
    has_logo = bool(logo_path and logo_path.exists())

    _add_banner(doc, industry, style)
    _accent_rule(doc, style["accent"])
    if not has_logo:
        _add_title_heading(doc, industry, style["accent"])

    summary_lines = INDUSTRY_SUMMARIES.get(industry, [])
    for i, line in enumerate(summary_lines):
        _add_body_paragraph(doc, line, keep=i < len(summary_lines) - 1)

    if industry == "Shenango Coke Works":
        _add_section_label(doc, "Tracks")
        _add_track_table(doc, SHENANGO_TRACK_ROWS, style["accent"])
        note = doc.add_paragraph()
        note.paragraph_format.space_before = Pt(6)
        note.paragraph_format.space_after = Pt(0)
        r = note.add_run("No numbered spots. Weigh all outgoing coke at South Yard scale.")
        r.font.size = FONT_BULLET
        r.font.name = "Georgia"
        r.font.color.rgb = COLOR_MUTED
        return

    _add_section_label(doc, "Tracks & spots")
    _add_spot_table(doc, rows, style["accent"])


def _add_yard_section(doc: Document, page: dict, *, page_break: bool) -> None:
    if page_break:
        doc.add_page_break()

    style = {
        "accent": page["accent"],
        "text": page["text"],
        "logo": page.get("logo"),
        "logo_width": float(page.get("logo_width") or 0.0),
    }
    _add_banner(doc, page["title"], style)
    _accent_rule(doc, page["accent"])
    # Always show the desk/yard name — logos are railroad marks, not page titles.
    _add_title_heading(doc, page["title"], page["accent"], subtitle=page.get("subtitle", ""))

    for line in page.get("role", []):
        _add_body_paragraph(doc, line)

    for label, items in page.get("sections", []):
        _add_section_label(doc, label)
        for item in items:
            _add_bullet(doc, item)

    if page.get("trains"):
        _add_section_label(doc, "Trains this session")
        for job in page["trains"]:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(job["name"])
            run.bold = True
            run.font.size = FONT_BULLET
            run.font.name = "Georgia"
            run.font.color.rgb = COLOR_INK
            _keep_with_next(p)
            for line in job["lines"]:
                _add_bullet(doc, line)

    if page.get("blocking"):
        _add_section_label(doc, "Blocking priority")
        for item in page["blocking"]:
            _add_bullet(doc, item)

    if page.get("jobs"):
        _add_section_label(doc, "Jobs")
        for item in page["jobs"]:
            _add_bullet(doc, item)


def _load_off_spot_rows() -> dict[str, list[dict]]:
    spots: dict[tuple[str, str], list[int]] = defaultdict(list)
    cars: dict[tuple[str, str], str] = {}

    with gw.SPOT_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            industry = gw._norm(row.get("Industry"))
            usage = gw._norm(row.get("Usage"))
            if not industry or usage.lower() not in gw.SKIP_USAGES:
                continue
            spot = gw._parse_spot_num(row.get("Spot #", ""))
            if spot:
                key = (industry, usage)
                spots[key].append(spot)
                cars[key] = row.get("Cars Applicable", "").replace(";", ", ")

    by_industry: dict[str, list[dict]] = defaultdict(list)
    for (industry, usage), nums in spots.items():
        by_industry[industry].append(
            {
                "spot": gw._format_spots(nums),
                "usage": _usage_label(usage),
                "cars": cars[(industry, usage)],
                "inbound": "—",
                "outbound": "—",
                "sort": min(nums),
            }
        )
    for industry in by_industry:
        by_industry[industry].sort(key=lambda r: r["sort"])
    return dict(by_industry)


def _load_all_spot_rows() -> dict[str, list[dict]]:
    combined: dict[str, list[dict]] = {name: [] for name in gw.INDUSTRY_ORDER}

    for group in gw.load_spot_groups():
        industry = group["Industry"]
        spec = gw._waybill_spec(industry, group["Usage"])
        combined[industry].append(
            {
                "spot": group["Spots"],
                "usage": _usage_label(group["Usage"]),
                "cars": ", ".join(group["CarTypes"]),
                "inbound": _format_inbound(spec),
                "outbound": _format_outbound(spec),
                "sort": int(group["Spots"].split("-")[0].split(",")[0]),
            }
        )

    off_spot = _load_off_spot_rows()
    for industry in gw.INDUSTRY_ORDER:
        combined[industry].extend(off_spot.get(industry, []))
        combined[industry].sort(key=lambda r: r["sort"])

    return combined


def generate() -> None:
    doc = Document()
    _configure_document(doc)

    by_industry = _load_all_spot_rows()
    ordered = sorted(SHEET_INDUSTRY_ORDER, key=lambda n: SHEET_INDUSTRY_ORDER[n])
    page_count = 0

    for industry in ordered:
        if industry == "Shenango Coke Works":
            _add_industry_section(doc, industry, [], page_break=page_count > 0)
            page_count += 1
            continue
        rows = by_industry.get(industry, [])
        if rows:
            _add_industry_section(doc, industry, rows, page_break=page_count > 0)
            page_count += 1

    for yard in YARD_PAGES:
        _add_yard_section(doc, yard, page_break=page_count > 0)
        page_count += 1

    doc.save(OUTPUT)
    print(
        f"Wrote {OUTPUT} ({PAGE_W.inches:.0f}×{PAGE_H.inches:.0f} in, "
        f"{page_count} pages)"
    )


if __name__ == "__main__":
    generate()
