#!/usr/bin/env python3
"""
Spread LayoutEditor track geometry along Y (increase vertical track spacing).

Scales every Y coordinate around a pivot while leaving X unchanged. Use small
factors incrementally (e.g. 1.15, 1.20, 1.25) and open each output in JMRI
before increasing further.

Does NOT change xscale/yscale draw scale (that skewed linear3). Does NOT move
topology — segment/turnout idents and connections stay the same.

Usage:
  python3 jmri/scripts/spread_layout_y.py input.xml output.xml --factor 1.20
  python3 jmri/scripts/spread_layout_y.py input.xml output.xml --factor 1.25 --pivot-y 178
"""
from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET

Y_ATTRS = frozenset({"y", "ya", "yb", "yc", "yd", "ycen"})

TRACK_GEOMETRY_TAGS = frozenset(
    {
        "positionablepoint",
        "layoutturnout",
        "layoutslip",
        "layoutxing",
        "levelxing",
        "layoutturntable",
        "layoutshape",
        "controlpoint",
    }
)

# LayoutEditor attrs that define turnout/crossover draw size (scale with Y spread).
TURNOUT_SIZE_ATTRS = frozenset(
    {
        "turnoutbx",
        "turnoutcx",
        "turnoutwid",
        "xoverlong",
        "xoverhwid",
        "xovershort",
    }
)


