"""OOXML cell and table helpers shared by the card pipeline and the publications.

python-docx has no API for cell shading, exact cell widths in twips, cell margins, exact row heights or nil table
borders, so these write the WordprocessingML elements directly. card_pipeline reaches this module through car_paths, which puts
publications/ on sys.path.
"""
from __future__ import annotations

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.oxml.table import CT_TcPr
from docx.table import Table, _Cell, _Row


def tc_pr(cell: _Cell) -> CT_TcPr:
    """The cell's w:tcPr, created when missing."""
    return cell._tc.get_or_add_tcPr()


def shade_cell(cell: _Cell, fill: str, *, auto_color: bool = False) -> None:
    """Append a solid w:shd fill (RRGGBB hex) to the cell.

    auto_color also writes w:color="auto". The attributes keep the order each document has always written, so the
    generated XML stays the same: fill, val without the colour; val, color, fill with it.
    """
    if len(fill) != 6:
        raise ValueError(f"cell fill must be RRGGBB hex, got {fill!r}")
    el = OxmlElement("w:shd")
    if auto_color:
        el.set(qn("w:val"), "clear")
        el.set(qn("w:color"), "auto")
        el.set(qn("w:fill"), fill)
    else:
        el.set(qn("w:fill"), fill)
        el.set(qn("w:val"), "clear")
    tc_pr(cell).append(el)


def set_cell_width(cell: _Cell, twips: int) -> None:
    """Set the cell's one w:tcW to an exact width in twips, replacing any width python-docx wrote."""
    pr = tc_pr(cell)
    el = pr.find(qn("w:tcW"))
    if el is None:
        el = OxmlElement("w:tcW")
        pr.append(el)
    el.set(qn("w:w"), str(twips))
    el.set(qn("w:type"), "dxa")


def set_cell_margins(cell: _Cell, *, top: int = 0, left: int = 0, bottom: int = 0, right: int = 0) -> None:
    """Replace the cell's w:tcMar with these margins in twips."""
    pr = tc_pr(cell)
    old = pr.find(qn("w:tcMar"))
    if old is not None:
        pr.remove(old)
    el = OxmlElement("w:tcMar")
    for side, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        s = OxmlElement(f"w:{side}")
        s.set(qn("w:w"), str(val))
        s.set(qn("w:type"), "dxa")
        el.append(s)
    pr.append(el)


def set_row_height(row: _Row, height_pt: float) -> None:
    """Replace the row's w:trHeight with an exact height in points (whole twips, rounded down)."""
    tr_pr = row._tr.get_or_add_trPr()
    old = tr_pr.find(qn("w:trHeight"))
    if old is not None:
        tr_pr.remove(old)
    el = OxmlElement("w:trHeight")
    el.set(qn("w:val"), str(int(height_pt * 20)))
    el.set(qn("w:hRule"), "exact")
    tr_pr.append(el)


def clear_table_borders(table: Table) -> None:
    """Append a w:tblBorders that sets all six edges to nil (size 0, colour auto)."""
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "auto")
        borders.append(el)
    table._tbl.tblPr.append(borders)
