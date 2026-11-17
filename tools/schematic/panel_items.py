"""Fixed panel items: icons and labels a Layout Editor panel carries that the schematic does not draw.

The input file is jmri/layouts/hart/data/schematic/panel_items.json, which is kept by hand. It replaces the
hand-placed overlay (staging_le/overlay.json, le_overlay.py) on the device-map path (build_staging_candidate.py)
with a short list of items placed by rule. It holds the status cluster panel_status.py drives (the sensor icons
Bridge HBLOOP, SML Mode and Track Power, the signal head icon IH9990 and their captions), the frame captions, the
helix destination labels and the backdrop image. More panel customisations go in the same file.

    {"_note": "...", "panel": "HART Railroad",
     "items": [{"id": "status", "anchor": {"to": "drawing", "at": "bottom-right", "dx": -78, "dy": 10},
                "members": [{"dx": 0, "dy": 0, "size": [21, 21], "xml": "<sensoricon sensor=... />"}, ...]},
               {"id": "backdrop", "anchor": {"to": "origin", "dx": 9, "dy": 0}, "size": [0, 0], "xml": "..."}]}

An item is one element (`xml` and `size`) or a group (`members`, each with its own dx, dy, size and xml), placed
at its anchor point plus dx, dy (plus the member's dx, dy):
- "origin": the panel's top-left corner (0, 0);
- "drawing": a point of the box of everything drawn (track, arcs, turnouts, anchors and end bumpers);
- "block": a point of the drawn box of one block's track (`block`).
`at` is one of the nine points of the box: top-left, top, top-right, left, centre, right, bottom-left, bottom and
bottom-right. `xml` is a Layout Editor element without x and y (the placement writes them). `size` is the item's
drawn size in px [w, h]: the panel grows to hold every item EDGE px beyond the furthest one (a [0, 0] backdrop
does not count). Only the item tags below are taken, and an item whose element names a sensor, head or text it
had before keeps it as written, so panel_status.py finds its icons by the same names.
"""
from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

POINTS = {"top-left": (0, 0), "top": (0.5, 0), "top-right": (1, 0), "left": (0, 0.5), "centre": (0.5, 0.5),
          "right": (1, 0.5), "bottom-left": (0, 1), "bottom": (0.5, 1), "bottom-right": (1, 1)}
TAGS = ("sensoricon", "positionablelabel", "signalheadicon", "turnouticon", "memoryicon", "signalmasticon")
EDGE = 20               # px kept free beyond the furthest item at the right and the bottom (as le_overlay.EDGE)
ITEM_FIELDS = {"id", "anchor", "xml", "size", "members", "note"}
MEMBER_FIELDS = {"dx", "dy", "xml", "size"}
ANCHOR_FIELDS = {"to", "at", "block", "dx", "dy"}


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
        raise ItemsError(f"{what}: xml does not parse ({exc})") from None
    if el.tag not in TAGS:
        raise ItemsError(f"{what}: <{el.tag}> is not one of {', '.join(TAGS)}")
    if "x" in el.attrib or "y" in el.attrib:
        raise ItemsError(f"{what}: xml holds x or y; the placement writes them")
    return el


def load(path: Path) -> dict:
    """The file, checked: every item well formed (see the module text). ItemsError names the item."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ItemsError(f"cannot read {path.name}: {exc}") from None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not data["items"]:
        raise ItemsError(f"{path.name}: needs a non-empty items list")
    if not isinstance(data.get("panel"), str):
        raise ItemsError(f"{path.name}: needs the panel's name")
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
                raise ItemsError(f"{mw}: fields are dx, dy, xml, size")
            _number(m.get("dx", 0), mw)
            _number(m.get("dy", 0), mw)
            _size(m.get("size"), mw)
            _element(m.get("xml"), mw)
    return data


def drawn_boxes(panel: ET.Element, le_mod, slots_mod) -> tuple[tuple, dict]:
    """(box of everything drawn, {block: box of its drawn track}) of a Layout Editor panel: visible track segments
    (arcs as Layout Editor draws them), turnout legs, anchors and end bumpers. A Bezier segment stops (none is
    drawn on these panels)."""
    ix = slots_mod.Index(panel)
    allp, by_block = [], {}
    for s in panel.findall("tracksegment"):
        if s.get("hidden") == "yes":
            continue
        a = ix.coords(s.get("connect1name"), s.get("type1"))
        b = ix.coords(s.get("connect2name"), s.get("type2"))
        if s.get("bezier") == "yes":
            raise ItemsError(f"track segment {s.get('ident')} is a Bezier, which drawn_boxes does not read")
        pts = le_mod.arc_points(a, b, float(s.get("angle") or 0) or 90.0, s.get("flip") == "yes", 12) \
            if s.get("arc") == "yes" and s.get("circle") == "yes" else [a, b]
        allp += pts
        by_block.setdefault(s.get("blockname") or "", []).extend(pts)
    for t in panel.findall("layoutturnout"):
        for leg in "ABCD":
            if t.get(f"connect{leg.lower()}name") or leg in "ABC":
                p = ix.leg_coords(t, leg)
                allp.append(p)
                block = t.get(f"block{leg.lower()}name") if leg != "A" else t.get("blockname")
                by_block.setdefault(block or t.get("blockname") or "", []).append(p)
    for p in panel.findall("positionablepoint"):
        allp.append((float(p.get("x")), float(p.get("y"))))
    if not allp:
        raise ItemsError(f"panel {panel.get('name')!r}: nothing drawn")

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


def place(panel: ET.Element, data: dict, le_mod, slots_mod, fit: tuple[int, int], chrome: tuple[int, int]) -> int:
    """Put every item of `data` (load()) on `panel`, at its place, after the panel's own elements; grow the panel to
    hold them (EDGE px beyond the furthest, the window at most `fit`). Stops on an item outside the panel's top or
    left. Returns how many elements went on."""
    whole, blocks = drawn_boxes(panel, le_mod, slots_mod)
    right, bottom, n = float(panel.get("panelwidth")), float(panel.get("panelheight")), 0
    for it in data["items"]:
        what = f"panel item {it['id']}"
        ax, ay = anchor_point(it["anchor"], whole, blocks, what)
        members = it.get("members") or [dict(dx=0, dy=0, xml=it["xml"], size=it["size"])]
        for m in members:
            el = _element(m["xml"], what)
            x, y = round(ax + m.get("dx", 0)), round(ay + m.get("dy", 0))
            if x < 0 or y < 0:
                raise ItemsError(f"{what}: placed at {x}, {y}, off the panel")
            el.set("x", str(x))
            el.set("y", str(y))
            w, h = _size(m["size"], what)
            if w and h:
                right, bottom = max(right, x + w + EDGE), max(bottom, y + h + EDGE)
            panel.append(el)
            n += 1
    w, h = math.ceil(right), math.ceil(bottom)
    panel.set("panelwidth", str(w))
    panel.set("panelheight", str(h))
    panel.set("windowwidth", str(min(w + chrome[0], fit[0])))
    panel.set("windowheight", str(min(h + chrome[1], fit[1])))
    return n
