#!/usr/bin/env python3
"""
Build turnout_mapping.csv and sensor_mapping.csv for linear4 ↔ live tables.xml.

Matches the 18 linear4 layout turnouts to live devices (16 MQTT + 2 crossover
internal legs using MQTT feedback + optional TO_CO double crossover) by x-position
on the main line (live MQTT band y≈375 aligns with linear4 geometry by x).

Usage:
  python3 jmri/scripts/build_linear4_device_mapping.py
  python3 jmri/scripts/build_linear4_device_mapping.py --write-panel
  python3 jmri/scripts/build_linear4_device_mapping.py --write-panel --dcc-label-placement split
  JMRI_LAYOUT=linear5 python3 jmri/scripts/build_linear4_device_mapping.py --layout linear5 \\
    --import-prod-geometry --write-panel --write-prod-panel --dcc-label-placement split
"""
from __future__ import annotations

import argparse
import copy
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _munkres(cost: list[list[float]]) -> list[tuple[int, int]]:
    """Hungarian algorithm (min-cost bipartite matching)."""
    n_rows, n_cols = len(cost), len(cost[0])
    n = max(n_rows, n_cols)
    c = [[0.0] * n for _ in range(n)]
    for i in range(n_rows):
        for j in range(n_cols):
            c[i][j] = cost[i][j]
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [float("inf")] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = 0
            for j in range(1, n + 1):
                if used[j]:
                    continue
                cur = c[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    pairs = []
    for j in range(1, n + 1):
        if p[j] <= n_rows and j <= n_cols:
            pairs.append((p[j] - 1, j - 1))
    return pairs

JMRI_ROOT = Path(__file__).resolve().parents[1]
JMRI_SCRIPTS = Path(__file__).resolve().parent
REPO_ROOT = JMRI_ROOT.parent
sys.path.insert(0, str(JMRI_SCRIPTS))
from apply_blocks_to_panel import (  # noqa: E402
    LABEL_STANDARD_FONT,
    LABEL_STANDARD_FONTNAME,
    LABEL_STANDARD_SIZE,
    LABEL_STANDARD_STYLE,
    apply_layout_defaults,
    remove_icon_positionable_labels,
)
LIVE_PANEL = REPO_ROOT / "tables.xml"

# Defaults (linear4); overridden by _activate_layout().
ACTIVE_LAYOUT = "linear4"
LINEAR4_GEOM = REPO_ROOT / "linear4.xml"
LINEAR4_BLOCKED = JMRI_ROOT / "layouts/linear4/output/linear4_blocked.xml"
OUT_DIR = JMRI_ROOT / "layouts/linear4/data"
TURNOUT_MAPPING_CSV = OUT_DIR / "turnout_mapping.csv"
OUT_PANEL = JMRI_ROOT / "layouts/linear4/output/linear4_devices.xml"
OUT_PROD_PANEL = JMRI_ROOT / "layouts/linear4/output/linear4_prod.xml"
PANEL_BG_ASSET = JMRI_ROOT / "layouts/linear4/assets/linear4_panel_bg.png"
PANEL_BG_PREF_URL = "preference:/linear4_panel_bg.png"
PANEL_LAYOUT_NAME = "linear4"


def _activate_layout(name: str) -> None:
    """Point paths at linear4 or linear5 layout folders."""
    global ACTIVE_LAYOUT, LINEAR4_GEOM, LINEAR4_BLOCKED, OUT_DIR
    global TURNOUT_MAPPING_CSV, OUT_PANEL, OUT_PROD_PANEL
    global PANEL_BG_ASSET, PANEL_BG_PREF_URL, PANEL_LAYOUT_NAME
    global DCC_LABEL_PLACEMENT_JSON, LAYOUT_AREA_LABELS_JSON, VIEWPORT_JSON, TRACK_LABELS_JSON

    if name not in ("linear4", "linear5"):
        raise SystemExit(f"Unknown --layout {name!r} (choose: linear4, linear5)")

    ACTIVE_LAYOUT = name
    base = JMRI_ROOT / "layouts" / name
    blocked = base / "output" / f"{name}_blocked.xml"
    OUT_DIR = base / "data"
    TURNOUT_MAPPING_CSV = OUT_DIR / "turnout_mapping.csv"
    OUT_PANEL = base / "output" / f"{name}_devices.xml"
    OUT_PROD_PANEL = base / "output" / f"{name}_prod.xml"
    PANEL_LAYOUT_NAME = "My Layout" if name == "linear5" else name
    if name == "linear5":
        PANEL_BG_ASSET = base / "assets" / "linear5_panel_bg.jpg"
        # JMRI resolves under UserFiles/resources/misc/ (see reference/tables.xml).
        PANEL_BG_PREF_URL = "preference:resources/misc/linear5_panel_bg.jpg"
    else:
        PANEL_BG_ASSET = JMRI_ROOT / "layouts/linear4/assets/linear4_panel_bg.png"
        PANEL_BG_PREF_URL = "preference:/linear4_panel_bg.png"

    if name == "linear4":
        LINEAR4_GEOM = REPO_ROOT / "linear4.xml"
        LINEAR4_BLOCKED = blocked
    else:
        if not blocked.is_file():
            raise SystemExit(f"Missing {blocked} — save manual geometry in JMRI first")
        LINEAR4_GEOM = blocked
        LINEAR4_BLOCKED = blocked
    _refresh_data_paths()
# LayoutEditor RGB fallback when preference image is not installed (light sky blue)
PANEL_BG_RGB = ("186", "210", "235")

# linear4 main line x extent (EB70 ≈ 67 … TOL29 ≈ 1099)
LINEAR4_X_MIN = 150.0
LINEAR4_X_MAX = 1150.0
LINEAR4_Y_MAINLINE = (140.0, 225.0)

# Authoritative linear4 ident → panel turnoutname (unique M2T*; IT* for crossover slave legs).
CURATED_PANEL_SYSTEM: dict[str, str] = {
    "TOL38": "M2T409",
    "TOL3": "M2T408",
    "TOL42": "M2T410",
    "TOR14": "M2T308",
    "TOL15": "M2T309",
    "TOL17": "M2T310",
    "TOL19": "M2T311",
    "TOR11": "M2T1208",
    "TOR9": "M2T1209",
    "TOR7": "M2T1210",
    "TOL6": "M2T1211",
    "TOR31": "M2T1212",
    "TOR32": "IT36",  # internal leg; motor M2T1212 (paired with TOR31)
    "TOL23": "M2T1213",
    "TOL2": "M2T108",
    "TOL1": "IT1",  # internal leg; motor M2T108 (paired with TOL2)
    "TOR36": "M2T109",
    "TOL29": "M2T110",
}

# Operator switch ID (MQTT Switch group-number) → DCC turnout address.
SWITCH_DCC_ADDRESS: dict[str, int] = {
    "4-8": 100,
    "4-9": 101,
    "4-10": 102,
    "3-8": 103,
    "3-9": 104,
    "3-10": 105,
    "3-11": 106,
    "12-8": 107,
    "12-9": 108,
    "12-10": 109,
    "12-11": 110,
    "12-12": 111,
    "12-13": 112,
    "1-8": 113,
    "1-9": 114,
    "1-10": 115,
    "4-11": 116,
    "13-8": 117,
    "13-9": 118,
    "13-10": 119,
}

# DCC label Y offset from turnout center (negative = above, positive = below track).
DCC_LABEL_PLACEMENT_PRESETS: dict[str, dict] = {
    "uniform": {"default": -14},
    "split": {
        # Shared row above track (not tied to each turnout ycen).
        "fixed_y": {100: 138, 101: 138, 111: 138, 113: 138},
        # TOL42 / SW4-10: midway between turnout center and signal mast below it.
        "between_mast": frozenset({102}),
        "above": frozenset({115}),
        "above_offset": -26,
        # Main line: below track (west uses turnout+20; east cluster +13 to match visual line of 103–106).
        "below": frozenset({103, 104, 105, 106}),
        "below_offset": 20,
        "below_east": frozenset({107, 108, 109, 110, 112, 114}),
        "below_east_offset": 13,
        "default": -14,
    },
}
DCC_LABEL_PLACEMENT_JSON = OUT_DIR / "dcc_label_placement.json"
LAYOUT_AREA_LABELS_JSON = OUT_DIR / "layout_area_labels.json"
VIEWPORT_JSON = OUT_DIR / "viewport.json"
TRACK_LABELS_JSON = OUT_DIR / "track_labels.json"

_LAYOUT_COORD_ATTRS = frozenset(
    {"x", "y", "xa", "xb", "xc", "xd", "xcen", "ya", "yb", "yc", "yd", "ycen"}
)
# JMRI schema: these LayoutEditor children require integer x/y (not 388.5 after 1.5× scale).
_INTEGER_COORD_TAGS = frozenset(
    {"positionablepoint", "signalmasticon", "positionablelabel"}
)
_LAYOUT_DIM_FLOAT_ATTRS = (
    "turnoutbx",
    "turnoutcx",
    "turnoutwid",
    "xoverlong",
    "xoverhwid",
    "xovershort",
)


def _refresh_data_paths() -> None:
    global DCC_LABEL_PLACEMENT_JSON, LAYOUT_AREA_LABELS_JSON, VIEWPORT_JSON, TRACK_LABELS_JSON
    DCC_LABEL_PLACEMENT_JSON = OUT_DIR / "dcc_label_placement.json"
    LAYOUT_AREA_LABELS_JSON = OUT_DIR / "layout_area_labels.json"
    VIEWPORT_JSON = OUT_DIR / "viewport.json"
    TRACK_LABELS_JSON = OUT_DIR / "track_labels.json"


def _fmt_layout_coord(value: float) -> str:
    rounded = round(value, 2)
    return str(int(rounded)) if rounded == int(rounded) else str(rounded)


def _local_tag(elem: ET.Element) -> str:
    return (elem.tag or "").split("}")[-1].lower()


def _scaled_coord_str(value: float, factor: float, *, as_integer: bool) -> str:
    scaled = float(value) * factor
    if as_integer:
        return str(int(round(scaled)))
    return _fmt_layout_coord(scaled)


def _remove_embedded_positionable_labels(layout: ET.Element) -> int:
    """blocked.xml is geometry-only; strip stale labels before prod build."""
    removed = 0
    for child in list(layout):
        if (child.tag or "").strip().lower() == "positionablelabel":
            layout.remove(child)
            removed += 1
    return removed


def _remove_embedded_signalmast_icons(layout: ET.Element) -> int:
    """blocked.xml must not carry signal mast icons; build adds one."""
    removed = 0
    for child in list(layout):
        if _local_tag(child) == "signalmasticon":
            layout.remove(child)
            removed += 1
    return removed


def _load_viewport() -> dict:
    if not VIEWPORT_JSON.is_file():
        return {}
    import json

    return json.loads(VIEWPORT_JSON.read_text(encoding="utf-8"))


def _load_display_scale() -> float:
    """Optional per-layout factor to bake JMRI zoom into panel output (linear5: 1.5)."""
    scale = float(_load_viewport().get("display_scale", 1.0))
    if scale <= 0:
        raise SystemExit(f"Invalid display_scale in {VIEWPORT_JSON}: {scale!r}")
    return scale


def _load_panel_x_shift() -> float:
    """Prod-pixel left shift baked into linear5 output (geometry + labels)."""
    if ACTIVE_LAYOUT != "linear5":
        return 0.0
    return float(_load_viewport().get("panel_x_shift_display", 0))


def _shift_layout_x(layout: ET.Element, delta: float) -> None:
    """Shift on-canvas X left by delta display pixels (linear5 viewport tuning)."""
    if not delta:
        return
    x_attrs = frozenset(a for a in _LAYOUT_COORD_ATTRS if a.startswith("x"))
    for el in layout.iter():
        tag = _local_tag(el)
        if tag == "positionablelabel" and el.get("icon") == "yes":
            continue
        as_int = tag in _INTEGER_COORD_TAGS
        for attr in x_attrs:
            val = el.get(attr)
            if not val:
                continue
            try:
                shifted = float(val) - delta
                el.set(
                    attr,
                    str(int(round(shifted)))
                    if as_int
                    else _fmt_layout_coord(shifted),
                )
            except ValueError:
                pass


def _shift_assigned_x(
    assigned: list[tuple[dict, dict, float]], delta: float
) -> list[tuple[dict, dict, float]]:
    if not delta:
        return assigned
    return [
        ({**new, "x": new["x"] - delta}, tgt, dx) for new, tgt, dx in assigned
    ]


def _scale_layout_geometry(layout: ET.Element, factor: float) -> None:
    """Uniform XY scale from origin; keeps blocked source at 1:1 for export/editing."""
    for el in layout.iter():
        as_int = _local_tag(el) in _INTEGER_COORD_TAGS
        for attr in _LAYOUT_COORD_ATTRS:
            val = el.get(attr)
            if not val:
                continue
            try:
                el.set(attr, _scaled_coord_str(float(val), factor, as_integer=as_int))
            except ValueError:
                pass
    for attr in ("panelwidth", "panelheight", "x", "y", "height"):
        val = layout.get(attr)
        if not val:
            continue
        try:
            layout.set(attr, str(int(round(float(val) * factor))))
        except ValueError:
            pass


def _scale_layout_display_dims(layout: ET.Element, factor: float) -> None:
    """Scale line widths and turnout draw sizes (run after apply_layout_defaults)."""
    if factor == 1.0:
        return
    for attr in ("mainlinetrackwidth", "sidetrackwidth", "turnoutcirclesize"):
        val = layout.get(attr)
        if not val:
            continue
        try:
            layout.set(attr, str(int(round(float(val) * factor))))
        except ValueError:
            pass
    for attr in _LAYOUT_DIM_FLOAT_ATTRS:
        val = layout.get(attr)
        if not val:
            continue
        try:
            layout.set(attr, _fmt_layout_coord(float(val) * factor))
        except ValueError:
            pass


def _scale_assigned(
    assigned: list[tuple[dict, dict, float]], factor: float
) -> list[tuple[dict, dict, float]]:
    if factor == 1.0:
        return assigned
    scaled: list[tuple[dict, dict, float]] = []
    for new, tgt, dx in assigned:
        scaled.append(
            (
                {**new, "x": new["x"] * factor, "y": new["y"] * factor},
                tgt,
                dx * factor,
            )
        )
    return scaled


def _scale_dcc_placement(placement: dict, factor: float) -> dict:
    if factor == 1.0:
        return placement
    scaled = dict(placement)
    for key in ("default", "above_offset", "below_offset", "below_east_offset"):
        if key in scaled:
            scaled[key] = float(scaled[key]) * factor
    if "fixed_y" in scaled:
        scaled["fixed_y"] = {k: float(v) * factor for k, v in scaled["fixed_y"].items()}
    if "fixed_x_offset" in scaled:
        scaled["fixed_x_offset"] = {
            k: float(v) * factor for k, v in scaled["fixed_x_offset"].items()
        }
    return scaled


def _scale_viewport_dims(dims: dict[str, str], factor: float) -> dict[str, str]:
    if factor == 1.0:
        return dims
    scaled = dict(dims)
    for key in ("x", "y", "panelwidth", "panelheight", "height"):
        if key in scaled:
            scaled[key] = str(int(round(float(scaled[key]) * factor)))
    return scaled


def _find_layout_editor(root: ET.Element) -> ET.Element | None:
    return root.find(".//LayoutEditor")


def _unscale_coord_str(
    value: float, factor: float, *, x_shift: float = 0.0
) -> str:
    if factor <= 0:
        raise ValueError(f"display_scale must be positive, got {factor}")
    return _fmt_layout_coord((float(value) + x_shift) / factor)


def _blocked_coord_from_prod(
    prod_val: str, factor: float, *, x_shift: float = 0.0
) -> str:
    return _unscale_coord_str(float(prod_val), factor, x_shift=x_shift)


def _copy_prod_coords_to_blocked_elem(
    blocked_el: ET.Element,
    prod_el: ET.Element,
    factor: float,
    *,
    attrs: frozenset[str] = _LAYOUT_COORD_ATTRS,
    x_shift: float = 0.0,
) -> int:
    n = 0
    for attr in attrs:
        prod_val = prod_el.get(attr)
        if prod_val is None:
            continue
        shift = x_shift if attr.startswith("x") else 0.0
        blocked_el.set(
            attr, _blocked_coord_from_prod(prod_val, factor, x_shift=shift)
        )
        n += 1
    return n


def import_prod_geometry_to_blocked(
    *,
    prod_path: Path | None = None,
    blocked_path: Path | None = None,
    display_scale: float | None = None,
    backup: bool = True,
) -> dict[str, int]:
    """
    Copy LayoutEditor track geometry from prod (display-scale) into blocked (1:1).

    Turnout leg endpoints and bezier control points keep fractional coordinates
    (e.g. 1076.0, 1092.33) — not rounded to integers.
    """
    prod_path = prod_path or OUT_PROD_PANEL
    blocked_path = blocked_path or LINEAR4_BLOCKED
    if not prod_path.is_file():
        raise SystemExit(f"Missing prod panel: {prod_path}")
    if not blocked_path.is_file():
        raise SystemExit(f"Missing blocked panel: {blocked_path}")

    factor = display_scale if display_scale is not None else _load_display_scale()
    x_shift = _load_panel_x_shift()
    if factor == 1.0 and ACTIVE_LAYOUT == "linear5":
        print(
            "  Warning: display_scale is 1.0 — linear5 prod is usually 1.5× blocked"
        )

    if backup:
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        ref_dir = blocked_path.parent.parent / "reference"
        ref_dir.mkdir(parents=True, exist_ok=True)
        for src, suffix in (
            (blocked_path, "blocked_pre_prod_import"),
            (prod_path, "prod_user"),
        ):
            dest = ref_dir / f"{ACTIVE_LAYOUT}_{suffix}_{ts}.xml"
            dest.write_bytes(src.read_bytes())
            print(f"  Backup: {dest.name}")

    prod_layout = _find_layout_editor(ET.parse(prod_path).getroot())
    blocked_root = ET.parse(blocked_path).getroot()
    blocked_layout = _find_layout_editor(blocked_root)
    if prod_layout is None or blocked_layout is None:
        raise SystemExit("LayoutEditor not found in prod or blocked panel")

    counts = {"anchors": 0, "turnouts": 0, "bezier": 0}

    prod_anchors = {
        pp.get("ident"): pp
        for pp in prod_layout.findall("positionablepoint")
        if pp.get("ident")
    }
    for blocked_pp in blocked_layout.findall("positionablepoint"):
        ident = blocked_pp.get("ident")
        prod_pp = prod_anchors.get(ident)
        if prod_pp is None:
            continue
        counts["anchors"] += _copy_prod_coords_to_blocked_elem(
            blocked_pp,
            prod_pp,
            factor,
            attrs=frozenset({"x", "y"}),
            x_shift=x_shift,
        )

    prod_turnouts = {
        lt.get("ident"): lt
        for lt in prod_layout.findall("layoutturnout")
        if lt.get("ident")
    }
    for blocked_lt in blocked_layout.findall("layoutturnout"):
        ident = blocked_lt.get("ident")
        prod_lt = prod_turnouts.get(ident)
        if prod_lt is None:
            continue
        counts["turnouts"] += _copy_prod_coords_to_blocked_elem(
            blocked_lt, prod_lt, factor, x_shift=x_shift
        )

    prod_segments = {
        seg.get("ident"): seg
        for seg in prod_layout.findall("tracksegment")
        if seg.get("ident")
    }
    for blocked_seg in blocked_layout.findall("tracksegment"):
        ident = blocked_seg.get("ident")
        prod_seg = prod_segments.get(ident)
        if prod_seg is None:
            continue
        prod_cps = prod_seg.findall("controlpoints/controlpoint")
        if not prod_cps:
            continue
        blocked_cps_parent = blocked_seg.find("controlpoints")
        if blocked_cps_parent is None:
            blocked_cps_parent = ET.SubElement(blocked_seg, "controlpoints")
        else:
            for child in list(blocked_cps_parent):
                blocked_cps_parent.remove(child)
        for prod_cp in prod_cps:
            ET.SubElement(
                blocked_cps_parent,
                "controlpoint",
                {
                    "index": prod_cp.get("index", "0"),
                    "x": _blocked_coord_from_prod(
                        prod_cp.get("x", "0"), factor, x_shift=x_shift
                    ),
                    "y": _blocked_coord_from_prod(prod_cp.get("y", "0"), factor),
                },
            )
            counts["bezier"] += 2

    _write_jmri_panel_xml(blocked_root, blocked_path)
    manual = blocked_path.parent.parent / "reference" / f"{ACTIVE_LAYOUT}_manual_save.xml"
    manual.parent.mkdir(parents=True, exist_ok=True)
    manual.write_bytes(blocked_path.read_bytes())

    total = sum(counts.values())
    print(
        f"  Imported prod → blocked ({factor}× unscale, fractional coords): "
        f"{counts['anchors']} anchor attrs, {counts['turnouts']} turnout attrs, "
        f"{counts['bezier']} bezier CP coords ({total} total)"
    )
    return counts


_TRACK_LABEL_TEXT_TO_IDS: dict[str, list[str]] = {
    "Brick": ["brick"],
    "Plane": ["plane"],
    "East End": ["east_end"],
    "Princess": ["princess"],
    "Main West": ["main_west"],
    "Main East": ["main_east"],
    "West Lead": ["west_lead"],
    "East Lead": ["east_lead"],
    "Track 3": ["track3"],
    "Track 4": ["track4"],
    "Track 5": ["track5"],
    "Track 1": ["track1_west", "track1_mid", "track1_east"],
    "Track 2": ["track2_west", "track2_mid", "track2_east"],
}


def _json_coord(value: float) -> float | int:
    rounded = round(value, 2)
    return int(rounded) if rounded == int(rounded) else rounded


def _sync_label_json_from_prod(
    prod_path: Path | None = None,
    display_scale: float | None = None,
) -> None:
    """Update layout_area_labels.json and track_labels.json from prod label positions."""
    import json

    prod_path = prod_path or OUT_PROD_PANEL
    factor = display_scale if display_scale is not None else _load_display_scale()
    x_shift = _load_panel_x_shift()
    prod_layout = _find_layout_editor(ET.parse(prod_path).getroot())
    if prod_layout is None:
        raise SystemExit("LayoutEditor not found in prod panel")

    area_labels = [
        lb
        for lb in prod_layout.findall("positionablelabel")
        if lb.get("level") == "3" and (lb.get("text") or "").strip()
    ]
    if LAYOUT_AREA_LABELS_JSON.is_file():
        area_data = json.loads(LAYOUT_AREA_LABELS_JSON.read_text(encoding="utf-8"))
        by_text = {e.get("text"): e for e in area_data.get("labels", [])}
        for lb in area_labels:
            text = (lb.get("text") or "").strip()
            entry = by_text.get(text)
            if entry is None:
                continue
            entry["x"] = _json_coord((float(lb.get("x", 0)) + x_shift) / factor)
            entry["y"] = _json_coord(float(lb.get("y", 0)) / factor)
        LAYOUT_AREA_LABELS_JSON.write_text(
            json.dumps(area_data, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  Updated {LAYOUT_AREA_LABELS_JSON.name} ({len(area_labels)} area labels)")

    track_labels = [
        lb
        for lb in prod_layout.findall("positionablelabel")
        if lb.get("level") == "4" and (lb.get("text") or "").strip()
    ]
    if TRACK_LABELS_JSON.is_file():
        track_data = json.loads(TRACK_LABELS_JSON.read_text(encoding="utf-8"))
        by_id = {e["id"]: e for e in track_data.get("labels", []) if e.get("id")}
        grouped: dict[str, list[tuple[float, float]]] = {}
        for lb in track_labels:
            text = (lb.get("text") or "").strip()
            grouped.setdefault(text, []).append(
                (float(lb.get("x", 0)), float(lb.get("y", 0)))
            )
        for text, ids in _TRACK_LABEL_TEXT_TO_IDS.items():
            prod_pts = grouped.get(text)
            if not prod_pts:
                continue
            prod_pts = sorted(prod_pts, key=lambda p: p[0])
            json_entries = [by_id[i] for i in ids if i in by_id]
            json_entries.sort(key=lambda e: float(e.get("x", 0)))
            for (px, py), entry in zip(prod_pts, json_entries):
                entry["x"] = _json_coord((px + x_shift) / factor)
                entry["y"] = _json_coord(py / factor)
        TRACK_LABELS_JSON.write_text(
            json.dumps(track_data, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  Updated {TRACK_LABELS_JSON.name}")


def _switch_id_from_mqtt_user(mqtt_user: str) -> str:
    """Group id (e.g. 3-8) from MQTT userName, if present."""
    user = (mqtt_user or "").strip()
    for prefix in ("MQTT Switch ", "Switch "):
        if user.startswith(prefix):
            tail = user[len(prefix) :].strip()
            if tail.isdigit():
                for group_id, dcc in SWITCH_DCC_ADDRESS.items():
                    if dcc == int(tail):
                        return group_id
                return tail
            return tail
    return user


def _dcc_from_turnout_user(user: str) -> int | None:
    """
    DCC address from live/route turnout userName.

    Supports ``Switch 114`` (route name = DCC address) and legacy
    ``MQTT Switch 3-8`` (group id → SWITCH_DCC_ADDRESS).
    """
    user = (user or "").strip()
    for prefix in ("MQTT Switch ", "Switch "):
        if user.startswith(prefix):
            tail = user[len(prefix) :].strip()
            if tail.isdigit():
                return int(tail)
            return SWITCH_DCC_ADDRESS.get(tail)
    return SWITCH_DCC_ADDRESS.get(user)


def _switch_dcc_fields(tgt: dict) -> tuple[str, str]:
    mqtt_user = ""
    if tgt.get("mqtt"):
        mqtt_user = (tgt["mqtt"].get("user") or "").strip()
    elif tgt.get("panel_user"):
        mqtt_user = tgt["panel_user"].strip()
    dcc = _dcc_from_turnout_user(mqtt_user)
    if dcc is None:
        return "", ""
    switch_id = _switch_id_from_mqtt_user(mqtt_user)
    return switch_id, str(dcc)


def _load_dcc_label_placement(name: str) -> dict:
    """Resolve preset name; optional JSON in data/ overrides offsets and above/below sets."""
    if name not in DCC_LABEL_PLACEMENT_PRESETS:
        known = ", ".join(sorted(DCC_LABEL_PLACEMENT_PRESETS))
        raise SystemExit(f"Unknown --dcc-label-placement {name!r} (choose: {known})")
    placement = dict(DCC_LABEL_PLACEMENT_PRESETS[name])
    if DCC_LABEL_PLACEMENT_JSON.is_file():
        import json

        overrides = json.loads(DCC_LABEL_PLACEMENT_JSON.read_text(encoding="utf-8"))
        # CLI --dcc-label-placement selects the preset; JSON only tunes offsets/sets.
        for key in (
            "default",
            "above_offset",
            "below_offset",
            "below_east_offset",
        ):
            if key in overrides:
                placement[key] = overrides[key]
        for key in ("above", "below", "below_east", "between_mast"):
            if key in overrides:
                placement[key] = frozenset(int(x) for x in overrides[key])
        if "fixed_y" in overrides:
            placement["fixed_y"] = {
                int(k): float(v) for k, v in overrides["fixed_y"].items()
            }
        if "fixed_x_offset" in overrides:
            placement["fixed_x_offset"] = {
                int(k): float(v) for k, v in overrides["fixed_x_offset"].items()
            }
    return placement


def _dcc_label_x_offset(dcc: int, placement: dict) -> float:
    return float((placement.get("fixed_x_offset") or {}).get(dcc, 0))


def _dcc_label_xy(
    new: dict,
    dcc: int,
    placement: dict,
) -> tuple[float, float]:
    x_off = _dcc_label_x_offset(dcc, placement)
    fixed_y = placement.get("fixed_y") or {}
    if dcc in fixed_y:
        return new["x"] + x_off, float(fixed_y[dcc])
    between_mast = placement.get("between_mast") or frozenset()
    if dcc in between_mast:
        _mx, mast_y = placement.get("_mast_xy", (new["x"], new["y"] + 22))
        return new["x"] + x_off, (new["y"] + float(mast_y)) / 2.0
    y_off = _dcc_label_y_offset(dcc, placement)
    return new["x"] + x_off, new["y"] + y_off


def _dcc_label_y_offset(dcc: int, placement: dict) -> float:
    if "above" in placement and dcc in placement["above"]:
        return float(placement["above_offset"])
    if "below_east" in placement and dcc in placement["below_east"]:
        return float(placement.get("below_east_offset", 13))
    if "below" in placement and dcc in placement["below"]:
        return float(placement["below_offset"])
    return float(placement.get("default", -14))


def _make_dcc_label(
    x: float, y: float, dcc: int, *, size: str | None = None
) -> ET.Element:
    return ET.Element(
        "positionablelabel",
        {
            "x": str(int(round(x))),
            "y": str(int(round(y))),
            "level": "4",
            "forcecontroloff": "false",
            "hidden": "no",
            "positionable": "true",
            "showtooltip": "true",
            "editable": "false",
            "text": str(dcc),
            "size": size or LABEL_STANDARD_SIZE,
            "style": LABEL_STANDARD_STYLE,
            "red": "0",
            "green": "0",
            "blue": "128",
            "hasBackground": "no",
            "justification": "centre",
            "fontFamily": LABEL_STANDARD_FONT,
            "fontname": LABEL_STANDARD_FONTNAME,
            "class": "jmri.jmrit.display.configurexml.PositionableLabelXml",
        },
    )


def _add_dcc_switch_labels(
    layout: ET.Element,
    assigned: list[tuple[dict, dict, float]],
    placement: dict,
    *,
    label_size: str | None = None,
) -> int:
    """One DCC label per motor turnout (skip internal crossover legs)."""
    seen_dcc: set[int] = set()
    count = 0
    for new, tgt, _ in assigned:
        if tgt["kind"] == "internal_mqtt_fb":
            continue
        switch_id, dcc_s = _switch_dcc_fields(tgt)
        if not switch_id or not dcc_s:
            continue
        dcc = int(dcc_s)
        if dcc in seen_dcc:
            continue
        seen_dcc.add(dcc)
        lx, ly = _dcc_label_xy(new, dcc, placement)
        layout.append(_make_dcc_label(lx, ly, dcc, size=label_size))
        count += 1
    return count


def _turnout_xy_by_dcc(
    assigned: list[tuple[dict, dict, float]],
) -> dict[int, tuple[float, float]]:
    by_dcc: dict[int, tuple[float, float]] = {}
    for new, tgt, _ in assigned:
        _sid, dcc_s = _switch_dcc_fields(tgt)
        if dcc_s:
            by_dcc[int(dcc_s)] = (new["x"], new["y"])
    return by_dcc


# Upper band: title centered above yard row; yard row above main track / DCC labels.
AREA_TITLE_Y = 35.0  # halfway between 38 (old) and 32 (last)
AREA_LABEL_ROW_Y = 100.0  # halfway between 88 (old) and 112 (last)
AREA_LABEL_EXTRA_DOWN = 12.0  # half of last +24px shift; also on direction row
PIR_LABEL_TEXT = "PIR Interchange"
# Unicode arrows (→ ←) render cleaner in JMRI than ASCII "->" / "<-"
WEST_DIRECTION_TEXT = "← Neville Island West"
EAST_DIRECTION_TEXT = "McKees Rocks, PA →"
PIR_LABEL_EDGE_MARGIN = 4.0  # px inset from east loop geometry
DIRECTION_ROW_BELOW_106 = 16.0  # px under the DCC 106 below-track label row


def _estimate_text_width_px(text: str, size_pt: float) -> float:
    """Approximate pixel width for layout area labels (Lucida Grande)."""
    return max(len(text), 1) * size_pt * 0.52


def _mean_dcc_x(by_dcc: dict[int, tuple[float, float]], *dccs: int) -> float:
    xs = [by_dcc[d][0] for d in dccs if d in by_dcc]
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def _layout_west_edge_x(layout: ET.Element) -> float:
    """West end of track (spur bumpers), not panel origin at x=0."""
    spur_x: list[float] = []
    for ap in layout.findall("positionablepoint"):
        ident = (ap.get("ident") or "").upper()
        try:
            x = float(ap.get("x", 0))
            y = float(ap.get("y", 0))
        except ValueError:
            continue
        if ident.startswith("EB") or (50 < x < 200 and 160 < y < 185):
            spur_x.append(x)
    if spur_x:
        return min(spur_x)
    return 67.0


def _layout_track_x_bounds(layout: ET.Element) -> tuple[float, float]:
    """Westernmost spur and easternmost loop geometry x on the panel."""
    west_x = _layout_west_edge_x(layout)
    max_x = 0.0
    for el in layout.iter():
        for attr in ("x", "xcen", "xa", "xb", "xc", "xd"):
            val = el.get(attr)
            if not val:
                continue
            try:
                max_x = max(max_x, float(val))
            except ValueError:
                pass
    return west_x, max_x


def _layout_max_track_x(layout: ET.Element) -> float:
    return _layout_track_x_bounds(layout)[1]


def _default_layout_area_labels(
    assigned: list[tuple[dict, dict, float]],
    *,
    layout_west_x: float,
    layout_east_x: float,
    display_scale: float = 1.0,
) -> list[dict]:
    """Title and yard names for the linear4 panel (1280×320)."""
    by_dcc = _turnout_xy_by_dcc(assigned)
    s = display_scale

    x_west = 105.0 * s
    x_south = _mean_dcc_x(by_dcc, 103, 104, 105, 106)
    x_industry = _mean_dcc_x(by_dcc, 107, 108, 109)
    label_size = 12.0 * s
    # JMRI Layout Editor (x,y) is the label top-left; "right" justification does not
    # move that anchor. Place left edge so the text ends at the east loop edge.
    x_pir_right = layout_east_x - PIR_LABEL_EDGE_MARGIN * s
    x_pir = x_pir_right - _estimate_text_width_px(PIR_LABEL_TEXT, label_size)
    x_east_dir_right = layout_east_x - PIR_LABEL_EDGE_MARGIN * s
    x_east_dir = x_east_dir_right - _estimate_text_width_px(EAST_DIRECTION_TEXT, label_size)
    title_x = (x_west + x_south + x_industry + (x_pir + x_pir_right) / 2.0) / 4.0

    _, y106 = by_dcc.get(106, (598.0, 194.74))
    y_direction = (
        y106 + 20.0 * s + DIRECTION_ROW_BELOW_106 * s + AREA_LABEL_EXTRA_DOWN * s
    )

    yard_style = {
        "size": str(int(round(12 * s))),
        "style": "0",
        "y": AREA_LABEL_ROW_Y * s,
    }
    direction_style = {
        "size": str(int(round(12 * s))),
        "style": "0",
        "y": y_direction,
        "justification": "left",
    }
    return [
        {
            "text": "Neville Island",
            "x": title_x,
            "y": AREA_TITLE_Y * s,
            "size": str(int(round(16 * s))),
            "style": "1",
        },
        {"text": "West Yard", "x": x_west, **yard_style},
        {"text": "South Yard", "x": x_south, **yard_style},
        {"text": "Industries", "x": x_industry, **yard_style},
        {
            "text": PIR_LABEL_TEXT,
            "x": x_pir,
            "justification": "left",
            **yard_style,
        },
        {"text": WEST_DIRECTION_TEXT, "x": layout_west_x, **direction_style},
        {"text": EAST_DIRECTION_TEXT, "x": x_east_dir, **direction_style},
    ]


def _load_layout_area_labels(
    assigned: list[tuple[dict, dict, float]],
    *,
    layout_west_x: float,
    layout_east_x: float,
    display_scale: float = 1.0,
) -> list[dict]:
    labels = _default_layout_area_labels(
        assigned,
        layout_west_x=layout_west_x,
        layout_east_x=layout_east_x,
        display_scale=display_scale,
    )
    if not LAYOUT_AREA_LABELS_JSON.is_file():
        return labels
    import json

    overrides = json.loads(LAYOUT_AREA_LABELS_JSON.read_text(encoding="utf-8"))
    by_text = {lb["text"]: dict(lb) for lb in labels}
    for entry in overrides.get("labels", overrides if isinstance(overrides, list) else []):
        text = entry.get("text")
        if not text:
            continue
        base = by_text.get(text, {"text": text})
        scaled_entry = dict(entry)
        x_shift = _load_panel_x_shift()
        if display_scale != 1.0:
            if "x" in scaled_entry:
                scaled_entry["x"] = (
                    float(scaled_entry["x"]) * display_scale - x_shift
                )
            if "y" in scaled_entry:
                scaled_entry["y"] = float(scaled_entry["y"]) * display_scale
            if "size" in scaled_entry:
                scaled_entry["size"] = str(
                    int(round(float(scaled_entry["size"]) * display_scale))
                )
        elif x_shift and "x" in scaled_entry:
            scaled_entry["x"] = float(scaled_entry["x"]) - x_shift
        base.update(scaled_entry)
        by_text[text] = base
    return list(by_text.values())


def _make_area_label(
    text: str,
    x: float,
    y: float,
    *,
    size: str = "12",
    style: str = "0",
    justification: str = "centre",
) -> ET.Element:
    return ET.Element(
        "positionablelabel",
        {
            "x": str(int(round(x))),
            "y": str(int(round(y))),
            "level": "3",
            "forcecontroloff": "false",
            "hidden": "no",
            "positionable": "true",
            "showtooltip": "true",
            "editable": "false",
            "text": text,
            "size": size,
            "style": style,
            "red": "0",
            "green": "0",
            "blue": "0",
            "hasBackground": "no",
            "justification": justification,
            "fontFamily": LABEL_STANDARD_FONT,
            "fontname": LABEL_STANDARD_FONTNAME,
            "class": "jmri.jmrit.display.configurexml.PositionableLabelXml",
        },
    )


def _ensure_panel_background_asset(*, force: bool = False) -> Path:
    if force or not PANEL_BG_ASSET.is_file():
        if ACTIVE_LAYOUT == "linear5":
            from generate_linear5_panel_background import generate
        else:
            from generate_linear4_panel_background import generate

        generate(PANEL_BG_ASSET)
        print(f"  Generated panel background {PANEL_BG_ASSET.name}")
    return PANEL_BG_ASSET


def _apply_panel_background_rgb(layout: ET.Element) -> None:
    layout.set("redBackground", PANEL_BG_RGB[0])
    layout.set("greenBackground", PANEL_BG_RGB[1])
    layout.set("blueBackground", PANEL_BG_RGB[2])


def _make_panel_background_label() -> ET.Element:
    """Background icon label (linear5 matches reference/tables.xml)."""
    attrs = {
        "x": "0",
        "y": "0",
        "icon": "yes",
        "forcecontroloff": "false",
        "hidden": "no",
        "positionable": "true",
        "showtooltip": "false",
        "class": "jmri.jmrit.display.configurexml.PositionableLabelXml",
    }
    if ACTIVE_LAYOUT == "linear5":
        attrs.update({"level": "1", "editable": "true"})
    else:
        attrs.update({"level": "0", "editable": "false"})
    label = ET.Element("positionablelabel", attrs)
    icon = ET.SubElement(
        label,
        "icon",
        {
            "url": PANEL_BG_PREF_URL,
            "degrees": "0",
            "scale": "1.0",
        },
    )
    ET.SubElement(icon, "rotation").text = "0"
    return label


def _finalize_layout_editor_order(layout: ET.Element) -> None:
    """Overlay labels/icons before track geometry (JMRI reference panel order)."""
    children = list(layout)
    for child in children:
        layout.remove(child)

    def _tag(el: ET.Element) -> str:
        return _local_tag(el)

    options = [c for c in children if _tag(c) == "layouttrackdrawingoptions"]
    area_labels = [
        c
        for c in children
        if _tag(c) == "positionablelabel"
        and c.get("level") == "3"
        and c.get("icon") != "yes"
    ]
    mast = [c for c in children if _tag(c) == "signalmasticon"]
    dcc_labels = [
        c
        for c in children
        if _tag(c) == "positionablelabel"
        and c.get("icon") != "yes"
        and (c.get("text") or "").strip().isdigit()
    ]
    track_labels = [
        c
        for c in children
        if _tag(c) == "positionablelabel"
        and c.get("level") == "4"
        and c.get("icon") != "yes"
        and not (c.get("text") or "").strip().isdigit()
    ]
    other_labels = [
        c
        for c in children
        if _tag(c) == "positionablelabel"
        and c.get("icon") != "yes"
        and c not in dcc_labels
        and c not in area_labels
        and c not in track_labels
    ]
    bg_icons = [
        c
        for c in children
        if _tag(c) == "positionablelabel" and c.get("icon") == "yes"
    ]
    turnouts = [c for c in children if _tag(c) == "layoutturnout"]
    segments = [c for c in children if _tag(c) == "tracksegment"]
    points = [c for c in children if _tag(c) == "positionablepoint"]
    used = set(
        id(c)
        for c in options
        + area_labels
        + mast
        + dcc_labels
        + track_labels
        + other_labels
        + bg_icons
        + turnouts
        + segments
        + points
    )
    other = [c for c in children if id(c) not in used]
    for group in (
        options,
        area_labels,
        dcc_labels,
        mast,
        track_labels,
        other_labels,
        bg_icons,
        turnouts,
        segments,
        points,
        other,
    ):
        for child in group:
            layout.append(child)


_LINEAR5_VIEWPORT_ATTRS = (
    "x",
    "y",
    "windowheight",
    "windowwidth",
    "panelheight",
    "panelwidth",
    "sliders",
    "scrollable",
)


def _apply_linear5_layout_viewport(layout: ET.Element) -> None:
    """Use panel/window attrs from reference/tables.xml (Pi save: no scrollbars, etc.)."""
    ref_path = JMRI_ROOT / "layouts/linear5/reference/tables.xml"
    if not ref_path.is_file():
        return
    ref_layout = ET.parse(ref_path).getroot().find(".//LayoutEditor")
    if ref_layout is None:
        return
    for attr in _LINEAR5_VIEWPORT_ATTRS:
        val = ref_layout.get(attr)
        if val is not None:
            layout.set(attr, val)
    for attr in ("height", "width"):
        if ref_layout.get(attr) is None and attr in layout.attrib:
            del layout.attrib[attr]


def _add_panel_background_image(layout: ET.Element) -> None:
    _ensure_panel_background_asset(force=ACTIVE_LAYOUT == "linear5")
    _apply_panel_background_rgb(layout)
    label = _make_panel_background_label()
    insert_at = len(layout)
    for i, child in enumerate(layout):
        if _local_tag(child) == "layoutturnout":
            insert_at = i
            break
    layout.insert(insert_at, label)


# Center ladder labels: label id → track segment ident (1:1 blocked geometry).
_CENTER_TRACK_SEGMENT: dict[str, str] = {
    "main_west": "F61-S-0",
    "track1_mid": "F46-S-0",
    "track2_mid": "F47-S-0",
    "track3": "F48-S-0",
    "track4": "F49-S-0",
    "track5": "F50-S-0",
    "main_east": "F68-S-0",
}
# Same Y as center Track 1 (F46-S-0): outer Track 2 + leads on that ladder rung.
_PARALLEL_TRACK1_Y_IDS = frozenset(
    {"track2_west", "track2_east", "west_lead", "east_lead"}
)


def _segment_endpoint_xy(
    layout: ET.Element,
    name: str,
    conn_type: str,
    pts: dict[str, tuple[float, float]],
) -> tuple[float, float] | None:
    if conn_type == "POS_POINT" and name in pts:
        return pts[name]
    if conn_type and conn_type.startswith("TURNOUT"):
        lt = layout.find(f".//layoutturnout[@ident='{name}']")
        if lt is None:
            return None
        leg = conn_type.rsplit("_", 1)[-1].lower()
        x = lt.get(f"x{leg}")
        y = lt.get(f"y{leg}")
        if x is not None and y is not None:
            return float(x), float(y)
    return None


def _segment_horizontal_y(layout: ET.Element, segment_ident: str) -> float | None:
    """Mean Y of a near-horizontal track segment (anchors or turnout legs)."""
    seg = layout.find(f".//tracksegment[@ident='{segment_ident}']")
    if seg is None:
        return None
    pts = {
        p.get("ident"): (float(p.get("x")), float(p.get("y")))
        for p in layout.findall("positionablepoint")
    }
    ends = [
        _segment_endpoint_xy(layout, seg.get("connect1name", ""), seg.get("type1", ""), pts),
        _segment_endpoint_xy(layout, seg.get("connect2name", ""), seg.get("type2", ""), pts),
    ]
    ends = [e for e in ends if e is not None]
    if len(ends) != 2:
        return None
    (x1, y1), (x2, y2) = ends
    if abs(y1 - y2) > 3.0:
        return None
    return (y1 + y2) / 2.0


def _align_center_track_labels(specs: list[dict], layout: ET.Element) -> None:
    """Place Main West / Track 1–5 / Main East on one X, Y above each segment (Main West spacing)."""
    by_id = {str(s.get("id", "")): s for s in specs if s.get("id")}
    anchor = by_id.get("main_west")
    if anchor is None or "x" not in anchor:
        return
    anchor_seg = _CENTER_TRACK_SEGMENT.get("main_west")
    anchor_y = _segment_horizontal_y(layout, anchor_seg) if anchor_seg else None
    if anchor_y is None:
        return
    offset = float(anchor["y"]) - anchor_y
    center_x = float(anchor["x"])
    for label_id, segment_ident in _CENTER_TRACK_SEGMENT.items():
        spec = by_id.get(label_id)
        if spec is None:
            continue
        track_y = _segment_horizontal_y(layout, segment_ident)
        if track_y is None:
            continue
        spec["x"] = center_x
        spec["y"] = track_y + offset
    track1 = by_id.get("track1_mid")
    if track1 is not None and "y" in track1:
        for label_id in _PARALLEL_TRACK1_Y_IDS:
            spec = by_id.get(label_id)
            if spec is not None:
                spec["y"] = track1["y"]


def _load_track_labels(
    layout: ET.Element | None = None, *, display_scale: float = 1.0
) -> tuple[list[dict], dict[str, dict]]:
    if not TRACK_LABELS_JSON.is_file():
        return [], {}
    import json

    data = json.loads(TRACK_LABELS_JSON.read_text(encoding="utf-8"))
    styles = data.get("styles") or {}
    labels: list[dict] = [dict(entry) for entry in data.get("labels", ())]
    if layout is not None:
        _align_center_track_labels(labels, layout)
    x_shift = _load_panel_x_shift()
    for spec in labels:
        if display_scale != 1.0:
            if "x" in spec:
                spec["x"] = float(spec["x"]) * display_scale - x_shift
            if "y" in spec:
                spec["y"] = float(spec["y"]) * display_scale
            if "size" in spec:
                spec["size"] = str(int(round(float(spec["size"]) * display_scale)))
        elif x_shift and "x" in spec:
            spec["x"] = float(spec["x"]) - x_shift
    return labels, styles


def _make_track_label(spec: dict, styles: dict[str, dict]) -> ET.Element:
    style_name = str(spec.get("style", "track"))
    style = dict(styles.get(style_name, styles.get("track", {})))
    attrs = {
        "x": str(int(round(float(spec["x"])))),
        "y": str(int(round(float(spec["y"])))),
        "level": "4",
        "forcecontroloff": "false",
        "hidden": "no",
        "positionable": "true",
        "showtooltip": "true",
        "editable": "false",
        "text": str(spec["text"]),
        "size": str(spec.get("size", "9")),
        "style": "0",
        "justification": str(spec.get("justification", "centre")),
        "class": "jmri.jmrit.display.configurexml.PositionableLabelXml",
    }
    attrs.update(style)
    if attrs.get("hasBackground") != "yes":
        attrs.setdefault("red", "0")
        attrs.setdefault("green", "0")
        attrs.setdefault("blue", "0")
        attrs.setdefault("hasBackground", "no")
    return ET.Element("positionablelabel", attrs)


def _add_track_labels(
    layout: ET.Element,
    *,
    align_layout: ET.Element | None = None,
    display_scale: float = 1.0,
) -> int:
    specs, styles = _load_track_labels(
        align_layout, display_scale=display_scale
    )
    for spec in specs:
        layout.append(_make_track_label(spec, styles))
    return len(specs)


def _add_layout_area_labels(
    layout: ET.Element,
    assigned: list[tuple[dict, dict, float]],
    *,
    display_scale: float = 1.0,
) -> int:
    layout_west_x, layout_east_x = _layout_track_x_bounds(layout)
    specs = _load_layout_area_labels(
        assigned,
        layout_west_x=layout_west_x,
        layout_east_x=layout_east_x,
        display_scale=display_scale,
    )
    insert_at = 0
    for i, child in enumerate(layout):
        if (child.tag or "").strip().lower() == "layouttrackdrawingoptions":
            insert_at = i + 1
            break
    for i, spec in enumerate(specs):
        layout.insert(
            insert_at + i,
            _make_area_label(
                spec["text"],
                float(spec["x"]),
                float(spec["y"]),
                size=str(spec.get("size", "12")),
                style=str(spec.get("style", "0")),
                justification=str(spec.get("justification", "centre")),
            ),
        )
    return len(specs)


def _parse_live():
    root = ET.parse(LIVE_PANEL).getroot()
    sensors_by_user: dict[str, str] = {}
    for s in root.findall(".//sensors/sensor"):
        un = (s.findtext("userName") or "").strip()
        sn = (s.findtext("systemName") or "").strip()
        if un:
            sensors_by_user[un] = sn

    internal: dict[str, dict] = {}
    mqtt: dict[str, dict] = {}
    for turnouts in root.findall("turnouts"):
        cls = turnouts.get("class", "")
        for t in turnouts.findall("turnout"):
            un = (t.findtext("userName") or "").strip()
            sn = (t.findtext("systemName") or "").strip()
            s1 = t.get("sensor1", "") or ""
            s2 = t.get("sensor2", "") or ""
            rec = {
                "system": sn,
                "user": un,
                "s1_user": s1,
                "s2_user": s2,
                "s1_sys": sensors_by_user.get(s1, ""),
                "s2_sys": sensors_by_user.get(s2, ""),
            }
            if "mqtt" in cls.lower():
                mqtt[un] = rec
            elif sn.startswith("IT"):
                internal[un] = rec

    mqtt_by_system = {rec["system"]: rec for rec in mqtt.values()}
    internal_by_system = {rec["system"]: rec for rec in internal.values()}

    layout_turnouts = []
    for lt in root.findall(".//layoutturnout"):
        y = float(lt.get("ycen", 0))
        x = float(lt.get("xcen", 0))
        ident = lt.get("ident", "")
        tn = lt.get("turnoutname", "") or ""
        sec = lt.get("secondturnoutname", "") or ""
        layout_turnouts.append(
            {
                "ident": ident,
                "x": x,
                "y": y,
                "type": lt.get("type", ""),
                "turnoutname": tn,
                "second": sec,
            }
        )

    signal_masts = []
    for sm in root.findall(".//signalmasts/*"):
        tag = sm.tag.split("}")[-1] if "}" in sm.tag else sm.tag
        if tag not in ("mqttsignalmast", "signalmast"):
            continue
        signal_masts.append(
            {
                "elem": sm,
                "system": (sm.findtext("systemName") or "").strip(),
                "user": (sm.findtext("userName") or "").strip(),
                "class": sm.get("class", ""),
            }
        )

    icons = root.findall(".//signalmasticon")

    return {
        "root": root,
        "sensors_by_user": sensors_by_user,
        "internal": internal,
        "internal_by_system": internal_by_system,
        "mqtt": mqtt,
        "mqtt_by_system": mqtt_by_system,
        "layout_turnouts": layout_turnouts,
        "signal_masts": signal_masts,
        "signal_icons": icons,
    }


def _linear4_turnouts(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    out = []
    for lt in root.findall(".//layoutturnout"):
        out.append(
            {
                "ident": lt.get("ident", ""),
                "x": float(lt.get("xcen", 0)),
                "y": float(lt.get("ycen", 0)),
                "type": lt.get("type", ""),
            }
        )
    return sorted(out, key=lambda t: t["x"])


def _target_from_mqtt_layout(live: dict, lt: dict) -> dict:
    mu = lt["turnoutname"]
    return {
        "kind": "mqtt",
        "layout_ident": lt["ident"],
        "x": lt["x"],
        "y": lt["y"],
        "panel_system": live["mqtt"][mu]["system"],
        "panel_user": mu,
        "internal": None,
        "mqtt": live["mqtt"][mu],
        "notes": "",
    }


def _internal_for_layout_turnout(live: dict, lt: dict) -> dict | None:
    ident = lt["ident"]
    it = live["internal"].get(ident)
    if it is not None:
        return it
    tn = lt.get("turnoutname", "")
    if tn.startswith("IT"):
        return live["internal_by_system"].get(tn)
    return None


def _target_from_internal(
    live: dict,
    lt: dict,
    kind: str,
    notes: str = "",
    *,
    internal_rec: dict | None = None,
) -> dict:
    ident = lt["ident"]
    it = internal_rec or _internal_for_layout_turnout(live, lt)
    if it is None:
        raise KeyError(f"No internal device for layout turnout {ident} ({lt.get('turnoutname')})")
    sec = lt.get("second", "")
    sec_mqtt = sec if sec.startswith("MQTT") else ""
    return {
        "kind": kind,
        "layout_ident": ident,
        "x": lt["x"],
        "y": lt["y"],
        "panel_system": it["system"],
        "panel_user": ident,
        "internal": it,
        "mqtt": live["mqtt"].get(sec_mqtt) if sec_mqtt else None,
        "notes": notes,
    }


def _mqtt_at_x(live: dict, x: float, tol: float = 35.0) -> dict | None:
    best = None
    for lt in live["layout_turnouts"]:
        if not (350 <= lt["y"] <= 420):
            continue
        if not lt["turnoutname"].startswith("MQTT"):
            continue
        d = abs(lt["x"] - x)
        if d > tol:
            continue
        if best is None or d < best[0]:
            best = (d, _target_from_mqtt_layout(live, lt))
    return best[1] if best else None


def _resolve_panel_target(live: dict, lt: dict) -> dict:
    """Panel turnoutname uses M2T when a MQTT device shares this x; feedback from live IT/MQTT."""
    ident = lt["ident"]
    it = _internal_for_layout_turnout(live, lt)
    mqtt_near = _mqtt_at_x(live, lt["x"])
    switch_fb = it and (
        it["s1_user"].startswith("Switch ") or it["s2_user"].startswith("Switch ")
    )
    if mqtt_near and it:
        kind = "internal_mqtt_fb" if switch_fb else "mqtt"
        motor = mqtt_near
        if switch_fb and lt.get("second", "").startswith("MQTT"):
            mu = lt["second"]
            motor = {
                "panel_system": live["mqtt"][mu]["system"],
                "panel_user": mu,
                "mqtt": live["mqtt"][mu],
            }
        base = _target_from_internal(
            live,
            lt,
            kind,
            f"Crossover leg; motor {motor['panel_user']}" if switch_fb else "",
        )
        base["panel_system"] = motor["panel_system"]
        base["panel_user"] = motor["panel_user"]
        base["mqtt"] = motor["mqtt"]
        return base
    if mqtt_near:
        return mqtt_near
    if it:
        kind = "internal_mqtt_fb" if switch_fb else "internal"
        return _target_from_internal(live, lt, kind)
    raise KeyError(f"No device for layout turnout {ident}")


def _candidate_targets(live: dict) -> list[dict]:
    """Main-line layout turnouts in the linear4 x/y window (then resolve M2T vs IT)."""
    out: list[dict] = []
    for lt in live["layout_turnouts"]:
        if not (LINEAR4_X_MIN <= lt["x"] <= LINEAR4_X_MAX):
            continue
        if not (LINEAR4_Y_MAINLINE[0] <= lt["y"] <= LINEAR4_Y_MAINLINE[1]):
            continue
        if lt["type"] == "DOUBLE_XOVER":
            continue
        out.append(_resolve_panel_target(live, lt))
    return out


def _layout_for_mqtt_user(live: dict, mqtt_user: str) -> dict | None:
    for lt in live["layout_turnouts"]:
        if lt["turnoutname"] == mqtt_user:
            return lt
    return None


def _layout_for_internal_user(
    live: dict,
    internal_user: str,
    panel_system: str | None = None,
    layout_ident: str | None = None,
) -> dict | None:
    if layout_ident:
        for lt in live["layout_turnouts"]:
            if lt["ident"] == layout_ident:
                return lt
    for lt in live["layout_turnouts"]:
        if lt["turnoutname"] == internal_user:
            return lt
    if panel_system:
        for lt in live["layout_turnouts"]:
            if lt["turnoutname"] == panel_system:
                return lt
    for lt in live["layout_turnouts"]:
        if lt["ident"] == internal_user:
            return lt
    return None


def _target_from_panel_system(live: dict, panel_system: str) -> dict:
    if panel_system.startswith("M2T"):
        mqtt_rec = live["mqtt_by_system"].get(panel_system)
        if not mqtt_rec:
            raise KeyError(f"Unknown M2T {panel_system}")
        lt = _layout_for_mqtt_user(live, mqtt_rec["user"])
        if lt is None:
            lt = {"ident": "", "x": 0.0, "y": 0.0, "turnoutname": mqtt_rec["user"], "second": ""}
            return {
                "kind": "mqtt",
                "layout_ident": "",
                "x": lt["x"],
                "y": lt["y"],
                "panel_system": panel_system,
                "panel_user": mqtt_rec["user"],
                "internal": None,
                "mqtt": mqtt_rec,
                "notes": "MQTT only (no layout turnout row found)",
            }
        return _target_from_mqtt_layout(live, lt)

    if panel_system.startswith("IT"):
        it = live["internal_by_system"].get(panel_system)
        if not it:
            raise KeyError(f"Unknown IT {panel_system}")
        layout_ident = next(
            (k for k, v in CURATED_PANEL_SYSTEM.items() if v == panel_system),
            None,
        )
        lt = _layout_for_internal_user(
            live, it["user"], panel_system, layout_ident
        )
        if lt is None:
            raise KeyError(f"No layout turnout for internal {it['user']} ({panel_system})")
        base = _target_from_internal(live, lt, "internal_mqtt_fb", internal_rec=it)
        sec = lt.get("second", "")
        if sec.startswith("MQTT") and sec in live["mqtt"]:
            base["mqtt"] = live["mqtt"][sec]
            base["notes"] = f"Crossover leg; motor {sec} ({base['mqtt']['system']})"
        elif it["s1_user"].startswith("Switch "):
            for mu, mrec in live["mqtt"].items():
                if mrec["s1_user"] == it["s1_user"]:
                    base["mqtt"] = mrec
                    base["notes"] = f"Crossover leg; motor {mu} ({mrec['system']})"
                    break
        return base

    raise ValueError(f"Expected M2T* or IT* panel system, got {panel_system!r}")


def _assign_curated(
    new_turnouts: list[dict], live: dict
) -> list[tuple[dict, dict, float]]:
    assigned = []
    for n in sorted(new_turnouts, key=lambda t: t["x"]):
        panel_system = CURATED_PANEL_SYSTEM.get(n["ident"])
        if not panel_system:
            raise SystemExit(f"No curated panel system for {n['ident']}")
        tgt = _target_from_panel_system(live, panel_system)
        d = abs(n["x"] - tgt["x"]) if tgt["x"] else 0.0
        assigned.append((n, tgt, d))
    return assigned


def _feedback_for_target(target: dict) -> tuple[dict, dict]:
    if target["kind"] == "mqtt" and target["mqtt"]:
        m = target["mqtt"]
        return (
            {"user": m["s1_user"], "system": m["s1_sys"]},
            {"user": m["s2_user"], "system": m["s2_sys"]},
        )
    if target["internal"]:
        it = target["internal"]
        return (
            {"user": it["s1_user"], "system": it["s1_sys"]},
            {"user": it["s2_user"], "system": it["s2_sys"]},
        )
    return ({"user": "", "system": ""}, {"user": "", "system": ""})


def _blocked_sensors() -> list[dict]:
    if not LINEAR4_BLOCKED.exists():
        return []
    root = ET.parse(LINEAR4_BLOCKED).getroot()
    rows = []
    for s in root.findall(".//sensors/sensor"):
        un = (s.findtext("userName") or "").strip()
        sn = (s.findtext("systemName") or "").strip()
        role = "block_occupancy" if un.startswith("BS ") else "other"
        if un.endswith(" FB_N"):
            role = "turnout_feedback_closed"
        elif un.endswith(" FB_R"):
            role = "turnout_feedback_thrown"
        rows.append({"user": un, "system": sn, "role": role})
    return rows


def write_csvs(assigned: list[tuple[dict, dict, float]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    turnout_path = OUT_DIR / "turnout_mapping.csv"
    sensor_path = OUT_DIR / "sensor_mapping.csv"

    with turnout_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "linear4_layout_ident",
                "linear4_x",
                "linear4_y",
                "live_layout_ident",
                "control_kind",
                "panel_turnout_system",
                "panel_turnout_user",
                "live_internal_system",
                "live_mqtt_system",
                "live_mqtt_user",
                "feedback_sensor1_user",
                "feedback_sensor1_system",
                "feedback_sensor2_user",
                "feedback_sensor2_system",
                "switch_id",
                "dcc_address",
                "match_dx_px",
                "notes",
            ]
        )
        for new, tgt, dx in assigned:
            fb1, fb2 = _feedback_for_target(tgt)
            mqtt_sys = tgt["mqtt"]["system"] if tgt.get("mqtt") else ""
            mqtt_user = tgt["mqtt"]["user"] if tgt.get("mqtt") else ""
            internal_sys = tgt["internal"]["system"] if tgt.get("internal") else ""
            switch_id, dcc_address = _switch_dcc_fields(tgt)
            w.writerow(
                [
                    new["ident"],
                    f"{new['x']:.2f}",
                    f"{new['y']:.2f}",
                    tgt["layout_ident"],
                    tgt["kind"],
                    tgt["panel_system"],
                    tgt["panel_user"],
                    internal_sys,
                    mqtt_sys,
                    mqtt_user,
                    fb1["user"],
                    fb1["system"],
                    fb2["user"],
                    fb2["system"],
                    switch_id,
                    dcc_address,
                    f"{dx:.1f}",
                    tgt.get("notes", ""),
                ]
            )

    with sensor_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "sensor_role",
                "linear4_user_name",
                "linear4_system_name",
                "live_physical_system",
                "live_physical_user",
                "associated_linear4_turnout",
                "associated_block",
                "notes",
            ]
        )
        # Turnout feedback from mapping
        for new, tgt, dx in assigned:
            fb1, fb2 = _feedback_for_target(tgt)
            for role, fb in (
                ("turnout_feedback_thrown", fb1),
                ("turnout_feedback_closed", fb2),
            ):
                if not fb["user"]:
                    continue
                w.writerow(
                    [
                        role,
                        f"{new['ident']} FB_R" if "thrown" in role else f"{new['ident']} FB_N",
                        "",
                        fb["system"],
                        fb["user"],
                        new["ident"],
                        "",
                        f"Carry over from live ({tgt['layout_ident']}); dx={dx:.0f}px",
                    ]
                )

        # Block occupancy sensors from linear4_blocked (internal until physical map filled)
        if LINEAR4_BLOCKED.exists():
            root = ET.parse(LINEAR4_BLOCKED).getroot()
            block_occ = {}
            for b in root.findall(".//block"):
                un = (b.findtext("userName") or "").strip()
                occ = (b.findtext("occupancysensor") or "").strip()
                if un and occ:
                    block_occ[occ] = un
            for row in _blocked_sensors():
                if row["role"] != "block_occupancy":
                    continue
                w.writerow(
                    [
                        "block_occupancy",
                        row["user"],
                        row["system"],
                        "",
                        "",
                        row["user"].replace("BS ", "", 1),
                        block_occ.get(row["user"], ""),
                        "Pipeline internal sensor; map live M2S* when hardware known",
                    ]
                )

    print(f"Wrote {turnout_path}")
    print(f"Wrote {sensor_path}")


def _blocked_panel_blocks() -> tuple[
    dict[str, str],
    ET.Element | None,
    ET.Element | None,
    list[ET.Element],
]:
    """
    Block names on track/turnouts plus blocks, layoutblocks, and occupancy sensors
    from linear4_blocked.xml (pipeline output).
    """
    if not LINEAR4_BLOCKED.exists():
        return {}, None, None, []
    root = ET.parse(LINEAR4_BLOCKED).getroot()
    blocked_layout = root.find(".//LayoutEditor")
    blocknames: dict[str, str] = {}
    if blocked_layout is not None:
        for seg in blocked_layout.findall("tracksegment"):
            ident = seg.get("ident")
            bn = seg.get("blockname")
            if ident and bn:
                blocknames[ident] = bn
        for lt in blocked_layout.findall("layoutturnout"):
            ident = lt.get("ident")
            bn = lt.get("blockname")
            if ident and bn:
                blocknames[ident] = bn

    blocks_elem = root.find("blocks")
    layoutblocks_elem = root.find("layoutblocks")

    needed_occ: set[str] = set()
    if blocks_elem is not None:
        for b in blocks_elem.findall("block"):
            occ = (b.findtext("occupancysensor") or "").strip()
            if occ:
                needed_occ.add(occ)

    block_sensors: list[ET.Element] = []
    for mgr in root.findall("sensors"):
        if "internal" not in (mgr.get("class") or "").lower():
            continue
        for s in mgr.findall("sensor"):
            un = (s.findtext("userName") or "").strip()
            if un in needed_occ:
                block_sensors.append(copy.deepcopy(s))
        break

    return blocknames, blocks_elem, layoutblocks_elem, block_sensors


def _apply_blocknames(layout: ET.Element, blocknames: dict[str, str]) -> tuple[int, int]:
    seg_n = to_n = 0
    for seg in layout.findall("tracksegment"):
        ident = seg.get("ident")
        if ident and ident in blocknames:
            seg.set("blockname", blocknames[ident])
            seg_n += 1
    for lt in layout.findall("layoutturnout"):
        ident = lt.get("ident")
        if ident and ident in blocknames:
            lt.set("blockname", blocknames[ident])
            to_n += 1
    return seg_n, to_n


def _merge_sensors_by_system(
    existing: list[ET.Element], extra: list[ET.Element]
) -> list[ET.Element]:
    seen = {(s.findtext("systemName") or "").strip() for s in existing}
    merged = list(existing)
    for s in extra:
        sn = (s.findtext("systemName") or "").strip()
        if sn and sn not in seen:
            merged.append(s)
            seen.add(sn)
    return merged


def _signal_mast_position() -> tuple[float, float, str]:
    """Below TOL42 (M2T410), rotated 180° from prior west-end orientation (270→90)."""
    root = ET.parse(LINEAR4_GEOM).getroot()
    for lt in root.findall(".//layoutturnout"):
        if lt.get("ident") == "TOL42":
            x = float(lt.get("xcen", 259))
            y = float(lt.get("ycen", 181))
            return x, y + 22.0, "90"
    return 259.0, 202.0, "90"


def _jmri_version_elem() -> ET.Element:
    """JMRI panel version; child order must be major, minor, test, modifier (XSD)."""
    v = ET.Element("jmriversion")
    test = "4" if ACTIVE_LAYOUT == "linear5" else "5"
    for tag, text in (("major", "5"), ("minor", "15"), ("test", test)):
        ET.SubElement(v, tag).text = text
    mod = ET.SubElement(v, "modifier")
    if ACTIVE_LAYOUT == "linear5":
        mod.text = "plus"
    return v


def _panel_root(live_root: ET.Element) -> ET.Element:
    """layout-config element with JMRI 5.x schema attrs (required for load)."""
    out = ET.Element("layout-config")
    for key, val in live_root.attrib.items():
        out.set(key, val)
    out.append(_jmri_version_elem())
    return out


def _ensure_clock_running_sensor(
    internal_sensors: list[ET.Element], live_root: ET.Element
) -> None:
    """timebase from tables.xml expects ISCLOCKRUNNING internal sensor."""
    if any(
        (s.findtext("systemName") or "") == "ISCLOCKRUNNING"
        for s in internal_sensors
    ):
        return
    for mgr in live_root.findall("sensors"):
        if "internal" not in (mgr.get("class") or "").lower():
            continue
        for s in mgr.findall("sensor"):
            if (s.findtext("systemName") or "") == "ISCLOCKRUNNING":
                internal_sensors.insert(0, copy.deepcopy(s))
                return


def _manager_shell(live_root: ET.Element, tag: str, class_substr: str) -> ET.Element | None:
    """Copy a sensors/turnouts manager without its device children."""
    for mgr in live_root.findall(tag):
        if class_substr not in (mgr.get("class") or "").lower():
            continue
        shell = copy.deepcopy(mgr)
        for child in list(shell):
            if child.tag in ("sensor", "turnout"):
                shell.remove(child)
        return shell
    return None


def _linear4_ident_to_mqtt_comment() -> dict[str, str]:
    """Map linear4 turnout idents (block comments) to live MQTT switch user names."""
    if not TURNOUT_MAPPING_CSV.is_file():
        return {}
    out: dict[str, str] = {}
    with TURNOUT_MAPPING_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ident = (row.get("linear4_layout_ident") or "").strip()
            mqtt = (row.get("live_mqtt_user") or "").strip()
            if ident and mqtt:
                out[ident] = mqtt
    return out


def _apply_block_switch_comments(
    blocks_elem: ET.Element | None,
    layoutblocks_elem: ET.Element | None,
    ident_to_mqtt: dict[str, str],
) -> int:
    """Rewrite turnout block comments from layout idents to MQTT Switch names."""
    if not ident_to_mqtt:
        return 0
    n = 0
    for blocks in (blocks_elem, layoutblocks_elem):
        if blocks is None:
            continue
        for block in blocks.findall("block"):
            c_el = block.find("comment")
            if c_el is None or not c_el.text:
                continue
            key = c_el.text.strip()
            if key in ident_to_mqtt:
                c_el.text = ident_to_mqtt[key]
                n += 1
    return n


def _write_jmri_panel_xml(root: ET.Element, path: Path) -> None:
    """Write panel XML with stylesheet PI (ElementTree omits it)."""
    ET.indent(ET.ElementTree(root), space="  ")
    body = ET.tostring(root, encoding="unicode", xml_declaration=False)
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<?xml-stylesheet href="/xml/XSLT/panelfile-5-5-5.xsl" type="text/xsl"?>\n'
        f"{body}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_panel(
    assigned: list[tuple[dict, dict, float]],
    live: dict,
    *,
    dcc_label_placement: str = "uniform",
) -> None:
    """Merge linear4.xml geometry with live MQTT sensors/turnouts/signal mast."""
    geom = ET.parse(LINEAR4_GEOM).getroot()
    live_root = live["root"]

    # Collect elements to copy from live
    mqtt_sensors = []
    for s in live_root.findall(".//sensors[@class='jmri.jmrix.mqtt.configurexml.MqttSensorManagerXml']/sensor"):
        un = (s.findtext("userName") or "").strip()
        if un.startswith("Switch "):
            mqtt_sensors.append(copy.deepcopy(s))

    needed_fb_users: set[str] = set()
    needed_mqtt_turnouts: set[str] = set()
    needed_internal: set[str] = set()
    layout_name_by_linear4: dict[str, str] = {}

    for new, tgt, _ in assigned:
        fb1, fb2 = _feedback_for_target(tgt)
        if fb1["user"]:
            needed_fb_users.add(fb1["user"])
        if fb2["user"]:
            needed_fb_users.add(fb2["user"])
        # Layout turnoutname: M2T* for motors, IT* for crossover slave legs.
        if tgt["kind"] == "internal_mqtt_fb" and tgt.get("internal"):
            layout_name_by_linear4[new["ident"]] = tgt["internal"]["system"]
        else:
            layout_name_by_linear4[new["ident"]] = tgt["panel_system"]
        if tgt.get("mqtt"):
            needed_mqtt_turnouts.add(tgt["mqtt"]["user"])
        elif tgt["kind"] == "mqtt":
            needed_mqtt_turnouts.add(tgt["panel_user"])
        if tgt.get("internal"):
            needed_internal.add(tgt["internal"]["user"])
        elif tgt["kind"] in ("internal", "internal_mqtt_fb"):
            needed_internal.add(tgt["panel_user"])

    # Internal feedback sensors (TO_CO etc.)
    internal_sensors = []
    for s in live_root.findall(
        ".//sensors[@class='jmri.jmrix.internal.configurexml.InternalSensorManagerXml']/sensor"
    ):
        un = (s.findtext("userName") or "").strip()
        if un in needed_fb_users or un.startswith("TO_CO34946"):
            internal_sensors.append(copy.deepcopy(s))

    mqtt_turnout_elems = []
    mqtt_turnout_manager = None
    for turnouts in live_root.findall("turnouts"):
        if "mqtt" not in turnouts.get("class", "").lower():
            continue
        for t in turnouts.findall("turnout"):
            un = (t.findtext("userName") or "").strip()
            if un in needed_mqtt_turnouts:
                mqtt_turnout_elems.append(copy.deepcopy(t))
        mqtt_turnout_manager = copy.deepcopy(turnouts)
        for child in list(mqtt_turnout_manager):
            if child.tag == "turnout":
                mqtt_turnout_manager.remove(child)
        break

    internal_turnout_elems = []
    for turnouts in live_root.findall("turnouts"):
        if "internal" not in turnouts.get("class", "").lower():
            continue
        for t in turnouts.findall("turnout"):
            un = (t.findtext("userName") or "").strip()
            if un in needed_internal:
                internal_turnout_elems.append(copy.deepcopy(t))
        break

    signal_mast_elem = None
    for sm in live["signal_masts"]:
        if sm["user"] == "Signal Mast 1":
            signal_mast_elem = copy.deepcopy(sm["elem"])
            break

    signalheads = live_root.find("signalheads")
    if signalheads is not None:
        signalheads = copy.deepcopy(signalheads)

    out = _panel_root(live_root)

    block_seg_n = block_to_n = 0
    blocks_elem = layoutblocks_elem = None
    blocknames, blocks_elem, layoutblocks_elem, block_sensors = _blocked_panel_blocks()
    if block_sensors:
        internal_sensors = _merge_sensors_by_system(internal_sensors, block_sensors)
    if ACTIVE_LAYOUT == "linear5":
        _ensure_clock_running_sensor(internal_sensors, live_root)

    if mqtt_sensors:
        mgr = ET.SubElement(
            out,
            "sensors",
            {
                "class": "jmri.jmrix.mqtt.configurexml.MqttSensorManagerXml",
            },
        )
        for s in mqtt_sensors:
            mgr.append(s)

    internal_sensor_shell = _manager_shell(
        live_root, "sensors", "internal"
    )
    if internal_sensors:
        mgr = (
            copy.deepcopy(internal_sensor_shell)
            if internal_sensor_shell is not None
            else ET.SubElement(
                out,
                "sensors",
                {
                    "class": "jmri.jmrix.internal.configurexml.InternalSensorManagerXml",
                },
            )
        )
        for s in internal_sensors:
            mgr.append(s)
        out.append(mgr)

    if mqtt_turnout_elems and mqtt_turnout_manager is not None:
        mgr = copy.deepcopy(mqtt_turnout_manager)
        for t in mqtt_turnout_elems:
            mgr.append(t)
        out.append(mgr)

    internal_turnout_shell = _manager_shell(
        live_root, "turnouts", "internal"
    )
    if internal_turnout_elems:
        mgr = (
            copy.deepcopy(internal_turnout_shell)
            if internal_turnout_shell is not None
            else ET.SubElement(
                out,
                "turnouts",
                {
                    "class": "jmri.jmrix.internal.configurexml.InternalTurnoutManagerXml",
                },
            )
        )
        for t in internal_turnout_elems:
            mgr.append(t)
        out.append(mgr)

    if signalheads is not None:
        out.append(signalheads)

    if signal_mast_elem is not None:
        smgr = ET.SubElement(
            out,
            "signalmasts",
            {
                "class": "jmri.managers.configurexml.DefaultSignalMastManagerXml",
            },
        )
        smgr.append(signal_mast_elem)

    ident_to_mqtt = _linear4_ident_to_mqtt_comment()
    if blocks_elem is not None:
        blocks_elem = copy.deepcopy(blocks_elem)
        _apply_block_switch_comments(blocks_elem, None, ident_to_mqtt)
    if layoutblocks_elem is not None:
        layoutblocks_elem = copy.deepcopy(layoutblocks_elem)
        _apply_block_switch_comments(None, layoutblocks_elem, ident_to_mqtt)

    if blocks_elem is not None:
        out.append(blocks_elem)
    else:
        ET.SubElement(out, "blocks", {"class": "jmri.configurexml.BlockManagerXml"})
    if layoutblocks_elem is not None:
        out.append(layoutblocks_elem)
    else:
        ET.SubElement(
            out,
            "layoutblocks",
            {"class": "jmri.jmrit.display.configurexml.LayoutBlockManagerXml"},
        )

    geom_layout = geom.find(".//LayoutEditor")
    sx = sy = 0
    signal_degrees = "90"
    display_scale = _load_display_scale()
    panel_assigned = _scale_assigned(assigned, display_scale)
    if geom_layout is not None:
        layout = copy.deepcopy(geom_layout)
        n_icon = remove_icon_positionable_labels(layout)
        if n_icon:
            print(f"  Removed {n_icon} background image label(s) (linear4.jpg)")
        n_embedded = _remove_embedded_positionable_labels(layout)
        if n_embedded:
            print(f"  Removed {n_embedded} embedded label(s) from blocked source")
        n_mast = _remove_embedded_signalmast_icons(layout)
        if n_mast:
            print(f"  Removed {n_mast} embedded signal mast icon(s) from blocked source")
        keep_dims = (
            "x",
            "y",
            "width",
            "height",
            "windowwidth",
            "windowheight",
            "panelwidth",
            "panelheight",
            "drawgrid",
        )
        if ACTIVE_LAYOUT != "linear5":
            keep_dims = (*keep_dims, "sliders", "scrollable")
        saved_dims = {k: layout.get(k) for k in keep_dims if layout.get(k) is not None}
        if display_scale != 1.0:
            _scale_layout_geometry(layout, display_scale)
            saved_dims = _scale_viewport_dims(saved_dims, display_scale)
        x_shift = _load_panel_x_shift()
        if x_shift:
            _shift_layout_x(layout, x_shift)
            panel_assigned = _shift_assigned_x(panel_assigned, x_shift)
        apply_layout_defaults(layout, str(LIVE_PANEL))
        layout.set("name", PANEL_LAYOUT_NAME)
        layout.set("editable", "no")
        for k, v in saved_dims.items():
            layout.set(k, v)
        _scale_layout_display_dims(layout, display_scale)
        for lt in layout.findall("layoutturnout"):
            ident = lt.get("ident", "")
            if ident in layout_name_by_linear4:
                lt.set("turnoutname", layout_name_by_linear4[ident])
        if blocknames:
            block_seg_n, block_to_n = _apply_blocknames(layout, blocknames)
        sx, sy, signal_degrees = _signal_mast_position()
        if display_scale != 1.0:
            sx *= display_scale
            sy *= display_scale
        if x_shift:
            sx -= x_shift
        mast_scale = str(display_scale) if display_scale != 1.0 else "1.0"
        icon = ET.Element(
            "signalmasticon",
            {
                "signalmast": "Signal Mast 1",
                "x": str(int(round(sx))),
                "y": str(int(round(sy))),
                "level": "9",
                "forcecontroloff": "false",
                "hidden": "no",
                "positionable": "true",
                "showtooltip": "true",
                "editable": "false",
                "degrees": signal_degrees,
                "clickmode": "0",
                "litmode": "false",
                "scale": mast_scale,
                "imageset": "default",
                "class": "jmri.jmrit.display.configurexml.SignalMastIconXml",
            },
        )
        layout.append(icon)
        label_placement = _scale_dcc_placement(
            _load_dcc_label_placement(dcc_label_placement), display_scale
        )
        label_placement["_mast_xy"] = (sx, sy)
        dcc_label_size = (
            str(int(round(float(LABEL_STANDARD_SIZE) * display_scale)))
            if display_scale != 1.0
            else None
        )
        n_dcc_labels = _add_dcc_switch_labels(
            layout,
            panel_assigned,
            label_placement,
            label_size=dcc_label_size,
        )
        if n_dcc_labels:
            above = sorted(label_placement.get("above", ()))
            below = sorted(label_placement.get("below", ()))
            extra = ""
            if above or below:
                extra = f", above={list(above)}, below={list(below)}"
            print(
                f"  DCC switch labels: {n_dcc_labels} "
                f"(placement={dcc_label_placement!r}{extra})"
            )
        n_area = _add_layout_area_labels(
            layout, panel_assigned, display_scale=display_scale
        )
        if n_area:
            print(f"  Layout area labels: {n_area}")
        n_track = _add_track_labels(
            layout, align_layout=geom_layout, display_scale=display_scale
        )
        if n_track:
            print(f"  Track labels: {n_track}")
        if display_scale != 1.0:
            print(
                f"  Display scale: {display_scale} (No Zoom load matches prior "
                f"{display_scale}x JMRI zoom)"
            )
        if x_shift:
            print(f"  Panel X shift: −{x_shift:g} display px (viewport.json)")
        if ACTIVE_LAYOUT == "linear5":
            _add_panel_background_image(layout)
            _finalize_layout_editor_order(layout)
            _apply_linear5_layout_viewport(layout)
            print(
                f"  Panel background: {PANEL_BG_ASSET.name} "
                f"({PANEL_BG_PREF_URL}; install under JMRI UserFiles/resources/misc/)"
            )
        else:
            _ensure_panel_background_asset()
            _apply_panel_background_rgb(layout)
            print(
                f"  Panel background: light blue RGB only "
                f"(optional image: {PANEL_BG_PREF_URL}; see assets/README.md)"
            )
        out.append(layout)

    _write_jmri_panel_xml(out, OUT_PANEL)
    print(f"Wrote {OUT_PANEL}")
    if ident_to_mqtt and blocks_elem is not None:
        n_mqtt_comments = sum(
            1
            for b in blocks_elem.findall("block")
            if (b.findtext("comment") or "").startswith("MQTT Switch ")
        )
        if n_mqtt_comments:
            print(f"  Block comments: {n_mqtt_comments} turnout blocks use MQTT switch names")
    if block_seg_n or block_to_n:
        n_blocks = len(blocks_elem.findall("block")) if blocks_elem is not None else 0
        print(
            f"  Blocks from {LINEAR4_BLOCKED.name}: {n_blocks} blocks, "
            f"{block_seg_n} segments + {block_to_n} turnouts named"
        )
    elif not LINEAR4_BLOCKED.exists():
        print(f"  Warning: {LINEAR4_BLOCKED} missing — no blocks on layout")
    print(
        f"  Signal Mast 1 at x={int(sx)}, y={int(sy)}, degrees={signal_degrees} (below TOL42 / M2T410)"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--layout",
        choices=("linear4", "linear5"),
        default="linear4",
        help="Panel layout folder (default: linear4)",
    )
    parser.add_argument(
        "--write-panel",
        action="store_true",
        help="Also write output/<layout>_devices.xml",
    )
    parser.add_argument(
        "--write-prod-panel",
        action="store_true",
        help="Also write output/<layout>_prod.xml (devices + LogixNG/memories/timebase from tables.xml)",
    )
    parser.add_argument(
        "--dcc-label-placement",
        choices=sorted(DCC_LABEL_PLACEMENT_PRESETS),
        default="uniform",
        help=(
            "DCC address label positions: uniform (all above turnout) or split "
            "(west cluster above, main line below). Optional overrides in "
            "jmri/layouts/<layout>/data/dcc_label_placement.json"
        ),
    )
    parser.add_argument(
        "--import-prod-geometry",
        action="store_true",
        help=(
            "Import LayoutEditor geometry from output/<layout>_prod.xml into "
            "<layout>_blocked.xml at 1/display_scale (fractional coords preserved)"
        ),
    )
    parser.add_argument(
        "--sync-label-json",
        action="store_true",
        help="Update data/layout_area_labels.json and track_labels.json from prod labels",
    )
    parser.add_argument(
        "--prod-path",
        type=Path,
        default=None,
        help="Prod panel to import geometry/labels from (default: output/<layout>_prod.xml)",
    )
    args = parser.parse_args()
    _activate_layout(args.layout)

    prod_import_path = args.prod_path or OUT_PROD_PANEL
    if args.import_prod_geometry:
        import_prod_geometry_to_blocked(prod_path=prod_import_path)
    if args.sync_label_json or args.import_prod_geometry:
        _sync_label_json_from_prod(prod_path=prod_import_path)

    live = _parse_live()
    new_turnouts = _linear4_turnouts(LINEAR4_GEOM)
    if len(new_turnouts) != 18:
        raise SystemExit(f"Expected 18 linear4 turnouts, got {len(new_turnouts)}")
    if set(CURATED_PANEL_SYSTEM) != {t["ident"] for t in new_turnouts}:
        raise SystemExit("CURATED_PANEL_SYSTEM keys must match linear4 turnout idents")
    m2t_vals = [v for v in CURATED_PANEL_SYSTEM.values() if v.startswith("M2T")]
    if len(m2t_vals) != len(set(m2t_vals)):
        dup = [v for v in set(m2t_vals) if m2t_vals.count(v) > 1]
        raise SystemExit(f"Duplicate M2T in CURATED_PANEL_SYSTEM: {dup}")

    assigned = _assign_curated(new_turnouts, live)
    write_csvs(assigned)

    if args.write_panel:
        write_panel(assigned, live, dcc_label_placement=args.dcc_label_placement)
    if args.write_prod_panel:
        if not OUT_PANEL.is_file():
            write_panel(assigned, live, dcc_label_placement=args.dcc_label_placement)
        from merge_linear4_prod_panel import merge_prod_panel

        live_for_merge = (
            JMRI_ROOT / "layouts/linear5/reference/tables.xml"
            if ACTIVE_LAYOUT == "linear5"
            and (JMRI_ROOT / "layouts/linear5/reference/tables.xml").is_file()
            else LIVE_PANEL
        )
        merge_prod_panel(
            OUT_PANEL,
            live_for_merge,
            OUT_PROD_PANEL,
            finalize_linear5=ACTIVE_LAYOUT == "linear5",
        )

    print(f"\nTurnout mapping ({ACTIVE_LAYOUT} → panel system name):")
    for new, tgt, dx in assigned:
        flag = " ***" if dx > 40 else ""
        print(f"  {new['ident']:8} → {tgt['panel_system']:8} ({tgt['kind']}) dx={dx:.0f}{flag}")


if __name__ == "__main__":
    main()
