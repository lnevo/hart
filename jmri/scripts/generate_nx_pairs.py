#!/usr/bin/env python3
"""
Build block connectivity from mac_jmri_blocked.xml and list valid Entry/Exit (NX) pairs.
Use this if JMRI Auto Generate doesn't find pairs: add these pairs manually in
Layout Editor → Tools → Entry Exit → Add Pair (Entry Point / Exit Point).

Reads: mac_jmri_blocked.xml (or path as first arg).
Writes: nx_pairs.txt with one line per pair: "EntrySensor\tExitSensor"
"""
import collections
import os
import sys
import xml.etree.ElementTree as ET

JMRI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JMRI_ROOT)
from layout_paths import layout_paths

_PATHS = layout_paths()
DEFAULT_PANEL = _PATHS["output"]
DEFAULT_OUT = _PATHS["nx_pairs"]


def get_segment_block_map(layout_elem):
    seg_block = {}
    for elem in layout_elem.iter():
        tag = (elem.tag or "").strip().lower()
        if tag != "tracksegment":
            continue
        ident = elem.get("ident")
        block = elem.get("blockname")
        if ident and block:
            seg_block[ident] = block
    return seg_block


def get_turnout_block_map(layout_elem):
    to_block = {}
    for elem in layout_elem.iter():
        tag = (elem.tag or "").strip().lower()
        if "layoutturnout" not in tag:
            continue
        ident = elem.get("ident") or elem.get("turnoutname")
        block = elem.get("blockname")
        if ident and block:
            to_block[ident] = block
    return to_block


def build_block_neighbors(seg_block, to_block, layout_elem):
    """From segments and turnouts: for each block, set of neighboring blocks (shared boundary)."""
    neighbors = collections.defaultdict(set)
    # Segment has connect1name, connect2name -> idents of positionable points or turnouts
    # So two segments that share a point are adjacent; their blocks are neighbors.
    point_to_segs = collections.defaultdict(list)
    for elem in layout_elem.iter():
        tag = (elem.tag or "").strip().lower()
        if tag != "tracksegment":
            continue
        ident = elem.get("ident")
        block = elem.get("blockname")
        if not ident or not block:
            continue
        c1 = elem.get("connect1name")
        c2 = elem.get("connect2name")
        if c1:
            point_to_segs[c1].append(block)
        if c2:
            point_to_segs[c2].append(block)
    # Turnout legs: connect*name can be segment idents. Segments connect to turnouts by ident.
    # So segment T-I-TOL35287 has connect1name TOL35287 (turnout), connect2name A149 (point).
    # Turnout has blockname; segment has blockname. So at point A149 we have segment block and maybe another segment.
    for point_ident, blocks_at_point in point_to_segs.items():
        for b in blocks_at_point:
            for b2 in blocks_at_point:
                if b != b2:
                    neighbors[b].add(b2)
    return neighbors


def all_reachable(neighbors, start_block, max_hops=50):
    """BFS from start_block; return set of blocks reachable within max_hops."""
    seen = {start_block}
    frontier = [start_block]
    for _ in range(max_hops):
        if not frontier:
            break
        next_frontier = []
        for b in frontier:
            for n in neighbors.get(b, []):
                if n not in seen:
                    seen.add(n)
                    next_frontier.append(n)
        frontier = next_frontier
    return seen


def boundary_sensors_and_blocks(layout_elem, seg_block):
    """Yield (sensor_user_name, block_name) for each boundary sensor. End bumper -> one block; anchor -> two (we yield both sides)."""
    for elem in layout_elem.iter():
        tag = (elem.tag or "").strip().lower()
        if "positionablepoint" not in tag:
            continue
        pt_type = (elem.get("type") or "").strip().upper()
        ident = elem.get("ident") or ""
        if not ident:
            continue
        east = elem.get("eastboundsensor")
        west = elem.get("westboundsensor")
        c1 = elem.get("connect1name")
        c2 = elem.get("connect2name")
        if pt_type == "END_BUMPER":
            track_seg = c1 if c1 and (not c2 or "LINK-" in (c2 or "")) else c2
            if not track_seg or "LINK-" in (track_seg or ""):
                track_seg = c1 or c2
            block = seg_block.get(track_seg) if track_seg else None
            if block and east:
                yield (east, block)
        elif pt_type == "ANCHOR" and c1 and c2:
            b1, b2 = seg_block.get(c1), seg_block.get(c2)
            if b1 and b2 and b1 != b2:
                if east:
                    yield (east, b1)  # east side toward b1
                if west:
                    yield (west, b2)


def main():
    panel_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PANEL
    out_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    if not os.path.isfile(panel_path):
        print(f"Panel file not found: {panel_path}")
        sys.exit(1)

    tree = ET.parse(panel_path)
    root = tree.getroot()
    layout = root.find(".//LayoutEditor")
    if layout is None:
        layout = root.find(".//{*}LayoutEditor")
    if layout is None:
        for elem in root.iter():
            if "LayoutEditor" in (elem.tag or ""):
                layout = elem
                break
    if layout is None:
        print("LayoutEditor not found in panel XML")
        sys.exit(1)

    seg_block = get_segment_block_map(layout)
    to_block = get_turnout_block_map(layout)
    neighbors = build_block_neighbors(seg_block, to_block, layout)

    sensor_to_block = list(boundary_sensors_and_blocks(layout, seg_block))
    # Multiple sensors can be at same block (e.g. anchor has NX A48-E and NX A48-W at boundary of two blocks)
    block_to_sensors = collections.defaultdict(list)
    for sen, blk in sensor_to_block:
        block_to_sensors[blk].append(sen)

    pairs = []
    for entry_sensor, entry_block in sensor_to_block:
        reachable = all_reachable(neighbors, entry_block)
        for exit_block in reachable:
            if exit_block == entry_block:
                continue
            for exit_sensor in block_to_sensors.get(exit_block, []):
                if exit_sensor != entry_sensor:
                    pairs.append((entry_sensor, exit_sensor))

    # Deduplicate (same pair might appear from different paths)
    seen_pair = set()
    unique = []
    for a, b in pairs:
        key = (min(a, b), max(a, b))
        if key not in seen_pair:
            seen_pair.add(key)
            unique.append((a, b))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Entry/Exit (NX) pairs: EntrySensor\tExitSensor\n")
        f.write("# Add these manually in Layout Editor → Tools → Entry Exit → Add Pair\n")
        for entry_sensor, exit_sensor in sorted(unique, key=lambda x: (x[0], x[1])):
            f.write(f"{entry_sensor}\t{exit_sensor}\n")

    print(f"Block graph: {len(neighbors)} blocks, boundary sensors at {len(sensor_to_block)} (sensor, block) sides")
    print(f"Generated {len(unique)} unique NX pairs → {out_path}")
    print("Add them in JMRI: Layout Editor → Tools → Entry Exit → Add Pair (choose Entry Point and Exit Point from the lists).")


if __name__ == "__main__":
    main()
