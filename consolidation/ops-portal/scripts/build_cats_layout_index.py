#!/usr/bin/env python3
"""Build Digicon/CATS device-map hotspots for the operator portal.

Uses the live Digicon panel (same default as cats/scripts/launch_cats.sh):
cats/panels/HART_Master_CTC_hold.xml.

Emits clickable:
  - turnout plants (SWITCHPOINTS)
  - signal masts (SECSIGNAL)

Joined to consolidation layout-index.json for MQTT / hardware when names match.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
CONS = PORTAL.parent
ROOT = CONS.parent
PANEL = ROOT / "cats/panels/HART_Master_CTC_hold.xml"
RENDER = ROOT / "cats/scripts/render_cats_panel.py"
OUT_IMG = PORTAL / "assets/layout/HART_cats_digicon.png"
OUT_JSON = PORTAL / "data/layout-index-cats.json"
LE_JSON = PORTAL / "data/layout-index.json"

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


def render() -> None:
    OUT_IMG.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(RENDER), str(PANEL), str(OUT_IMG)],
        check=True,
    )


def le_by_keys() -> dict[str, dict]:
    if not LE_JSON.is_file():
        return {}
    data = json.loads(LE_JSON.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for it in data.get("items") or []:
        for key in (
            it.get("publicName"),
            it.get("systemName"),
            it.get("hardware"),
            (it.get("block") or "").replace("OS ", "").strip(),
        ):
            if key:
                out[str(key).strip().lower()] = it
        sn = (it.get("systemName") or "").strip()
        if sn.startswith("Switch "):
            out[sn.replace("Switch ", "to").lower()] = it
            out[f"to{sn.split()[-1]}".lower()] = it
        iid = it.get("id") or ""
        if "TO" in iid.upper():
            to = iid.upper().split("TO")[-1]
            digits = "".join(ch for ch in to if ch.isdigit())
            if digits:
                out[f"to{digits}"] = it
                out[digits] = it
                out[f"switch {digits}"] = it
        # Mast 24RA style
        for key in (it.get("publicName"), it.get("systemName")):
            if key and "mast" in str(key).lower():
                out[str(key).strip().lower()] = it
                bare = re.sub(r"^mast\s+", "", str(key).strip(), flags=re.I)
                out[bare.lower()] = it
                out[f"mast {bare.lower()}"] = it
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


def match_turnout(by: dict, stations: set[str], blocks: set[str]) -> dict | None:
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


def build() -> dict:
    root = ET.parse(PANEL).getroot()
    tp = root.find("TRACKPLAN")
    sections = tp.findall("SECTION")
    xs = [int(s.get("X")) for s in sections]
    ys = [int(s.get("Y")) for s in sections]
    minx, miny = min(xs), min(ys)

    by = le_by_keys()
    items: list[dict] = []
    seen_masts: set[str] = set()

    for s in sections:
        x, y = int(s.get("X")), int(s.get("Y"))
        x0, y0 = cell_origin(x, y, minx, miny)
        stations: set[str] = set()
        blocks: set[str] = set()
        has_points = False

        for e in s.findall("SEC_EDGE"):
            if e.find("SWITCHPOINTS") is not None:
                has_points = True
            for b in e.findall("BLOCK"):
                if b.get("STATION"):
                    stations.add(b.get("STATION"))
                if b.get("NAME"):
                    blocks.add(b.get("NAME"))

            for sig in e.findall("SECSIGNAL"):
                name = mast_name(sig)
                if not name:
                    continue
                key = name.lower()
                if key in seen_masts:
                    continue
                seen_masts.add(key)
                panel = sig.find("PANELSIGNAL")
                loc = (panel.get("SIGLOCATION") if panel is not None else None) or "CENTER"
                fx, fy = SIG_LOC.get(loc.upper(), SIG_LOC["CENTER"])
                px = x0 + fx * CELL
                py = y0 + fy * CELL
                override = HOTSPOT_OVERRIDE.get(key)
                if override:
                    px, py = override
                match = by.get(key) or by.get(name.lower())
                if not match:
                    bare = re.sub(r"^mast\s+", "", name, flags=re.I).strip().lower()
                    match = by.get(bare) or by.get(f"mast {bare}")
                items.append(
                    {
                        "id": f"cats-sig-{re.sub(r'[^a-zA-Z0-9]+', '-', name).strip('-')}",
                        "kind": "signal",
                        "x": round(px, 1),
                        "y": round(py, 1),
                        "systemName": (match or {}).get("systemName") or name,
                        "publicName": (match or {}).get("publicName") or name,
                        "cp": (match or {}).get("cp") or "",
                        "hardware": (match or {}).get("hardware") or "",
                        "mqtt": (match or {}).get("mqtt") or "",
                        "comment": (match or {}).get("comment")
                        or f"Digicon SECSIGNAL @ cell ({x},{y}) {loc}",
                        "block": (match or {}).get("block") or "",
                    }
                )

        if not has_points:
            continue

        match = match_turnout(by, stations, blocks)
        public = (match or {}).get("publicName")
        if not public:
            for st in stations:
                if st in STATION_TO_SWITCH:
                    public = STATION_TO_SWITCH[st]
                    break
        if not public:
            if stations:
                public = f"Plant {', '.join(sorted(stations))}"
            elif blocks:
                public = sorted(blocks)[0]
            else:
                public = f"Plant ({x},{y})"

        items.append(
            {
                "id": f"cats-to-{x}-{y}",
                "kind": "turnout",
                "x": round(x0 + CELL / 2, 1),
                "y": round(y0 + CELL / 2, 1),
                "systemName": (match or {}).get("systemName") or "",
                "publicName": public,
                "cp": (match or {}).get("cp") or (sorted(stations)[0] if stations else ""),
                "hardware": (match or {}).get("hardware") or "",
                "mqtt": (match or {}).get("mqtt") or "",
                "comment": (match or {}).get("comment")
                or (
                    f"Digicon plant @ {x},{y}; OS {', '.join(sorted(blocks))}"
                    if blocks
                    else f"Digicon plant @ {x},{y}"
                ),
                "block": (match or {}).get("block") or (sorted(blocks)[0] if blocks else ""),
            }
        )

    from PIL import Image

    w, h = Image.open(OUT_IMG).size
    n_to = sum(1 for it in items if it["kind"] == "turnout")
    n_sig = sum(1 for it in items if it["kind"] == "signal")
    return {
        "source": {
            "workspace": "consolidation",
            "panel": "cats/panels/HART_Master_CTC_hold.xml",
            "view": "digicon-cats",
        },
        "image": {
            "path": "assets/layout/HART_cats_digicon.png",
            "width": w,
            "height": h,
            "scale": 1.0,
        },
        "items": items,
        "counts": {
            "turnout": n_to,
            "signal": n_sig,
            "occupancy": 0,
            "sensor": 0,
            "mapped": len(items),
            "total": len(items),
        },
    }


def main() -> int:
    if not PANEL.is_file():
        raise SystemExit(f"missing {PANEL}")
    render()
    payload = build()
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    c = payload["counts"]
    print(
        f"wrote {OUT_JSON.relative_to(CONS)} "
        f"to={c['turnout']} sig={c['signal']} mapped={c['mapped']} "
        f"img={payload['image']['width']}x{payload['image']['height']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
