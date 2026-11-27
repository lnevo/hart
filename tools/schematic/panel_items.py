"""Fixed panel items: icons and labels a Layout Editor panel carries that the schematic does not draw.

The input file is jmri/layouts/hart/data/schematic/panel_items.json, which is kept by hand. Since the device-map
switch-over (2026-11-17) it replaces the hand-placed overlay the build used to carry, with a short list of items
placed by rule (build_layout_le.py). It holds the status cluster panel_status.py drives (the sensor icons
Bridge HBLOOP, SML Mode and Track Power, the signal head icon IH9990 and their captions), the frame captions, the
helix destination labels and the backdrop image. More panel customisations go in the same file.

    {"_note": "...",
     "items": [{"id": "status", "anchor": {"to": "drawing", "at": "bottom-right", "dx": -78, "dy": 10},
                "members": [{"dx": 0, "dy": 0, "size": [21, 21], "xml": "<sensoricon sensor=... />"}, ...]},
               {"id": "backdrop", "anchor": {"to": "origin", "dx": 9, "dy": 0}, "size": [0, 0], "xml": "..."}]}

The file also gives the panel's `attributes` (Layout Editor attributes, all but the name, place and size the build
writes: SET_BY_BUILD) and `drawing_options` (its <layoutTrackDrawingOptions> element as text), read by
panel_attributes, so the device-map path reads no frozen panel.json.

An item is one element (`xml` and `size`) or a group (`members`, each with its own dx, dy, size and xml), placed
at its anchor point plus dx, dy (plus the member's dx, dy):
- "origin": the panel's top-left corner (0, 0);
- "drawing": a point of the box of everything drawn (track, arcs, turnouts, anchors and end bumpers);
- "block": a point of the drawn box of one block's track (`block`).
`at` is one of the nine points of the box: top-left, top, top-right, left, centre, right, bottom-left, bottom and
bottom-right. `xml` is a Layout Editor element without x and y (the placement writes them). `size` is the item's
drawn size in px [w, h]: the panel grows to hold every item EDGE px beyond the furthest one (a [0, 0] backdrop
does not count). A text label member may give `right` in place of dx and size: its right edge stands at that dx,
its size measured from its text, font size and style with the Pi's Dialog widths (pi_dialog: what JMRI draws on
the Pi), so captions of different lengths line up on their right edges beside their lamps there (on the Mac and
Windows, whose Dialog is another font, they may differ by a pixel). The label must name fontFamily and fontname
Dialog. Only the item tags below are taken, and an item whose element names a sensor, head or text it had before
keeps it as written, so panel_status.py finds its icons by the same names.
"""
from __future__ import annotations

import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir() and str(p / "tools/hartlib/src") not in sys.path][:1]

import pi_dialog  # noqa: E402  the Pi's Dialog widths, for a member placed by its right edge
from hartlib import hand_lists  # noqa: E402  the items file's reader (read_panel_items)

POINTS = {"top-left": (0, 0), "top": (0.5, 0), "top-right": (1, 0), "left": (0, 0.5), "centre": (0.5, 0.5),
          "right": (1, 0.5), "bottom-left": (0, 1), "bottom": (0.5, 1), "bottom-right": (1, 1)}
TAGS = ("sensoricon", "positionablelabel", "signalheadicon", "turnouticon", "memoryicon", "signalmasticon")
EDGE = 20               # px kept free beyond the furthest item at the right and the bottom
ITEM_FIELDS = {"id", "anchor", "xml", "size", "members", "note"}
MEMBER_FIELDS = {"dx", "dy", "xml", "size", "right"}
ANCHOR_FIELDS = {"to", "at", "block", "dx", "dy"}
FILE_FIELDS = {"_note", "attributes", "drawing_options", "items"}    # the panel is the build's (TEMPLATE_PANEL)
# the panel attributes the build writes (the plugin's to_xml: name, place and size), never the file
SET_BY_BUILD = {"class", "name", "x", "y", "panelwidth", "panelheight", "windowwidth", "windowheight"}


def panel_attributes(data: dict) -> tuple[dict, ET.Element | None]:
    """(the panel's attributes, its <layoutTrackDrawingOptions>) from a loaded file; ItemsError when it has none."""
    if data.get("attributes") is None:
        raise ItemsError("the items file gives no panel attributes")
    opts = data.get("drawing_options")
    return dict(data["attributes"]), (ET.fromstring(opts) if opts else None)


class ItemsError(RuntimeError):
    pass


def _number(v, what) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ItemsError(f"{what}: {v!r} is not a number")
    return float(v)


