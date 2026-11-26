#!/usr/bin/env python3
"""Write the wiring schematic deck, docs/wiring/Wiring_Schematic.pptx.

- Slide 1: every client node (C{radio address}) with its board and block counts.
- Slide 2: the turnouts, one row per JMRI turnout, in two tables.
- Then one slide per client node: its output boards on the left, its input boards and blocks on the right.

It reads the inventory's sheets as write_inventory.py builds them in memory from the wiring model (the device master,
hartlib.wiring's wiring.csv, lcos_nodes.csv and signal_head_plan.csv), the same sheets it saves as
LCOS_Layout_Inventory_v86.xlsx. The workbook file is an output only: this script never opens it (ADR-039).

    python3 tools/wiring/create_wiring_schematic_ppt.py [--out PATH]    # needs python-pptx
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

import write_inventory  # tools/wiring/, the script's own folder: the wiring model's inventory sheets

OUT = Path(__file__).resolve().parents[2] / "docs" / "wiring" / "Wiring_Schematic.pptx"
BLANK = 6                                   # the default template's blank slide layout
UNNUMBERED = 999                            # sorts a node ID without a number after every numbered one
HEADER_FILL = RGBColor(68, 114, 196)        # blue: table headers and output boards
INPUT_FILL = RGBColor(112, 173, 71)         # green: input boards
BLOCK_FILL = RGBColor(237, 125, 49)         # orange: the blocks table
STRIPE_FILL = RGBColor(242, 242, 242)       # every second data row
WHITE = RGBColor(255, 255, 255)
PORTS_PER_BOARD = 8
MIDDLE = 1                                  # MSO_ANCHOR.MIDDLE
SUMMARY_HEADERS = ("Node ID", "Location", "Radio Address", "12V Boards", "5V Boards", "Input Boards", "Num Blocks")
TURNOUT_HEADERS = ("Turnout", "Node", "Button", "Feedback", "Signals")
TURNOUT_WIDTHS = (0.7, 0.5, 0.9, 1.4, 1.0)  # inches; they add up to the table's 4.5
# a node slide's six table places, (x, y) in inches: left column top to bottom, then the right column
SECTION_W, SECTION_H = 4.5, 1.7
LEFT_X, RIGHT_X = 0.5, 0.5 + SECTION_W + 0.2
ROWS_Y = (1.0, 3.09, 5.27)


class WiringDeckError(Exception):
    """A sheet of the in-memory inventory lacks a column this deck reads; the message names the sheet and column."""


@dataclass(frozen=True)
class NodeSummary:
    node_id: str
    location: str
    address: str
    boards_12v: int
    boards_5v: int
    num_blocks: int


@dataclass
class NodeBoards:
    """One client node's boards: board ID -> {port number: device text}, and its block ports."""
    outputs: dict[str, dict[int, str]] = field(default_factory=dict)
    inputs: dict[str, dict[int, str]] = field(default_factory=dict)
    blocks: list[tuple[str, str]] = field(default_factory=list)       # (port ID, block section name)


@dataclass
class TurnoutRow:
    turnout: str
    node: str
    button: str
    feedback: str
    signals: list[str]


Record = dict[str, object]


def records(ws: object, sheet: str, needed: Sequence[str]) -> list[Record]:
    """A sheet's data rows as {header: value}; WiringDeckError when a needed header is missing."""
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0]) if rows else []
    missing = [h for h in needed if h not in headers]
    if missing:
        raise WiringDeckError(f"sheet {sheet!r} has no column {', '.join(map(repr, missing))}")
    return [dict(zip(headers, row)) for row in rows[1:]]


def node_number(node_id: str) -> int:
    """C12 -> 12; a node ID without a number after C sorts last."""
    return int(node_id[1:]) if node_id[1:].isdigit() else UNNUMBERED


def split_port(port: object) -> tuple[str, int] | None:
    """'C3-OU1-1' -> ('C3-OU1', 1); None for a port ID of fewer than three parts or a port that is not a number."""
    parts = str(port).split("-")
    if len(parts) < 3 or not parts[2].isdigit():
        return None
    return f"{parts[0]}-{parts[1]}", int(parts[2])


def _count(value: object) -> int:
    return int(value) if value else 0


