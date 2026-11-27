"""build_cats_panel.py's dress step: the frozen header and plate put on the generated document, the ABS twin's
words, and the desk's label clashes."""
import copy
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

from cats_panel_facts import CatsPanelError
from hartlib import paths

HEADER = paths.CATS_DIR / "data/generated_desk_header.xml"   # frozen from the live desk
# The ABS twin: every CTC block ABS, and the plate's words (the hand-wired ABS desk's)
ABS_PLATE = {"CTC DIGICON": "ABS DIGICON", "DS-CTC": "DS-ABS"}
# The live desk's top-level order (HART_CTC.xml); the plugin's ROWWRAPTAG follows COMPRESSIONTAG
ORDER = ("FONTDEFINITION", "LINE", "COUNTER", "SIGNALTEMPLATE", "TRAINSTORE", "JOBSTORE", "CREWSTORE",
         "COLORDEFINITION", "TRAINSTATLABEL", "COMPRESSIONTAG", "ROWWRAPTAG", "OPERATIONS", "JMRINAME", "TRACKPLAN")
PLATE_PX = {"FONT_SUBTITLE": (9, 15)}   # pixels per character, line height, for plate fonts the plugin does not size
LABEL_GAP_PX = 6                         # the clear space a plate keeps from every other label
OS_SWITCH = re.compile(r"OS Switch (\d+)[a-d]?")   # a staging plant's OS block, its switch number in group 1

Cell = tuple[int, int]          # a desk cell: (column, row)
Fit = tuple[int, int]           # the desk window in cells: (columns, rows)


class Box(NamedTuple):
    """A label's extent in pixels, as the plugin's cats_px.frill_box gives it."""
    left: int
    top: int
    right: int
    bottom: int

    def near(self, other: "Box", gap: int = LABEL_GAP_PX) -> bool:
        """True when the two boxes overlap or come within `gap` pixels side to side."""
        return (other.top < self.bottom and self.top < other.bottom
                and other.left < self.right + gap and self.left < other.right + gap)


class Label(NamedTuple):
    """A desk label: the cell it is written in and its box."""
    cell: Cell
    box: Box


def frozen_header(path: Path = HEADER) -> tuple[list[ET.Element], list[ET.Element]]:
    """The template's elements (comments left out) and the plate SECTIONs of its TRACKPLAN."""
    root = ET.parse(path).getroot()
    if root.tag != "DOCUMENT":
        raise CatsPanelError(f"{path}: not a CATS panel template (its root is {root.tag})")
    els = [el for el in root if isinstance(el.tag, str)]
    bad = sorted({el.tag for el in els} - set(ORDER))
    if bad:
        raise CatsPanelError(f"{path}: elements {', '.join(bad)} are not header elements ({', '.join(ORDER)})")
    lacking = [t for t in ("SIGNALTEMPLATE", "JMRINAME") if not any(el.tag == t for el in els)]
    if lacking:
        raise CatsPanelError(f"{path}: no {' or '.join(lacking)} elements; the staging bindings' masts and IOSPECs "
                         "need them")
    plan = root.find("TRACKPLAN")
    return [el for el in els if el.tag != "TRACKPLAN"], list(plan) if plan is not None else []


def plate_box(cats: ModuleType, cell: Cell, loc: str, text: str, font: str) -> Box:
    """The box of label `text` in `font` at `loc` in `cell` (`cats`: the plugin's CATS module, its pixel sizes)."""
    per, h = PLATE_PX.get(font) or cats.TEXT_PX.get(font, cats.TEXT_PX["FONT_LABEL"])
    return Box(*cats.frill_box(cell, loc, per * len(text) + 4, h))


def _name_box(cats: ModuleType, cell: Cell, name: ET.Element) -> Box:
    """plate_box of a SEC_NAME element's text."""
    return plate_box(cats, cell, name.get("LOC_NAME", ""), name.get("NAME", ""), name.get("FONT_NAME", ""))


def _cell(sec: ET.Element) -> Cell:
    """A SECTION's cell; CatsPanelError when it has no whole-number X and Y."""
    try:
        return int(sec.get("X", "")), int(sec.get("Y", ""))
    except ValueError as exc:
        raise CatsPanelError(f"a desk SECTION has X {sec.get('X')!r}, Y {sec.get('Y')!r}: not a cell") from exc


def right_edge(cats: ModuleType, fit: Fit) -> int:
    """The x, in pixels, no desk label may run past: the `fit` columns and one more, as dress keeps the frozen
    plate and station_plates the control point plates."""
    return (fit[0] + 1) * cats.GRID_PX