def _size(v, what) -> tuple[float, float]:
    if not isinstance(v, list) or len(v) != 2:
        raise ItemsError(f"{what}: size must be [w, h]")
    w, h = (_number(x, what) for x in v)
    if w < 0 or h < 0:
        raise ItemsError(f"{what}: size {v} below zero")
    return w, h


def _element(text, what) -> ET.Element:
    if not isinstance(text, str):
        raise ItemsError(f"{what}: xml must be text")
    try:
        el = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ItemsError(f"{what}: xml does not parse ({exc})") from exc
    if el.tag not in TAGS:
        raise ItemsError(f"{what}: <{el.tag}> is not one of {', '.join(TAGS)}")
    if "x" in el.attrib or "y" in el.attrib:
        raise ItemsError(f"{what}: xml holds x or y; the placement writes them")
    return el


def member_box(m: dict, what: str) -> tuple[float, tuple[float, float]]:
    """(dx, (w, h)) of a member: as written, or for one with `right`, its text label's width and height on the Pi
    (pi_dialog) and the dx that puts its right edge at `right`. ItemsError names the member."""
    if "right" not in m:
        return _number(m.get("dx", 0), what), _size(m.get("size"), what)
    if "dx" in m or "size" in m:
        raise ItemsError(f"{what}: right places a label by its right edge and measures its size; give no dx or size")
    right = _number(m["right"], what)
    el = _element(m.get("xml"), what)
    text, size, style = el.get("text"), el.get("size"), el.get("style", "0")
    if el.tag != "positionablelabel" or not text:
        raise ItemsError(f"{what}: right needs a positionablelabel with text")
    if el.get("fontFamily") != "Dialog" or el.get("fontname") != "Dialog":
        raise ItemsError(f"{what}: right measures the Dialog font; the label must name fontFamily and fontname "
                         f"Dialog, not {el.get('fontFamily')!r} and {el.get('fontname')!r}")
    if style not in ("0", "1") or not (size or "").isdigit():
        raise ItemsError(f"{what}: right needs a whole font size and style 0 or 1, not size {size!r} style {style!r}")
    bold = style == "1"
    try:
        w, h = pi_dialog.width(text, int(size), bold), pi_dialog.height(int(size), bold)
    except pi_dialog.PiTextError as exc:
        raise ItemsError(f"{what}: {exc}") from exc
    return right - w, (float(w), float(h))


def load(path: Path | None = None) -> dict:
    """The file (ITEMS unless `path`; hartlib.hand_lists.read_panel_items), checked: every item well formed (see the
    module text). ItemsError names the item."""
    path = ITEMS if path is None else Path(path)
    try:
        data = hand_lists.read_panel_items(path)
    except hand_lists.HandListError as exc:
        raise ItemsError(str(exc)) from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not data["items"]:
        raise ItemsError(f"{path.name}: needs a non-empty items list")
    if set(data) - FILE_FIELDS:
        raise ItemsError(f"{path.name}: unknown keys {sorted(set(data) - FILE_FIELDS)}")
    attrs = data.get("attributes")
    if attrs is not None and (not isinstance(attrs, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                                     for k, v in attrs.items())):
        raise ItemsError(f"{path.name}: attributes must be an object of text values")
    if attrs is not None and set(attrs) & SET_BY_BUILD:
        raise ItemsError(f"{path.name}: attributes {sorted(set(attrs) & SET_BY_BUILD)} are the build's to set")
    if data.get("drawing_options") is not None:
        try:
            el = ET.fromstring(data["drawing_options"])
        except (TypeError, ET.ParseError) as exc:
            raise ItemsError(f"{path.name}: drawing_options does not parse ({exc})") from exc
        if el.tag != "layoutTrackDrawingOptions":
            raise ItemsError(f"{path.name}: drawing_options is <{el.tag}>, not <layoutTrackDrawingOptions>")
    seen = set()
    for it in data["items"]:
        what = f"{path.name} item {it.get('id') if isinstance(it, dict) else it!r}"
        if not isinstance(it, dict) or not isinstance(it.get("id"), str) or it["id"] in seen:
            raise ItemsError(f"{what}: needs an id of its own")
        seen.add(it["id"])
        if set(it) - ITEM_FIELDS:
            raise ItemsError(f"{what}: unknown fields {sorted(set(it) - ITEM_FIELDS)}")
        a = it.get("anchor")
        if not isinstance(a, dict) or set(a) - ANCHOR_FIELDS or a.get("to") not in ("origin", "drawing", "block"):
            raise ItemsError(f"{what}: anchor must be {{to: origin, drawing or block, at, block, dx, dy}}")
        if a["to"] != "origin" and a.get("at") not in POINTS:
            raise ItemsError(f"{what}: anchor at must be one of {', '.join(POINTS)}")
        if (a["to"] == "block") != isinstance(a.get("block"), str):
            raise ItemsError(f"{what}: a block anchor names its block, no other does")
        for k in ("dx", "dy"):
            _number(a.get(k, 0), f"{what} anchor {k}")
        if ("members" in it) == ("xml" in it):
            raise ItemsError(f"{what}: give xml and size, or members")
        members = it.get("members") or [dict(dx=0, dy=0, xml=it.get("xml"), size=it.get("size"))]
        if not isinstance(members, list) or not members:
            raise ItemsError(f"{what}: members must be a non-empty list")
        for k, m in enumerate(members):
            mw = f"{what} member {k}"
            if not isinstance(m, dict) or set(m) - MEMBER_FIELDS:
                raise ItemsError(f"{mw}: fields are dx, dy, xml, size (or right in place of dx and size)")
            _number(m.get("dy", 0), mw)
            _element(m.get("xml"), mw)
            member_box(m, mw)
    return data