def collect_nodes(wb: object) -> tuple[list[NodeSummary], dict[str, NodeBoards]]:
    """The client nodes in node-number order, and each one's boards and blocks."""
    summaries: dict[str, NodeSummary] = {}
    boards: dict[str, NodeBoards] = {}
    for row in records(wb["Nodes"], "Nodes", ("Node ID", "Location", "Address", "12V Boards", "5V Boards",
                                               "Num Blocks")):
        node_id = row["Node ID"]
        if not node_id or not str(node_id).startswith("C"):
            continue
        summaries[node_id] = NodeSummary(node_id, str(row["Location"] or "N/A"), str(row["Address"] or "N/A"),
                                         _count(row["12V Boards"]), _count(row["5V Boards"]), _count(row["Num Blocks"]))
        boards[node_id] = NodeBoards()
    for sheet, port_col, attr in (("DNOU8", "Output Port ID", "outputs"), ("DNIN8", "Input Port ID", "inputs")):
        for row in records(wb[sheet], sheet, ("Parent Node ID", port_col, "Connected Device")):
            node, port, device = row["Parent Node ID"], row[port_col], row["Connected Device"]
            place = split_port(port) if node in boards and port else None
            if place and place[1]:
                getattr(boards[node], attr).setdefault(place[0], {})[place[1]] = str(device).strip() if device else ""
    for row in records(wb["BlockSensors"], "BlockSensors", ("Node ID", "Port ID", "Block Section Name")):
        node, port, block = row["Node ID"], row["Port ID"], row["Block Section Name"]
        if node in boards and port and block and str(block).strip():
            boards[node].blocks.append((str(port), str(block).strip()))
    order = sorted(summaries, key=node_number)
    return [summaries[n] for n in order], boards


def collect_turnouts(wb: object) -> list[TurnoutRow] | None:
    """One row per JMRI turnout, sorted by node number then turnout; a crossover's two half rows (one JMRI turnout,
    labelled by OS block) are one row with both halves' signals. None when the inventory has no TurnoutSummary."""
    if "TurnoutSummary" not in wb.sheetnames:
        return None
    signal_cols = ("Entry Signal", "Normal Exit Signal", "Reverse Exit Signal")
    rows = records(wb["TurnoutSummary"], "TurnoutSummary",
                   ("JMRI Turnout", "Parent Node", "Button", "Feedback N", "Feedback R", *signal_cols))
    by_turnout: dict[str, TurnoutRow] = {}
    for row in rows:
        turnout = row["JMRI Turnout"]
        if not turnout:
            continue
        signals = [str(row[c]) for c in signal_cols if row[c]]
        held = by_turnout.get(str(turnout))
        if held:
            held.signals += [s for s in signals if s not in held.signals]
            continue
        feedback = [f"{side}:{row[col]}" for side, col in (("N", "Feedback N"), ("R", "Feedback R")) if row[col]]
        node = row["Parent Node"]
        by_turnout[str(turnout)] = TurnoutRow(str(turnout), str(node) if node else "",
                                              str(row["Button"]) if row["Button"] else "", ", ".join(feedback), signals)
    out = list(by_turnout.values())
    out.sort(key=lambda t: (node_number(t.node) if t.node.startswith("C") else UNNUMBERED, t.turnout))
    return out


# ---------------------------------------------------------------- slides

def title(slide: object, text: str, top: float, height: float, size: int) -> None:
    frame = slide.shapes.add_textbox(Inches(0.5), Inches(top), Inches(9), Inches(height)).text_frame
    frame.text = text
    frame.paragraphs[0].font.size = Pt(size)
    frame.paragraphs[0].font.bold = True


def grid(slide: object, headers: Sequence[str], rows: Sequence[Sequence[str]], x: float, y: float, w: float, h: float,
         header_pt: int, body_pt: int, widths: Sequence[float] = ()) -> None:
    """A table with a blue header row and striped data rows."""
    table = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(x), Inches(y), Inches(w), Inches(h)).table
    for col, text in enumerate(headers):
        cell = table.cell(0, col)
        cell.text = text
        cell.fill.solid()
        cell.fill.fore_color.rgb = HEADER_FILL
        para = cell.text_frame.paragraphs[0]
        para.font.color.rgb = WHITE
        para.font.bold = True
        para.font.size = Pt(header_pt)
    for col, inches in enumerate(widths):
        table.columns[col].width = Inches(inches)
    for idx, values in enumerate(rows, 1):
        for col, text in enumerate(values):
            table.cell(idx, col).text = text
        for col in range(len(headers)):
            cell = table.cell(idx, col)
            cell.text_frame.paragraphs[0].font.size = Pt(body_pt)
            if idx % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = STRIPE_FILL


def summary_slide(prs: object, nodes: Sequence[NodeSummary], boards: dict[str, NodeBoards]) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[BLANK])
    title(slide, "Wiring Schematic - Node Summary", 0.3, 0.8, 32)
    rows = [(n.node_id, n.location, n.address, str(n.boards_12v), str(n.boards_5v),
             str(len(boards[n.node_id].inputs)), str(n.num_blocks)) for n in nodes]
    grid(slide, SUMMARY_HEADERS, rows, 0.5, 1.5, 9, 5.5, 12, 10)


