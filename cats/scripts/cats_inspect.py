#!/usr/bin/env python3
"""Read-only inspectors of a CATS panel XML. Nothing here writes a file.

    python3 cats/scripts/cats_inspect.py edges PANEL...        how each SEC_EDGE joint is typed, with a total for 2+
    python3 cats/scripts/cats_inspect.py grid PANEL...         every TRACKPLAN cell: tracks and edge kinds
    python3 cats/scripts/cats_inspect.py trace PANEL           every wired plant: its OS block and where each leg leads
    python3 cats/scripts/cats_inspect.py trace PANEL X Y LEG   the block one leg of the plant at (X, Y) leads to

edges: the edge runtime class comes from tools/cats/src-repo/cats/src/cats/layout/items/EdgeBuilder:
  child BLOCK        -> BlkEdge   (AbstractTrackEdge)
  child SWITCHPOINTS -> OSEdge / PtsEdge (AbstractTrackEdge)
  neither            -> plain SecEdge (NOT AbstractTrackEdge)

trace uses digicon_trace.py, the module the desk builders import, so it follows a leg as the build does.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

EDGES = ("LEFT", "RIGHT", "TOP", "BOTTOM")

# ---- edges ---------------------------------------------------------------------------------------------------------

OPP = {
    "LEFT": ("RIGHT", -1, 0),
    "RIGHT": ("LEFT", 1, 0),
    "TOP": ("BOTTOM", 0, -1),
    "BOTTOM": ("TOP", 0, 1),
}

# track type -> the two edges it terminates on
TRACK_ENDS = {
    "HORIZONTAL": ("LEFT", "RIGHT"),
    "VERTICAL": ("TOP", "BOTTOM"),
    "UPPERSLASH": ("TOP", "LEFT"),
    "LOWERSLASH": ("BOTTOM", "RIGHT"),
    "UPPERBACKSLASH": ("TOP", "RIGHT"),
    "LOWERBACKSLASH": ("BOTTOM", "LEFT"),
}


def joint_kind(e: ET.Element) -> str:
    if e.find("SWITCHPOINTS") is not None:
        return "PTS"
    if e.find("BLOCK") is not None:
        b = e.find("BLOCK")
        return "BLK*" if b.get("NAME") else "BLK"
    return "PLAIN"


def sections(root: ET.Element) -> dict[tuple[int, int], ET.Element]:
    tp = root.find("TRACKPLAN")
    out = {}
    for s in tp.findall("SECTION"):
        if s.find("TRACKGROUP") is None:
            continue
        out[(int(s.get("X")), int(s.get("Y")))] = s
    return out


def tracks_of(sec: ET.Element) -> list[str]:
    tg = sec.find("TRACKGROUP")
    return [] if tg is None else [(t.text or "").strip() for t in tg.findall("TRACK")]


def analyze(path: Path) -> Counter:
    root = ET.parse(path).getroot()
    secs = sections(root)
    pairs: Counter = Counter()
    problems: list[str] = []

    for (x, y), sec in sorted(secs.items()):
        kinds = {e.get("EDGE"): joint_kind(e) for e in sec.findall("SEC_EDGE")}
        used = set()
        for t in tracks_of(sec):
            used.update(TRACK_ENDS.get(t, ()))
        missing = used - set(kinds)
        if missing:
            problems.append(f"({x},{y}) tracks need edges {sorted(missing)}; has {sorted(kinds)}")
        extra = set(kinds) - used
        if extra:
            problems.append(f"({x},{y}) edge(s) {sorted(extra)} with no track end")
        for e in sec.findall("SEC_EDGE"):
            if e.find("BLOCK") is not None and e.find("SWITCHPOINTS") is not None:
                problems.append(f"({x},{y}) {e.get('EDGE')} has BLOCK+SWITCHPOINTS")

        for ed, k in kinds.items():
            ned, dx, dy = OPP[ed]
            n = secs.get((x + dx, y + dy))
            if n is None:
                pairs[f"{k} <-> (none)"] += 1
                continue
            nk = None
            for ee in n.findall("SEC_EDGE"):
                if ee.get("EDGE") == ned:
                    nk = joint_kind(ee)
            if nk is None:
                pairs[f"{k} <-> (no-edge)"] += 1
                continue
            pairs["  <->  ".join(sorted([k, nk]))] += 1

    print(f"--- {path.name}  sections={len(secs)}")
    for k, v in sorted(pairs.items()):
        print(f"    {v:4d}  {k}")
    for p in problems:
        print(f"    !! {p}")
    return pairs


def cmd_edges(args: argparse.Namespace) -> int:
    total: Counter = Counter()
    for a in args.panels:
        total += analyze(Path(a))
    if len(args.panels) > 1:
        print("=== TOTAL")
        for k, v in sorted(total.items()):
            print(f"    {v:4d}  {k}")
    return 0


# ---- grid ----------------------------------------------------------------------------------------------------------


def cell_edge_kind(e: ET.Element) -> str:
    blk = e.find("BLOCK")
    if e.find("SWITCHPOINTS") is not None:
        return "SP"
    if e.find("CROSSINGEDGE") is not None:
        return "XING"
    if blk is not None:
        name = blk.get("NAME")
        vis = blk.get("VISIBLE")
        if name:
            return f"BLK[{name}{'' if vis == 'true' else ' !vis'}]"
        return "BLK[-]"
    return "plain"


def routes(e: ET.Element) -> str:
    sp = e.find("SWITCHPOINTS")
    if sp is None:
        return ""
    parts = []
    for r in sp.findall("ROUTEINFO"):
        parts.append(r.get("ROUTEID") + ("*" if r.get("NORMAL") == "true" else ""))
    return "{" + ",".join(parts) + "}"


def dump(path: Path) -> None:
    root = ET.parse(path).getroot()
    tp = root.find("TRACKPLAN")
    print("=" * 78)
    print(f"{path}  WIDTH={root.get('WIDTH')} HEIGHT={root.get('HEIGHT')} {tp.attrib}")
    cells = []
    for s in tp.findall("SECTION"):
        x, y = int(s.get("X")), int(s.get("Y"))
        tg = s.find("TRACKGROUP")
        if tg is None:
            nm = s.find("SEC_NAME")
            if nm is not None:
                cells.append((y, x, f"({x},{y}) LABEL {nm.get('NAME')!r}"))
            continue
        tracks = "+".join((t.text or "").strip() for t in tg.findall("TRACK"))
        eds = []
        for e in s.findall("SEC_EDGE"):
            eds.append(f"{e.get('EDGE')}={cell_edge_kind(e)}{routes(e)}")
        cells.append((y, x, f"({x},{y}) {tracks:<28} " + "  ".join(eds)))
    for _y, _x, line in sorted(cells):
        print("  " + line)
    names = sorted({b.get("NAME") for b in root.iter("BLOCK") if b.get("NAME")})
    print(f"  -- track cells: {sum(1 for s in tp.findall('SECTION') if s.find('TRACKGROUP') is not None)}")
    print(f"  -- named blocks ({len(names)}): {', '.join(names)}")


def cmd_grid(args: argparse.Namespace) -> int:
    for a in args.panels:
        dump(Path(a))
    return 0


# ---- trace ---------------------------------------------------------------------------------------------------------


def cmd_trace(args: argparse.Namespace) -> int:
    import digicon_trace as trace  # needs cats/scripts on the path (above) and tools/hartlib (digicon_lib finds it)

    cells = trace.track_cells(ET.parse(args.panel).getroot().find("TRACKPLAN"))
    if args.x is not None:
        xy = (args.x, args.y)
        if xy not in cells:
            print(f"no track cell at {xy}", file=sys.stderr)
            return 1
        try:
            name = trace.trace_leg(cells, xy, args.leg)
        except trace.PlantError as e:
            print(f"!! {e}", file=sys.stderr)
            return 1
        print(name if name is not None else "(none)")
        return 0 if name is not None else 1
    bad = 0
    for xy, sec in sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if sec.find("SEC_EDGE/SWITCHPOINTS/ROUTEINFO") is None:
            continue
        pts, legs = trace.plant_edges(sec)
        try:
            os_name = trace.plant_os(cells, xy)
        except trace.PlantError as e:
            print(f"  ({xy[0]},{xy[1]}) !! {e}")
            bad += 1
            continue
        ends = "  ".join(f"{leg}->{trace.trace_leg(cells, xy, leg, own=os_name) or '(none)'}" for leg in legs)
        print(f"  ({xy[0]},{xy[1]}) {os_name:<24} points {pts}  {ends}")
    return 1 if bad else 0


# ---- dispatch ------------------------------------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("edges", help="how each SEC_EDGE joint is typed")
    p.add_argument("panels", nargs="+", metavar="PANEL")
    p.set_defaults(func=cmd_edges)
    p = sub.add_parser("grid", help="every TRACKPLAN cell: tracks and edge kinds")
    p.add_argument("panels", nargs="+", metavar="PANEL")
    p.set_defaults(func=cmd_grid)
    p = sub.add_parser("trace", help="where a plant's legs lead (all plants, or one leg)")
    p.add_argument("panel", metavar="PANEL")
    p.add_argument("x", nargs="?", type=int, metavar="X")
    p.add_argument("y", nargs="?", type=int, metavar="Y")
    p.add_argument("leg", nargs="?", choices=EDGES, metavar="LEG")
    p.set_defaults(func=cmd_trace)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = parser()
    args = ap.parse_args(argv)
    if args.cmd == "trace" and (args.x is None) != (args.leg is None):
        ap.error("trace takes PANEL alone, or PANEL X Y LEG")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
