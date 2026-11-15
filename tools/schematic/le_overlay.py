"""The live "HART Railroad" panel's icons and labels carried onto the generated staging panel (LE cut-over, Phase 2).

    records = le_overlay.carry(live_le, gen_le, P, root)    # from build_layout_le.build(as_live=True)

Everything on the live panel that is not track, a turnout, a point, a mast icon or the drawing options is overlay:
occupancy lamps, Entry/Exit sensor icons, the Dispatcher System station clusters, status lamps, block contents
labels, yard ladder buttons, the Turnouts signal head, text labels and the background picture. Each is copied with
every attribute and child as live; only x and y change.

Where each goes. In the live panel each item is tied to what it belongs to, then put at the same place against that
thing on the new panel:
- slot: an Entry/Exit sensor icon to the slot its sensor is bound in (same ident and slot on both panels), at the
  same offset from the boundary point;
- turnout: an item of a switch's OS block (lamp, block contents) or its "SW-<n>" label to that turnout's centre (a
  crossover half to the middle of its legs), at the same offset;
- block: an item of a track block (lamp, block contents, a label naming the block, the station clusters) at the same
  share of the way along the block's track, left to right, and the same distance to its side;
- station: a caption that a generated station label also gives (Brick, South Yard ...) centred where that label
  was, and the generated label dropped (the live one is the panel's);
- frame: what is tied to no track (region captions, the status cluster, any item over NEAR px from the track) keeps
  its place against the track's bounding box: across it by share, outside it by distance;
- backdrop: the background picture (an icon label at level 1 or below) stays at its live x and y, under everything.
The station clusters (level 12, one per Dispatcher station) and the status cluster (the LCOS, Turnouts, Signals and
Track Power lamps and captions) move as one block each. Generated switch numbers and track names that a live label
also gives are dropped the same way.

Then each item, in order (lamps, sensors, clusters, labels, captions), takes the nearest spot (STEP px at a time,
out to REACH px) clear of the track, the turnouts and their control circles, the mast icons, the labels and the
items placed before it. An occupancy lamp (a circuit lamp) sits on its own track by the owner's rule (2026-11-13), so
track and turnouts do not count against it; icons and labels do. An item with no clear spot stops the build. Last,
if anything stands above the panel's top the whole panel moves down, and the panel grows to hold everything, within
the FIT window; checked again from scratch.
"""
from __future__ import annotations

import copy
import functools
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

TRACK_TAGS = {"layoutTrackDrawingOptions", "layoutturnout", "tracksegment", "positionablepoint", "signalmasticon",
              "layoutShape"}
OVERLAY_TAGS = {"sensoricon", "BlockContentsIcon", "positionablelabel", "turnouticon", "signalheadicon"}
# px of each icon image (the JMRI 5.16 program resources and the repo's preference resources)
ICON_SIZES = (("smallschematics/tracksegments/circuit-", (10, 10)), ("icons/USS/sensor/", (21, 21)),
              ("icons/markers/loco-", (60, 20)), ("buttons/triangle_", (16, 16)),
              ("misc/hart_panel_bg.jpg", (1900, 600)))
BCI_CHARS = 5           # a block contents label shows a train name: room for this many characters
STATUS_LABELS = {"LCOS", "Turnouts", "Signals", "Track Power"}          # panel_status.py's lamps and captions
STATUS_SENSORS = {"Bridge HBLOOP", "SML Mode", "Track Power"}
STATUS_HEADS = {"IH9990"}
STATION_LEVEL = "12"    # the Dispatcher System station clusters (reconcile_dispatcher_stations.py)
NEAR = 60               # px: an item further than this from every track is tied to the frame, not to a track
STEP = 2                # px between the spots tried
REACH = (40, 80, 120)   # px out to which spots are tried, widening only when no spot is clear
TOP = 6                 # px: nothing above this on the panel
EDGE = 20               # px kept free beyond the furthest item at the right and the bottom
CLEAR = 1.5             # px from a track line or turnout leg an item must keep
TURNOUT_R = 8           # px around a turnout's centre: its control circle
EPS = 1e-6


class OverlayError(RuntimeError):
    pass


# ---------------------------------------------------------------- geometry of a panel (live or generated)

def num(el, attr, what):
    try:
        v = float(el.get(attr))
    except (TypeError, ValueError):
        raise OverlayError(f"{what}: {attr}={el.get(attr)!r} is no number") from None
    if not math.isfinite(v):
        raise OverlayError(f"{what}: {attr}={el.get(attr)!r} is no finite number")
    return v