PLATE_FONT, PLATE_LOC = "FONT_CP", "LOWCENT"     # a control point plate, as the hand-built desk wrote them


def station_plates(cats: ModuleType, root: ET.Element, stations: Iterable[tuple[str, Sequence[str]]],
                   used: MutableMapping[Cell, ET.Element | None], boxes: list[Label],
                   fit: Fit) -> list[tuple[str, Cell]]:
    """[(text, cell)] of the control point plates (`stations`: [(name, switch numbers)] of stations.csv's desk_plate
    rows, read_stations), each the station's name in capitals in the free cell nearest the plant cells of its
    switches (digicon_trace.desk_plants: the bound staging plants), ties to the cell above, then to the left. A cell
    is free when no section uses it, nor any cell the plate's label spans, and the label is clear of every other label
    (`boxes`) by 6 px and inside the window (`fit` rows, right_edge): the desk never grows. CatsPanelError naming the station when one has
    no plant on the desk or no free cell. `used`: {cell: section} of the desk, `boxes`: [(cell, box)] of its labels,
    both added to."""
    import digicon_trace as trace          # cats/scripts, on build_cats_panel's path
    cells = trace.track_cells(root.find("TRACKPLAN"))
    from hartlib import devices, tables_build
    plants = trace.desk_plants(cells, bound=True, level_turnouts=tables_build.level_turnouts(r.cells() for r in devices.load()))
    out = []
    for name, switches in stations:
        mine = [xy for os_name, xy in plants.items()
                if (m := OS_SWITCH.fullmatch(os_name)) and m.group(1) in switches]
        if not mine:
            raise CatsPanelError(f"stations.csv: {name}'s plate: none of its switches ({', '.join(switches)}) has a "
                             "plant on the desk")
        centre = sum(x for x, _ in mine) / len(mine), sum(y for _, y in mine) / len(mine)
        text = name.upper()
        found = _free_cell(cats, text, centre, used, boxes, fit)
        if found is None:
            raise CatsPanelError(f"stations.csv: no free cell on the desk for {name}'s plate {text!r} (the desk keeps "
                             f"its {fit[0]} x {fit[1]} cells)")
        used[found.cell] = None
        boxes.append(found)
        out.append((text, found.cell))
    return out