def _local_tag(elem: ET.Element) -> str:
    tag = elem.tag or ""
    return tag.split("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _find_layout(root: ET.Element) -> ET.Element | None:
    layout = root.find(".//LayoutEditor")
    if layout is None:
        layout = root.find(".//{*}LayoutEditor")
    if layout is None:
        for elem in root.iter():
            if elem.tag and "LayoutEditor" in elem.tag:
                return elem
    return layout


def _elem_y_values(elem: ET.Element) -> list[float]:
    ys: list[float] = []
    for attr in Y_ATTRS:
        v = elem.get(attr)
        if v is None:
            continue
        try:
            ys.append(float(v))
        except ValueError:
            pass
    return ys


def _collect_track_y(layout: ET.Element) -> list[float]:
    """Y range for pivot/height — track geometry only (ignore labels at y=0)."""
    ys: list[float] = []
    for elem in layout.iter():
        if elem is layout:
            continue
        if _local_tag(elem) not in TRACK_GEOMETRY_TAGS:
            continue
        ys.extend(_elem_y_values(elem))
    return ys


def _collect_all_y(layout: ET.Element) -> list[float]:
    ys: list[float] = []
    for elem in layout.iter():
        if elem is layout:
            continue
        ys.extend(_elem_y_values(elem))
    return ys


def _scale_y_value(y: float, pivot: float, factor: float) -> float:
    return pivot + (y - pivot) * factor


def _set_scaled_y_attr(elem: ET.Element, attr: str, pivot: float, factor: float) -> bool:
    v = elem.get(attr)
    if v is None:
        return False
    try:
        ny = _scale_y_value(float(v), pivot, factor)
        elem.set(attr, str(round(ny, 3)))
        return True
    except ValueError:
        return False


def _spread_all_y(layout: ET.Element, pivot: float, factor: float) -> int:
    """Single pass: every Y attr under LayoutEditor (avoids double-scaling controlpoints)."""
    n = 0
    for elem in layout.iter():
        if elem is layout:
            continue
        for attr in Y_ATTRS:
            if _set_scaled_y_attr(elem, attr, pivot, factor):
                n += 1
    return n


def _scale_turnout_draw_sizes(layout: ET.Element, factor: float) -> int:
    n = 0
    for attr in TURNOUT_SIZE_ATTRS:
        v = layout.get(attr)
        if v is None:
            continue
        try:
            layout.set(attr, str(round(float(v) * factor, 3)))
            n += 1
        except ValueError:
            pass
    return n


def _remove_bg_labels(layout: ET.Element) -> int:
    removed = 0
    for ch in list(layout):
        if _local_tag(ch) != "positionablelabel":
            continue
        icon = ch.find("icon")
        if icon is not None and (icon.get("url") or "").strip():
            layout.remove(ch)
            removed += 1
    return removed


def _fit_panel_height(
    layout: ET.Element,
    *,
    bottom_margin: float,
    min_height: int,
) -> tuple[int, float, float]:
    ys = _collect_all_y(layout)
    if not ys:
        raise SystemExit("No Y coordinates found after spread")
    ymin, ymax = min(ys), max(ys)
    new_h = max(min_height, int(math.ceil(ymax + bottom_margin)))
    for attr in ("height", "panelheight", "windowheight"):
        layout.set(attr, str(new_h))
    return new_h, ymin, ymax


def spread_layout_y(
    layout: ET.Element,
    *,
    factor: float,
    pivot_y: float | None,
    expand_panel_height: bool,
    bottom_margin: float,
    min_panel_height: int,
    scale_turnout_sizes: bool,
) -> dict[str, float | int]:
    if factor <= 0:
        raise SystemExit("--factor must be positive")
    if abs(factor - 1.0) < 1e-9:
        raise SystemExit("--factor must differ from 1.0")

    n_labels = _remove_bg_labels(layout)

    ys_before = _collect_track_y(layout)
    if not ys_before:
        raise SystemExit("No track geometry Y coordinates found")
    pivot = pivot_y if pivot_y is not None else (min(ys_before) + max(ys_before)) / 2.0

    n_y = _spread_all_y(layout, pivot, factor)
    n_turnout = _scale_turnout_draw_sizes(layout, factor) if scale_turnout_sizes else 0
    ys_after = _collect_track_y(layout)
    ymin_a, ymax_a = min(ys_after), max(ys_after)

    new_h = int(layout.get("panelheight") or layout.get("height") or 320)
    if expand_panel_height:
        new_h, ymin_a, ymax_a = _fit_panel_height(
            layout,
            bottom_margin=bottom_margin,
            min_height=min_panel_height,
        )

    return {
        "pivot_y": pivot,
        "factor": factor,
        "y_min_before": min(ys_before),
        "y_max_before": max(ys_before),
        "y_min_after": ymin_a,
        "y_max_after": ymax_a,
        "coords_updated": n_y,
        "turnout_size_attrs": n_turnout,
        "bg_labels_removed": n_labels,
        "panel_height": new_h,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Spread layout track geometry along Y around a pivot (X unchanged)."
    )
    ap.add_argument("input", help="Source panel XML (e.g. linear4 anyrail export)")
    ap.add_argument("output", help="Output panel XML path")
    ap.add_argument(
        "--factor",
        type=float,
        required=True,
        help="Y spread factor (>1 widens track spacing, e.g. 1.20 = +20%% from pivot)",
    )
    ap.add_argument(
        "--pivot-y",
        type=float,
        default=None,
        help="Pivot Y in layout coords (default: midpoint of track Y range)",
    )
    ap.add_argument(
        "--layout-name",
        default=None,
        help="Set LayoutEditor name attribute (e.g. linear5)",
    )
    ap.add_argument(
        "--no-expand-panel-height",
        action="store_true",
        help="Keep panelheight; only move geometry",
    )
    ap.add_argument("--bottom-margin", type=float, default=48.0)
    ap.add_argument("--min-panel-height", type=int, default=320)
    ap.add_argument(
        "--no-scale-turnout-sizes",
        action="store_true",
        help="Do not scale turnoutbx/turnoutcx/turnoutwid/xover* on LayoutEditor",
    )
    args = ap.parse_args()

    tree = ET.parse(args.input)
    layout = _find_layout(tree.getroot())
    if layout is None:
        raise SystemExit(f"No LayoutEditor in {args.input}")

    if args.layout_name:
        layout.set("name", args.layout_name)

    stats = spread_layout_y(
        layout,
        factor=args.factor,
        pivot_y=args.pivot_y,
        expand_panel_height=not args.no_expand_panel_height,
        bottom_margin=args.bottom_margin,
        min_panel_height=args.min_panel_height,
        scale_turnout_sizes=not args.no_scale_turnout_sizes,
    )

    ET.indent(tree, space="  ", level=0)
    out_dir = __import__("os").path.dirname(args.output)
    if out_dir:
        __import__("os").makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)

    print(f"Wrote {args.output}")
    print(f"  Factor: {stats['factor']}  pivot Y: {stats['pivot_y']:.2f}")
    print(
        f"  Track Y: {stats['y_min_before']:.1f}–{stats['y_max_before']:.1f} "
        f"→ {stats['y_min_after']:.1f}–{stats['y_max_after']:.1f}"
    )
    print(f"  Y coordinates updated: {stats['coords_updated']}")
    if stats["turnout_size_attrs"]:
        print(f"  Turnout draw size attrs scaled: {stats['turnout_size_attrs']}")
    if stats["bg_labels_removed"]:
        print(f"  Removed {stats['bg_labels_removed']} background image label(s)")
    print(f"  panelheight: {stats['panel_height']}")


if __name__ == "__main__":
    main()
