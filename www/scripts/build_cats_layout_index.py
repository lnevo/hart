#!/usr/bin/env python3
"""Build Digicon/CATS device-map hotspots for the operator portal.

Uses the live Digicon panel (same default as cats/scripts/launch_cats.sh):
cats/panels/HART_CTC.xml.

Emits clickable:
  - turnout plants (SWITCHPOINTS)
  - signal masts (SECSIGNAL)

Joined to the layout index (build_layout_index.py, built in memory) for MQTT / hardware when names match.

    python3 www/scripts/build_cats_layout_index.py          # render the PNG, stamp it, write the local JSON
    python3 www/scripts/build_cats_layout_index.py --check  # build in memory; exit 1 if a check fails

www/data/layout-index-cats.json is built where it is used, not committed (ADR-036): the site build and the local
preview call index_text() (site_views.py). The PNG stays committed with its render stamp (png_stamp.py).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_layout_index  # noqa: E402
import png_stamp  # noqa: E402
from build_layout_index import Item  # noqa: E402
from build_layout_index import paths  # noqa: E402  (hartlib.paths, put on sys.path by build_layout_index)

PORTAL = Path(__file__).resolve().parents[1]
ROOT = PORTAL.parent
PANEL = ROOT / "cats/panels/HART_CTC.xml"
RENDER = ROOT / "cats/scripts/render_cats_panel.py"
OUT_IMG = PORTAL / "assets/layout/HART_cats_digicon.png"
OUT_JSON = PORTAL / "data/layout-index-cats.json"
BUILD = "python3 www/scripts/build_cats_layout_index.py"

CELL = 60
PAD_X = 60
PAD_Y = 90

# Digicon station numbers → public LE switch names (crossovers)
STATION_TO_SWITCH = {
    "111": "Switch 23",
    "113": "Switch 35",
    "117": "Switch 7",
}

# SECSIGNAL PANELSIGNAL SIGLOCATION → fraction inside the cell (x, y)
SIG_LOC = {
    "UPLEFT": (0.22, 0.18),
    "UPCENT": (0.50, 0.18),
    "UPRIGHT": (0.78, 0.18),
    "MIDLEFT": (0.22, 0.50),
    "MIDCENT": (0.50, 0.50),
    "MIDRIGHT": (0.78, 0.50),
    "LOWLEFT": (0.22, 0.82),
    "LOWCENT": (0.50, 0.82),
    "LOWRIGHT": (0.78, 0.82),
    "LEFT": (0.18, 0.50),
    "RIGHT": (0.82, 0.50),
    "CENTER": (0.50, 0.50),
    # Digicon aliases seen on Master CTC
    "LEFTLOW": (0.18, 0.82),
    "LEFTUP": (0.18, 0.18),
    "RIGHTLOW": (0.82, 0.82),
    "RIGHTUP": (0.82, 0.18),
}

# Portal-only pixel nudges when Digicon cell slots still sit on top of the plant.
# Values are absolute image coords (same space as CELL/PAD in render_cats_panel).
HOTSPOT_OVERRIDE = {
    # Down + right of OS Switch 31 plant (2550, 480) — clear of points & lower slash.
    "mast 32r": (2610.0, 525.0),
}


class CatsIndexError(Exception):
    """The CATS layout index cannot be built, or what was built fails a check; the message says why."""


def render() -> None:
    OUT_IMG.parent.mkdir(parents=True, exist_ok=True)
    if subprocess.run([sys.executable, str(RENDER), str(PANEL), str(OUT_IMG)]).returncode:
        raise CatsIndexError(f"render failed: {RENDER.name} {PANEL}")


def le_by_keys(le_index: dict) -> dict[str, Item]:
    """The layout index's items by every name a Digicon cell may use for them."""
    items = le_index.get("items")
    if not isinstance(items, list) or not items:
        raise CatsIndexError("the layout index it joins to has no items")
    out: dict[str, Item] = {}
    # Names first; they are authoritative.
    for it in items:
        for key in (
            it.get("publicName"),
            it.get("systemName"),
            it.get("hardware"),
            (it.get("block") or "").replace("OS ", "").strip(),
        ):
            if key:
                out.setdefault(str(key).strip().lower(), it)
        # Mast 24RA style
        for key in (it.get("publicName"), it.get("systemName")):
            if key and "mast" in str(key).lower():
                out.setdefault(str(key).strip().lower(), it)
                bare = re.sub(r"^mast\s+", "", str(key).strip(), flags=re.I)
                out.setdefault(bare.lower(), it)
                out.setdefault(f"mast {bare.lower()}", it)
    # Id-derived keys only fill gaps: LE id "to-TO1" is Switch 13, not Switch 1.
    for it in items:
        sn = (it.get("systemName") or "").strip()
        if sn.startswith("Switch "):
            out.setdefault(f"to{sn.split()[-1]}".lower(), it)
        iid = it.get("id") or ""
        if "TO" in iid.upper():
            to = iid.upper().split("TO")[-1]
            digits = "".join(ch for ch in to if ch.isdigit())
            if digits:
                out.setdefault(f"to{digits}", it)
                out.setdefault(digits, it)
                out.setdefault(f"switch {digits}", it)
    return out