class Track:
    """A panel's drawn track: per block the pieces of its visible segments (arcs and Beziers as short lines),
    ordered into one run left to right where they form one; turnouts by ident."""

    def __init__(self, le: ET.Element, le_mod, slots_mod, what: str):
        self.what = what
        self.ix = slots_mod.Index(le)
        self.turnouts = self.ix.turnouts
        self.pieces = defaultdict(list)          # block -> [(a, b)]
        for s in le.findall("tracksegment"):
            if s.get("hidden") == "yes":
                continue
            a = self.ix.coords(s.get("connect1name"), s.get("type1"))
            b = self.ix.coords(s.get("connect2name"), s.get("type2"))
            if s.get("arc") == "yes":
                angle = float(s.get("angle") or 0) or 90.0
                pts = le_mod.arc_points(a, b, angle, s.get("flip") == "yes", 12) if s.get("circle") == "yes" \
                    else [a, b]
            elif s.get("bezier") == "yes":
                ctrl = [(float(c.get("x")), float(c.get("y")))
                        for c in sorted(s.iter("controlpoint"), key=lambda c: int(c.get("index") or 0))]
                pts = bezier(a, ctrl, b)
            else:
                pts = [a, b]
            for p, q in zip(pts, pts[1:]):
                if math.dist(p, q) > EPS:
                    self.pieces[s.get("blockname") or ""].append((p, q))
        self.runs, self.unchained = {}, []
        for block, pcs in self.pieces.items():
            self.runs[block], one = chain(pcs)
            if not one:
                self.unchained.append(block)
        allp = [p for pcs in self.pieces.values() for pc in pcs for p in pc]
        for t in self.turnouts.values():
            allp += [self.ix.leg_coords(t, L) for L in "ABC"]
        if not allp:
            raise OverlayError(f"{what}: no track drawn")
        xs, ys = [p[0] for p in allp], [p[1] for p in allp]
        self.box = (min(xs), min(ys), max(xs), max(ys))

    def turnout_point(self, ident, block):
        """The middle of the legs of turnout `ident` that are in `block` (its centre for its own block)."""
        t = self.turnouts[ident]
        if block == t.get("blockname"):
            if "XOVER" not in (t.get("type") or ""):
                return (float(t.get("xcen")), float(t.get("ycen")))
            legs = ["A"] + [L for L in "BCD" if (t.get(f"block{L.lower()}name") or t.get("blockname")) == block]
        else:
            legs = [L for L in "BCD" if t.get(f"block{L.lower()}name") == block]
        if not legs:
            raise OverlayError(f"{self.what}: turnout {ident} has no leg in {block}")
        pts = [self.ix.leg_coords(t, L) for L in legs]
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    def os_turnouts(self):
        """{block: turnout ident} for each block a turnout holds (its own, or a crossover half's)."""
        out = {}
        for ident, t in self.turnouts.items():
            for a in ("blockname", "blockbname", "blockcname", "blockdname"):
                if t.get(a):
                    out.setdefault(t.get(a), ident)
        return out

    def where(self, block, p):
        """(share of the way along the block's run, signed px to its side, None) of point p against its nearest
        piece; past either end of the run, (share 0 or 1, 0, (dx, dy) from that end)."""
        run = self.runs.get(block)
        if not run:
            raise OverlayError(f"{self.what}: block {block} has no drawn track")
        total = sum(math.dist(a, b) for a, b in run)
        best, acc = None, 0.0
        for k, (a, b) in enumerate(run):
            L = math.dist(a, b)
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            raw = (p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1]
            t = max(0.0, min(L, raw))
            q = (a[0] + u[0] * t, a[1] + u[1] * t)
            d = math.dist(p, q)
            side = (p[0] - q[0]) * -u[1] + (p[1] - q[1]) * u[0]
            # past either end of the run: kept as the plain (dx, dy) from that end, so an item beyond a track's
            # end stays beyond it however the end piece slopes
            past = (k == 0 and raw < 0) or (k == len(run) - 1 and raw > L)
            if best is None or d < best[0] - EPS:
                best = (d, (acc + t) / total, 0.0 if past else (math.copysign(d, side) if d > EPS else 0.0),
                        (p[0] - q[0], p[1] - q[1]) if past else None)
            acc += L
        return best[1], best[2], best[3]

    def at(self, block, share, off, past=None):
        """The point at `share` of the way along the block's run, `off` px to its side; or, with `past` (dx, dy),
        that far from the run's end (as where())."""
        run = self.runs.get(block)
        if not run:
            raise OverlayError(f"{self.what}: block {block} has no drawn track")
        total = sum(math.dist(a, b) for a, b in run)
        want, acc = share * total, 0.0
        for a, b in run:
            L = math.dist(a, b)
            if acc + L >= want - EPS or (a, b) == run[-1]:
                u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
                t = max(0.0, min(L, want - acc))
                q = (a[0] + u[0] * t, a[1] + u[1] * t)
                if past is not None:
                    return (q[0] + past[0], q[1] + past[1])
                return (q[0] - u[1] * off, q[1] + u[0] * off)
            acc += L
        raise OverlayError(f"{self.what}: block {block}: no point at share {share}")

    def nearest_block(self, p):
        best = None
        for block, pcs in self.pieces.items():
            d = min(pt_seg(p, a, b) for a, b in pcs)
            if best is None or d < best[0]:
                best = (d, block)
        return best


