#!/usr/bin/env python3
"""Build Digicon/CATS device-map hotspots for the operator portal.

Renders cats/panels/HART_ctc.xml and places clickable plants on every SECTION
that has SWITCHPOINTS. Station / OS names are joined to the consolidation
layout-index (and LE turnout names) so the detail pane still shows MQTT /
hardware when we know the mapping.
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
CONS = PORTAL.parent
ROOT = CONS.parent
PANEL = ROOT / "cats/panels/HART_ctc.xml"
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
        # TO111 / Switch 23 style bridges
        sn = (it.get("systemName") or "").strip()
        if sn.startswith("Switch "):
            out[sn.replace("Switch ", "to").lower()] = it
            out[f"to{sn.split()[-1]}".lower()] = it
        iid = (it.get("id") or "")
        # ids look like "to-TO111" from the LE builder
        if "TO" in iid.upper():
            to = iid.upper().split("TO")[-1]
            digits = "".join(ch for ch in to if ch.isdigit())
            if digits:
                out[f"to{digits}"] = it
                out[digits] = it
                out[f"switch {digits}"] = it
    return out

def build() -> dict:
    root = ET.parse(PANEL).getroot()
    tp = root.find("TRACKPLAN")
    sections = tp.findall("SECTION")
    xs = [int(s.get("X")) for s in sections]
    ys = [int(s.get("Y")) for s in sections]
    minx, miny = min(xs), min(ys)

    by = le_by_keys()
    items = []
    for s in sections:
        x, y = int(s.get("X")), int(s.get("Y"))
        if not any(e.find("SWITCHPOINTS") is not None for e in s.findall("SEC_EDGE")):
            continue
        stations: set[str] = set()
        blocks: set[str] = set()
        for e in s.findall("SEC_EDGE"):
            for b in e.findall("BLOCK"):
                if b.get("STATION"):
                    stations.add(b.get("STATION"))
                if b.get("NAME"):
                    blocks.add(b.get("NAME"))
        # cell center in rendered image pixels (must match render_cats_panel.py)
        px = PAD_X + (x - minx) * CELL + CELL / 2
        py = PAD_Y + (y - miny) * CELL + CELL / 2

        match = None
        for st in stations:
            pref = STATION_TO_SWITCH.get(st)
            if pref:
                match = by.get(pref.lower()) or by.get(f"to{st}")
            if not match:
                match = by.get(f"to{st}") or by.get(st.lower()) or by.get(f"switch {st}")
            if match:
                break
        if not match:
            for bl in blocks:
                match = by.get(bl.lower()) or by.get(bl.replace("OS ", "").lower())
                if match:
                    break

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
                "id": f"cats-{x}-{y}",
                "kind": "turnout",
                "x": round(px, 1),
                "y": round(py, 1),
                "systemName": (match or {}).get("systemName") or "",
                "publicName": public,
                "cp": (match or {}).get("cp") or (sorted(stations)[0] if stations else ""),
                "hardware": (match or {}).get("hardware") or "",
                "mqtt": (match or {}).get("mqtt") or "",
                "comment": (match or {}).get("comment")
                or (f"CATS Digicon plant @ {x},{y}; OS {', '.join(sorted(blocks))}" if blocks else f"CATS plant @ {x},{y}"),
                "block": (match or {}).get("block") or (sorted(blocks)[0] if blocks else ""),
            }
        )

    from PIL import Image

    w, h = Image.open(OUT_IMG).size
    return {
        "source": {
            "workspace": "consolidation",
            "panel": "cats/panels/HART_ctc.xml",
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
            "turnout": len(items),
            "signal": 0,
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
    print(
        f"wrote {OUT_JSON.relative_to(CONS)} "
        f"plants={payload['counts']['mapped']} "
        f"img={payload['image']['width']}x{payload['image']['height']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
