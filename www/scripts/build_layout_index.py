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
import re
import subprocess
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices as device_master, names, paths, railroad_facts, tables  # noqa: E402
from hartlib.names import row_comment  # noqa: E402

PORTAL = Path(__file__).resolve().parents[1]
ROOT = paths.REPO_ROOT

PANEL = paths.TABLES_XML
NAMES = paths.DEVICES
CPS = paths.LAYOUT_DATA / "schematic" / "control_points_staging.csv"   # with switch_legs.csv: station_group_rows
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
    for _line, row in device_master.name_map_lines(path):
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


def load_devices(path: Path = PANEL):
    """Device rows read from tables.xml: system name -> {kind, userName, mqtt, comment}.

    Covers the layout hardware only: MQTT occupancy and feedback sensors, turnouts
    (MQTT and the DCC mirror), signal heads, signal masts, and the detected track blocks
    (not the hidden throat blocks). Internal lamps, lever and CTC sensors are left out.
    """
    root = tables.read(path)
    out = {}
    pair = {}  # DCC mirror turnout -> its "Node: n Turnout: k" text, to sit beside its MQTT turnout
    address = re.compile(r"^(?:M2[ST]|IH)(\d+)$")  # hardware systems whose number is an MQTT address

    def node_comment(el):
        return tables.text(el, "comment").startswith("Node:")

    def add(el, kind):
        sn = tables.system_name(el)
        m = address.match(sn)
        out[sn] = {
            "kind": kind,
            "userName": tables.user_name(el),
            "mqtt": m.group(1) if m else "",
            "comment": tables.text(el, "comment"),
        }

    detectors = {}  # occupancy sensor user name or system name -> MQTT address ("" for internal sensors)
    for el in tables.sensors(root):
        sn = tables.system_name(el)
        m = address.match(sn)
        number = m.group(1) if m else ""
        detectors[sn] = detectors[tables.user_name(el)] = number
        if m and sn.startswith("M2S") and node_comment(el):
            add(el, "occupancy" if "Block:" in tables.text(el, "comment") else "feedback")
    for el in tables.turnouts(root):
        sn = tables.system_name(el)
        if sn.startswith("M2T"):
            add(el, "turnout")
        elif sn.startswith("MTT"):
            add(el, "lcc turnout")
            pair[sn] = names.first_group(tables.text(el, "comment"))
    for el in tables.signal_heads(root):
        if tables.system_name(el).startswith("IH") and node_comment(el):
            add(el, "signal head")
    for el in tables.masts(root):
        add(el, "signal mast")
    for el in tables.blocks(root):
        if tables.text(el, "comment").startswith("Hidden"):
            continue
        add(el, "os block" if tables.user_name(el).startswith("OS ") else "block")
        out[tables.system_name(el)]["mqtt"] = detectors.get(tables.text(el, "occupancysensor"), "")

    # Address order (node, port), a block or DCC mirror after its sensor or turnout, masts last.
    turnout_at = {names.first_group(d["comment"]): d["mqtt"] for sn, d in out.items() if sn.startswith("M2T")}

    def key(item):
        sn, d = item
        addr = d["mqtt"] or turnout_at.get(pair.get(sn, ""), "")
        late = sn in pair or d["kind"] in ("block", "os block")
        return (int(addr) if addr.isdigit() else 10 ** 9, late, not sn.startswith("IB:AUTO"))

    return dict(sorted(out.items(), key=key))


def load_cps(path: Path, legs: Path = paths.LAYOUT_DATA / "switch_legs.csv"):
    """(OS block number, control point) pairs, e.g. ("23a", "East End"), from staging's control points."""
    pairs = []
    for row in railroad_facts.station_group_rows(path, legs):
        for part in row["switches"].split(","):
            if part:
                pairs.append((part, row["cp_name"]))
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
    # a failed render must stop the run: the JSON records the render inputs, so --check would pass on an old PNG
    if subprocess.run(cmd).returncode:
        raise SystemExit(f"render failed: {RENDER.name} {PANEL}")


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
    devices = load_devices(PANEL)
    by_user = {d["userName"]: sn for sn, d in devices.items() if d["userName"]}
    on_panel = set()  # device system names already drawn from the panel, so no dev- item repeats them
    cps = load_cps(CPS)
    items = []

    for i, t in enumerate(turnouts):
        tn = t.get("tn") or ""
        rec = by_hw.get(tn) or {}
        dsn = tn if tn in devices else by_user.get(tn, "")
        on_panel.add(dsn)
        if not rec:
            un = (devices.get(dsn) or {}).get("userName") or ""
            rec = by_name.get(un) or {}
        public = rec.get("proposed") or rec.get("current") or tn or t.get("ident")
        block = t.get("block") or ""
        cp = cp_for(public, cps, rec.get("cp") or "")
        if not cp and block.startswith("OS "):
            cp = block
        dev = devices.get(dsn) or {}
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
        on_panel.add(mast if mast in devices else by_user.get(mast, ""))
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

    for sn, dev in devices.items():
        if sn in on_panel:
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
            # the checkout's file, also when HART_TABLES points PANEL at a candidate copy elsewhere
            "panel": paths.rel(paths.REPO_TABLES_XML),
            "names": str(NAMES.relative_to(ROOT)),
            "devices": paths.rel(paths.REPO_TABLES_XML),
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
    if not args.check:
        # never render the public site's schematic from a HART_TABLES candidate the owner has not approved
        paths.exit_if_overridden(Path(__file__).name)
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
