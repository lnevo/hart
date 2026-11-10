#!/usr/bin/env python3
"""Generate archive/docs/HART_STS_Operations_Article.docx."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, RGBColor

OUT = Path(__file__).resolve().parent.parent / "archive" / "docs" / "HART_STS_Operations_Article.docx"


def _set_run_font(run, *, size: float | None = None, bold: bool = False, italic: bool = False):
    run.bold = bold
    run.italic = italic
    run.font.name = "Calibri"
    run.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
    if size is not None:
        run.font.size = Pt(size)


def add_superscript(paragraph, text: str, *, size: float = 9):
    run = paragraph.add_run(text)
    _set_run_font(run, size=size)
    run.font.superscript = True


def title(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.first_line_indent = Inches(0)
    r = p.add_run(text)
    _set_run_font(r, size=16, bold=True)


def deck(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(14)
    p.paragraph_format.first_line_indent = Inches(0)
    r = p.add_run(text)
    _set_run_font(r, size=11, italic=True)


def heading(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.first_line_indent = Inches(0)
    r = p.add_run(text)
    _set_run_font(r, size=13, bold=True)


def body(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Inches(0.2)
    r = p.add_run(text)
    _set_run_font(r, size=11)
    return p


def body_with_cite(doc, parts: list[tuple[str, str | None]]):
    """parts: (text, optional superscript marker)."""
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Inches(0.2)
    for text, cite in parts:
        r = p.add_run(text)
        _set_run_font(r, size=11)
        if cite:
            add_superscript(p, cite)
    return p


def ref(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.first_line_indent = Inches(0)
    r = p.add_run(text)
    _set_run_font(r, size=10)


def generate(output: Path = OUT) -> Path:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)
    section.top_margin = Inches(0.85)
    section.bottom_margin = Inches(0.85)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
    normal.paragraph_format.space_after = Pt(9)
    normal.paragraph_format.line_spacing = 1.2

    title(doc, "Setting Up Car Movement on the HART Railroad")
    deck(
        doc,
        "Building repeatable session traffic with STS on a Pittsburgh-area ops layout · July 2026",
    )

    body(
        doc,
        "My layout is the HART Railroad, Pittsburgh & Chartiers Valley Division — a "
        "Pittsburgh-area shortline centered on Neville Island. It interchanges with "
        "CSX and POHC and works mainland staging and yards at Scully, Demmler, "
        "McKees Rocks, and McKeesport. On the island are the industries crews switch — "
        "Aristech Plastics, Calgon Carbon, A Stucki Co, Ferrel Gas, and Kosmos Cement — "
        "plus South Yard for classification and interchange. Nearby, Shenango Coke "
        "Works loads coke for steel customers such as U.S. Steel. The goal was simple: "
        "operations that feel like a real railroad, not a pile of car cards.",
    )

    heading(doc, "From Post-its to STS")
    body(
        doc,
        "Before any traffic software, the first problem was physical: I needed car "
        "cards and waybills for HART. For the first session we used Post-it flags — "
        "obviously temporary. I already had roster data for the fleet, and I used AI "
        "to help build the cards, matching photos to that roster by running OCR on "
        "the images and comparing reporting marks. The same pass also pulled stencil "
        "data off the cars — built dates and weights among them — and drafted "
        "waybill-side information for the industries and moves on the layout: rolling "
        "stock, locations, commodities, and the shipments that tie them together.",
    )
    body_with_cite(
        doc,
        [
            (
                "When it came time to pick a traffic system, the choice was STS — the "
                "Shipper-driven Traffic Simulator",
                "1",
            ),
            (
                " — rather than JMRI Operations Pro. STS matched how the prototype "
                "moves cars: shippers create demand, the railroad fills it with cars, "
                "and the paperwork follows the move. It could already generate traffic, "
                "build lists, and support a multi-session railroad, so HART could build "
                "on that foundation instead of starting from scratch. The card and "
                "waybill data became the seed — shipments, commodities, locations, and "
                "the car roster — so the digital railroad matched the paper we had "
                "started. That work carried forward: today we still use the refined "
                "data coming back out of STS to manage our waybills.",
                None,
            ),
        ],
    )

    heading(doc, "An Ops Desk You Can Read")
    body(
        doc,
        "Once STS held the HART data, the next gaps showed up at the desk. I needed "
        "to know what was going on as I went through a session, and it was hard to "
        "tell without digging through screens. Filling car orders still meant too "
        "much manual assignment when the matches were obvious. And generate, fill, "
        "pick up, and set out took too many clicks — more like four separate "
        "clipboards than one train sheet.",
    )
    body(
        doc,
        "So I put live session stats on the operations menu and cleaned up the ops "
        "dashboard. The biggest day-to-day win was auto-assign on Fill Car Orders: "
        "STS can match cars to open orders in bulk, including reposition empties that "
        "used to get skipped. Around that, I reworked the operations layout and menu "
        "navigation so those pages flowed better, with filtering and counts added in "
        "the dropdowns. The Cars database page got a matching overhaul.",
    )

    heading(doc, "Building the Track Scale")
    body(
        doc,
        "I wanted something unique on HART: weighing cars mid-move, not just at "
        "origin or destination. The stencil weights we had already pulled for the "
        "car cards suddenly had somewhere to go. The first session tried dice on the "
        "aisle to simulate a scale — random enough, but it never caught on with the "
        "operators.",
    )
    body_with_cite(
        doc,
        [
            (
                "What I wanted in STS was that mid-shipment decision: coke leaves "
                "Shenango, hits the South Yard scale on the west lead, and either "
                "continues outbound or comes back to reload. STS had no native way to "
                "do that, and I did not want a HART-only feature hard-wired into core, "
                "so I built it as a plugin",
                "2",
            ),
            (".", None),
        ],
    )
    body(
        doc,
        "Calibration became its own step in the recipe, and that mattered more than "
        "I expected. The scale drifts between sessions unless you recalibrate. Skip "
        "it and more cars fall out of tolerance and route to reload; calibrate every "
        "session and weighing stays steady, so reload work stays intentional.",
    )
    body_with_cite(
        doc,
        [
            (
                "We did not have AAR General Information Bulletin No. 5 on proper "
                "hopper balance",
                "3",
            ),
            (
                " when we built this. Finding it later confirmed the same idea: "
                "overloaded and unbalanced cars are unsafe, railroads catch them on "
                "the scale, and bad loads get switched out to reload. What we put on "
                "HART was not just a layout novelty — it represents a real-world "
                "operation.",
                None,
            ),
        ],
    )

    heading(doc, "After Session #2: A Session Recipe")
    body(
        doc,
        "We ran STS on the layout for the first time during Session #2. On paper and "
        "in the simulator, things went well. In the aisle we learned choreography the "
        "virtual railroad could not fully capture — which jobs overlap, who waits on "
        "whom, when a train can leave South Yard or clear the bridge, and how Island "
        "locals and mainland staging actually share the railroad. On a still-new "
        "layout, that made it clear: the next session could not depend on remembering "
        "every click and timing cue.",
    )
    body(
        doc,
        "Reproducing a session in STS still meant working through generate, fill, "
        "assign, switch lists, and reports by hand. Miss a step and the paperwork "
        "diverged. Fine for occasional play; not fine for tuning traffic or handing "
        "someone else a repeatable ops package.",
    )
    body(
        doc,
        "So I built a workflow editor and paired it with a Session Browser. The "
        "editor saves the session as a recipe — generate, fill, assign, cancel, "
        "switch lists, reports, and optional scale steps — with parameters I can see "
        "and reorder. That recipe was key for choreography: jobs overlap where they "
        "share the railroad, yet each can still run independently when the crew board "
        "or schedule calls for it. Traffic settings live there too: new orders per "
        "session, when automatic generate should pause on a high unfilled backlog, "
        "which commodities stay out of the automatic lottery on their own gated "
        "steps, and the if/then gates for coke. The Session Browser is where I open "
        "what the recipe produced — overview, trains, switch lists, waybills, and "
        "reports — including printing filters and locked backups so a good baseline "
        "does not get restarted by accident.",
    )

    heading(doc, "Proper Balance of Cars")
    body(
        doc,
        "Even with a saved recipe, the traffic still had to feel right — and for a "
        "while it did not. We were seeing too many orders, yards that got stuck, and "
        "cars that were not moving the way we expected. The roster is slim; there was "
        "no spare fleet to throw at every industry. Tuning meant maximizing what we "
        "own: cars earning their keep, work spread across jobs, and steady movement "
        "instead of a few cars bouncing back and forth.",
    )
    body(
        doc,
        "That meant watching the whole cycle — empty reassignments, pending orders, "
        "loads and unloads — not just how many new orders appeared. Flood the "
        "railroad and the yardmaster drowns; starve it and crews stand around with "
        "thin lists. Coke was the sharp case: run wild and it crowds everything else; "
        "starve it and the Island and Shenango story goes flat. Operator interest "
        "lives in the middle — every job still has a reason to be there.",
    )

    heading(doc, "Simulate, Score, Adjust")
    body_with_cite(
        doc,
        [
            (
                "Comparing settings by hand was never going to work. Each idea needed "
                "many simulated sessions, a fair starting point, and a way to see "
                "whether the railroad got better or quietly worse somewhere else. The "
                "workflow became a partnership: I set the goals and judged what felt "
                "right for HART; an AI coding assistant ran the heavy iteration — "
                "restoring locked baselines, replaying recipes, sweeping gates and "
                "intervals, scoring results, and looping again when a fix for one "
                "commodity pushed pressure onto another — using the HART simulation "
                "and seed tooling we keep alongside STS",
                "4",
            ),
            (".", None),
        ],
    )
    body(
        doc,
        "We did not chase maximum volume. After each multi-session sweep we asked "
        "whether backlog stayed stable; whether coke and other priority moves still "
        "worked when gated; whether empties and scale work dried up; and whether "
        "later sessions still looked operable. When two settings looked similar on "
        "counts, we kept the one closer to how HART clears. Priority stayed "
        "practical: backlog first, gated commodities next, then empties, scale "
        "reloads, and job order.",
    )
    body(
        doc,
        "The campaign was large — many scenarios of ten to twenty sessions each, "
        "often across several random seeds. That adds up to hundreds of simulated "
        "operating sessions, and likely past a thousand with re-runs: more than a "
        "person can fairly compare at the keyboard, but a natural fit for a "
        "simulate–score–adjust loop. The saved recipe and locked baselines made "
        "those comparisons honest.",
    )

    heading(doc, "Where We Stand")
    body(
        doc,
        "The through-line was never the software for its own sake. It was turning a "
        "new railroad and a slim roster into sessions crews want to work — from "
        "Post-it flags and paper cards, through STS and the tools we built around it, "
        "to traffic that stays interesting without flooding the aisle.",
    )
    body(
        doc,
        "Along the way I have learned a lot — about railroading, about operations, "
        "and about AI. What we achieved here took a few weeks of focused work; "
        "without these tools it could easily have taken months, if not longer. I am "
        "amazed at what I can do with them, and I look forward to how they will keep "
        "improving the work I do for the layout.",
    )
    body(
        doc,
        "Ahead, the job is still to keep operating and keep listening. Future "
        "sessions will show what still snags a crew and where the traffic still "
        "needs a nudge. The measure of success stays simple: every operator who "
        "shows up should find interesting work, clear paper, and a railroad that "
        "feels a little more real than the session before.",
    )

    heading(doc, "References")
    ref(
        doc,
        "1. Shipper-driven Traffic Simulator (STS) Facebook group (official community "
        "/ support): https://www.facebook.com/groups/541367466453352/",
    )
    ref(
        doc,
        "2. HART / STS Docker packaging and Track Scale plugin work (GitHub): "
        "https://github.com/lnevo/sts-docker",
    )
    ref(
        doc,
        "3. Association of American Railroads, Operations and Maintenance Department, "
        "Damage Prevention and Freight Claim Services. General Information Bulletin "
        "No. 5, Proper Balancing of Hopper Cars — Overloaded or Unbalanced Hopper "
        "Cars Are Unsafe. Washington, D.C., August 1993. Available at: "
        "https://www.csx.com/index.cfm/library/files/customers/leads/"
        "proper-balancing-of-hopper-cars",
    )
    ref(
        doc,
        "4. HART STS helpers, seed, and simulation tooling (GitHub): "
        "https://github.com/lnevo/sts-docker-helpers",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    # Avoid stomping a Word lock file if present; write then replace.
    tmp = output.with_suffix(".tmp.docx")
    doc.save(tmp)
    tmp.replace(output)
    return output


if __name__ == "__main__":
    path = generate()
    print(f"Wrote {path}")