def bezier(a, ctrl, b, n=16):
    pts = [a, *ctrl, b]
    out = []
    for i in range(n + 1):
        t = i / n
        q = list(pts)
        while len(q) > 1:
            q = [((1 - t) * p[0] + t * r[0], (1 - t) * p[1] + t * r[1]) for p, r in zip(q, q[1:])]
        out.append(q[0])
    return out


def chain(pieces):
    """(pieces, True): the pieces of one block as one run from its left end (then top), when they join end to end;
    else (the pieces sorted left to right, False), the share then read against that list (carry() reports it)."""
    ends = defaultdict(list)
    key = lambda p: (round(p[0], 1), round(p[1], 1))       # noqa: E731
    for i, (a, b) in enumerate(pieces):
        ends[key(a)].append(i)
        ends[key(b)].append(i)
    tips = [k for k, v in ends.items() if len(v) == 1]
    if len(tips) != 2 or any(len(v) > 2 for v in ends.values()):
        return sorted(pieces, key=lambda pc: (min(pc[0][0], pc[1][0]), min(pc[0][1], pc[1][1]))), False
    here = min(tips)
    out, used = [], set()
    for _ in range(len(pieces)):
        i = next(j for j in ends[here] if j not in used)
        used.add(i)
        a, b = pieces[i]
        if key(a) != here:
            a, b = b, a
        out.append((a, b))
        here = key(b)
    return out, True


def pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < EPS else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


# ---------------------------------------------------------------- the items

def icon_size(el, what):
    """(w, h) of an icon item from its images (all the same size), or None for a text-only item."""
    sizes = set()
    for c in el.iter():
        url = c.get("url")
        if not url:
            continue
        got = next((s for k, s in ICON_SIZES if k in url), None)
        if got is None:
            raise OverlayError(f"{what}: image {url} has no known size (add it to ICON_SIZES)")
        sizes.add(got)
    if len(sizes) > 1:
        raise OverlayError(f"{what}: its images differ in size {sorted(sizes)}")
    return sizes.pop() if sizes else None


def text_box(text, size):
    return 0.6 * size * len(text), float(size)


def describe(el):
    name = (el.get("sensor") or el.get("blockcontents") or el.get("turnout") or el.get("signalhead") or
            el.get("text") or (el.find("icon").get("url") if el.find("icon") is not None else "") or "?")
    return f"{el.tag} {name!r}"


class Item:
    def __init__(self, el, index):
        self.el, self.index = el, index
        self.what = describe(el)
        self.x, self.y = num(el, "x", self.what), num(el, "y", self.what)
        icon = icon_size(el, self.what)
        texty = el.tag == "BlockContentsIcon" or el.get("text") is not None
        size = int(num(el, "size", self.what)) if texty else None      # a text item without a size stops
        if el.tag == "BlockContentsIcon":
            w, h = text_box("M" * BCI_CHARS, size)
        elif icon:
            w, h = icon
            if el.get("text"):
                tw, th = text_box(el.get("text"), size)
                w, h = max(w, tw), max(h, th)
        elif el.get("text") is not None:
            if not el.get("text").strip():
                raise OverlayError(f"{self.what}: a text label with no text")
            w, h = text_box(el.get("text"), size)
        else:
            raise OverlayError(f"{self.what}: neither an image nor text, so its size is unknown")
        self.w, self.h = w, h
        self.lamp = el.tag == "sensoricon" and any("circuit-" in (c.get("url") or "") for c in el.iter())
        self.backdrop = el.tag == "positionablelabel" and icon is not None and int(el.get("level") or 0) <= 1
        self.group = None       # a cluster key: its members move as one
        self.anchor = None      # (kind, ...) in the live panel
        self.new = None         # (x, y) on the new panel

    @property
    def centre(self):
        return (self.x + self.w / 2, self.y + self.h / 2)


def overlay_items(live_le):
    items = []
    for i, el in enumerate(live_le):
        if el.tag in TRACK_TAGS:
            continue
        if el.tag not in OVERLAY_TAGS:
            raise OverlayError(f"live panel: {el.tag} is neither track nor an overlay item this build carries")
        items.append(Item(el, i))
    return items


# ---------------------------------------------------------------- tying each item to what it belongs to

def sensor_blocks(root):
    out = defaultdict(set)
    for blocks in root.findall("blocks"):
        for b in blocks.findall("block"):
            s, n = (b.findtext("occupancysensor") or "").strip(), (b.findtext("userName") or "").strip()
            if s and n:
                out[s].add(n)
    return out