def mast_name(el: ET.Element) -> str:
    parts: list[str] = []
    if el.text and el.text.strip():
        parts.append(el.text.strip())
    for child in el:
        if child.tail and child.tail.strip():
            parts.append(child.tail.strip())
    name = " ".join(parts).strip()
    name = re.sub(r"\s+", " ", name)
    return name


def cell_origin(x: int, y: int, minx: int, miny: int) -> tuple[float, float]:
    return PAD_X + (x - minx) * CELL, PAD_Y + (y - miny) * CELL


def match_turnout(by: dict[str, Item], stations: set[str], blocks: set[str]) -> Item | None:
    def is_turnout(it: Item | None) -> bool:
        return it is not None and it.get("kind") == "turnout"

    for bl in blocks:
        name = bl.replace("OS ", "").lower()
        # a double crossover's corner block (OS Switch 225b) is a block of the Layout Editor, not a turnout: its
        # points belong to the crossover's one turnout (Switch 225)
        for key in (name, re.sub(r"(?<=\d)[a-d]$", "", name)):
            if is_turnout(by.get(key)):
                return by[key]
    for st in stations:
        pref = STATION_TO_SWITCH.get(st)
        match = None
        if pref:
            match = by.get(pref.lower()) or by.get(f"to{st}")
        if not match:
            match = by.get(f"to{st}") or by.get(st.lower()) or by.get(f"switch {st}")
        if match:
            return match
    for bl in blocks:
        match = by.get(bl.lower()) or by.get(bl.replace("OS ", "").lower())
        if match:
            return match
    return None


EFFECTIVE = re.compile(r"Eff \d{4}-\d{2}-\d{2}")


def render_inputs_sha256() -> str:
    """What the desk PNG is drawn from: the desk's TRACKPLAN (build date left out) and the renderer.

    Recorded in the PNG (png_stamp) and the JSON so --check finds a PNG that needs re-rendering without drawing it.
    """
    tp = ET.tostring(ET.parse(PANEL).getroot().find("TRACKPLAN"), encoding="unicode")
    h = hashlib.sha256(EFFECTIVE.sub("Eff DATE", tp).encode("utf-8"))
    h.update(RENDER.read_bytes())
    return h.hexdigest()


def build(le_index: dict | None = None) -> dict:
    """The CATS index, joined to `le_index` (build_layout_index.build(), built now when None). CatsIndexError when a
    source is missing or cannot be read."""
    try:
        return _build(le_index)
    except (ET.ParseError, ValueError, OSError) as err:
        raise CatsIndexError(f"cannot build the CATS index from its sources: {type(err).__name__}: {err}") from err


Cell = tuple[int, int]  # a TRACKPLAN section's X, Y


def read_sections() -> list[ET.Element]:
    """The desk's TRACKPLAN sections; CatsIndexError when a source is missing or the plan has none."""
    for path in (PANEL, RENDER, OUT_IMG):
        if not path.is_file():
            raise CatsIndexError(f"missing {paths.rel(path)}" + (f": run {BUILD}" if path == OUT_IMG else ""))
    tp = ET.parse(PANEL).getroot().find("TRACKPLAN")
    if tp is None or not tp.findall("SECTION"):
        raise CatsIndexError(f"{paths.rel(PANEL)} has no TRACKPLAN sections")
    return tp.findall("SECTION")