def _free_cell(cats: ModuleType, text: str, centre: tuple[float, float], used: Mapping[Cell, ET.Element | None],
               boxes: Sequence[Label], fit: Fit) -> Label | None:
    """The plate label `text` in the free cell of the `fit` window nearest `centre` (ties to the cell above, then to
    the left; free as station_plates says), or None when no cell is free."""
    cx, cy = centre
    cols, rows = fit
    taken = set(used)
    for cell in sorted(((x, y) for x in range(cols) for y in range(rows)),
                       key=lambda c: ((c[0] - cx) ** 2 + (c[1] - cy) ** 2, c[1], c[0])):
        box = plate_box(cats, cell, PLATE_LOC, text, PLATE_FONT)
        spans = {(x, cell[1]) for x in range(box.left // cats.GRID_PX, (box.right - 1) // cats.GRID_PX + 1)}
        if box.left < 0 or box.right > right_edge(cats, fit) or spans & taken:
            continue
        if any(box.near(other.box) for other in boxes):
            continue
        return Label(cell, box)
    return None


def dress(cats: ModuleType, root: ET.Element, header: Sequence[ET.Element], plate: Iterable[ET.Element],
          desk: str, fit: Fit, stations: Iterable[tuple[str, Sequence[str]]] | None = None) -> str:
    """The generated document `root` with the frozen header and the plate: the template's fonts the plugin does
    not write (its own keep their values), the template's other elements in place of the plugin's copies, every
    element in the live desk's order, and the plate's labels on free cells of their row, clear of each other and of
    the labels there, within the `fit` columns; then each control point plate of `stations` (station_plates).
    desk "ABS": every CTC block ABS and the plate's ABS words."""
    _merge_header(root, header)
    tp = root.find("TRACKPLAN")
    if tp is None:
        raise CatsPanelError("the generated desk has no TRACKPLAN")
    where: dict[Cell, ET.Element | None] = {_cell(sec): sec for sec in tp.findall("SECTION")}
    boxes = []
    for sec in tp.findall("SECTION"):
        n = sec.find("SEC_NAME")
        if n is not None:
            cell = _cell(sec)
            boxes.append(Label(cell, _name_box(cats, cell, n)))
    for sec in plate:
        _place_plate(cats, copy.deepcopy(sec), desk, fit, where, boxes)
    for text, cell in station_plates(cats, root, stations or [], where, boxes, fit):
        sec = ET.Element("SECTION", X=str(cell[0]), Y=str(cell[1]))
        ET.SubElement(sec, "SEC_NAME", LOC_NAME=PLATE_LOC, NAME=text, FONT_NAME=PLATE_FONT)
        where[cell] = sec
    _restack(tp, where)
    if desk == "ABS":
        for b in root.iter("BLOCK"):
            if b.get("DISCIPLINE") == "CTC":
                b.set("DISCIPLINE", "ABS")
    ET.indent(root, "  ")
    return "<?xml version='1.0' encoding='UTF-8'?>\n" + ET.tostring(root, encoding="unicode") + "\n"


def _merge_header(root: ET.Element, header: Sequence[ET.Element]) -> None:
    """Put `header`'s elements in `root` in place of the plugin's copies, in the live desk's ORDER: a header font
    the plugin also writes keeps the plugin's element, every other header element is a copy. CatsPanelError on an
    element ORDER does not place."""
    fonts = {el.get("FONTKEY"): el for el in root.findall("FONTDEFINITION")}
    taken = {el.tag for el in header}           # a tag the header supplies replaces the plugin's copies
    kids = [el for el in root if el.tag != "FONTDEFINITION"]
    for el in list(root):
        root.remove(el)
    picked = []
    for el in header:
        if el.tag == "FONTDEFINITION":
            own = fonts.pop(el.get("FONTKEY"), None)       # an Element with no children is falsy: test for None
            picked.append(own if own is not None else copy.deepcopy(el))
        else:
            picked.append(copy.deepcopy(el))
    picked += list(fonts.values()) + [el for el in kids if el.tag not in taken]
    unknown = sorted({el.tag for el in picked} - set(ORDER))
    if unknown:
        raise CatsPanelError(f"the generated desk has elements {', '.join(unknown)}, which ORDER does not place; add them")
    for el in sorted(picked, key=lambda el: ORDER.index(el.tag)):
        root.append(el)


def _place_plate(cats: ModuleType, sec: ET.Element, desk: str, fit: Fit,
                 where: MutableMapping[Cell, ET.Element | None], boxes: list[Label]) -> None:
    """Put plate SECTION `sec` (one SEC_NAME, its ABS words on the ABS desk) in `where` and its label in `boxes`.
    CatsPanelError when it holds more than its name, sits on a cell the desk uses, runs into another label or runs
    past the `fit` columns."""
    cell = _cell(sec)
    n = sec.find("SEC_NAME")
    if n is None or len(sec) != 1:
        raise CatsPanelError(f"{HEADER.name}: plate cell {cell} holds one SEC_NAME and nothing else")
    if desk == "ABS":
        text = n.get("NAME", "")
        for ctc, abs_ in ABS_PLATE.items():
            text = text.replace(ctc, abs_)
        n.set("NAME", text)
    if cell in where:
        raise CatsPanelError(f"{HEADER.name}: plate cell {cell} ({n.get('NAME')}) is a cell the desk uses")
    box = _name_box(cats, cell, n)
    hit = [other.cell for other in boxes if box.near(other.box)]
    if hit:
        raise CatsPanelError(f"{HEADER.name}: plate label {n.get('NAME')!r} at {cell} runs into the label at {hit[0]}")
    if box.right > right_edge(cats, fit):
        raise CatsPanelError(f"{HEADER.name}: plate label {n.get('NAME')!r} at {cell} runs past column {fit[0]}")
    boxes.append(Label(cell, box))
    where[cell] = sec


def _restack(tp: ET.Element, where: Mapping[Cell, ET.Element | None]) -> None:
    """Replace the SECTIONs of TRACKPLAN `tp` by `where`'s, row by row. CatsPanelError on a cell held with no
    SECTION (a station plate's cell before its SECTION is made)."""
    for sec in tp.findall("SECTION"):
        tp.remove(sec)
    for cell in sorted(where, key=lambda c: (c[1], c[0])):
        placed = where[cell]
        if placed is None:
            raise CatsPanelError(f"desk cell {cell} holds a station plate with no SECTION")
        tp.append(placed)


def label_clashes(log: Iterable[str]) -> list[str]:
    """The plugin's log lines (cats_labels.place_labels' words) for a label with no room or crossing something."""
    return [line for line in log if line.startswith("no room for label")
            or (line.startswith("label ") and " crosses " in line)]
