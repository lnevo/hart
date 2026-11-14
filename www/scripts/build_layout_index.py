#!/usr/bin/env python3
"""Build the www layout index from live repo data.

Uses the same LE geometry + overview transform as jmri/layouts/hart/scripts/render_le_layout.py
so hotspot pixels align with assets/layout/HART_le_schematic.png.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402
from hartlib.names import row_comment  # noqa: E402

PORTAL = Path(__file__).resolve().parents[1]
ROOT = paths.REPO_ROOT

PANEL = paths.TABLES_XML
NAMES = paths.PUBLIC_NAME_MAP
DEVICES = PORTAL / "review-data/hart_devices_review.json"
CPS = paths.LAYOUT_DATA / "control_points.csv"
OUT_JSON = PORTAL / "data/layout-index.json"
SCHEMATIC = PORTAL / "assets/layout/HART_le_schematic.png"
RENDER = paths.LAYOUT_SCRIPTS / "render_le_layout.py"

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
                "comment": row_comment(row),
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


def render_inputs_sha256(geometry) -> str:
    """What the schematic PNG is drawn from: the panel geometry the renderer reads, and the renderer.

    Recorded in the JSON so --check finds a PNG that needs re-rendering without drawing it
    (the renderer's fonts differ by machine, so its pixels cannot be compared in CI).
    """
    h = hashlib.sha256(repr(geometry).encode("utf-8"))
    h.update(RENDER.read_bytes())
    return h.hexdigest()


def build():
    mod = load_render_mod()
    geometry = mod.load_geometry(PANEL)
    _pp, _legs, turnouts, segs, signals, stations = geometry
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
            "workspace": "hart",
            "panel": str(PANEL.relative_to(ROOT)),
            "names": str(NAMES.relative_to(ROOT)),
            "devices": str(DEVICES.relative_to(ROOT)) if DEVICES.is_file() else None,
        },
        "image": {
            "path": "assets/layout/HART_le_schematic.png",
            "width": width,
            "height": height,
            "scale": scale,
            "inputs_sha256": render_inputs_sha256(geometry),
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="build without rendering or writing; exit 1 if layout-index.json or the PNG "
                         "(by its recorded render inputs) is stale")
    args = ap.parse_args(argv)
    if not PANEL.is_file():
        raise SystemExit(f"missing panel: {PANEL}")
    if not NAMES.is_file():
        raise SystemExit(f"missing names: {NAMES}")
    if args.check:
        want = json.dumps(build(), indent=2) + "\n"
        have = OUT_JSON.read_text(encoding="utf-8") if OUT_JSON.is_file() else ""
        if want != have:
            print(f"{OUT_JSON.relative_to(ROOT)} or {SCHEMATIC.relative_to(ROOT)} is stale: run "
                  "python3 www/scripts/build_layout_index.py and commit both", file=sys.stderr)
            return 1
        print(f"{OUT_JSON.relative_to(ROOT)} is current")
        return 0
    refresh_schematic()
    payload = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    c = payload["counts"]
    print(
        f"wrote {OUT_JSON.relative_to(ROOT)} "
        f"total={c['total']} mapped={c['mapped']} "
        f"to={c['turnout']} sig={c['signal']} "
        f"img={payload['image']['width']}x{payload['image']['height']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
