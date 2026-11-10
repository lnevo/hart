#!/usr/bin/env python3
"""Rebuild Neville Island New Operator Primer (HB-01, Revision B).

Readable pre-session handbook for new crew: island background, how the
railroad works, jobs at a glance, destination colors, scale overview, and
pointers to the desk sheets used during the session.

Drawn from past session invite emails and the current DS / YM / CI / EQ pubs.

Usage (from repo root):
  .venv/bin/python publications/rebuild_operator_primer.py

Writes:
  docs/Neville_Island_New_Operator_Primer.docx
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/ops"
PUB = Path(__file__).resolve().parent
sys.path.insert(0, str(PUB))

from hart_pub_helpers import (  # noqa: E402
    ACCENT,
    BODY,
    MUTED,
    RULE,
    _set_run_font,
    add_horizontal_rule,
    add_publication_footer,
    add_station_map_page,
    fill_header_row,
    fill_swatch_cell,
    style_table,
)

CANONICAL = DOCS / "Neville_Island_New_Operator_Primer.docx"

PUBLICATION = {
    "title": "New Operator Primer",
    "pub_id": "HB-01",
    "revision": "B",
    "effective": "15 October 2026",
}

BLOCK_LEGEND: list[tuple[str, str, str, str, str]] = [
    ("BLUE", "0000CD", "FFFFFF", "Demmler Yard; McKeesport", "D749"),
    ("YELLOW", "FFFF00", "000000", "Aristech Plastics", "NVL"),
    ("GREEN", "008000", "FFFFFF", "A. Stucki Co.", "NVL"),
    ("PURPLE", "800080", "FFFFFF", "Calgon Carbon", "NVL"),
    ("RED", "FF0000", "FFFFFF", "Ferrellgas", "NVL"),
    ("PINK", "FFC0CB", "000000", "Kosmos Cement", "NVL"),
    ("BLACK", "000000", "FFFFFF", "Shenango Coke Works", "CK1"),
    ("ORANGE", "FFA500", "000000", "Scully Yard; McKees Rocks", "NVL return"),
]

JOBS: list[tuple[str, str, str]] = [
    (
        "D749",
        "CSX Neville Island Switcher",
        (
            "The CSX local that comes over from Demmler / McKeesport. It drops "
            "its inbound cars at South Yard, visits the engine terminal, then "
            "picks up the outbound block and heads back."
        ),
    ),
    (
        "NVL",
        "Neville Island Turn",
        (
            "The Pittsburgh & Ohio Central local from Scully Yard. It swaps "
            "cars at South Yard, switches the island industries, then takes "
            "the return cut back toward McKees Rocks."
        ),
    ),
    (
        "CK1",
        "Coke Transfer",
        (
            "Works Shenango Coke Works—the pickup, the weigh, and the sort. "
            "Also calibrates the track scale at the start of the session. "
            "The Yardmaster assigns the engine."
        ),
    ),
    (
        "Yardmaster",
        "South Yard",
        (
            "Keeps South Yard organized. Builds cuts by color, hands work to "
            "each train, and keeps D749, NVL, and CK1 from stepping on each "
            "other. YM-01 is the working sequence."
        ),
    ),
    (
        "Dispatcher",
        "Neville Island Ops",
        (
            "Gives clearance and keeps freight out of the streetcar's way. "
            "When things get busy, Route 23 and the main trains come first. "
            "DS-01 has the full lineup."
        ),
    ),
    (
        "Route 23",
        "Streetcar",
        (
            "A refurbished PCC car running local passenger service across the "
            "island. Freight holds until the streetcar clears."
        ),
    ),
]


def _set_comfortable_page(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)
    section.header_distance = Inches(0.5)
    section.footer_distance = Inches(0.5)


def _page_break(doc: Document) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.add_run().add_break(WD_BREAK.PAGE)


def _light_masthead(doc: Document) -> None:
    brand = doc.add_paragraph()
    brand.alignment = WD_ALIGN_PARAGRAPH.CENTER
    brand.paragraph_format.space_before = Pt(0)
    brand.paragraph_format.space_after = Pt(4)
    r = brand.add_run("HART Railroad")
    _set_run_font(r, size_pt=20, bold=True, color=ACCENT)

    div = doc.add_paragraph()
    div.alignment = WD_ALIGN_PARAGRAPH.CENTER
    div.paragraph_format.space_before = Pt(0)
    div.paragraph_format.space_after = Pt(10)
    r = div.add_run("Pittsburgh & Chartiers Valley Division")
    _set_run_font(r, size_pt=11, color=MUTED)

    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(0)
    rule.paragraph_format.space_after = Pt(12)
    add_horizontal_rule(rule, RULE)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(4)
    r = title.add_run(PUBLICATION["title"])
    _set_run_font(r, size_pt=16, bold=True, color=BODY)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_before = Pt(0)
    sub.paragraph_format.space_after = Pt(18)
    r = sub.add_run("A short briefing for new crew on Neville Island")
    _set_run_font(r, size_pt=11, color=MUTED)


def _heading(doc: Document, text: str, *, space_before: float = 18) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    _set_run_font(r, size_pt=13, bold=True, color=ACCENT)
    add_horizontal_rule(p, ACCENT)


def _body(
    doc: Document,
    text: str,
    *,
    space_before: float = 0,
    space_after: float = 10,
) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.35
    r = p.add_run(text)
    _set_run_font(r, size_pt=11, color=BODY, name="Calibri")


def _bullets(doc: Document, items: list[str]) -> None:
    for item in items:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.3
        p.paragraph_format.left_indent = Inches(0.2)
        r = p.add_run(f"•  {item}")
        _set_run_font(r, size_pt=11, color=BODY, name="Calibri")


def _job_block(doc: Document, code: str, name: str, blurb: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(code)
    _set_run_font(r, size_pt=12, bold=True, color=ACCENT, name="Calibri")
    r = p.add_run(f"  ·  {name}")
    _set_run_font(r, size_pt=11, bold=True, color=BODY, name="Calibri")
    _body(doc, blurb, space_before=0, space_after=6)


def _add_color_table(doc: Document) -> None:
    table = doc.add_table(rows=1 + len(BLOCK_LEGEND), cols=3)
    style_table(table)
    fill_header_row(table.rows[0], ["Color", "Destination", "Train"])
    for i, (label, fill, text_hex, dest, blocking) in enumerate(BLOCK_LEGEND, start=1):
        row = table.rows[i]
        fill_swatch_cell(row.cells[0], label, fill_hex=fill, text_hex=text_hex)
        for cell, text in ((row.cells[1], dest), (row.cells[2], blocking)):
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            r = p.add_run(text)
            _set_run_font(r, size_pt=10, color=BODY, name="Calibri")


def _link_line(doc: Document, label: str, url: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.left_indent = Inches(0.2)
    p.paragraph_format.line_spacing = 1.3
    r = p.add_run(f"•  {label}\n     ")
    _set_run_font(r, size_pt=10.5, color=BODY, name="Calibri")
    r = p.add_run(url)
    _set_run_font(r, size_pt=9.5, color=ACCENT, name="Calibri")


def build() -> Path:
    doc = Document()
    _set_comfortable_page(doc)
    _light_masthead(doc)

    # —— Page 1: welcome + place + railroad ——
    _heading(doc, "Welcome", space_before=0)
    _body(
        doc,
        (
            "If this is your first Neville Island session, this primer is "
            "meant to give you the story behind the railroad and a feel for "
            "how a session runs. You do not need to memorize it. At the "
            "session you will get a simple job sheet for whatever you are "
            "assigned—and the Yardmaster and Dispatcher are there to help."
        ),
    )

    _heading(doc, "Neville Island")
    _body(
        doc,
        (
            "Nestled between Pittsburgh and the Chartiers Valley in the Ohio "
            "River lies a five-mile strip of land. Originally called Montour's "
            "Island and later Long Island, it was renamed Neville Island in "
            "honor of Revolutionary War General John Neville. It was once "
            "farmland renowned as the \"Market Basket of Pittsburgh,\" which "
            "all changed at the turn of the century."
        ),
    )
    _body(
        doc,
        (
            "Bridges and an electric street railway opened easy access to the "
            "mainland. American Steel & Wire began the island's first mill in "
            "1900. During World War I the government took land for a munitions "
            "plant. After Pearl Harbor, the Dravo Corporation built ships for "
            "the Navy—and that sealed the island's industrial future."
        ),
    )
    _body(
        doc,
        (
            "Today the 1,200-acre township is a mix of heavy industry, "
            "logistics, and a small residential community. Manufacturing and "
            "chemical plants still work here, alongside cleanup and "
            "redevelopment."
        ),
    )

    # —— Page 2: railroad ——
    _page_break(doc)
    _heading(doc, "The Railroad Today", space_before=0)
    _body(
        doc,
        (
            "From 1899 until January 31, 1994, the Pittsburgh & Ohio Valley "
            "Railway switched the island's furnaces, coke ovens, and "
            "interchange. HART Railroad's Pittsburgh & Chartiers Valley "
            "Division is its successor: we handle the interchange between CSX "
            "and the Pittsburgh & Ohio Central, and we switch the industries "
            "on the island."
        ),
    )
    _body(
        doc,
        (
            "Cars arrive from Demmler / McKeesport on one side and from "
            "Scully / McKees Rocks on the other. South Yard is where those "
            "moves meet—and where most of the sorting gets done."
        ),
    )
    _body(doc, "The industries we work:", space_after=4)
    _bullets(
        doc,
        [
            "Aristech Plastics",
            "A. Stucki Company",
            "Calgon Carbon",
            "Ferrellgas",
            "Kosmos Cement",
            "Shenango Coke Works",
        ],
    )
    _body(
        doc,
        (
            "On the real railroad, CSX's D749 works the island toward Demmler, "
            "and the POHC comes over from McKees Rocks—often waiting for D749 "
            "to clear the trestle over the Ohio. There is scrap, steel, "
            "chemicals, and fuel for the airport. Our session compresses that "
            "into a few overlapping jobs that all share South Yard."
        ),
        space_before=8,
    )

    # —— Page 3: jobs ——
    _page_break(doc)
    _heading(doc, "Jobs on the Board", space_before=0)
    _body(
        doc,
        (
            "Here is the usual crew board for a full session. Exact "
            "assignments are confirmed in the invitation and again at the "
            "briefing."
        ),
        space_after=4,
    )
    for code, name, blurb in JOBS:
        _job_block(doc, code, name, blurb)

    # —— Page 4: colors, scale, session, reading ——
    _page_break(doc)
    _heading(doc, "Destination Colors", space_before=0)
    _body(
        doc,
        (
            "We sort cars by color. Each color is a place—an industry or an "
            "interchange. The same colors show up on switch lists, car cards, "
            "and the yard sheets, so everyone is speaking the same language."
        ),
        space_after=10,
    )
    _add_color_table(doc)

    _heading(doc, "The Track Scale")
    _body(
        doc,
        (
            "Shenango loads a lot of coke, and not every hopper comes out "
            "perfectly. Before those cars leave the island, we weigh them on "
            "the scale at South Yard. Cars that check out continue on their "
            "way. Cars that are too heavy or out of balance go back for a "
            "reload."
        ),
    )
    _body(
        doc,
        (
            "Someone—usually CK1—calibrates the scale before the first weigh "
            "of the session. Without that, the readings start to drift. The "
            "full how-to is on the Scale Operating Instructions sheet (EQ-01) "
            "if you draw that job."
        ),
    )

    _heading(doc, "What to Expect")
    _body(
        doc,
        (
            "Times and food plans are in the invitation. Evening sessions "
            "usually open around 6:30 p.m., with trains from about 7:00 to "
            "10:00. Daytime sessions often start mid-morning with a short "
            "briefing before anyone moves a locomotive."
        ),
    )
    _bullets(
        doc,
        [
            "The house address is in your invitation email",
            "We will cover job assignments and anything unusual at the briefing",
            "You will get a crew sheet for your job; ask if something is unclear",
            "Please let us know early if you cannot make it so we can cover the board",
        ],
    )

    _heading(doc, "If You Want to Dig Deeper")
    _body(
        doc,
        (
            "At the session you may also see yardmaster and dispatcher sheets, "
            "the station map, and the Route 23 timetable. Those are handy "
            "references once trains are rolling—not homework beforehand."
        ),
        space_after=8,
    )
    _body(doc, "A few prototype links, if you are curious:", space_after=4)
    _link_line(
        doc,
        "Pittsburgh & Ohio Valley Railway history",
        "https://www.hartrailroad.com/library/pittsburgh-ohio-valley-railway.html",
    )
    _link_line(
        doc,
        "Pittsburgh & Ohio Central overview",
        "https://www.lundsten.dk/railfan_pa/poc/index.html",
    )
    _link_line(
        doc,
        "Neville Island operations notes",
        "https://railroad.net/post1592461.html#p1592461",
    )
    _link_line(
        doc,
        "Proper balancing of hopper cars",
        "https://www.csx.com/index.cfm/library/files/customers/leads/proper-balancing-of-hopper-cars/",
    )

    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(20)
    rule.paragraph_format.space_after = Pt(12)
    add_horizontal_rule(rule)

    sig = doc.add_paragraph()
    sig.paragraph_format.space_before = Pt(0)
    sig.paragraph_format.space_after = Pt(2)
    r = sig.add_run("Looking forward to having you over.")
    _set_run_font(r, size_pt=11, color=BODY, name="Calibri")

    for line, bold in (
        ("Lee Nevo", True),
        ("Superintendent, Neville Island Operations", False),
        ("HART Railroad  ·  P&CV Division", False),
    ):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(line)
        _set_run_font(
            r,
            size_pt=10.5 if bold else 10,
            bold=bold,
            color=BODY if bold else MUTED,
            name="Calibri",
        )

    # —— Final page: station map ——
    add_station_map_page(doc, page_break=True)

    add_publication_footer(
        doc,
        pub_id=PUBLICATION["pub_id"],
        revision=PUBLICATION["revision"],
        effective=PUBLICATION["effective"],
    )

    CANONICAL.parent.mkdir(parents=True, exist_ok=True)
    doc.save(CANONICAL)
    return CANONICAL


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path}")