def cell_of(s: ET.Element) -> Cell:
    return int(s.get("X")), int(s.get("Y"))


def blocks_by_cell(sections: Sequence[ET.Element]) -> dict[Cell, list[tuple[str, str]]]:
    """(x, y) -> (OS block, station) on that cell's edges, for switch cells that carry none."""
    out: dict[Cell, list[tuple[str, str]]] = {}
    for s in sections:
        for e in s.findall("SEC_EDGE"):
            for b in e.findall("BLOCK"):
                if b.get("NAME"):
                    out.setdefault(cell_of(s), []).append((b.get("NAME"), b.get("STATION") or ""))
    return out


def signal_item(sig: ET.Element, name: str, cell: Cell, origin: tuple[float, float], by: dict[str, Item]) -> Item:
    """The hotspot of one SECSIGNAL, joined to the layout index by its mast name."""
    key = name.lower()
    panel = sig.find("PANELSIGNAL")
    loc = (panel.get("SIGLOCATION") if panel is not None else None) or "CENTER"
    fx, fy = SIG_LOC.get(loc.upper(), SIG_LOC["CENTER"])
    px, py = HOTSPOT_OVERRIDE.get(key) or (origin[0] + fx * CELL, origin[1] + fy * CELL)
    match = by.get(key)
    if not match:
        bare = re.sub(r"^mast\s+", "", name, flags=re.I).strip().lower()
        match = by.get(bare) or by.get(f"mast {bare}")
    m = match or {}
    return build_layout_index.item(
        f"cats-sig-{re.sub(r'[^a-zA-Z0-9]+', '-', name).strip('-')}", "signal", (px, py),
        m.get("systemName") or name, m.get("publicName") or name, m.get("cp") or "", m.get("hardware") or "",
        m.get("mqtt") or "", m.get("comment") or f"Digicon SECSIGNAL @ cell ({cell[0]},{cell[1]}) {loc}",
        m.get("block") or "")


def plant_item(cell: Cell, origin: tuple[float, float], stations: set[str], blocks: set[str],
               near_blocks: dict[Cell, list[tuple[str, str]]], by: dict[str, Item]) -> Item:
    """The hotspot of a cell with switch points, joined to the layout index's turnout."""
    x, y = cell
    if not blocks and not stations:
        # Points cell with no OS of its own: take the OS that surrounds it.
        near: dict[tuple[str, str], int] = {}
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            for nb in near_blocks.get((x + dx, y + dy), []):
                near[nb] = near.get(nb, 0) + 1
        if near:
            name, station = max(near, key=near.get)
            blocks.add(name)
            if station:
                stations.add(station)
    m = match_turnout(by, stations, blocks) or {}
    public = m.get("publicName")
    if not public:
        public = next((STATION_TO_SWITCH[st] for st in stations if st in STATION_TO_SWITCH), None)
    if not public:
        if stations:
            public = f"Plant {', '.join(sorted(stations))}"
        elif blocks:
            public = sorted(blocks)[0]
        else:
            public = f"Plant ({x},{y})"
    where = f"Digicon plant @ {x},{y}" + (f"; OS {', '.join(sorted(blocks))}" if blocks else "")
    return build_layout_index.item(
        f"cats-to-{x}-{y}", "turnout", (origin[0] + CELL / 2, origin[1] + CELL / 2), m.get("systemName") or "",
        public, m.get("cp") or (sorted(stations)[0] if stations else ""), m.get("hardware") or "",
        m.get("mqtt") or "", m.get("comment") or where, m.get("block") or (sorted(blocks)[0] if blocks else ""))


def section_items(sections: Sequence[ET.Element], by: dict[str, Item]) -> list[Item]:
    """Each cell's signals (each mast once, where it first appears) and, for a cell with points, its turnout."""
    minx, miny = min(cell_of(s)[0] for s in sections), min(cell_of(s)[1] for s in sections)
    near_blocks = blocks_by_cell(sections)
    seen_masts: set[str] = set()
    items: list[Item] = []
    for s in sections:
        cell = cell_of(s)
        origin = cell_origin(*cell, minx, miny)
        stations: set[str] = set()
        blocks: set[str] = set()
        has_points = False
        for e in s.findall("SEC_EDGE"):
            has_points = has_points or e.find("SWITCHPOINTS") is not None
            for b in e.findall("BLOCK"):
                if b.get("STATION"):
                    stations.add(b.get("STATION"))
                if b.get("NAME"):
                    blocks.add(b.get("NAME"))
            for sig in e.findall("SECSIGNAL"):
                name = mast_name(sig)
                if name and name.lower() not in seen_masts:
                    seen_masts.add(name.lower())
                    items.append(signal_item(sig, name, cell, origin, by))
        if has_points:
            items.append(plant_item(cell, origin, stations, blocks, near_blocks, by))
    return items


