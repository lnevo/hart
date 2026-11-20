"""build_cats_panel.py's dress step: the frozen header and plate put on the generated document, the ABS twin's
words, and the desk's label clashes. Moved out of build_cats_panel.py unchanged."""
import copy
import xml.etree.ElementTree as ET

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
        raise SystemExit(f"{path}: not a CATS panel template (its root is {root.tag})")
    els = [el for el in root if isinstance(el.tag, str)]
    bad = sorted({el.tag for el in els} - set(ORDER))
    if bad:
        raise SystemExit(f"{path}: elements {', '.join(bad)} are not header elements ({', '.join(ORDER)})")
    lacking = [t for t in ("SIGNALTEMPLATE", "JMRINAME") if not any(el.tag == t for el in els)]
    if lacking:
        raise SystemExit(f"{path}: no {' or '.join(lacking)} elements; the staging bindings' masts and IOSPECs "
                         "need them")
    plan = root.find("TRACKPLAN")
    return [el for el in els if el.tag != "TRACKPLAN"], list(plan) if plan is not None else []


def plate_box(cats, cell, loc, text, font):
    per, h = PLATE_PX.get(font) or cats.TEXT_PX.get(font, cats.TEXT_PX["FONT_LABEL"])
    return cats.frill_box(cell, loc, per * len(text) + 4, h)


def dress(cats, root, header, plate, desk, fit):
    """The generated document `root` with the frozen header and the plate: the template's fonts the plugin does
    not write (its own keep their values), the template's other elements in place of the plugin's copies, every
    element in the live desk's order, and the plate's labels on free cells of their row, clear of each other and of
    the labels there, within the `fit` columns. desk "ABS": every CTC block ABS and the plate's ABS words."""
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
        raise SystemExit(f"the generated desk has elements {', '.join(unknown)}, which ORDER does not place; add them")
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
            raise SystemExit(f"{HEADER.name}: plate cell {cell} holds one SEC_NAME and nothing else")
        if desk == "ABS":
            text = n.get("NAME")
            for ctc, abs_ in ABS_PLATE.items():
                text = text.replace(ctc, abs_)
            n.set("NAME", text)
        if cell in where:
            raise SystemExit(f"{HEADER.name}: plate cell {cell} ({n.get('NAME')}) is a cell the desk uses")
        box = plate_box(cats, cell, n.get("LOC_NAME"), n.get("NAME"), n.get("FONT_NAME"))
        hit = [c for c, b in boxes if b[1] < box[3] and box[1] < b[3] and b[0] < box[2] + 6 and box[0] < b[2] + 6]
        if hit:
            raise SystemExit(f"{HEADER.name}: plate label {n.get('NAME')!r} at {cell} runs into the label at {hit[0]}")
        if box[2] > (fit[0] + 1) * cats.GRID_PX:
            raise SystemExit(f"{HEADER.name}: plate label {n.get('NAME')!r} at {cell} runs past column {fit[0]}")
        boxes.append((cell, box))
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