def drawn_boxes(panel: ET.Element, le_mod, slots_mod, frame_idents=None) -> tuple[tuple, dict]:
    """(box of everything drawn, {block: box of its drawn track}) of a Layout Editor panel: visible track segments
    (arcs as Layout Editor draws them) and turnout legs. `frame_idents`: the "drawing" box is of these track segments
    and turnouts only (one level of a panel of several: the items stand where they stand when that level is drawn
    alone; by ident, since a helix block is drawn on two levels). A Bezier segment stops (none is drawn on these
    panels)."""
    ix = slots_mod.Index(panel)
    allp, by_block = [], {}
    framed = (lambda el: True) if frame_idents is None else (lambda el: el.get("ident") in frame_idents)  # noqa: E731
    for s in panel.findall("tracksegment"):
        if s.get("hidden") == "yes":
            continue
        a = ix.coords(s.get("connect1name"), s.get("type1"))
        b = ix.coords(s.get("connect2name"), s.get("type2"))
        if s.get("bezier") == "yes":
            raise ItemsError(f"track segment {s.get('ident')} is a Bezier, which drawn_boxes does not read")
        pts = le_mod.arc_points(a, b, float(s.get("angle") or 0) or 90.0, s.get("flip") == "yes", 12) \
            if s.get("arc") == "yes" and s.get("circle") == "yes" else [a, b]
        block = s.get("blockname") or ""
        if framed(s):
            allp += pts
        by_block.setdefault(block, []).extend(pts)
    for t in panel.findall("layoutturnout"):
        for leg in "ABCD":
            if t.get(f"connect{leg.lower()}name") or leg in "ABC":
                p = ix.leg_coords(t, leg)
                block = (t.get(f"block{leg.lower()}name") if leg != "A" else None) or t.get("blockname") or ""
                if framed(t):
                    allp.append(p)
                by_block.setdefault(block, []).append(p)
    if not allp:
        raise ItemsError(f"panel {panel.get('name')!r}: nothing drawn"
                         + (" of the frame's track" if frame_idents is not None else ""))

    def box(pts):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))
    return box(allp), {b: box(p) for b, p in by_block.items() if b}


def anchor_point(anchor: dict, whole: tuple, blocks: dict, what: str) -> tuple[float, float]:
    if anchor["to"] == "origin":
        base = (0.0, 0.0)
    else:
        if anchor["to"] == "block" and anchor["block"] not in blocks:
            raise ItemsError(f"{what}: block {anchor['block']!r} is not drawn on the panel")
        x0, y0, x1, y1 = whole if anchor["to"] == "drawing" else blocks[anchor["block"]]
        fx, fy = POINTS[anchor["at"]]
        base = (x0 + fx * (x1 - x0), y0 + fy * (y1 - y0))
    return base[0] + anchor.get("dx", 0), base[1] + anchor.get("dy", 0)