def _build(le_index: dict | None) -> dict:
    sections = read_sections()
    if le_index is None:
        try:
            le_index = build_layout_index.build()
        except build_layout_index.LayoutIndexError as err:
            raise CatsIndexError(f"cannot build the layout index it joins to: {err}") from err
    items = section_items(sections, le_by_keys(le_index))
    try:
        w, h = png_stamp.size(OUT_IMG)
    except png_stamp.PngError as err:
        raise CatsIndexError(str(err)) from err
    return {
        "source": {
            "workspace": "hart",
            "panel": "cats/panels/HART_CTC.xml",
            "view": "digicon-cats",
        },
        "image": {
            "path": "assets/layout/HART_cats_digicon.png",
            "width": w,
            "height": h,
            "scale": 1.0,
            "inputs_sha256": render_inputs_sha256(),
        },
        "items": items,
        "counts": {
            "turnout": sum(1 for it in items if it["kind"] == "turnout"),
            "signal": sum(1 for it in items if it["kind"] == "signal"),
            "occupancy": 0,
            "sensor": 0,
            "mapped": len(items),
            "total": len(items),
        },
    }


def problems(payload: dict) -> list[str]:
    """What is wrong with a built index: no turnouts or signals, counts that do not add up, repeated ids, or a PNG
    whose stamp is not the hash of what it is drawn from now (re-render it)."""
    out = []
    items = payload.get("items") or []
    counts = payload.get("counts") or {}
    for kind in ("turnout", "signal"):
        if not counts.get(kind):
            out.append(f"the index has no {kind} hotspots")
    if counts.get("total") != len(items):
        out.append(f"counts.total is {counts.get('total')}, the index has {len(items)} items")
    ids = [it.get("id") for it in items]
    if len(set(ids)) != len(ids):
        out.append("repeated item ids: " + ", ".join(sorted({i for i in ids if ids.count(i) > 1}, key=str)[:10]))
    want = (payload.get("image") or {}).get("inputs_sha256")
    try:
        have = png_stamp.stamp(OUT_IMG)
    except png_stamp.PngError as err:
        out.append(str(err))
    else:
        if have != want:
            out.append(f"{paths.rel(OUT_IMG)} was drawn from other inputs (its stamp is {have}, they hash to "
                       f"{want}): run {BUILD} and commit the PNG")
    return out


def index_text(payload: dict | None = None, le_index: dict | None = None) -> str:
    """The checked layout-index-cats.json text of `payload` (built now, joined to `le_index`, when None).
    CatsIndexError when it cannot be built or fails a check."""
    payload = build(le_index) if payload is None else payload
    bad = problems(payload)
    if bad:
        raise CatsIndexError(f"{paths.rel(OUT_JSON)} fails its checks:\n  " + "\n  ".join(bad))
    return json.dumps(payload, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="build in memory and write nothing; exit 1 if the index fails a check or the PNG "
                         "(by its render stamp) is stale")
    args = ap.parse_args(argv)
    try:
        if args.check:
            text = index_text()
            print(f"{paths.rel(OUT_JSON)} builds and passes its checks "
                  f"({len(json.loads(text)['items'])} items, the PNG's render stamp is current)")
            return 0
        render()
        payload = build()
        png_stamp.write_stamp(OUT_IMG, payload["image"]["inputs_sha256"])
        text = index_text(payload)
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(text, encoding="utf-8")
    except (CatsIndexError, png_stamp.PngError, OSError, ET.ParseError) as err:
        print(err, file=sys.stderr)
        return 1
    c = json.loads(text)["counts"]
    print(f"wrote {paths.rel(OUT_IMG)} (to commit) and {paths.rel(OUT_JSON)} (not committed) "
          f"to={c['turnout']} sig={c['signal']} mapped={c['mapped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