def sensor_slots(live_le):
    out = {}
    for p in live_le.findall("positionablepoint"):
        for slot in ("east", "west"):
            if p.get(f"{slot}boundsensor"):
                out[p.get(f"{slot}boundsensor")] = ("point", p.get("ident"), slot)
    for t in live_le.findall("layoutturnout"):
        for leg in "ABCD":
            el = t.find(f"sensor{leg}")
            if el is not None and (el.text or "").strip():
                out[el.text.strip()] = ("turnout", t.get("ident"), leg)
    return out


def slot_point(track, kind, ident, slot):
    if kind == "turnout":
        if ident not in track.turnouts:
            raise OverlayError(f"{track.what}: no turnout {ident}")
        return track.ix.leg_coords(track.turnouts[ident], slot)
    if ident not in track.ix.points:
        raise OverlayError(f"{track.what}: no point {ident}")
    return track.ix.coords(ident, "POS_POINT")


def station_key(sensor):
    """MoveToTrack_K-1_stored / MoveInProgressTrack_K-1 -> Track K-1."""
    m = re.fullmatch(r"(?:MoveTo(.+)_stored|MoveInProgress(.+))", sensor or "")
    return (m.group(1) or m.group(2)).replace("_", " ") if m else None


def assign_groups(items):
    """Set the group of each status lamp or caption ("status") and each Dispatcher station cluster item ("station
    <block>": its MoveTo and MoveInProgress icons and the level-12 lamp nearest them)."""
    stations = defaultdict(list)
    for it in items:
        el = it.el
        if (el.tag == "positionablelabel" and (el.get("text") or "").strip() in STATUS_LABELS
                or el.get("sensor") in STATUS_SENSORS or el.get("signalhead") in STATUS_HEADS):
            it.group = "status"
        elif el.get("level") == STATION_LEVEL and el.tag == "sensoricon" and station_key(el.get("sensor")):
            stations[station_key(el.get("sensor"))].append(it)
    keys = sorted(stations)
    for key in keys:
        if not any(i.el.get("sensor", "").startswith("MoveTo") for i in stations[key]):
            raise OverlayError(f"live station cluster {key}: no MoveTo icon")
    for it in items:
        if it.el.get("level") == STATION_LEVEL and it.el.tag == "sensoricon" and not station_key(it.el.get("sensor")):
            if not keys:
                raise OverlayError(f"live {it.what} (level {STATION_LEVEL}) stands by no station cluster")
            near = min(keys, key=lambda k: min(math.dist(it.centre, o.centre) for o in stations[k]))
            if min(math.dist(it.centre, o.centre) for o in stations[near]) > 30:
                raise OverlayError(f"live {it.what} (level {STATION_LEVEL}) stands by no station cluster")
            stations[near].append(it)
    for key in keys:
        for it in stations[key]:
            it.group = f"station {key}"


def tie(items, live, root, switch_ident, station_labels):
    """Set each item's group (assign_groups) or anchor, from the live panel."""
    assign_groups(items)
    by_sensor = sensor_blocks(root)
    slots_of = sensor_slots(live.le)
    os_of = live.os_turnouts()
    for it in items:
        el = it.el
        sensor = el.get("sensor")
        text = (el.get("text") or "").strip()
        if it.group:
            continue
        if it.backdrop:
            it.anchor = ("backdrop",)
        elif sensor in slots_of:
            it.anchor = ("slot",) + slots_of[sensor] + (sub(it.centre, slot_point(live, *slots_of[sensor])),)
        elif el.tag == "positionablelabel" and re.fullmatch(r"SW-(\d+)", text):
            n = text[3:]
            if n not in switch_ident:
                raise OverlayError(f"live label {text!r}: switch {n} is not in switches.csv")
            ident = switch_ident[n]
            if ident not in live.turnouts:
                raise OverlayError(f"live label {text!r}: switches.csv's turnout {ident} is not on the live panel")
            block = live.turnouts[ident].get("blockname")
            it.anchor = ("turnout", ident, block, sub(it.centre, live.turnout_point(ident, block)))
        elif el.tag == "positionablelabel" and text.lower() in station_labels:
            it.anchor = ("station", text.lower())
        else:
            blocks = set()
            if el.tag == "BlockContentsIcon":
                blocks = {el.get("blockcontents")}
            elif sensor:
                blocks = by_sensor.get(sensor, set())
            elif el.tag == "positionablelabel" and text in live.pieces:
                blocks = {text}
            it.anchor = block_anchor(it, blocks, live, os_of)


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def block_anchor(it, blocks, live, os_of):
    """The nearest of the item's blocks in the live panel (an OS block by its turnout, a track by its run), or the
    frame when no track of its own (or none at all) is within NEAR px."""
    best = None
    for b in sorted(blocks):
        if b in os_of:
            p = live.turnout_point(os_of[b], b)
            d = math.dist(it.centre, p)
            cand = (d, ("turnout", os_of[b], b, sub(it.centre, p)))
        elif b in live.runs:
            d = min(pt_seg(it.centre, a, c) for a, c in live.pieces[b])
            cand = (d, ("block", b) + live.where(b, it.centre))
        else:
            continue
        if best is None or cand[0] < best[0]:
            best = cand
    if best is None and not blocks:
        near = live.nearest_block(it.centre)
        if near and near[0] <= NEAR:
            b = near[1]
            best = (near[0], ("turnout", os_of[b], b, sub(it.centre, live.turnout_point(os_of[b], b)))
                    if b in os_of else ("block", b) + live.where(b, it.centre))
    if best is None or (not blocks and best[0] > NEAR):
        return ("frame",)
    return best[1]


