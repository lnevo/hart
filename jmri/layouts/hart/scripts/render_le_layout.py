#!/usr/bin/env python3
"""Render the true JMRI Layout Editor geometry (turnouts + track segments)
from a JMRI panel XML to PNG(s).

Uses real LE coordinates (positionablepoint x/y and layoutturnout
xa/ya..xd/yd leg endpoints), so paths are fully contiguous and every turnout
is shown exactly as wired. Supports a whole-layout render and a set of
professional, zoomed control-point views. Its parts: render_le_geometry.py reads the panel, render_le_draw.py
draws a view; SOURCES lists the three files, which build_layout_index.py hashes into the site PNG's stamp.

Usage:
    # whole layout
    python3 jmri/layouts/hart/scripts/render_le_layout.py <panel.xml> <out.png>
    # full professional view set into a directory
    python3 jmri/layouts/hart/scripts/render_le_layout.py <panel.xml> --all-views <out_dir>
    # single custom window
    python3 jmri/layouts/hart/scripts/render_le_layout.py <panel.xml> <out.png> \
        --title "West Yard" --xwin 440 630
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:       # its parts sit beside it; build_layout_index.py loads this file by path
    sys.path.insert(0, str(HERE))
try:            # mast icon sizes, as build_layout_le.py places them; the schematic's signals file
    from hartlib import layer_files
except ImportError:     # run as a script: find the repo's hartlib above this file
    sys.path[:0] = [str(p / "tools/hartlib/src") for p in HERE.parents
                    if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
    from hartlib import layer_files
from hartlib.errors import HartlibError  # noqa: E402

# the parts, re-exported: callers and tests read them here
import render_le_draw  # noqa: E402
from render_le_draw import (  # noqa: E402,F401
    DIVERGE, KIND_COLOUR, MAIN, OVERVIEW_W, PAD, POINT, SIDE, SIGNAL, TOP, UNLISTED, WINDOW_W, Frame, LegendEntry,
    Visible,
)
from render_le_geometry import (  # noqa: E402,F401
    Decor, Geometry, Label, MastIcon, Point, RenderError, Segment, Shape, StationIcon, TurnoutRow, arc_points,
    bezier_points, find_panel, icon_box, load_decor, load_geometry, shape_outline,
)

# this file and its parts: what the drawing depends on, for a stamp of its inputs
SOURCES = (Path(__file__).resolve(), HERE / "render_le_geometry.py", HERE / "render_le_draw.py")

KINDS_FILE = layer_files.path("signals")      # the schematic's signals file; --kinds-sheet picks its section
KINDS_SHEET = "staging"

# Professional panel views. Each: (title, subtitle, xmin, xmax) in LE coords.
VIEWS = {
    "01_overview": ("HART CTC — Full Railroad", "all 20 control points", None, None),
    "02_brick_plane": ("West End — Brick & Plane", "OS 100 / 101 / 102", 210, 430),
    "03_west_yard_engine": ("West Yard Ladder & Engine Terminal",
                            "OS 116-119 (Switch 116/117/118/119) + Scale-T13", 435, 640),
    "04_south_yard": ("South Yard Ladder", "OS 103-106 + Yard Tracks 1-5", 600, 900),
    "05_east_end": ("East End Ladder", "OS 107-112 + 111 crossover / East Lead", 1050, 1410),
    "06_princess_loops": ("Princess & East Loops",
                          "OS 113-115 + McKees Rocks / McKeesport", 1470, 1680),
}


# The legend's first row of swatches, drawn under every view.
LEGEND_ROW = (
    LegendEntry(0, MAIN, 6, "mainline"),
    LegendEntry(120, SIDE, 3, "yard/siding"),
    LegendEntry(250, DIVERGE, 5, "diverging leg"),
    LegendEntry(400, POINT, 0, "control point (turnout)"),
    LegendEntry(590, SIGNAL, 0, "signal facing"),
)

# render_le_draw.render_view with this legend: what callers and the command draw
render_view = functools.partial(render_le_draw.render_view, legend=LEGEND_ROW)


class MastKindsError(HartlibError, ValueError):
    """A --kinds signals file mast_kinds cannot use; the message names the file and what is wrong."""


def positive(text: str) -> float:
    """A --scale above zero."""
    try:
        v = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from exc
    if not v > 0 or math.isinf(v):
        raise argparse.ArgumentTypeError(f"{text!r}: the scale must be above zero")
    return v


def mast_kinds(path: str | Path, sheet: str | None = None) -> dict[str, str]:
    """{mast user name: kind} from a schematic signals file's `signals` list (mast, kind): hart's signals.json, a
    section per sheet (hartlib.layer_files), read at `sheet`'s section (staging when None), or a plain signals file (the plugin's
    signals command's output). Names take the layer-1 `mast_prefix` of `sheet`'s section of the plan_overrides.json beside a
    sectioned file, or of the NAME.plan_overrides.json beside a plain NAME.signals.json, or "Mast " when it sets none.
    MastKindsError on a file it cannot use, a sheet it has no section for, a `sheet` given for a plain file, or a mast listed twice."""
    path = Path(path)
    prefix = "Mast "
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        sectioned = isinstance(data, dict) and data.get(layer_files.SECTIONS) is True
        if sectioned:
            sheet = sheet or KINDS_SHEET
            data = layer_files.section_of(layer_files.parse(text, "signals", str(path)), sheet, str(path))
        rows = data["signals"]
        if not isinstance(rows, list):
            raise TypeError("signals is not a list")
    except (OSError, ValueError, KeyError, TypeError) as e:          # a LayerFileError is a ValueError
        raise MastKindsError(f"--kinds {path}: cannot read a signals list ({e})") from e
    if not sectioned and sheet is not None:
        raise MastKindsError(f"--kinds-sheet {sheet}: {path.name} has no sections; the sheet applies only to a "
                         "sectioned signals.json")
    over = (layer_files.path("plan_overrides", path.parent) if sectioned
            else path.with_name(path.name.replace(".signals.json", ".plan_overrides.json")))
    if over.exists() and over != path:
        try:
            layer = (layer_files.read("plan_overrides", sheet or KINDS_SHEET, path.parent) if sectioned
                     else json.loads(over.read_text(encoding="utf-8")))
            prefix = layer.get("mast_prefix", prefix)
            if not isinstance(prefix, str):
                raise TypeError(f"mast_prefix {prefix!r} is not text")
        except (OSError, ValueError, AttributeError, TypeError) as e:
            raise MastKindsError(f"--kinds: cannot read {over} for the mast prefix ({e})") from e
    out: dict[str, str] = {}
    for r in rows:
        if not isinstance(r, dict) or not r.get("mast") or r.get("kind") not in KIND_COLOUR:
            raise MastKindsError(f"--kinds {path}: each signal needs a mast and a kind of {', '.join(KIND_COLOUR)}: {r!r}")
        name = prefix + r["mast"]
        if name in out:
            raise MastKindsError(f"--kinds {path}: {name} is listed twice")
        out[name] = r["kind"]
    return out


def main(argv: list[str] | None = None) -> int:
    """The command: 0 when drawn, 1 with the message when the panel or the signals file cannot be used."""
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path, nargs="?")
    ap.add_argument("--all-views", type=Path, metavar="OUTDIR")
    ap.add_argument("--title", default="HART Layout")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--xwin", type=float, nargs=2, metavar=("XMIN", "XMAX"))
    ap.add_argument("--panel", help="Layout Editor panel name (default: HART Railroad)")
    ap.add_argument("--curves", action="store_true", help="draw Bezier and arc track as curves, not chords")
    ap.add_argument("--labels", action="store_true",
                    help="draw the panel as Layout Editor shows it: its labels, shapes and single crossovers")
    ap.add_argument("--scale", type=positive, help="image pixels per panel pixel (1 draws the panel at 100%% zoom)")
    ap.add_argument("--kinds", type=Path, nargs="?", const=KINDS_FILE, metavar="SIGNALS_JSON",
                    help="colour mast icons by kind (field, virtual, planned) from a schematic signals file "
                         "(default: signals.json, its --kinds-sheet section)")
    ap.add_argument("--kinds-sheet", metavar="SHEET",
                    help=f"the section of a sectioned signals file to read (default: {KINDS_SHEET}); "
                         "refused for a plain signals file")
    args = ap.parse_args(argv)
    if not args.all_views and not args.out:
        ap.error("out PNG path required unless --all-views is used")
    try:
        draw(args)
    except (OSError, ET.ParseError, RenderError, MastKindsError) as exc:
        print(f"render_le_layout: {exc}", file=sys.stderr)
        return 1
    return 0


def draw(args: argparse.Namespace) -> None:
    """Draw what the parsed arguments ask: every VIEWS view, or one view to `out`."""
    root = ET.parse(args.src).getroot()
    pp, legs, turnouts, segs, signals, stations = load_geometry(args.src, args.panel, args.curves, root)
    if args.kinds:
        kinds = mast_kinds(args.kinds, args.kinds_sheet)
        unlisted = sorted(s["name"] for s in signals if s["name"] not in kinds)
        if unlisted:
            print(f"--kinds: not in {args.kinds.name}, drawn grey: {', '.join(unlisted)}")
        for s in signals:
            s["kind"] = kinds.get(s["name"])

    if args.all_views:
        for key, (title, subtitle, xmin, xmax) in VIEWS.items():
            render_view(pp, legs, turnouts, segs, signals, stations,
                        args.all_views / f"hart_ctc_{key}.png",
                        title, subtitle, xmin, xmax)
        return
    xmin = args.xwin[0] if args.xwin else None
    xmax = args.xwin[1] if args.xwin else None
    render_view(
        pp, legs, turnouts, segs, signals, stations,
        args.out, args.title, args.subtitle, xmin, xmax,
        decor=load_decor(args.src, args.panel, root) if args.labels else None,
        fixed_scale=args.scale,
    )


if __name__ == "__main__":
    sys.exit(main())
