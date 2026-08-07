#!/usr/bin/env python3
"""
Build a tables-ready JMRI panel XML from an AnyRail / layout-only export.

- Removes positionablelabel (background image icons)
- Applies draw scale and optional layoutTrackDrawingOptions from a reference panel
"""
from __future__ import annotations

import importlib.util
import os
import sys
import xml.etree.ElementTree as ET

JMRI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JMRI_ROOT)

_spec = importlib.util.spec_from_file_location(
    "sync_linear_panel",
    os.path.join(JMRI_ROOT, "scripts", "sync_linear_panel.py"),
)
_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sync)

_apply_draw_scale = _sync._apply_draw_scale
_ensure_drawing_options = _sync._ensure_drawing_options
_find_layout = _sync._find_layout
DRAW_SCALE = _sync.DRAW_SCALE


def _local_tag(elem: ET.Element) -> str:
    tag = elem.tag or ""
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    return tag.lower()


def _remove_positionable_labels(layout: ET.Element) -> int:
    removed = 0
    for ch in list(layout):
        if _local_tag(ch) == "positionablelabel":
            layout.remove(ch)
            removed += 1
    return removed


def prepare(
    source_path: str,
    output_path: str,
    reference_path: str | None = None,
    draw_scale: float | None = DRAW_SCALE,
) -> None:
    tree = ET.parse(source_path)
    layout = _find_layout(tree.getroot())
    if layout is None:
        raise SystemExit(f"No LayoutEditor in {source_path}")

    ref_layout = None
    if reference_path and os.path.isfile(reference_path):
        ref_layout = _find_layout(ET.parse(reference_path).getroot())

    n_labels = _remove_positionable_labels(layout)
    if draw_scale is not None and draw_scale != 1.0:
        if ref_layout is not None:
            _ensure_drawing_options(layout, ref_layout, factor=draw_scale)
        _apply_draw_scale(layout, factor=draw_scale)

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    ET.indent(tree, space="  ", level=0)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)

    print(f"Wrote {output_path}")
    print(f"  Removed {n_labels} positionablelabel element(s)")
    if draw_scale is not None and draw_scale != 1.0:
        print(f"  Draw scale x{draw_scale}")
    else:
        print("  Geometry unchanged (1:1 from export; no draw-scale)")


def main() -> None:
    import argparse
    from layout_paths import layout_paths

    ap = argparse.ArgumentParser(description="Prepare AnyRail export for JMRI / tables.")
    ap.add_argument("source", nargs="?", help="AnyRail layout XML")
    ap.add_argument("output", nargs="?", help="Output path")
    ap.add_argument("reference", nargs="?", help="Reference panel for drawing options (optional)")
    ap.add_argument(
        "--scale",
        type=float,
        default=None,
        help="Draw scale factor (default: 2 for legacy linear, 1 for linear3 / --scale 1)",
    )
    args = ap.parse_args()

    paths = layout_paths()
    source = args.source or paths["anyrail"]
    output = args.output or os.path.join(paths["working"], "tables_linear3.xml")
    ref = args.reference or paths.get("style_defaults") or paths["authoritative"]
    scale = args.scale
    if scale is None:
        scale = (
            1.0
            if os.environ.get("JMRI_LAYOUT") in ("linear3", "linear4")
            else DRAW_SCALE
        )
    prepare(source, output, reference_path=ref, draw_scale=scale)


if __name__ == "__main__":
    main()