# ---------------------------------------------------------------- where each goes on the new panel

def frame_point(p, live_box, gen_box):
    """p against the live track's box -> the same against the new one: by share inside, by distance outside."""
    out = []
    for k in (0, 1):
        lo, hi, glo, ghi = live_box[k], live_box[k + 2], gen_box[k], gen_box[k + 2]
        if p[k] < lo:
            out.append(glo - (lo - p[k]))
        elif p[k] > hi:
            out.append(ghi + (p[k] - hi))
        else:
            out.append(glo + (p[k] - lo) / (hi - lo) * (ghi - glo))
    return tuple(out)


def target(it, live, gen, station_at):
    """The centre the item would take on the new panel before it is nudged clear."""
    kind = it.anchor[0]
    if kind == "slot":
        _k, what, ident, slot, off = it.anchor
        p = slot_point(gen, "turnout" if what == "turnout" else "point", ident, slot)
        return (p[0] + off[0], p[1] + off[1])
    if kind == "turnout":
        _k, ident, block, off = it.anchor
        if ident not in gen.turnouts:
            raise OverlayError(f"{it.what}: turnout {ident} is not on the new panel")
        p = gen.turnout_point(ident, block)
        return (p[0] + off[0], p[1] + off[1])
    if kind == "block":
        _k, block, share, off, past = it.anchor
        if block not in gen.runs:
            raise OverlayError(f"{it.what}: block {block} is not drawn on the new panel")
        return gen.at(block, share, off, past)
    if kind == "station":
        return station_at[it.anchor[1]]
    if kind == "frame":
        return frame_point(it.centre, live.box, gen.box)
    raise OverlayError(f"{it.what}: anchor {kind} not known")


# ---------------------------------------------------------------- clear spots

class Rect:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def moved(self, dx, dy):
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def overlaps(self, o, margin=0.5):
        return not (self.x + self.w + margin <= o.x or o.x + o.w + margin <= self.x or
                    self.y + self.h + margin <= o.y or o.y + o.h + margin <= self.y)

    def gap_seg(self, a, b):
        """px from the segment a-b to the rectangle (0 when they touch or cross)."""
        if self.inside(a) or self.inside(b):
            return 0.0
        corners = [(self.x, self.y), (self.x + self.w, self.y), (self.x + self.w, self.y + self.h),
                   (self.x, self.y + self.h)]
        edges = list(zip(corners, corners[1:] + corners[:1]))
        if any(cross_segs(a, b, p, q) for p, q in edges):
            return 0.0
        return min([pt_seg(c, a, b) for c in corners] + [pt_seg(a, p, q) for p, q in edges] +
                   [pt_seg(b, p, q) for p, q in edges])

    def gap_point(self, p):
        return math.hypot(max(self.x - p[0], 0, p[0] - self.x - self.w), max(self.y - p[1], 0, p[1] - self.y - self.h))

    def inside(self, p):
        return self.x <= p[0] <= self.x + self.w and self.y <= p[1] <= self.y + self.h


def cross_segs(a, b, c, d):
    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(v) < EPS else (1 if v > 0 else -1)
    return orient(a, b, c) != orient(a, b, d) and orient(c, d, a) != orient(c, d, b)