def turnout_slide(prs: object, turnouts: Sequence[TurnoutRow]) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[BLANK])
    title(slide, "Turnout Summary", 0.3, 0.8, 32)
    rows = [(t.turnout, t.node, t.button, t.feedback, ", ".join(t.signals)) for t in turnouts]
    half = (len(rows) + 1) // 2
    for x, part in ((0.32, rows[:half]), (5.18, rows[half:])):
        grid(slide, TURNOUT_HEADERS, part, x, 1.41, 4.5, 5.5, 9, 8, TURNOUT_WIDTHS)


def port_table(slide: object, place: tuple[float, float], heading: str, fill: RGBColor,
               rows: Sequence[tuple[str, str]], body_rows: int) -> None:
    """A two-column table under a merged coloured heading row, with `body_rows` rows below it."""
    table = slide.shapes.add_table(body_rows + 1, 2, Inches(place[0]), Inches(place[1]),
                                   Inches(SECTION_W), Inches(SECTION_H)).table
    head = table.cell(0, 0)
    head.text = heading
    head.merge(table.cell(0, 1))
    para = head.text_frame.paragraphs[0]
    para.font.bold = True
    para.font.size = Pt(10)
    para.alignment = PP_ALIGN.CENTER
    head.fill.solid()
    head.fill.fore_color.rgb = fill
    para.font.color.rgb = WHITE
    for idx, (left, right) in enumerate(rows, 1):
        table.cell(idx, 0).text = left
        table.cell(idx, 1).text = right
        for col in range(2):
            cell = table.cell(idx, col)
            para = cell.text_frame.paragraphs[0]
            para.font.size = Pt(8)
            cell.vertical_anchor = MIDDLE
            para.space_after = Pt(0)
            para.space_before = Pt(0)
            para.line_spacing = 0.9


def board_rows(board_id: str, ports: dict[int, str]) -> list[tuple[str, str]]:
    return [(f"{board_id}-{p}", ports.get(p, "")) for p in range(1, PORTS_PER_BOARD + 1)]


def node_slide(prs: object, node: NodeSummary, boards: NodeBoards, continued: bool) -> None:
    """Titles use the radio-address node ID only; the inventory's Legacy Node ID column is not printed."""
    slide = prs.slides.add_slide(prs.slide_layouts[BLANK])
    title(slide, f"Node {node.node_id} - {node.location}" + (" (cont'd)" if continued else ""), 0.2, 0.6, 28)
    left = [(LEFT_X, y) for y in ROWS_Y]
    right = [(RIGHT_X, y) for y in ROWS_Y]
    for place, board_id in zip(left, sorted(boards.outputs)):
        port_table(slide, place, board_id, HEADER_FILL, board_rows(board_id, boards.outputs[board_id]), PORTS_PER_BOARD)
    inputs = sorted(boards.inputs)
    for place, board_id in zip(right, inputs):
        port_table(slide, place, board_id, INPUT_FILL, board_rows(board_id, boards.inputs[board_id]), PORTS_PER_BOARD)
    if boards.blocks and len(inputs) < len(right):
        blocks = sorted(boards.blocks, key=lambda b: b[0])[:PORTS_PER_BOARD]
        port_table(slide, right[len(inputs)], f"{node.node_id} Blocks", BLOCK_FILL, blocks, len(blocks))


def build_deck(nodes: Sequence[NodeSummary], boards: dict[str, NodeBoards],
               turnouts: Sequence[TurnoutRow] | None) -> object:
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(7.5)
    summary_slide(prs, nodes, boards)
    if turnouts is not None:
        turnout_slide(prs, turnouts)
    previous = None
    for node in nodes:
        node_slide(prs, node, boards[node.node_id], continued=previous is not None and node.location == previous)
        previous = node.location
    prs.core_properties.author = ""             # the repo is public: no personal names in the file's metadata
    prs.core_properties.last_modified_by = ""
    return prs


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write Wiring_Schematic.pptx from the wiring model.")
    ap.add_argument("--out", type=Path, default=OUT, help="where the deck goes")
    args = ap.parse_args(None if argv is None else list(argv))
    print(f"Using the wiring model (the sheets of {write_inventory.OUT.name}, built in memory)")
    try:
        wb = write_inventory.workbook()
        nodes, boards = collect_nodes(wb)
        turnouts = collect_turnouts(wb)
    except (write_inventory.FactsError, WiringDeckError) as exc:     # bad wiring data: one line, as write_inventory.py
        print(f"{Path(__file__).name}: {exc}", file=sys.stderr)
        return 2
    prs = build_deck(nodes, boards, turnouts)
    prs.save(args.out)
    print(f"Saved {args.out}: {len(prs.slides)} slides, {len(nodes)} of them one per client node")
    return 0


if __name__ == "__main__":
    sys.exit(main())