def place(panel: ET.Element, data: dict, le_mod, slots_mod, fit: tuple[int, int], chrome: tuple[int, int],
          frame_idents=None) -> dict:
    """Put every item of `data` (load()) on `panel`, at its place, after the panel's own elements; grow the panel to
    hold them (EDGE px beyond the furthest, the window at most `fit`). `frame_idents`: as drawn_boxes. Stops on an
    item outside the panel's top or left. Returns {count: elements put on, size: (panel w, h), bottom: the lowest
    sized item's bottom, or None}."""
    whole, blocks = drawn_boxes(panel, le_mod, slots_mod, frame_idents)
    right, bottom, n = float(panel.get("panelwidth")), float(panel.get("panelheight")), 0
    lowest = None
    for it in data["items"]:
        what = f"panel item {it['id']}"
        ax, ay = anchor_point(it["anchor"], whole, blocks, what)
        members = it.get("members") or [dict(dx=0, dy=0, xml=it["xml"], size=it["size"])]
        for m in members:
            el = _element(m["xml"], what)
            dx, (w, h) = member_box(m, what)
            x, y = round(ax + dx), round(ay + m.get("dy", 0))
            if x < 0 or y < 0:
                raise ItemsError(f"{what}: placed at {x}, {y}, off the panel")
            el.set("x", str(x))
            el.set("y", str(y))
            if w and h:
                right, bottom = max(right, x + w + EDGE), max(bottom, y + h + EDGE)
                lowest = y + h if lowest is None else max(lowest, y + h)
            panel.append(el)
            n += 1
    w, h = math.ceil(right), math.ceil(bottom)
    panel.set("panelwidth", str(w))
    panel.set("panelheight", str(h))
    panel.set("windowwidth", str(min(w + chrome[0], fit[0])))
    panel.set("windowheight", str(min(h + chrome[1], fit[1])))
    return dict(count=n, size=(w, h), bottom=lowest)


# ---------------------------------------------------------------- the status beans (device-master rows)

WRITER = "panel_items.json"      # the device master written_by of the status beans, one of hartlib.devices.WRITERS
ITEMS = hand_lists.PANEL_ITEMS   # the items file, kept by hand
# The beans the status cluster's icons show (panel_status.py finds them by name), kept by hand
LAMPS = hand_lists.PANEL_LAMPS


def _devices():
    """hartlib.devices, found the way the repo's scripts find hartlib (tools/hartlib/src above this file)."""
    import sys
    src = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents if (p / "tools/hartlib/src").is_dir()]
    if not src:
        raise ItemsError(f"no tools/hartlib/src above {__file__}")
    if src[0] not in sys.path:
        sys.path.insert(0, src[0])
    from hartlib import devices
    return devices


def status_rows(data: dict, lamps_path: Path = LAMPS) -> list[dict]:
    """The device master rows (hartlib.devices.COLUMNS) of the status beans of `lamps_path` (panel_lamps.csv,
    hartlib.hand_lists.read_panel_lamps), each held by this file (written_by panel_items.json). HandListError on a
    bad lamps file; ItemsError when no item of `data` (load()) has an icon naming one of them: the two files would
    disagree about what the panel shows."""
    devices = _devices()
    lamps = hand_lists.read_panel_lamps(lamps_path)
    from hartlib import device_ids
    named = {}                  # (icon tag, the bean it names) -> the key of the item it is in
    for it in data["items"]:
        for m in it.get("members") or [it]:
            el = _element(m["xml"], f"item {it['id']}")
            for k in ((el.tag, el.get(a)) for a in ("sensor", "signalhead") if el.get(a)):
                if named.setdefault(k, it["id"]) != it["id"]:
                    raise ItemsError(f"{k[0]} {k[1]!r} is in items {named[k]!r} and {it['id']!r}; a status bean "
                                     "is in one item, which its device ID names")
    rows = []
    for lamp in lamps:
        system = lamp.system_name
        tag, name = ("sensoricon", lamp.user_name) if lamp.icon == "sensor" else ("signalheadicon", system)
        if (tag, name) not in named:
            raise ItemsError(f"status bean {lamp.user_name!r} ({system}) has no {tag} naming {name!r} in the items "
                             "file")
        row = {c: "" for c in devices.COLUMNS}
        # its device ID: the item its icon is in and the bean's system name (hartlib.device_ids.panel_id)
        row.update(level="1", layer=lamp.layer, role="panel_status",
                   id=device_ids.panel_id(named[(tag, name)], system), user_name=lamp.user_name, assignment=lamp.assignment, system_name=system, jmri_name=system,
                   jmri_comment=lamp.jmri_comment, written_by=WRITER, description=lamp.description)
        rows.append(row)
    return rows


def main(argv=None) -> int:
    """python3 tools/schematic/panel_items.py [--check]: write the status beans' rows of the device master (and the files it
    generates), or, with --check, exit 1 when they are not as the items file gives them."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(description=main.__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the device master is out of date")
    args = ap.parse_args(argv)
    try:
        devices = _devices()
        files = devices.Files.here()
        want = devices.outputs_after_rows(WRITER, status_rows(load(ITEMS)), files)
    except (ItemsError, ValueError) as exc:          # devices.DevicesError is a ValueError
        print(f"panel_items.py: {exc}", file=sys.stderr)
        return 2
    stale = [p for p, text in want.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale:
            print(devices.stale_message(p, files, "tools/schematic/panel_items.py"), file=sys.stderr)
        return 1 if stale else 0
    for p in devices.write_all(files, want):
        print(f"wrote {p.name}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