class Obstacles:
    """The new panel's track lines, turnouts, mast icons, labels and the items placed so far, indexed by grid cell
    (CELL px) so a spot is scored against what is near it only."""
    CELL = 32

    def __init__(self, gen, masts, labels, shapes):
        self.grid = defaultdict(list)       # cell -> [(kind, payload)]
        for pcs in gen.pieces.values():
            for a, b in pcs:
                self._add(("line", (a, b)), min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        for t in gen.turnouts.values():
            cen = (float(t.get("xcen")), float(t.get("ycen")))
            legs = [gen.ix.leg_coords(t, L) for L in ("ABCD" if "XOVER" in (t.get("type") or "") else "ABC")]
            xs, ys = [cen[0]] + [p[0] for p in legs], [cen[1]] + [p[1] for p in legs]
            self._add(("body", (cen, [(cen, p) for p in legs])), min(xs) - TURNOUT_R, min(ys) - TURNOUT_R,
                      max(xs) + TURNOUT_R, max(ys) + TURNOUT_R)
        for n, r in masts:
            self.add_rect("mast " + n, r)
        for n, r in labels:
            self.add_rect("label " + n, r)
        for c, rad in shapes:
            self._add(("shape", (c, rad)), c[0] - rad, c[1] - rad, c[0] + rad, c[1] + rad)

    def _cells(self, x0, y0, x1, y1):
        C = self.CELL
        return [(i, j) for i in range(int(math.floor(x0 / C)), int(math.floor(x1 / C)) + 1)
                for j in range(int(math.floor(y0 / C)), int(math.floor(y1 / C)) + 1)]

    def _add(self, obj, x0, y0, x1, y1):
        for c in self._cells(x0 - 2, y0 - 2, x1 + 2, y1 + 2):
            self.grid[c].append(obj)

    def add_rect(self, name, r):
        self._add(("rect", (name, r)), r.x, r.y, r.x + r.w, r.y + r.h)

    def hits(self, r, lamp):
        """What rectangle r would stand on: [reason]."""
        seen, why = set(), []
        for c in self._cells(r.x - 2, r.y - 2, r.x + r.w + 2, r.y + r.h + 2):
            for obj in self.grid.get(c, ()):
                if id(obj) in seen:
                    continue
                seen.add(id(obj))
                kind, v = obj
                if kind == "line" and not lamp and r.gap_seg(*v) < CLEAR:
                    why.append("track")
                elif kind == "body" and not lamp and (r.gap_point(v[0]) < TURNOUT_R or
                                                      any(r.gap_seg(a, b) < CLEAR for a, b in v[1])):
                    why.append("turnout")
                elif kind == "rect" and r.overlaps(v[1]):
                    why.append(v[0])
                elif kind == "shape" and r.gap_point(v[0]) < v[1] + CLEAR:
                    why.append("shape")
        return why


@functools.lru_cache(maxsize=None)
def spots(reach):
    """The offsets tried out to `reach` px, nearest first (built once per reach)."""
    return tuple(sorted(((dx, dy) for dx in range(-reach, reach + 1, STEP) for dy in range(-reach, reach + 1, STEP)
                         if dx * dx + dy * dy <= reach * reach), key=lambda d: (d[0] ** 2 + d[1] ** 2, d)))


def nudge(rects, obstacles, lamp, bounds, what):
    """(dx, dy): the nearest offset at which no rectangle of `rects` hits anything, inside `bounds` (x0, x1)."""
    for reach in REACH:
        for dx, dy in spots(reach):
            moved = [r.moved(dx, dy) for r in rects]
            if any(m.x < bounds[0] or m.x + m.w > bounds[1] for m in moved):
                continue
            if not any(obstacles.hits(m, lamp) for m in moved):
                return dx, dy
    here = [obstacles.hits(r, lamp) for r in rects]
    raise OverlayError(f"{what}: no clear spot within {REACH[-1]} px (where it would stand it meets "
                       f"{sorted({w for h in here for w in h}) or 'nothing'}, but it is off the panel)")


# ---------------------------------------------------------------- carry

ORDER = ("lamp", "slot", "station", "turnout", "block", "label", "frame", "status", "backdrop")


def rank(unit):
    its = unit["items"]
    if its[0].backdrop:
        return ORDER.index("backdrop")
    if unit["key"] == "status":
        return ORDER.index("status")
    if unit["key"].startswith("station "):
        return ORDER.index("station")
    it = its[0]
    if it.lamp:
        return ORDER.index("lamp")
    kind = it.anchor[0]
    if it.el.tag == "positionablelabel" and kind in ("turnout", "block"):
        return ORDER.index("label")
    return ORDER.index(kind if kind in ORDER else "frame")


def carry(live_le, gen_le, P, root, le_mod, slots_mod, switch_ident: dict, fit: tuple) -> dict:
    """Copy every live overlay item onto gen_le (see the module text). Returns a report: records [(item, anchor,
    live xy, new xy, moved px)], dropped generated labels, the vertical shift and the new panel size."""
    live = Track(live_le, le_mod, slots_mod, "live panel")
    live.le = live_le
    gen = Track(gen_le, le_mod, slots_mod, "new panel")
    items = overlay_items(live_le)

    # the generated labels: switch numbers, track names, station names, titles
    gen_labels = [lb for lb in gen_le.findall("positionablelabel")]
    live_texts = {(it.el.get("text") or "").strip() for it in items if it.el.tag == "positionablelabel"}
    station_labels, drop = {}, []
    lower = {t.lower() for t in live_texts}
    for lb in gen_labels:
        text = lb.get("text") or ""
        x, y, size = num(lb, "x", "label"), num(lb, "y", "label"), int(num(lb, "size", "label"))
        w, h = text_box(text, size)
        if text.isupper() and text.lower() in lower and lb.get("style") == "1":
            station_labels[text.lower()] = (x + w / 2, y + h / 2)
            drop.append(lb)
        elif re.fullmatch(r"\d+", text) and f"SW-{text}" in live_texts:
            drop.append(lb)
        elif f"Track {text}" in live_texts:
            drop.append(lb)
    tie(items, live, root, switch_ident, station_labels)
    for lb in drop:
        gen_le.remove(lb)
    kept = [lb for lb in gen_le.findall("positionablelabel")]
    labels = []
    for lb in kept:
        x, y, size = num(lb, "x", "label"), num(lb, "y", "label"), int(num(lb, "size", "label"))
        labels.append((lb.get("text"), Rect(x, y, *text_box(lb.get("text"), size))))
    masts = [(m["mast"], Rect(*m["box"])) for m in P.masts]
    shapes = [(tuple(sh["centre"]), sh["r"]) for sh in P.shapes]
    obstacles = Obstacles(gen, masts, labels, shapes)

    # units: a group moves as one, every other item alone
    groups = defaultdict(list)
    for it in items:
        groups[it.group or f"item {it.index}"].append(it)
    units = []
    for key, its in groups.items():
        units.append(dict(key=key, items=its))
    units.sort(key=lambda u: (rank(u), u["items"][0].index))
    W = fit[0] - le_mod.CHROME[0]
    records = []
    for u in units:
        its = u["items"]
        if its[0].backdrop:
            for it in its:
                it.new = (it.x, it.y)
                records.append(dict(item=it.what, anchor="backdrop", live=(it.x, it.y), new=it.new, nudged=0.0))
            continue
        if u["key"] == "status" or u["key"].startswith("station "):
            box = (min(i.x for i in its), min(i.y for i in its), max(i.x + i.w for i in its),
                   max(i.y + i.h for i in its))
            centre = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            if u["key"] == "status":
                want = frame_point(centre, live.box, gen.box)
            else:
                key = u["key"][len("station "):]
                if key not in gen.runs or key not in live.runs:
                    raise OverlayError(f"station cluster {key}: its block is not drawn on both panels")
                want = gen.at(key, *live.where(key, centre))
            shift = sub(want, centre)
        else:
            want = target(its[0], live, gen, station_labels)
            shift = sub(want, its[0].centre)
        shift = (round(shift[0]), round(shift[1]))        # whole pixels, as JMRI stores them
        rects = [Rect(i.x + shift[0], i.y + shift[1], i.w, i.h) for i in its]
        what = u["key"] if not u["key"].startswith("item ") else its[0].what
        dx, dy = nudge(rects, obstacles, all(i.lamp for i in its), (0, W), what)
        for i, r in zip(its, rects):
            i.new = (r.x + dx, r.y + dy)
            obstacles.add_rect(i.what, Rect(i.new[0], i.new[1], i.w, i.h))
        for i in its:
            kind = "group " + u["key"] if i.group else i.anchor[0]
            records.append(dict(item=i.what, anchor=kind, live=(i.x, i.y), new=i.new,
                                nudged=round(math.hypot(dx, dy), 1)))

    # everything below TOP, then the panel big enough for it all, within the window
    for it in items:
        if it.new != (round(it.new[0]), round(it.new[1])):
            raise OverlayError(f"{it.what}: placed at {it.new}, not on whole pixels")
        it.new = (round(it.new[0]), round(it.new[1]))
    top = min(min(it.new[1] for it in items if not it.backdrop), TOP)
    down = TOP - top if top < TOP else 0
    if down:
        shift_panel(gen_le, down)
    carried = []
    for it in items:
        el = copy.deepcopy(it.el)
        carried.append(el)
        y = it.new[1] if it.backdrop else it.new[1] + down
        el.set("x", str(it.new[0]))
        el.set("y", str(y))
        gen_le.append(el)
        it.final = (it.new[0], y)
    for r in records:
        r["new"] = (round(r["new"][0]), round(r["new"][1]) + (0 if r["anchor"] == "backdrop" else down))
    size = fit_size(gen_le, items, P, down, le_mod, fit)
    for it, el in zip(items, carried):
        if (int(el.get("x")), int(el.get("y"))) != it.final:
            raise OverlayError(f"overlay check: {it.what} is not where it was placed")
    bad = check(gen_le, live_le, le_mod, slots_mod, {m["mast"]: m["size"] for m in P.masts})
    if bad:
        raise OverlayError("overlay check: " + "; ".join(bad))
    return dict(records=records, dropped=[lb.get("text") for lb in drop], down=down, size=size,
                unchained=sorted(set(live.unchained) | set(gen.unchained)))


def shift_panel(le, dy):
    """Move everything already on the generated panel down dy px (track, turnouts, labels, icons, shapes)."""
    for el in le:
        if el.tag == "layoutturnout":
            for a in ("ycen", "ya", "yb", "yc", "yd"):
                if el.get(a) is not None:
                    el.set(a, f"{float(el.get(a)) + dy:.1f}")
        elif el.tag == "positionablepoint":
            el.set("y", f"{float(el.get('y')) + dy:.1f}")
        elif el.tag in ("positionablelabel", "signalmasticon"):
            el.set("y", str(int(round(float(el.get("y")))) + dy))
        elif el.tag == "layoutShape":
            for p in el.iter("point"):
                p.set("y", f"{float(p.get('y')) + dy:.1f}")


def fit_size(le, items, P, down, le_mod, fit):
    """Grow the panel to hold every item (EDGE px beyond the furthest), within the window less its frame."""
    W, H = fit[0] - le_mod.CHROME[0], fit[1] - le_mod.CHROME[1]
    right = max([P.size[0]] + [it.final[0] + it.w + EDGE for it in items if not it.backdrop])
    bottom = max([P.size[1] + down] + [it.final[1] + it.h + EDGE for it in items if not it.backdrop])
    w, h = math.ceil(right), math.ceil(bottom)
    if w > W or h > H:
        raise OverlayError(f"with its overlay the panel is {w}x{h} px, more than the {W}x{H} px the {fit[0]}x"
                           f"{fit[1]} window leaves")
    le.set("panelwidth", str(w))
    le.set("panelheight", str(h))
    le.set("windowwidth", str(w + le_mod.CHROME[0]))
    le.set("windowheight", str(h + le_mod.CHROME[1]))
    return (w, h)


def strip(el):
    """An element as text without its x and y (and whitespace): what must match between live and carried."""
    e = copy.deepcopy(el)
    e.attrib.pop("x", None)
    e.attrib.pop("y", None)
    for c in e.iter():
        c.tail = None
        c.text = (c.text or "").strip() or None
    return ET.tostring(e)


def check(gen_le, live_le, le_mod, slots_mod, mast_size) -> list[str]:
    """Problems with the overlay on a written panel, read from scratch: each live overlay item there exactly once
    with the same attributes and children but x and y, nothing else of the overlay kinds but the generated labels;
    no item over track (lamps excepted), turnouts, mast icons (`mast_size`: mast name -> (w, h) upright), labels,
    shapes or another item (within one cluster excepted); every item on the panel."""
    items = overlay_items(live_le)
    assign_groups(items)
    by_key = defaultdict(list)
    for el in gen_le:
        if el.tag in OVERLAY_TAGS:
            by_key[strip(el)].append(el)
    bad, placed = [], []
    for it in items:
        got = by_key.get(strip(it.el))
        if not got:
            bad.append(f"{it.what} is missing (or its attributes differ)")
            continue
        el = got.pop(0)
        it.final = (num(el, "x", it.what), num(el, "y", it.what))
    extra = [el for v in by_key.values() for el in v]
    labels = []
    for el in extra:
        if el.tag != "positionablelabel" or not el.get("text"):
            bad.append(f"{describe(el)} is on the new panel but not on the live one")
            continue
        labels.append((el.get("text"), Rect(num(el, "x", "label"), num(el, "y", "label"),
                                            *text_box(el.get("text"), int(num(el, "size", describe(el)))))))
    masts = []
    for icon in gen_le.findall("signalmasticon"):
        name = icon.get("signalmast")
        if name not in mast_size:
            bad.append(f"mast icon {name}: no size known")
            continue
        bw, bh = slots_mod.icon_box(mast_size[name], float(icon.get("degrees") or 0))
        masts.append((name, Rect(num(icon, "x", name), num(icon, "y", name), bw, bh)))
    shapes = []
    for sh in gen_le.findall("layoutShape"):
        pts = [(float(p.get("x")), float(p.get("y"))) for p in sh.iter("point")]
        c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        # the plugin's circle: eight curve points at r / cos(22.5 degrees) from the centre
        shapes.append((c, max(math.dist(c, p) for p in pts) * math.cos(math.pi / 8)))
    obstacles = Obstacles(Track(gen_le, le_mod, slots_mod, "new panel"), masts, labels, shapes)
    w, h = num(gen_le, "panelwidth", "panel"), num(gen_le, "panelheight", "panel")
    for it in items:
        if it.backdrop or not hasattr(it, "final"):
            continue
        r = Rect(it.final[0], it.final[1], it.w, it.h)
        if r.x < 0 or r.y < 0 or r.x + r.w > w or r.y + r.h > h:
            bad.append(f"{it.what} is off the panel")
        hit = obstacles.hits(r, it.lamp)
        hit += [n for (n, g), o in placed if r.overlaps(o) and not (it.group and g == it.group)]
        if hit:
            bad.append(f"{it.what} meets {sorted(set(hit))}")
        placed.append(((it.what, it.group), r))
    return bad
