#!/usr/bin/env python3
"""
Post-process linear5 (or any spread layout): east-end arc roundness (default).

1. Move anchor A48 right — scale its X offset from the east vertical (A58/A67) by
   --arc-x-scale (default 4, matching Y spread factor).

Optional --level: snap anchors to turnout leg Y and average horizontal segments
(can look jagged; off by default).

Usage:
  python3 jmri/scripts/polish_linear5_geometry.py panel.xml [output.xml]
  python3 jmri/scripts/polish_linear5_geometry.py panel.xml --arc-x-scale 4
  python3 jmri/scripts/polish_linear5_geometry.py panel.xml --level   # leveling
  python3 jmri/scripts/polish_linear5_geometry.py panel.xml --round-only --coord-decimals 0
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import xml.etree.ElementTree as ET

_LINEAR4_LAYOUT = (
    Path(__file__).resolve().parents[1] / "layouts/linear4/authoritative/linear4.xml"
)

Y_ATTRS = frozenset({"y", "ya", "yb", "yc", "yd", "ycen"})
EAST_ARC_ANCHORS = frozenset({"A48", "A58", "A67"})
LEG_PREFIX = (
    ("T-I-", "ycen"),
    ("T-ER-", "yb"),
    ("T-EL-", "yc"),
)


def _local_tag(elem: ET.Element) -> str:
    tag = elem.tag or ""
    return tag.split("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _find_layout(root: ET.Element) -> ET.Element | None:
    layout = root.find(".//LayoutEditor")
    if layout is None:
        for elem in root.iter():
            if elem.tag and "LayoutEditor" in elem.tag:
                return elem
    return layout


_COORD_DECIMALS = 2


def _fmt_coord(value: float, places: int | None = None) -> str:
    p = _COORD_DECIMALS if places is None else places
    r = round(value, p)
    if p == 0 or r == int(r):
        return str(int(r))
    return str(r)


def _fmt_y(y: float, places: int | None = None) -> str:
    return _fmt_coord(y, places)


def _fmt_x(x: float, places: int | None = None) -> str:
    return _fmt_coord(x, places)


def _anchor_index(layout: ET.Element) -> dict[str, ET.Element]:
    return {
        pp.get("ident"): pp
        for pp in layout.findall("positionablepoint")
        if pp.get("ident")
    }


def _turnout_index(layout: ET.Element) -> dict[str, ET.Element]:
    return {
        lt.get("ident"): lt
        for lt in layout.findall("layoutturnout")
        if lt.get("ident")
    }


def _leg_y_for_segment(
    leg_seg: str,
    turnouts: dict[str, ET.Element],
) -> float | None:
    for prefix, attr in LEG_PREFIX:
        if not leg_seg.startswith(prefix):
            continue
        ident = leg_seg[len(prefix) :]
        lt = turnouts.get(ident)
        if lt is None:
            return None
        v = lt.get(attr if attr != "ycen" else "ycen")
        return float(v) if v is not None else None
    return None


def _snap_anchors_to_turnout_legs(
    layout: ET.Element,
    anchors: dict[str, ET.Element],
    turnouts: dict[str, ET.Element],
) -> int:
    n = 0
    for ident, pp in anchors.items():
        if ident in EAST_ARC_ANCHORS:
            continue
        conns = [c for c in (pp.get("connect1name"), pp.get("connect2name")) if c]
        target: float | None = None
        for prefix, _ in LEG_PREFIX:
            for conn in conns:
                if conn.startswith(prefix):
                    target = _leg_y_for_segment(conn, turnouts)
                    if target is not None:
                        break
            if target is not None:
                break
        if target is None:
            continue
        old = float(pp.get("y") or 0)
        if abs(old - target) < 0.05:
            continue
        pp.set("y", _fmt_y(target))
        n += 1
    return n


def _is_straight_horizontal(
    seg: ET.Element,
    anchors: dict[str, ET.Element],
    *,
    min_dx: float = 25.0,
) -> tuple[str, str] | None:
    if seg.get("arc") == "yes" or seg.get("bezier") == "yes":
        return None
    c1, t1 = seg.get("connect1name"), seg.get("type1")
    c2, t2 = seg.get("connect2name"), seg.get("type2")
    if t1 != "POS_POINT" or t2 != "POS_POINT":
        return None
    if c1 not in anchors or c2 not in anchors:
        return None
    if c1 in EAST_ARC_ANCHORS or c2 in EAST_ARC_ANCHORS:
        return None
    x1, y1 = float(anchors[c1].get("x")), float(anchors[c1].get("y"))
    x2, y2 = float(anchors[c2].get("x")), float(anchors[c2].get("y"))
    if abs(x2 - x1) < min_dx:
        return None
    if abs(y2 - y1) > 12.0:
        return None
    return c1, c2


def _level_horizontal_segments(
    layout: ET.Element,
    anchors: dict[str, ET.Element],
    *,
    passes: int = 4,
) -> int:
    n = 0
    for _ in range(passes):
        for seg in layout.findall("tracksegment"):
            pair = _is_straight_horizontal(seg, anchors)
            if pair is None:
                continue
            c1, c2 = pair
            y1 = float(anchors[c1].get("y"))
            y2 = float(anchors[c2].get("y"))
            avg = (y1 + y2) / 2.0
            if abs(y1 - avg) > 0.02:
                anchors[c1].set("y", _fmt_y(avg))
                n += 1
            if abs(y2 - avg) > 0.02:
                anchors[c2].set("y", _fmt_y(avg))
                n += 1
    return n


def _update_bezier_controls(
    layout: ET.Element,
    anchors: dict[str, ET.Element],
    old_y: dict[str, float],
) -> int:
    n = 0
    for seg in layout.findall("tracksegment"):
        if seg.get("bezier") != "yes":
            continue
        c1, t1 = seg.get("connect1name"), seg.get("type1")
        c2, t2 = seg.get("connect2name"), seg.get("type2")
        ends: list[tuple[float, float, float]] = []
        if t1 == "POS_POINT" and c1 in anchors:
            x = float(anchors[c1].get("x"))
            y = float(anchors[c1].get("y"))
            dy = y - old_y.get(c1, y)
            ends.append((x, y, dy))
        if t2 == "POS_POINT" and c2 in anchors:
            x = float(anchors[c2].get("x"))
            y = float(anchors[c2].get("y"))
            dy = y - old_y.get(c2, y)
            ends.append((x, y, dy))
        if len(ends) != 2:
            continue
        (x1, _, dy1), (x2, _, dy2) = ends[0], ends[1]
        if abs(x2 - x1) < 1e-6:
            continue
        for cp in seg.findall("controlpoints/controlpoint"):
            cx = float(cp.get("x") or 0)
            cy = float(cp.get("y") or 0)
            t = (cx - x1) / (x2 - x1)
            t = max(0.0, min(1.0, t))
            shift = dy1 * (1.0 - t) + dy2 * t
            if abs(shift) < 0.02:
                continue
            cp.set("y", _fmt_y(cy + shift))
            n += 1
    return n


def _anchor_on_leg(layout: ET.Element, leg_name: str) -> ET.Element | None:
    for pp in layout.findall("positionablepoint"):
        for conn in (pp.get("connect1name"), pp.get("connect2name")):
            if conn == leg_name:
                return pp
    return None


def _set_turnout_lane_y(lt: ET.Element, ref_y: float) -> None:
    """Set ycen and yb to ref_y; keep diverging-leg offset (yc − yb)."""
    yc_off = float(lt.get("yc") or ref_y) - float(lt.get("yb") or ref_y)
    lt.set("ycen", _fmt_y(ref_y))
    lt.set("yb", _fmt_y(ref_y))
    lt.set("yc", _fmt_y(ref_y + yc_off))


def _level_mainline_turnout(lt: ET.Element, ref_y: float) -> None:
    """Level ya/yb/yd/ycen to ref_y; preserve diverging yc offset from ycen."""
    old_ycen = float(lt.get("ycen") or ref_y)
    yc_off = float(lt.get("yc") or old_ycen) - old_ycen
    for attr in ("ycen", "ya", "yb", "yd"):
        lt.set(attr, _fmt_y(ref_y))
    lt.set("yc", _fmt_y(ref_y + yc_off))


_UPPER_MAIN_LANE_Y = 106.58
_UPPER_MAIN_TURNOUTS = ("TOL3", "TOL38", "TOR31", "TOL1", "TOL29")
_UPPER_MAIN_ANCHORS = (
    "EB70",
    "A54",
    "A33",
    "A29",
    "A59",
    "A34",
    "A7",
    "A63",
    "A51",
    "A66",
    "EB71",
)


def _fix_upper_main_lane(
    layout: ET.Element,
    anchors: dict[str, ET.Element],
    turnouts: dict[str, ET.Element],
    *,
    ref_y: float = _UPPER_MAIN_LANE_Y,
) -> list[str]:
    """Level F41/F58 upper main: turnouts + anchors at one Y (like TOL3)."""
    log: list[str] = []
    for tid in _UPPER_MAIN_TURNOUTS:
        lt = turnouts.get(tid)
        if lt is None:
            continue
        old_legs = {a: float(lt.get(a) or ref_y) for a in ("ya", "yb", "yd")}
        _level_mainline_turnout(lt, ref_y)
        for leg in (f"T-I-{tid}", f"T-ER-{tid}", f"T-EL-{tid}"):
            pp = _anchor_on_leg(layout, leg)
            if pp is None or pp.get("ident") == "A1":
                continue
            if pp.get("ident") in _UPPER_MAIN_ANCHORS:
                pp.set("y", _fmt_y(ref_y))
        if any(abs(v - ref_y) > 0.02 for v in old_legs.values()):
            log.append(f"{tid} main legs → y={ref_y:.2f} (F41/F58 lane)")
    for aid in _UPPER_MAIN_ANCHORS:
        pp = anchors.get(aid)
        if pp is None:
            continue
        old = float(pp.get("y") or ref_y)
        if abs(old - ref_y) > 0.02:
            pp.set("y", _fmt_y(ref_y))
            log.append(f"{aid} y {old:.2f} → {ref_y:.2f} (upper main)")
    return log


_SCHEME_Y_PAIRS: tuple[tuple[str, str], ...] = (
    ("A6", "A19"),
    ("A42", "A22"),
    ("A10", "A5"),
    ("A46", "A36"),
    ("A41", "A39"),
    ("A14", "A32"),
)


def _enforce_scheme_y_pairs(
    anchors: dict[str, ET.Element],
    turnouts: dict[str, ET.Element],
) -> list[str]:
    """Snap established west/east anchor pairs to matching Y."""
    log: list[str] = []
    for west, east in _SCHEME_Y_PAIRS:
        w, e = anchors.get(west), anchors.get(east)
        if w is None or e is None:
            continue
        yw, ye = float(w.get("y")), float(e.get("y"))
        if abs(yw - ye) < 0.05:
            continue
        target = yw
        e.set("y", _fmt_y(target))
        log.append(f"{east} y {ye:.2f} → {target:.2f} (match {west})")
    tor7 = turnouts.get("TOR7")
    a61 = anchors.get("A61")
    if tor7 is not None and a61 is not None:
        target = float(tor7.get("ycen"))
        old = float(a61.get("y"))
        if abs(old - target) > 0.05:
            a61.set("y", _fmt_y(target))
            log.append(f"A61 y {old:.2f} → {target:.2f} (TOR7 ycen)")
    return log


def _shift_turnout_y(lt: ET.Element, dy: float) -> None:
    for attr in Y_ATTRS:
        v = lt.get(attr)
        if v is not None:
            lt.set(attr, _fmt_y(float(v) + dy))


def _load_linear4_y_reference() -> tuple[
    float,
    dict[str, float],
    dict[str, float],
    dict[str, list[tuple[float, float]]],
]:
    """linear4 anchor Y, turnout ycen, bezier CPs; offsets are relative to TOL3 ycen."""
    layout = _find_layout(ET.parse(_LINEAR4_LAYOUT).getroot())
    if layout is None:
        raise RuntimeError(f"No LayoutEditor in {_LINEAR4_LAYOUT}")
    pts = {
        pp.get("ident"): float(pp.get("y"))
        for pp in layout.findall("positionablepoint")
        if pp.get("ident")
    }
    to_ycen = {
        lt.get("ident"): float(lt.get("ycen"))
        for lt in layout.findall("layoutturnout")
        if lt.get("ident")
    }
    bez: dict[str, list[tuple[float, float]]] = {}
    for seg in layout.findall("tracksegment"):
        if seg.get("bezier") != "yes":
            continue
        ident = seg.get("ident")
        if not ident:
            continue
        cps = [
            (float(cp.get("x")), float(cp.get("y")))
            for cp in seg.findall("controlpoint")
        ]
        if cps:
            bez[ident] = cps
    ref = to_ycen["TOL3"]
    return ref, pts, to_ycen, bez


def _align_east_of_tol19(
    layout: ET.Element,
    anchors: dict[str, ET.Element],
    turnouts: dict[str, ET.Element],
) -> list[str]:
    """East of TOL19: linear4 lane spacing from TOL3; TOR31 ycen = TOL3 (not l4 offset)."""
    log: list[str] = []
    tol19 = turnouts.get("TOL19")
    tol3 = turnouts.get("TOL3")
    if tol19 is None or tol3 is None:
        return log

    l4_ref, l4_pts, l4_to, l4_bez = _load_linear4_y_reference()
    ref_y = float(tol3.get("ycen"))
    x_min = float(tol19.get("xcen"))

    def target_y(l4_y: float) -> float:
        return ref_y + (l4_y - l4_ref)

    moved_to: set[str] = set()
    for tid, lt in sorted(turnouts.items(), key=lambda kv: float(kv[1].get("xcen") or 0)):
        if float(lt.get("xcen") or 0) <= x_min:
            continue
        if tid not in l4_to:
            continue
        tgt = ref_y if tid == "TOR31" else target_y(l4_to[tid])
        old = float(lt.get("ycen"))
        if abs(old - tgt) < 0.05:
            continue
        _shift_turnout_y(lt, tgt - old)
        log.append(f"{tid} ycen {old:.2f} → {tgt:.2f} (east lane / TOL3 ref)")
        moved_to.add(tid)

    for tid in moved_to:
        lt = turnouts[tid]
        for prefix, attr in LEG_PREFIX:
            leg = f"{prefix}{tid}"
            y = _leg_y_for_segment(leg, turnouts)
            if y is None:
                continue
            pp = _anchor_on_leg(layout, leg)
            if pp is not None:
                old = float(pp.get("y"))
                if abs(old - y) > 0.05:
                    pp.set("y", _fmt_y(y))
                    log.append(f"{pp.get('ident')} y {old:.2f} → {y:.2f} ({leg})")

    leg_anchors = {
        pp.get("ident")
        for pp in layout.findall("positionablepoint")
        for conn in (pp.get("connect1name"), pp.get("connect2name"))
        if conn and conn.startswith(("T-I-", "T-ER-", "T-EL-"))
    }

    for ident, pp in sorted(anchors.items(), key=lambda kv: float(kv[1].get("x") or 0)):
        if float(pp.get("x") or 0) <= x_min:
            continue
        if ident in leg_anchors:
            continue
        if ident not in l4_pts:
            continue
        tgt = target_y(l4_pts[ident])
        old = float(pp.get("y"))
        if abs(old - tgt) < 0.05:
            continue
        pp.set("y", _fmt_y(tgt))
        log.append(f"{ident} y {old:.2f} → {tgt:.2f} (east anchor)")

    for seg in layout.findall("tracksegment"):
        if seg.get("bezier") != "yes":
            continue
        ident = seg.get("ident")
        if not ident or ident not in l4_bez:
            continue
        cps = list(seg.findall("controlpoint"))
        for i, cp in enumerate(cps):
            if i >= len(l4_bez[ident]):
                break
            if float(cp.get("x") or 0) <= x_min:
                continue
            tgt = target_y(l4_bez[ident][i][1])
            old = float(cp.get("y"))
            if abs(old - tgt) > 0.05:
                cp.set("y", _fmt_y(tgt))
                log.append(f"{ident} CP[{i}] y {old:.2f} → {tgt:.2f}")

    return log


# linear4 anchor X used to scale west diverging-leg offsets (same factor as A48 arc).
_LINEAR4_DIVERGE_X: dict[tuple[str, str], float] = {
    ("TOL3", "A60"): 247.13,
}

# JMRI Ellipse track: arc=yes circle=no (not circle arc with angle).
_JMRI_ELLIPSE_FLIP: dict[str, str] = {
    "F62-S-0": "no",
}

# JMRI-verified manual edits (linear5_blocked.xml): anchor move, not turnout resize.
_TOL15_A53_XY = (519.34, 183.62)
_TOL15_YC = 183.22
_TOL3_BEZIER_A60_XY = (195.15, 211.03)
_TOL3_BEZIER_CP: tuple[tuple[float, float], ...] = (
    (241.13, 187.14),
    (197.48, 181.24),
)


def _a21_x_for_45_line(tol38: ET.Element, target_y: float) -> float:
    """A21 x so T-EL-TOL38 is a 45° straight from turnout C leg to target y."""
    xc = float(tol38.get("xc") or 0)
    yc = float(tol38.get("yc") or 0)
    return xc - (target_y - yc)


def _find_segment(layout: ET.Element, ident: str) -> ET.Element | None:
    for seg in layout.findall("tracksegment"):
        if seg.get("ident") == ident:
            return seg
    return None


def _set_segment_straight(seg: ET.Element) -> None:
    for key in ("bezier", "arc", "circle", "flip", "angle", "hideConLines"):
        seg.attrib.pop(key, None)
    cp_el = seg.find("controlpoints")
    if cp_el is not None:
        seg.remove(cp_el)


def _set_segment_jmri_ellipse(seg: ET.Element, *, flip: str) -> None:
    """JMRI Ellipse: arc=yes circle=no (see linear5_blocked.xml reference)."""
    for key in ("bezier", "angle", "hideConLines"):
        seg.attrib.pop(key, None)
    cp_el = seg.find("controlpoints")
    if cp_el is not None:
        seg.remove(cp_el)
    seg.set("arc", "yes")
    seg.set("circle", "no")
    seg.set("flip", flip)


def _set_segment_bezier(
    seg: ET.Element,
    control_points: tuple[tuple[float, float], ...],
    *,
    hide_con_lines: str = "no",
) -> None:
    _set_segment_straight(seg)
    seg.set("bezier", "yes")
    seg.set("hideConLines", hide_con_lines)
    cp_el = ET.SubElement(seg, "controlpoints")
    for i, (x, y) in enumerate(control_points):
        cp = ET.SubElement(cp_el, "controlpoint")
        cp.set("index", str(i))
        cp.set("x", _fmt_x(x))
        cp.set("y", _fmt_y(y))


def _fix_segment_styles(
    layout: ET.Element,
    anchors: dict[str, ET.Element],
    turnouts: dict[str, ET.Element],
) -> list[str]:
    """F43 straight; F62 JMRI ellipse; TOL38 legs straight."""
    log: list[str] = []

    f43 = _find_segment(layout, "F43-S-0")
    if f43 is not None and f43.get("bezier") == "yes":
        _set_segment_straight(f43)
        log.append("F43-S-0 → straight line")

    for ident in ("F62-S-0",):
        seg = _find_segment(layout, ident)
        flip = _JMRI_ELLIPSE_FLIP.get(ident)
        if seg is not None and flip is not None:
            _set_segment_jmri_ellipse(seg, flip=flip)
            log.append(f"{ident} → JMRI ellipse (flip {flip})")

    tol38 = turnouts.get("TOL38")
    if tol38 is not None:
        ter = _find_segment(layout, "T-ER-TOL38")
        if ter is not None:
            _set_segment_straight(ter)
            log.append("T-ER-TOL38 → straight (A54 / EB70 spur)")
        tel38 = _find_segment(layout, "T-EL-TOL38")
        if tel38 is not None:
            _set_segment_straight(tel38)
            log.append("T-EL-TOL38 → straight 45° (A21)")

    return log


def _scale_diverge_anchor_x(
    pp: ET.Element,
    turnout: ET.Element,
    linear4_x: float,
    scale: float,
) -> float:
    pivot = float(turnout.get("xcen"))
    new_x = pivot + (linear4_x - pivot) * scale
    pp.set("x", _fmt_x(new_x))
    return new_x


def _remove_segment(layout: ET.Element, ident: str) -> bool:
    for seg in list(layout.findall("tracksegment")):
        if seg.get("ident") == ident:
            layout.remove(seg)
            return True
    return False


def _remove_anchor(layout: ET.Element, anchors: dict[str, ET.Element], ident: str) -> bool:
    pp = anchors.pop(ident, None)
    if pp is None:
        return False
    layout.remove(pp)
    return True


def _remove_a64_merge_f61(layout: ET.Element, anchors: dict[str, ET.Element]) -> bool:
    if "A64" not in anchors:
        return False
    for seg in list(layout.findall("tracksegment")):
        if seg.get("ident") == "F61-S-0" and seg.get("connect2name") == "A64":
            seg.set("connect2name", "A34")
        if seg.get("ident") == "F45-S-0":
            layout.remove(seg)
    a34 = anchors.get("A34")
    if a34 is not None and a34.get("connect1name") == "F45-S-0":
        a34.set("connect1name", "F61-S-0")
    layout.remove(anchors["A64"])
    del anchors["A64"]
    return True


def _simplify_tor14_anchors(
    layout: ET.Element,
    anchors: dict[str, ET.Element],
) -> list[str]:
    """Drop A18/A40: F16→TOR14 (C), F46→TOR14 (B); remove leg segments."""
    log: list[str] = []
    tor14 = None
    for lt in layout.findall("layoutturnout"):
        if lt.get("ident") == "TOR14":
            tor14 = lt
            break
    if tor14 is None:
        return log

    f16 = _find_segment(layout, "F16-S-0")
    f46 = _find_segment(layout, "F46-S-0")
    if f16 is not None:
        f16.set("connect1name", "TOR14")
        f16.set("type1", "TURNOUT_C")
        f16.set("connect2name", "A6")
        f16.set("type2", "POS_POINT")
        tor14.set("connectcname", "F16-S-0")
        log.append("F16-S-0 now TOR14 (C)→A6")
    if f46 is not None:
        f46.set("connect2name", "TOR14")
        f46.set("type2", "TURNOUT_B")
        tor14.set("connectbname", "F46-S-0")
        log.append("F46-S-0 now A37→TOR14 (B)")

    for drop in ("T-ER-TOR14", "T-EL-TOR14"):
        if _remove_segment(layout, drop):
            log.append(f"Removed {drop}")
    for aid in ("A18", "A40"):
        if _remove_anchor(layout, anchors, aid):
            log.append(f"Removed {aid}")

    return log


def _fix_tol15_f47_anchor(
    anchors: dict[str, ET.Element],
    turnouts: dict[str, ET.Element],
) -> list[str]:
    """Align F47 at A53 with TOL15 C leg (move anchor + slight yc nudge)."""
    log: list[str] = []
    a53 = anchors.get("A53")
    tol15 = turnouts.get("TOL15")
    if a53 is None or tol15 is None:
        return log

    tx, ty = _TOL15_A53_XY
    old_x, old_y = float(a53.get("x")), float(a53.get("y"))
    a53.set("x", _fmt_x(tx))
    a53.set("y", _fmt_y(ty))
    if abs(old_x - tx) > 0.05 or abs(old_y - ty) > 0.05:
        log.append(f"A53 ({old_x:.2f},{old_y:.2f}) → ({tx:.2f},{ty:.2f}) (F47 / TOL15)")

    old_yc = float(tol15.get("yc") or _TOL15_YC)
    if abs(old_yc - _TOL15_YC) > 0.05:
        tol15.set("yc", _fmt_y(_TOL15_YC))
        log.append(f"TOL15 yc {old_yc:.2f} → {_TOL15_YC:.2f} (C leg / F47)")

    return log


def _fix_tol3_bezier(
    layout: ET.Element,
    anchors: dict[str, ET.Element],
) -> list[str]:
    """T-EL-TOL3 bezier + A60 junction (JMRI reference; not ellipse)."""
    log: list[str] = []
    seg = _find_segment(layout, "T-EL-TOL3")
    if seg is not None:
        _set_segment_bezier(seg, _TOL3_BEZIER_CP)
        log.append("T-EL-TOL3 → bezier (reference control points)")

    a60 = anchors.get("A60")
    if a60 is not None:
        tx, ty = _TOL3_BEZIER_A60_XY
        old_x, old_y = float(a60.get("x")), float(a60.get("y"))
        a60.set("x", _fmt_x(tx))
        a60.set("y", _fmt_y(ty))
        if abs(old_x - tx) > 0.05 or abs(old_y - ty) > 0.05:
            log.append(f"A60 ({old_x:.2f},{old_y:.2f}) → ({tx:.2f},{ty:.2f}) (T-EL-TOL3)")

    return log


def _connect_a49_tol42(layout: ET.Element, anchors: dict[str, ET.Element]) -> list[str]:
    """One segment A49→TOL42 (B); drop A2, A25, F44, T-ER-TOL42."""
    log: list[str] = []
    a49 = anchors.get("A49")
    if a49 is None:
        return log
    f51 = None
    for seg in layout.findall("tracksegment"):
        if seg.get("ident") == "F51-S-0":
            f51 = seg
            break
    if f51 is None:
        return log
    f51.set("connect1name", "A49")
    f51.set("type1", "POS_POINT")
    f51.set("connect2name", "TOL42")
    f51.set("type2", "TURNOUT_B")
    tol42 = None
    for lt in layout.findall("layoutturnout"):
        if lt.get("ident") == "TOL42":
            tol42 = lt
            break
    if tol42 is not None and tol42.get("connectbname") == "T-ER-TOL42":
        tol42.set("connectbname", "F51-S-0")
        log.append("TOL42 connectbname T-ER-TOL42 → F51-S-0")
    for drop in ("F44-S-0", "T-ER-TOL42"):
        if _remove_segment(layout, drop):
            log.append(f"Removed {drop}")
    for aid in ("A2", "A25"):
        if _remove_anchor(layout, anchors, aid):
            log.append(f"Removed {aid}")
    log.append("F51-S-0 now A49→TOL42 (single segment)")
    return log


def _west_end_f39_cleanup(
    layout: ET.Element,
    anchors: dict[str, ET.Element],
    turnouts: dict[str, ET.Element],
    *,
    ref_y: float,
    a45_y: float,
) -> list[str]:
    log: list[str] = []
    tol38 = turnouts.get("TOL38")
    a21 = anchors.get("A21")
    if tol38 is None or a21 is None:
        return log

    if _remove_segment(layout, "F39-S-0"):
        log.append("Removed F39-S-0")

    # Match TOL3: main legs on TOR31 lane; lower spur (A21/EB73) at A45 height.
    spur_y = float(tol38.get("yc") or ref_y)
    a21.set("y", _fmt_y(a45_y))
    a21.set("connect1name", "F54-S-0")

    old_x = float(a21.get("x"))
    new_x = _a21_x_for_45_line(tol38, a45_y)
    a21.set("x", _fmt_x(new_x))
    if abs(old_x - new_x) > 0.05:
        log.append(f"A21 x {old_x:.2f} → {new_x:.2f} (45° line from TOL38 C)")

    for seg in layout.findall("tracksegment"):
        if seg.get("ident") == "F54-S-0":
            seg.set("connect2name", "A21")
            break

    if _remove_anchor(layout, anchors, "A52"):
        log.append("Removed A52")

    eb73 = anchors.get("EB73")
    if eb73 is not None:
        old = float(eb73.get("y"))
        eb73.set("y", _fmt_y(a45_y))
        log.append(f"EB73 y {old:.2f} → {a45_y:.2f} (A45 / lower spur)")

    log.append(
        f"TOL38 ycen/yb={ref_y:.2f}, yc={spur_y:.2f}; A21/EB73 at A45 y={a45_y:.2f}"
    )

    a54 = anchors.get("A54")
    if a54 is not None:
        old = float(a54.get("y"))
        a54.set("y", _fmt_y(ref_y))
        if abs(old - ref_y) > 0.05:
            log.append(f"A54 y {old:.2f} → {ref_y:.2f} (T-ER / F61 lane)")

    eb70 = anchors.get("EB70")
    if eb70 is not None:
        old = float(eb70.get("y"))
        eb70.set("y", _fmt_y(ref_y))
        if abs(old - ref_y) > 0.05:
            log.append(f"EB70 y {old:.2f} → {ref_y:.2f} (F53 / F61 lane)")

    return log


def _scale_a60_diverge(
    layout: ET.Element,
    anchors: dict[str, ET.Element],
    turnouts: dict[str, ET.Element],
    *,
    arc_x_scale: float,
) -> list[str]:
    log: list[str] = []
    tol3 = turnouts.get("TOL3")
    a60 = anchors.get("A60")
    if tol3 is None or a60 is None:
        return log
    l4_x = _LINEAR4_DIVERGE_X.get(("TOL3", "A60"))
    if l4_x is None:
        return log
    old_x = float(a60.get("x"))
    new_x = _scale_diverge_anchor_x(a60, tol3, l4_x, arc_x_scale)
    log.append(f"A60 x {old_x:.2f} → {new_x:.2f} (diverge scale {arc_x_scale})")
    return log


def _apply_linear5_corrections(
    layout: ET.Element,
    *,
    arc_x_scale: float = 4.0,
) -> list[str]:
    """Targeted topology + Y/X fixes from linear5 review (no bulk leveling)."""
    log: list[str] = []
    anchors = _anchor_index(layout)
    turnouts = _turnout_index(layout)

    if _remove_a64_merge_f61(layout, anchors):
        log.append("Removed A64; F61-S-0 now A59→A34 (dropped F45-S-0)")

    tor31 = turnouts.get("TOR31")
    if tor31 is None:
        return log
    ref_y = float(tor31.get("ycen"))

    for tid in ("TOL3", "TOL38"):
        lt = turnouts.get(tid)
        if lt is None:
            continue
        old = float(lt.get("ycen"))
        _set_turnout_lane_y(lt, ref_y)
        for leg in (f"T-I-{tid}", f"T-ER-{tid}"):
            pp = _anchor_on_leg(layout, leg)
            if pp is not None:
                pp.set("y", _fmt_y(ref_y))
        log.append(f"{tid} ycen/yb {old:.2f} → {ref_y:.2f} (TOR31 ref)")

    a54 = anchors.get("A54")

    for aid in ("A59", "A34"):
        pp = anchors.get(aid)
        if pp is not None:
            pp.set("y", _fmt_y(ref_y))

    tor14 = turnouts.get("TOR14")
    a45 = anchors.get("A45")
    if tor14 is not None and a45 is not None:
        target = float(tor14.get("ycen"))
        old = float(a45.get("y"))
        a45.set("y", _fmt_y(target))
        log.append(f"A45 y {old:.2f} → {target:.2f} (TOR14 ycen)")

    log.extend(_simplify_tor14_anchors(layout, anchors))

    a49 = anchors.get("A49")
    tol42 = turnouts.get("TOL42")
    if a49 is not None and tol42 is not None:
        target = float(a49.get("y"))
        old = float(tol42.get("ycen"))
        _shift_turnout_y(tol42, target - old)
        tol42.set("yb", _fmt_y(target))
        leg_y = {
            "T-I-TOL42": float(tol42.get("ycen")),
            "T-EL-TOL42": float(tol42.get("yc")),
        }
        for leg, y in leg_y.items():
            pp = _anchor_on_leg(layout, leg)
            if pp is not None:
                pp.set("y", _fmt_y(y))
        log.append(f"TOL42 ycen/yb {old:.2f} → {target:.2f} (A49 y)")

    log.extend(_connect_a49_tol42(layout, anchors))
    log.extend(_scale_a60_diverge(layout, anchors, turnouts, arc_x_scale=arc_x_scale))

    a45 = anchors.get("A45")
    a45_y = float(a45.get("y")) if a45 is not None else ref_y
    log.extend(
        _west_end_f39_cleanup(
            layout, anchors, turnouts, ref_y=ref_y, a45_y=a45_y
        )
    )

    a60 = anchors.get("A60")
    if a60 is not None:
        old = float(a60.get("y"))
        a60.set("y", _fmt_y(a45_y))
        if abs(old - a45_y) > 0.05:
            log.append(f"A60 y {old:.2f} → {a45_y:.2f} (A45)")

    log.extend(_fix_segment_styles(layout, anchors, turnouts))
    log.extend(_fix_tol15_f47_anchor(anchors, turnouts))
    log.extend(_fix_tol3_bezier(layout, anchors))

    return log


def normalize_linear5_manual(
    layout: ET.Element,
    *,
    places: int | None = None,
) -> list[str]:
    """Safe post-save pass: upper-main Y, scheme pairs, round — no topology edits."""
    log: list[str] = []
    anchors = _anchor_index(layout)
    turnouts = _turnout_index(layout)
    tor31 = turnouts.get("TOR31")
    ref_y = float(tor31.get("ycen")) if tor31 is not None else _UPPER_MAIN_LANE_Y
    log.extend(_fix_upper_main_lane(layout, anchors, turnouts, ref_y=ref_y))
    log.extend(_enforce_scheme_y_pairs(anchors, turnouts))
    n_round = _round_geometry(layout, places=places)
    if n_round:
        p = _COORD_DECIMALS if places is None else places
        log.append(f"Rounded {n_round} coordinate attribute(s) to {p} decimal(s)")
    return log


def _adjust_a48_arc(
    anchors: dict[str, ET.Element],
    *,
    arc_x_scale: float,
) -> str | None:
    a48 = anchors.get("A48")
    a58 = anchors.get("A58")
    a67 = anchors.get("A67")
    if a48 is None or a58 is None or a67 is None:
        return None
    x_vert = (float(a58.get("x")) + float(a67.get("x"))) / 2.0
    old_x = float(a48.get("x"))
    offset = old_x - x_vert
    new_x = x_vert + offset * arc_x_scale
    a48.set("x", _fmt_x(new_x))
    return f"A48 x {old_x:.2f} → {new_x:.2f} (vertical x≈{x_vert:.2f}, scale {arc_x_scale})"


def _round_geometry(layout: ET.Element, places: int | None = None) -> int:
    p = _COORD_DECIMALS if places is None else places
    n = 0
    for elem in layout.iter():
        if elem is layout:
            continue
        tag = _local_tag(elem)
        if tag not in (
            "positionablepoint",
            "layoutturnout",
            "tracksegment",
            "controlpoint",
        ):
            continue
        for attr in (
            "x",
            "y",
            "xa",
            "ya",
            "xb",
            "yb",
            "xc",
            "yc",
            "xd",
            "yd",
            "xcen",
            "ycen",
        ):
            v = elem.get(attr)
            if v is None:
                continue
            try:
                f = float(v)
                elem.set(attr, _fmt_coord(f, p))
                n += 1
            except ValueError:
                pass
    return n


def polish_linear5_geometry(
    layout: ET.Element,
    *,
    arc_x_scale: float = 4.0,
    level: bool = False,
    corrections: bool = True,
) -> list[str]:
    log: list[str] = []
    anchors = _anchor_index(layout)

    msg = _adjust_a48_arc(anchors, arc_x_scale=arc_x_scale)
    if msg:
        log.append(msg)

    if corrections:
        log.extend(_apply_linear5_corrections(layout, arc_x_scale=arc_x_scale))

    if not level:
        return log

    turnouts = _turnout_index(layout)
    old_y = {ident: float(pp.get("y") or 0) for ident, pp in anchors.items()}

    n_leg = _snap_anchors_to_turnout_legs(layout, anchors, turnouts)
    if n_leg:
        log.append(f"Snapped {n_leg} anchor(s) to turnout leg Y")

    n_horiz = _level_horizontal_segments(layout, anchors)
    if n_horiz:
        log.append(f"Leveled {n_horiz} horizontal anchor Y adjustment(s)")

    n_bez = _update_bezier_controls(layout, anchors, old_y)
    if n_bez:
        log.append(f"Shifted {n_bez} bezier control point(s)")

    n_round = _round_geometry(layout)
    if n_round:
        log.append(f"Rounded {n_round} coordinate attribute(s)")

    return log


def apply_east_alignment_to_panel(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> list[str]:
    """Align east-of-TOL19 geometry in a full panel XML (e.g. linear5_manual_save)."""
    out = Path(output_path or input_path)
    tree = ET.parse(input_path)
    layout = _find_layout(tree.getroot())
    if layout is None:
        raise SystemExit(f"No LayoutEditor in {input_path}")
    anchors = _anchor_index(layout)
    turnouts = _turnout_index(layout)
    log = _align_east_of_tol19(layout, anchors, turnouts)
    ET.indent(tree, space="  ", level=0)
    with open(out, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)
    return log


def main() -> None:
    ap = argparse.ArgumentParser(description="Polish linear5 arc + level track Y")
    ap.add_argument("input", help="Panel XML path")
    ap.add_argument("output", nargs="?", help="Output path (default: overwrite input)")
    ap.add_argument(
        "--east-align-only",
        action="store_true",
        help="Only align turnouts/anchors east of TOL19 (panel XML with blocks)",
    )
    ap.add_argument(
        "--arc-x-scale",
        type=float,
        default=4.0,
        help="Multiply A48 X offset from east vertical (default 4)",
    )
    ap.add_argument(
        "--level",
        action="store_true",
        help="Also snap/level anchor Y (off by default — can look jagged)",
    )
    ap.add_argument(
        "--no-corrections",
        action="store_true",
        help="Skip targeted track corrections (A64, TOR31 ref, A45, TOL42)",
    )
    ap.add_argument(
        "--normalize-only",
        action="store_true",
        help="Safe manual-save pass only (upper main Y, scheme pairs, round)",
    )
    ap.add_argument(
        "--round-only",
        action="store_true",
        help="Only round geometry coordinates (no arc/level/corrections)",
    )
    ap.add_argument(
        "--coord-decimals",
        type=int,
        default=2,
        metavar="N",
        help="Decimal places for geometry coords (0 = whole numbers; default 2)",
    )
    args = ap.parse_args()
    out = args.output or args.input
    global _COORD_DECIMALS
    _COORD_DECIMALS = args.coord_decimals

    if args.round_only:
        tree = ET.parse(args.input)
        layout = _find_layout(tree.getroot())
        if layout is None:
            raise SystemExit(f"No LayoutEditor in {args.input}")
        n = _round_geometry(layout, places=args.coord_decimals)
        ET.indent(tree, space="  ", level=0)
        with open(out, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)
        print(f"Wrote {out}")
        print(f"Rounded {n} coordinate attribute(s) to {args.coord_decimals} decimal(s)")
        return

    if args.normalize_only:
        tree = ET.parse(args.input)
        layout = _find_layout(tree.getroot())
        if layout is None:
            raise SystemExit(f"No LayoutEditor in {args.input}")
        log = normalize_linear5_manual(layout, places=args.coord_decimals)
        ET.indent(tree, space="  ", level=0)
        with open(out, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)
        print(f"Wrote {out}")
        for line in log:
            print(line)
        if not log:
            print("No changes.")
        return

    if args.east_align_only:
        log = apply_east_alignment_to_panel(args.input, out)
        print(f"Wrote {out}")
        for line in log:
            print(f"  {line}")
        return

    tree = ET.parse(args.input)
    layout = _find_layout(tree.getroot())
    if layout is None:
        raise SystemExit(f"No LayoutEditor in {args.input}")

    log = polish_linear5_geometry(
        layout,
        arc_x_scale=args.arc_x_scale,
        level=args.level,
        corrections=not args.no_corrections,
    )

    ET.indent(tree, space="  ", level=0)
    with open(out, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)

    print(f"Wrote {out}")
    for line in log:
        print(f"  {line}")


if __name__ == "__main__":
    main()
