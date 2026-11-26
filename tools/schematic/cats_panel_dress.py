"""build_cats_panel.py's dress step: the frozen header and plate put on the generated document, the ABS twin's
words, and the desk's label clashes."""
import copy
import re
import xml.etree.ElementTree as ET

from cats_panel_facts import CatsPanelError
from hartlib import paths

HEADER = paths.CATS_DIR / "data/generated_desk_header.xml"   # frozen from the live desk (2026-11-15)
# The ABS twin: every CTC block ABS, and the plate's words (the hand-wired ABS desk's)
ABS_PLATE = {"CTC DIGICON": "ABS DIGICON", "DS-CTC": "DS-ABS"}
# The live desk's top-level order (HART_CTC.xml); the plugin's ROWWRAPTAG follows COMPRESSIONTAG
ORDER = ("FONTDEFINITION", "LINE", "COUNTER", "SIGNALTEMPLATE", "TRAINSTORE", "JOBSTORE", "CREWSTORE",
         "COLORDEFINITION", "TRAINSTATLABEL", "COMPRESSIONTAG", "ROWWRAPTAG", "OPERATIONS", "JMRINAME", "TRACKPLAN")
PLATE_PX = {"FONT_SUBTITLE": (9, 15)}   # pixels per character, line height, for plate fonts the plugin does not size


def frozen_header(path=HEADER):
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


def plate_box(cats, cell, loc, text, font):
    per, h = PLATE_PX.get(font) or cats.TEXT_PX.get(font, cats.TEXT_PX["FONT_LABEL"])
    return cats.frill_box(cell, loc, per * len(text) + 4, h)


def right_edge(cats, fit) -> int:
    """The x, in pixels, no desk label may run past: the `fit` columns and one more, as dress keeps the frozen
    plate and station_plates the control point plates."""
    return (fit[0] + 1) * cats.GRID_PX


PLATE_FONT, PLATE_LOC = "FONT_CP", "LOWCENT"     # a control point plate, as the hand-built desk wrote them


def station_plates(cats, root, stations, used: dict, boxes: list, fit) -> list[tuple[str, tuple[int, int]]]:
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
    plants = trace.desk_plants(cells, bound=True, level_turnouts=tables_build.level_turnouts(devices.load()))
    cols, rows = fit
    out = []
    for name, switches in stations:
        mine = [xy for os_name, xy in plants.items()
                if re.fullmatch(r"OS Switch (\d+)[a-d]?", os_name)
                and re.fullmatch(r"OS Switch (\d+)[a-d]?", os_name).group(1) in switches]
        if not mine:
            raise CatsPanelError(f"stations.csv: {name}'s plate: none of its switches ({', '.join(switches)}) has a "
                             "plant on the desk")
        cx, cy = sum(x for x, _ in mine) / len(mine), sum(y for _, y in mine) / len(mine)
        text = name.upper()
        found = None
        for cell in sorted(((x, y) for x in range(cols) for y in range(rows)),
                           key=lambda c: ((c[0] - cx) ** 2 + (c[1] - cy) ** 2, c[1], c[0])):
            box = plate_box(cats, cell, PLATE_LOC, text, PLATE_FONT)
            spans = {(x, cell[1]) for x in range(box[0] // cats.GRID_PX, (box[2] - 1) // cats.GRID_PX + 1)}
            if box[0] < 0 or box[2] > right_edge(cats, fit) or spans & set(used):
                continue
            if any(b[1] < box[3] and box[1] < b[3] and b[0] < box[2] + 6 and box[0] < b[2] + 6 for _c, b in boxes):
                continue
            found = (cell, box)
            break
        if found is None:
            raise CatsPanelError(f"stations.csv: no free cell on the desk for {name}'s plate {text!r} (the desk keeps "
                             f"its {cols} x {rows} cells)")
        used[found[0]] = None
        boxes.append(found)
        out.append((text, found[0]))
    return out


def dress(cats, root, header, plate, desk, fit, stations=None):
    """The generated document `root` with the frozen header and the plate: the template's fonts the plugin does
    not write (its own keep their values), the template's other elements in place of the plugin's copies, every
    element in the live desk's order, and the plate's labels on free cells of their row, clear of each other and of
    the labels there, within the `fit` columns; then each control point plate of `stations` (station_plates).
    desk "ABS": every CTC block ABS and the plate's ABS words."""
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
    tp = root.find("TRACKPLAN")
    where = {(int(sec.get("X")), int(sec.get("Y"))): sec for sec in tp.findall("SECTION")}
    boxes = []
    for sec in tp.findall("SECTION"):
        n = sec.find("SEC_NAME")
        if n is not None:
            cell = (int(sec.get("X")), int(sec.get("Y")))
            boxes.append((cell, plate_box(cats, cell, n.get("LOC_NAME"), n.get("NAME"), n.get("FONT_NAME"))))
    for sec in plate:
        sec = copy.deepcopy(sec)
        cell = (int(sec.get("X")), int(sec.get("Y")))
        n = sec.find("SEC_NAME")
        if n is None or len(sec) != 1:
            raise CatsPanelError(f"{HEADER.name}: plate cell {cell} holds one SEC_NAME and nothing else")
        if desk == "ABS":
            text = n.get("NAME")
            for ctc, abs_ in ABS_PLATE.items():
                text = text.replace(ctc, abs_)
            n.set("NAME", text)
        if cell in where:
            raise CatsPanelError(f"{HEADER.name}: plate cell {cell} ({n.get('NAME')}) is a cell the desk uses")
        box = plate_box(cats, cell, n.get("LOC_NAME"), n.get("NAME"), n.get("FONT_NAME"))
        hit = [c for c, b in boxes if b[1] < box[3] and box[1] < b[3] and b[0] < box[2] + 6 and box[0] < b[2] + 6]
        if hit:
            raise CatsPanelError(f"{HEADER.name}: plate label {n.get('NAME')!r} at {cell} runs into the label at {hit[0]}")
        if box[2] > right_edge(cats, fit):
            raise CatsPanelError(f"{HEADER.name}: plate label {n.get('NAME')!r} at {cell} runs past column {fit[0]}")
        boxes.append((cell, box))
        where[cell] = sec
    for text, cell in station_plates(cats, root, stations or [], where, boxes, fit):
        sec = ET.Element("SECTION", X=str(cell[0]), Y=str(cell[1]))
        ET.SubElement(sec, "SEC_NAME", LOC_NAME=PLATE_LOC, NAME=text, FONT_NAME=PLATE_FONT)
        where[cell] = sec
    for sec in tp.findall("SECTION"):
        tp.remove(sec)
    for cell in sorted(where, key=lambda c: (c[1], c[0])):
        tp.append(where[cell])
    if desk == "ABS":
        for b in root.iter("BLOCK"):
            if b.get("DISCIPLINE") == "CTC":
                b.set("DISCIPLINE", "ABS")
    ET.indent(root, "  ")
    return "<?xml version='1.0' encoding='UTF-8'?>\n" + ET.tostring(root, encoding="unicode") + "\n"


def label_clashes(log):
    """The plugin's log lines (cats_labels.place_labels' words) for a label with no room or crossing something."""
    return [line for line in log if line.startswith("no room for label")
            or (line.startswith("label ") and " crosses " in line)]
