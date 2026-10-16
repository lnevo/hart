#!/usr/bin/env python3
"""Build consolidation/ops-portal layout index from consolidation SoR only.

Uses the same LE geometry + overview transform as cats/scripts/render_le_layout.py
so hotspot pixels align with assets/layout/HART_le_schematic.png.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
CONS = PORTAL.parent
ROOT = CONS.parent

PANEL = CONS / "external/hart-runtime/jmri/layouts/hart/output/hart_prod.xml"
NAMES = CONS / "sor/names/public_name_map.csv"
DEVICES = CONS / "sor/names/hart_devices_review.json"
CPS = CONS / "external/hart-runtime/jmri/layouts/hart/data/control_points.csv"
MAPS_SRC = CONS / "external/hart-ops/publications/assets"
OUT_JSON = PORTAL / "data/layout-index.json"
SCHEMATIC = PORTAL / "assets/layout/HART_le_schematic.png"
MAPS_DST = PORTAL / "assets/maps"
RENDER = ROOT / "cats/scripts/render_le_layout.py"

PAD = 34
TOP = 78
TARGET_W = 2000


def load_render_mod():
    spec = importlib.util.spec_from_file_location("render_le_layout", RENDER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {RENDER}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_names(path: Path):
    by_hw, by_name = {}, {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            hist = "historical" in (row.get("notes") or "").lower()
            hw = (row.get("hardware") or "").strip()
            current = (row.get("current") or "").strip()
            proposed = (row.get("proposed") or "").strip()
            rec = {
                "current": current,
                "proposed": proposed,
                "cp": row.get("cp") or "",
                "hardware": hw,
                "comment": row.get("comment") or "",
                "historical": hist,
            }

            def prefer(store, key):
                if not key:
                    return
                prev = store.get(key)
                if prev is None or (prev.get("historical") and not hist):
                    store[key] = rec

            prefer(by_hw, hw)
            prefer(by_name, current)
            prefer(by_name, proposed)
    return by_hw, by_name


def load_devices(path: Path):
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("devices") or []
    return {
        (r.get("systemName") or "").strip(): r
        for r in rows
        if (r.get("systemName") or "").strip()
    }


def load_cps(path: Path):
    pairs = []
    if not path.is_file():
        return pairs
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cp = (row.get("cp_name") or row.get("cp") or "").strip()
            for part in str(row.get("switches") or "").replace(";", ",").split(","):
                part = part.strip()
                if part:
                    pairs.append((part, cp))
    return pairs


def cp_for(public: str, pairs, fallback: str) -> str:
    if fallback:
        return fallback
    bare = public.replace("Switch ", "").strip()
    for token, cp in pairs:
        if token == bare or token in public:
            return cp
    return ""


def overview_xy(turnouts, segs, signals, stations):
    """Match render_le_layout.render_view overview window (xmin=None)."""
    pts = []
    for a, b, _m, _bl in segs:
        pts += [a, b]
    for t in turnouts:
        pts.append(t["cen"])
    for s in signals:
        pts.append((s["x"], s["y"]))
    for s in stations:
        pts.append((s["x"], s["y"]))
    if not pts:
        raise SystemExit("no geometry")
    bx0 = min(p[0] for p in pts) - PAD
    bx1 = max(p[0] for p in pts) + PAD
    by0 = min(p[1] for p in pts) - PAD
    by1 = max(p[1] for p in pts) + PAD
    scale = max((TARGET_W - 2 * PAD) / (bx1 - bx0), 1.0)
    width = int((bx1 - bx0) * scale + 2 * PAD)
    height = int((by1 - by0) * scale + TOP + PAD)

    def X(v):
        return PAD + (v - bx0) * scale

    def Y(v):
        return TOP + (v - by0) * scale

    return X, Y, width, height, scale


def refresh_schematic():
    SCHEMATIC.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(RENDER), str(PANEL), str(SCHEMATIC)]
    print("render:", " ".join(cmd))
    subprocess.run(cmd, check=False)


def sync_maps():
    MAPS_DST.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in sorted(MAPS_SRC.glob("station_map_*.png")):
        shutil.copy2(src, MAPS_DST / src.name)
        n += 1
    panel = MAPS_SRC / "dispatcher_panel_neville_island.png"
    if panel.is_file():
        shutil.copy2(panel, PORTAL / "assets/layout/dispatcher_panel_neville_island.png")
    print(f"copied {n} station maps")


def build():
    mod = load_render_mod()
    _pp, _legs, turnouts, segs, signals, stations = mod.load_geometry(PANEL)
    X, Y, width, height, scale = overview_xy(turnouts, segs, signals, stations)

    by_hw, by_name = load_names(NAMES)
    devices = load_devices(DEVICES)
    cps = load_cps(CPS)
    items = []

    for i, t in enumerate(turnouts):
        tn = t.get("tn") or ""
        rec = by_hw.get(tn) or {}
        if not rec:
            un = (devices.get(tn) or {}).get("userName") or ""
            rec = by_name.get(un) or {}
        public = rec.get("proposed") or rec.get("current") or tn or t.get("ident")
        block = t.get("block") or ""
        cp = cp_for(public, cps, rec.get("cp") or "")
        if not cp and block.startswith("OS "):
            cp = block
        dev = devices.get(tn) or {}
        items.append(
            {
                "id": f"to-{t.get('ident') or i}",
                "kind": "turnout",
                "x": round(X(t["cen"][0]), 1),
                "y": round(Y(t["cen"][1]), 1),
                "systemName": tn,
                "publicName": public,
                "cp": cp,
                "hardware": rec.get("hardware") or tn,
                "mqtt": str(dev.get("mqtt") or ""),
                "comment": rec.get("comment") or (dev.get("comment") or ""),
                "block": block,
            }
        )

    for i, s in enumerate(signals):
        mast = s.get("name") or ""
        rec = by_name.get(mast) or by_hw.get(mast) or {}
        public = rec.get("proposed") or rec.get("current") or mast
        items.append(
            {
                "id": f"sig-{i}",
                "kind": "signal",
                "x": round(X(s["x"]), 1),
                "y": round(Y(s["y"]), 1),
                "systemName": mast,
                "publicName": public,
                "cp": rec.get("cp") or "",
                "hardware": rec.get("hardware") or "",
                "mqtt": "",
                "comment": rec.get("comment") or "",
                "block": "",
            }
        )

    mapped = {it["systemName"] for it in items if it.get("systemName")}
    for sn, dev in devices.items():
        if sn in mapped:
            continue
        kind_raw = (dev.get("kind") or "").lower()
        if "turnout" in kind_raw:
            kind = "turnout"
        elif "signal" in kind_raw or "mast" in kind_raw or "head" in kind_raw:
            kind = "signal"
        elif "occup" in kind_raw or "block" in kind_raw:
            kind = "occupancy"
        else:
            kind = "sensor"
        un = (dev.get("userName") or sn).strip()
        rec = by_hw.get(sn) or by_name.get(un) or {}
        items.append(
            {
                "id": f"dev-{sn}",
                "kind": kind,
                "x": None,
                "y": None,
                "systemName": sn,
                "publicName": rec.get("proposed") or rec.get("current") or un,
                "cp": rec.get("cp") or "",
                "hardware": rec.get("hardware") or sn,
                "mqtt": str(dev.get("mqtt") or ""),
                "comment": rec.get("comment") or (dev.get("comment") or ""),
                "block": "",
            }
        )

    # Prefer actual PNG size after render
    if SCHEMATIC.is_file():
        try:
            from PIL import Image

            width, height = Image.open(SCHEMATIC).size
        except Exception:
            pass

    return {
        "source": {
            "workspace": "consolidation",
            "panel": str(PANEL.relative_to(CONS)),
            "names": str(NAMES.relative_to(CONS)),
            "devices": str(DEVICES.relative_to(CONS)) if DEVICES.is_file() else None,
        },
        "image": {
            "path": "assets/layout/HART_le_schematic.png",
            "width": width,
            "height": height,
            "scale": scale,
        },
        "items": items,
        "counts": {
            "turnout": sum(1 for it in items if it["kind"] == "turnout"),
            "signal": sum(1 for it in items if it["kind"] == "signal"),
            "occupancy": sum(1 for it in items if it["kind"] == "occupancy"),
            "sensor": sum(1 for it in items if it["kind"] == "sensor"),
            "mapped": sum(1 for it in items if it.get("x") is not None),
            "total": len(items),
        },
    }


def main() -> int:
    if not PANEL.is_file():
        raise SystemExit(f"missing panel: {PANEL}")
    if not NAMES.is_file():
        raise SystemExit(f"missing names: {NAMES}")
    refresh_schematic()
    sync_maps()
    payload = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    c = payload["counts"]
    print(
        f"wrote {OUT_JSON.relative_to(CONS)} "
        f"total={c['total']} mapped={c['mapped']} "
        f"to={c['turnout']} sig={c['signal']} "
        f"img={payload['image']['width']}x{payload['image']['height']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
