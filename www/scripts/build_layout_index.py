#!/usr/bin/env python3
"""Build the www layout index from live repo data.

    python3 www/scripts/build_layout_index.py          # render the PNG, stamp it, write the local JSON
    python3 www/scripts/build_layout_index.py --check  # build in memory; exit 1 if a check fails

Uses the same LE geometry + overview transform as jmri/layouts/hart/scripts/render_le_layout.py
so hotspot pixels align with assets/layout/HART_le_schematic.png.

www/data/layout-index.json is built where it is used, not committed (ADR-036): the site build
(prepare_github_pages.py, through site_views.py) and the local preview (serve_portal.py, make site-data) call
index_text(). The PNG stays committed; it carries the hash of what it is drawn from (png_stamp.py), so --check
finds a PNG that needs re-rendering without drawing it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices as device_master, names, paths, railroad_facts, tables  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import png_stamp  # noqa: E402

PORTAL = Path(__file__).resolve().parents[1]
ROOT = paths.REPO_ROOT

PANEL = paths.TABLES_XML
NAMES = device_master.MASTER
STATIONS = paths.LAYOUT_DATA / "schematic" / "stations.csv"   # its desk areas, with switches.csv: station_group_rows
OUT_JSON = PORTAL / "data/layout-index.json"
SCHEMATIC = PORTAL / "assets/layout/HART_le_schematic.png"
RENDER = paths.LAYOUT_SCRIPTS / "render_le_layout.py"

PAD = 34
TOP = 78
TARGET_W = 2000
BUILD = "python3 www/scripts/build_layout_index.py"


class LayoutIndexError(Exception):
    """The layout index cannot be built, or what was built fails a check; the message says why."""


def load_render_mod():
    spec = importlib.util.spec_from_file_location("render_le_layout", RENDER)
    if spec is None or spec.loader is None:
        raise LayoutIndexError(f"cannot load {RENDER}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_names(path: Path):
    """({system name: record}, {user name: record}) of staging's rows of the device master: its user name (current and
    proposed, as the page keys them), cp, system name (hardware) and JMRI comment (hartlib.devices.comment_of)."""
    by_hw, by_name = {}, {}
    for row in device_master.load(path):
        if row["level"] != railroad_facts.STAGING_LEVEL:
            continue
        rec = {
            "current": row["user_name"],
            "proposed": row["user_name"],
            "cp": row["cp"],
            "hardware": row["system_name"],
            "comment": device_master.comment_of(row),
        }
        if row["system_name"]:
            by_hw.setdefault(row["system_name"], rec)
        by_name.setdefault(row["user_name"], rec)
    return by_hw, by_name


def load_devices(path: Path = PANEL, master_files: "device_master.Files | None" = None):
    """Device rows read from tables.xml: system name -> {kind, userName, mqtt, comment}. A block's kind is its row's
    role in the device master (`master_files`, the repo's when None), never its name.

    Covers the layout hardware only: MQTT occupancy and feedback sensors, turnouts
    (MQTT and the DCC mirror), signal heads, signal masts, and the detected track blocks
    (not the hidden throat blocks). Internal lamps, lever and CTC sensors are left out.
    """
    root = tables.read(path)
    master = device_master.index(master_files)
    out = {}
    pair = {}  # DCC mirror turnout -> its "Node: n Turnout: k" text, to sit beside its MQTT turnout
    address = re.compile(r"^(?:M2[ST]|IH)(\d+)$")  # hardware systems whose number is an MQTT address

    def node_comment(el):
        # "Node: ..." first, or after a wired head's place ("Plane | Switch 5 | Node: 4 ...")
        return re.search(r"(?:^| \| )Node: ", tables.text(el, "comment")) is not None

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
        # its kind is its device-master role, never its name (hand-off row 8)
        # a device not on the layout yet (no level, no role: its beans come from its jmri_bean) is a plain block
        name = tables.user_name(el)
        add(el, "block" if master.is_unplaced("block", name) or not master.is_os(name) else "os block")
        out[tables.system_name(el)]["mqtt"] = detectors.get(tables.text(el, "occupancysensor"), "")

    # Address order (node, port), a block or DCC mirror after its sensor or turnout, masts last.
    turnout_at = {names.first_group(d["comment"]): d["mqtt"] for sn, d in out.items() if sn.startswith("M2T")}

    def key(item):
        sn, d = item
        addr = d["mqtt"] or turnout_at.get(pair.get(sn, ""), "")
        late = sn in pair or d["kind"] in ("block", "os block")
        return (int(addr) if addr.isdigit() else 10 ** 9, late, not sn.startswith("IB:AUTO"))

    return dict(sorted(out.items(), key=key))


def load_cps(path: Path, switches: Path = paths.LAYOUT_DATA / "switches.csv"):
    """(OS block number, control point) pairs, e.g. ("23a", "East End"), from the desk areas of stations.csv, every
    level's (staging's only so far; a switch number is unique railroad-wide, so the levels cannot mix)."""
    pairs = []
    for row in railroad_facts.station_group_rows(path, switches):
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
        raise LayoutIndexError(f"no geometry in {PANEL}")
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
    # a failed render must stop the run: the stamp records the render inputs, so --check would pass on an old PNG
    if subprocess.run(cmd).returncode:
        raise LayoutIndexError(f"render failed: {RENDER.name} {PANEL}")


def render_inputs_sha256(geometry) -> str:
    """What the schematic PNG is drawn from: the panel geometry the renderer reads, and the renderer.

    Recorded in the PNG (png_stamp) and the JSON so --check finds a PNG that needs re-rendering without drawing it
    (the renderer's fonts differ by machine, so its pixels cannot be compared in CI).
    """
    h = hashlib.sha256(repr(geometry).encode("utf-8"))
    h.update(RENDER.read_bytes())
    return h.hexdigest()


def build():
    """The layout index from its sources. LayoutIndexError when a source is missing or cannot be read (a tables.xml
    that is not XML, a device master or stations.csv hartlib refuses)."""
    try:
        return _build()
    except (ET.ParseError, railroad_facts.FactsError, ValueError, OSError) as err:
        raise LayoutIndexError(f"cannot build the layout index from its sources: {type(err).__name__}: {err}") from None


def _build():
    for path, what in ((PANEL, "panel"), (NAMES, "names"), (STATIONS, "stations")):
        if not path.is_file():
            raise LayoutIndexError(f"missing {what}: {path}")
    if not SCHEMATIC.is_file():
        raise LayoutIndexError(f"missing {paths.rel(SCHEMATIC)}: run {BUILD} to render it, and commit it")
    mod = load_render_mod()
    geometry = mod.load_geometry(PANEL)
    _pp, _legs, turnouts, segs, signals, stations = geometry
    X, Y, _width, _height, scale = overview_xy(turnouts, segs, signals, stations)

    by_hw, by_name = load_names(NAMES)
    devices = load_devices(PANEL)
    by_user = {d["userName"]: sn for sn, d in devices.items() if d["userName"]}
    on_panel = set()  # device system names already drawn from the panel, so no dev- item repeats them
    cps = load_cps(STATIONS)
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

    try:
        width, height = png_stamp.size(SCHEMATIC)  # the PNG the hotspots sit on
    except png_stamp.PngError as err:
        raise LayoutIndexError(str(err)) from None

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


def problems(payload: dict) -> list[str]:
    """What is wrong with a built index: no items, counts that do not add up, repeated ids, or a PNG whose stamp is
    not the hash of what it is drawn from now (re-render it)."""
    out = []
    items = payload.get("items") or []
    if not items:
        out.append("the index has no items")
    ids = [it.get("id") for it in items]
    if len(set(ids)) != len(ids):
        out.append("repeated item ids: " + ", ".join(sorted({i for i in ids if ids.count(i) > 1}, key=str)[:10]))
    counts = payload.get("counts") or {}
    if counts.get("total") != len(items):
        out.append(f"counts.total is {counts.get('total')}, the index has {len(items)} items")
    if not counts.get("mapped"):
        out.append("no item has a place on the schematic (counts.mapped is 0)")
    want = (payload.get("image") or {}).get("inputs_sha256")
    try:
        have = png_stamp.stamp(SCHEMATIC)
    except png_stamp.PngError as err:
        out.append(str(err))
    else:
        if have != want:
            out.append(f"{paths.rel(SCHEMATIC)} was drawn from other inputs (its stamp is {have}, they hash to "
                       f"{want}): run {BUILD} and commit the PNG")
    return out


def index_text(payload: dict | None = None) -> str:
    """The checked layout-index.json text of `payload` (built now when None). LayoutIndexError when it cannot be
    built or fails a check."""
    payload = build() if payload is None else payload
    bad = problems(payload)
    if bad:
        raise LayoutIndexError(f"{paths.rel(OUT_JSON)} fails its checks:\n  " + "\n  ".join(bad))
    return json.dumps(payload, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="build in memory and write nothing; exit 1 if the index fails a check or the PNG "
                         "(by its render stamp) is stale")
    args = ap.parse_args(argv)
    if not args.check:
        # never render the public site's schematic from a HART_TABLES candidate the owner has not approved
        paths.exit_if_overridden(Path(__file__).name)
    try:
        if args.check:
            text = index_text()
            print(f"{paths.rel(OUT_JSON)} builds and passes its checks "
                  f"({len(json.loads(text)['items'])} items, the PNG's render stamp is current)")
            return 0
        refresh_schematic()
        payload = build()
        png_stamp.write_stamp(SCHEMATIC, payload["image"]["inputs_sha256"])
        text = index_text(payload)
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(text, encoding="utf-8")
    except (LayoutIndexError, png_stamp.PngError, OSError) as err:
        print(err, file=sys.stderr)
        return 1
    c = json.loads(text)["counts"]
    print(f"wrote {paths.rel(SCHEMATIC)} (to commit) and {paths.rel(OUT_JSON)} (not committed) "
          f"total={c['total']} mapped={c['mapped']} to={c['turnout']} sig={c['signal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
