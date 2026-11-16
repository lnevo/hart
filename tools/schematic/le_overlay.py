"""The old "HART Railroad" panel's icons carried onto the generated staging panel (LE cut-over, Phases 2 and 3b),
placed around the labels and block readouts the plugin generates.

    frozen = le_overlay.freeze(live_le, gen_le, root, le_mod, slots_mod, note, switch_prefix)   # once (--freeze)
    report = le_overlay.carry(frozen, gen_le, P, le_mod, slots_mod, fit, switch_prefix)        # every build

The overlay is frozen (Phase 3b, owner requirement 2026-11-15): freeze() reads each item off the hand-drawn panel
once, with what it is tied to there and its offset from that thing, into
jmri/layouts/hart/data/schematic/staging_le/overlay.json (le_inputs.py); carry() places the items from that file
alone, so the generated panel is rebuilt with no hand-drawn panel in the tables. Each item's XML in the file keeps
its x and y on the hand-drawn panel: a cluster's members keep their places against each other from them, and every
other item only needs its size.

Generated labels win (owner, 2026-11-15). The plugin's label layer writes every switch number, track name, station
caption and block contents icon (one per block, every OS block too) with its own no-overlap check. So freeze()
leaves out of the file the hand-drawn panel's block contents icons, its "SW-<n>" labels, its labels naming a block
and every caption a generated label also gives (same text, any case: Brick, West Yard, South Yard ...), and records
them under "dropped"; carry() stops unless the generated panel gives each of them (a generated block contents icon
for each dropped one, once the plugin writes any), and stops on a carried label that repeats a generated one.

What is carried: occupancy lamps, the Dispatcher System station clusters, the status cluster, the region captions
(Neville Island, Industries, the helix arrows) and the background picture. Each is copied with every attribute and
child as live; only x and y change. Not carried (owner, 2026-11-16; LEFT_OUT): the Entry/Exit sensor icons, whose
sensors stay bound in their mast slots (the build binds them, so the NX pairs resolve without an icon), and the yard
ladder buttons.

Where each goes. In the hand-drawn panel each item is tied to what it belongs to, then put at the same place against
that thing on the new panel:
- slot: an item whose sensor is bound in a slot to that slot (same ident and slot on both panels), at the same
  offset from the boundary point (no carried item is one since the NX icons went; kept for a re-freeze);
- turnout: an item of a switch's OS block (its lamp) to that turnout's centre (a crossover half to the middle of its
  legs), at the same offset;
- block: an item of a track block (its lamp, a caption by it) at the same share of the way along the block's track,
  left to right, and the same distance to its side;
- frame: what is tied to no track (region captions, the status cluster, any item over NEAR px from the track) keeps
  its place against the track's bounding box: across it by share, outside it by distance (the staging band's box
  when the panel holds more levels: carry's `frame_blocks`);
- backdrop: the background picture (an icon label at level 1 or below) stays at its live x and y, under everything.
The station clusters (level 12, one per Dispatcher station: a loco marker with its track's name and two lamps) and
the status cluster (the LCOS, Turnouts, Signals and Track Power lamps and captions) move as one block each. A station
cluster is not tied to its hand-drawn place: the plugin's label layer places it (owner, 2026-11-16). The build
passes each cluster's box to `schematic le` as an extra (station_extras: id and block its track block, size its
bounding box as JMRI draws it), placed by its own track in the same rounds as the block contents icons and before
them, with the same no-overlap check; carry() moves the cluster as one to the box's place in P.extras
(station_shift) and stops if the plugin placed none, one of another size, or one that meets a carried item.

Then each other item, in order (lamps, sensors, labels, captions), takes the nearest spot (STEP px at a
time, out to REACH px) clear of the track, the turnouts and their control circles, the mast icons, the generated
labels and block contents icons, and the items placed before it. An occupancy lamp (a circuit lamp) sits on its own
track by the owner's rule (2026-11-13), so track and turnouts do not count against it; icons and labels do. Every
item stays inside the FIT window (TOP px from the top, EDGE px from the right and bottom), so the panel never moves;
an item with no clear spot stops the build. Sizes are what JMRI draws: text by the plugin's schematic.jmri_text
(Dialog, the larger of Mac and Pi), an icon with text the larger of the two each way. Last, the panel grows to hold
everything within the window, and check() reads the written panel again from scratch.
"""
from __future__ import annotations

import copy
import functools
import importlib
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

TRACK_TAGS = {"layoutTrackDrawingOptions", "layoutturnout", "tracksegment", "positionablepoint", "signalmasticon",
              "layoutShape"}
OVERLAY_TAGS = {"sensoricon", "BlockContentsIcon", "positionablelabel", "turnouticon", "signalheadicon"}
CARRIED_TAGS = OVERLAY_TAGS - {"BlockContentsIcon"}         # block contents icons are the plugin's now
# px of each icon image (the JMRI 5.16 program resources and the repo's preference resources)
ICON_SIZES = (("smallschematics/tracksegments/circuit-", (10, 10)), ("icons/USS/sensor/", (21, 21)),
              ("icons/markers/loco-", (60, 20)), ("buttons/triangle_", (16, 16)),
              ("misc/hart_panel_bg.jpg", (1900, 600)))
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
GIVEN = ("block_contents", "switch_numbers", "track_names", "captions")    # dropped: the generated panel gives them
NOT_CARRIED = ("nx_icons", "ladder_buttons")                                # dropped: on no panel (LEFT_OUT)
DROPPED = GIVEN + NOT_CARRIED                                               # overlay.json "dropped" lists
# Not carried at all (owner, 2026-11-16): the Entry/Exit sensor icons (the sensors stay bound in their mast slots,
# so the NX pairs still resolve; only the panel icons go) and the yard ladder buttons.
LEFT_OUT = (("sensoricon", "sensor", "NX ", "nx_icons"), ("turnouticon", "turnout", "IT:HART:YL:", "ladder_buttons"))
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

    def box_of(self, blocks):
        """(x0, y0, x1, y1) of the drawn track of `blocks` and of the turnouts whose own block is one of them; stops
        when none of them is drawn."""
        blocks = set(blocks)
        allp = [p for b in blocks for pc in self.pieces.get(b, ()) for p in pc]
        for t in self.turnouts.values():
            if t.get("blockname") in blocks:
                allp += [self.ix.leg_coords(t, L) for L in "ABC"]
        if not allp:
            raise OverlayError(f"{self.what}: none of the frame's {len(blocks)} blocks is drawn")
        xs, ys = [p[0] for p in allp], [p[1] for p in allp]
        return (min(xs), min(ys), max(xs), max(ys))

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

    def length(self, block):
        run = self.runs.get(block)
        if not run:
            raise OverlayError(f"{self.what}: block {block} has no drawn track")
        return sum(math.dist(a, b) for a, b in run)

    def point_dir(self, block, along):
        """(point, unit direction) `along` px from the start of the block's run (clamped to the run)."""
        run = self.runs.get(block)
        if not run:
            raise OverlayError(f"{self.what}: block {block} has no drawn track")
        acc = 0.0
        for a, b in run:
            L = math.dist(a, b)
            if acc + L >= along - EPS or (a, b) == run[-1]:
                u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
                t = max(0.0, min(L, along - acc))
                return (a[0] + u[0] * t, a[1] + u[1] * t), u
            acc += L
        raise OverlayError(f"{self.what}: block {block}: no point {along} px along")

    def at(self, block, share, off, past=None):
        """The point at `share` of the way along the block's run, `off` px to its side; or, with `past` (dx, dy),
        that far from the run's end (as where())."""
        q, u = self.point_dir(block, share * self.length(block))
        if past is not None:
            return (q[0] + past[0], q[1] + past[1])
        return (q[0] - u[1] * off, q[1] + u[0] * off)

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


@functools.lru_cache(maxsize=None)
def jmri_text():
    """The plugin's schematic.jmri_text: the Dialog sizes JMRI draws (the plugin is on sys.path in a build)."""
    try:
        return importlib.import_module("schematic.jmri_text")
    except ImportError as exc:
        raise OverlayError(f"cannot size text: the schematic-maps plugin's schematic.jmri_text is not importable "
                           f"({exc}); run through build_layout_le.py, which puts the plugin on the path") from None


def text_box(text, size, bold, what):
    """(w, h) px JMRI gives `text` at `size` in Dialog (bold or plain)."""
    jt = jmri_text()
    if size not in jt.SIZES:
        raise OverlayError(f"{what}: font size {size} has no measured Dialog size ({jt.SIZES.start}.."
                           f"{jt.SIZES.stop - 1})")
    return float(jt.width(text, size, bold)), float(jt.height(size, bold))


def text_size(el, what):
    """(size, bold) of a text item's font, read from its attributes (a size that is no whole number stops)."""
    size = num(el, "size", what)
    if size != int(size):
        raise OverlayError(f"{what}: size={el.get('size')!r} is no whole number")
    style = el.get("style") or "0"
    if style not in ("0", "1", "2", "3"):
        raise OverlayError(f"{what}: style={style!r} is not a JMRI font style (0..3)")
    return int(size), style in ("1", "3")


@functools.lru_cache(maxsize=None)
def bci_text(key="block_contents_text"):
    """The train name a block contents icon's box is reserved for: the plugin label layer's default
    (schematic.le_labels DEFAULTS `key`: block_contents_text, or block_contents_short for an icon that fits only
    the shorter box; carry() checks the plugin's own boxes agree)."""
    try:
        return importlib.import_module("schematic.le_labels").DEFAULTS[key]
    except (ImportError, AttributeError, KeyError) as exc:
        raise OverlayError(f"cannot size block contents icons: the schematic-maps plugin's label layer "
                           f"(schematic.le_labels DEFAULTS[{key!r}]) is missing ({exc})") from None


def bci_box(el, what):
    """(w, h) a block contents icon takes: the full reserved train name (bci_text()) in its font. The XML does
    not say which icons the plugin gave the short reserve, so every one is kept clear at full width (the wider
    box holds the shorter one)."""
    return text_box(bci_text(), *text_size(el, what), what)


def describe(el):
    name = (el.get("sensor") or el.get("blockcontents") or el.get("turnout") or el.get("signalhead") or
            el.get("text") or (el.find("icon").get("url") if el.find("icon") is not None else "") or "?")
    return f"{el.tag} {name!r}"


class Item:
    """One overlay item: its place (x, y), its image size and font read at once (a bad one stops); its drawn size
    (w, h) on first use, from the plugin's font sizes, so le_inputs.load can check the file without the plugin."""

    def __init__(self, el, index):
        self.el, self.index = el, index
        self.what = describe(el)
        self.x, self.y = num(el, "x", self.what), num(el, "y", self.what)
        self.icon = icon_size(el, self.what)
        self.text = el.get("text")
        texty = el.tag == "BlockContentsIcon" or self.text is not None
        self.font = text_size(el, self.what) if texty else None      # a text item without a size stops
        if el.tag != "BlockContentsIcon" and not self.icon:
            if self.text is None:
                raise OverlayError(f"{self.what}: neither an image nor text, so its size is unknown")
            if not self.text.strip():
                raise OverlayError(f"{self.what}: a text label with no text")
        self._size = None
        self.lamp = el.tag == "sensoricon" and any("circuit-" in (c.get("url") or "") for c in el.iter())
        self.backdrop = el.tag == "positionablelabel" and self.icon is not None and int(el.get("level") or 0) <= 1
        self.group = None       # a cluster key: its members move as one
        self.anchor = None      # (kind, ...) in the live panel
        self.new = None         # (x, y) on the new panel

    @property
    def size(self):
        """(w, h) px as JMRI draws it: an icon with text the larger of the two each way (PositionableLabel)."""
        if self._size is None:
            if self.el.tag == "BlockContentsIcon":
                self._size = bci_box(self.el, self.what)
            elif self.text:
                tw, th = text_box(self.text, *self.font, self.what)
                iw, ih = self.icon or (0, 0)
                self._size = (max(iw, tw), max(ih, th))
            else:
                self._size = self.icon
        return self._size

    @property
    def w(self):
        return self.size[0]

    @property
    def h(self):
        return self.size[1]

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


def generated(elements, bci_widths=None):
    """[(kind, name, Rect)] of the generated labels ("label", its text) and block contents icons ("block contents",
    its block) among `elements`, sized as JMRI draws them. A hidden label (the generated-panel marker) is not drawn
    on the running panel, so it is left out. A block contents icon is as wide as the full reserve, or with
    `bci_widths` ({block: px}, the plugin's boxes; same_boxes checks they are a reserve) as the plugin placed it."""
    out = []
    for el in elements:
        what = describe(el)
        if el.tag == "positionablelabel" and el.get("text") and el.get("hidden") != "yes":
            w, h = text_box(el.get("text"), *text_size(el, what), what)
            out.append(("label", el.get("text"), Rect(num(el, "x", what), num(el, "y", what), w, h)))
        elif el.tag == "BlockContentsIcon":
            if not el.get("blockcontents"):
                raise OverlayError(f"generated panel: a block contents icon at {el.get('x')}, {el.get('y')} names "
                                   "no block")
            w, h = bci_box(el, what)
            if bci_widths is not None:
                if el.get("blockcontents") not in bci_widths:
                    raise OverlayError(f"generated panel: {what} is not among the plugin's block contents icons")
                w = bci_widths[el.get("blockcontents")]
            out.append(("block contents", el.get("blockcontents"), Rect(num(el, "x", what), num(el, "y", what), w, h)))
    return out


def switch_number(text, switch_prefix):
    """The switch number a label names ("SW-13" -> "13", "SW-35A" -> "35A", with `switch_prefix` "SW-"), else None.
    With no prefix nothing is a switch label (a bare number may be an equipment label)."""
    if not switch_prefix or not text.startswith(switch_prefix):
        return None
    n = text[len(switch_prefix):]
    return n if re.fullmatch(r"\d+[A-Z]?", n) else None


def left_out(el) -> str | None:
    """The "dropped" list of an item the generated panel does not carry at all (LEFT_OUT: "nx_icons" for an NX sensor
    icon, "ladder_buttons" for a yard ladder button), else None."""
    return next((key for tag, attr, prefix, key in LEFT_OUT
                 if el.tag == tag and (el.get(attr) or "").startswith(prefix)), None)


def split_generated(items, live, gen, switch_prefix):
    """(kept items, dropped {kind: [name]}): the hand-drawn items the generated panel gives itself now (`gen`:
    generated() of it) left out. Block contents icons, switch number labels (`switch_prefix` and the number) and
    labels naming a block always; a caption when a generated label has its text, in any case. A label with no text
    (the backdrop, an icon-only label) is never one of them. The items no panel carries (left_out) are listed too,
    under their own lists (NOT_CARRIED)."""
    gen_texts = {name.lower() for kind, name, _r in gen if kind == "label"}
    blocks = set(live.pieces) | set(live.os_turnouts())
    kept, dropped = [], {k: set() for k in DROPPED}
    for it in items:
        el, text = it.el, (it.el.get("text") or "").strip()
        if left_out(el):
            dropped[left_out(el)].add(el.get("sensor") or el.get("turnout"))
            continue
        if el.tag == "BlockContentsIcon":
            if not el.get("blockcontents"):
                raise OverlayError(f"live {it.what} names no block")
            dropped["block_contents"].add(el.get("blockcontents"))
        elif el.tag != "positionablelabel" or it.backdrop or not text:
            kept.append(it)
        elif switch_number(text, switch_prefix):
            dropped["switch_numbers"].add(switch_number(text, switch_prefix))
        elif text in blocks:
            dropped["track_names"].add(text.removeprefix("Track "))
        elif text.lower() in gen_texts:
            dropped["captions"].add(text)
        else:
            kept.append(it)
    return kept, {k: sorted(v, key=lambda t: (len(t), t)) for k, v in dropped.items()}


def given(dropped, gen, what, switch_prefix=""):
    """[notes]: stop with OverlayError when the generated panel (`gen`: generated() of it) lacks a switch number,
    track name or caption that the hand-drawn panel had and the overlay no longer carries (a switch number with the
    plugin's `switch_prefix`), or a block contents icon of a dropped one; a note instead when it has no block
    contents icon at all (a plugin without the label layer)."""
    texts = {name for kind, name, _r in gen if kind == "label"}
    lower = {t.lower() for t in texts}
    bcis = {name for kind, name, _r in gen if kind == "block contents"}
    missing = [f"switch number {switch_prefix}{n}" for n in dropped["switch_numbers"] if switch_prefix + n not in texts]
    missing += [f"track name {t}" for t in dropped["track_names"] if t not in texts]
    missing += [f"caption {c!r}" for c in dropped["captions"] if c.lower() not in lower]
    notes = []
    if bcis:
        missing += [f"block contents icon of {b}" for b in dropped["block_contents"] if b not in bcis]
    elif dropped["block_contents"]:
        notes.append(f"the generated panel has no block contents icon (the plugin has no label layer?): "
                     f"{len(dropped['block_contents'])} blocks show no train")
    if missing:
        raise OverlayError(f"{what}: the generated panel lacks what the hand-drawn panel showed and the overlay "
                           f"leaves to it: {', '.join(missing)}")
    return notes


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


def tie(items, live, root):
    """Set each item's group (assign_groups) or anchor, from the live panel (`items`: split_generated()'s kept)."""
    assign_groups(items)
    by_sensor = sensor_blocks(root)
    slots_of = sensor_slots(live.le)
    os_of = live.os_turnouts()
    for it in items:
        el = it.el
        sensor = el.get("sensor")
        if it.group:
            continue
        if el.tag not in CARRIED_TAGS:
            raise OverlayError(f"live {it.what}: the generated panel gives these, so it is not carried")
        if it.backdrop:
            it.anchor = ("backdrop",)
        elif sensor in slots_of:
            it.anchor = ("slot",) + slots_of[sensor] + (sub(it.centre, slot_point(live, *slots_of[sensor])),)
        else:
            it.anchor = block_anchor(it, by_sensor.get(sensor, set()) if sensor else set(), live, os_of)


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
        if hi - lo < EPS:
            raise OverlayError(f"the live track spans no {'width' if k == 0 else 'height'}, so an item's share "
                               "across it is undefined")
        if p[k] < lo:
            out.append(glo - (lo - p[k]))
        elif p[k] > hi:
            out.append(ghi + (p[k] - hi))
        else:
            out.append(glo + (p[k] - lo) / (hi - lo) * (ghi - glo))
    return tuple(out)


def target(it, frame, gen, gen_frame):
    """The centre the item would take on the new panel before it is nudged clear (`frame`: the hand-drawn track's
    bounding box; `gen_frame`: the box on the new panel a frame item keeps its place against)."""
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
    if kind == "frame":
        return frame_point(it.centre, frame, gen_frame)
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
    """The new panel's track lines, turnouts, mast icons, generated labels and block contents icons, and the items
    placed so far, indexed by grid cell (CELL px) so a spot is scored against what is near it only. `fixed`:
    [(name, Rect)] of the generated labels and icons (generated(), named "<kind> <name>")."""
    CELL = 32

    def __init__(self, gen, masts, fixed, shapes):
        self.grid = defaultdict(list)       # cell -> [(kind, payload)]
        for block, pcs in gen.pieces.items():
            for a, b in pcs:
                self._add(("line", (a, b, block)), min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]),
                          max(a[1], b[1]))
        for t in gen.turnouts.values():
            cen = (float(t.get("xcen")), float(t.get("ycen")))
            legs = [gen.ix.leg_coords(t, L) for L in ("ABCD" if "XOVER" in (t.get("type") or "") else "ABC")]
            xs, ys = [cen[0]] + [p[0] for p in legs], [cen[1]] + [p[1] for p in legs]
            self._add(("body", (cen, [(cen, p) for p in legs])), min(xs) - TURNOUT_R, min(ys) - TURNOUT_R,
                      max(xs) + TURNOUT_R, max(ys) + TURNOUT_R)
        for n, r in masts:
            self.add_rect("mast " + n, r)
        for n, r in fixed:
            self.add_rect(n, r)
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

    def hits(self, r, lamp, own=None):
        """What rectangle r would stand on: [reason]. A lamp may stand on any track and turnout; with `own` (a
        block) r may stand on that block's track lines."""
        seen, why = set(), []
        for c in self._cells(r.x - 2, r.y - 2, r.x + r.w + 2, r.y + r.h + 2):
            for obj in self.grid.get(c, ()):
                if id(obj) in seen:
                    continue
                seen.add(id(obj))
                kind, v = obj
                if kind == "line" and not lamp and v[2] != own and r.gap_seg(v[0], v[1]) < CLEAR:
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


def inside(rects, bounds):
    """True when every rectangle is inside `bounds` (x0, y0, x1, y1)."""
    return all(r.x >= bounds[0] and r.y >= bounds[1] and r.x + r.w <= bounds[2] and r.y + r.h <= bounds[3]
               for r in rects)


def nudge(rects, obstacles, lamp, bounds, what):
    """(dx, dy): the nearest offset at which no rectangle of `rects` hits anything, inside `bounds` (x0, y0, x1,
    y1)."""
    for reach in REACH:
        for dx, dy in spots(reach):
            moved = [r.moved(dx, dy) for r in rects]
            if inside(moved, bounds) and not any(obstacles.hits(m, lamp) for m in moved):
                return dx, dy
    here = [obstacles.hits(r, lamp) for r in rects]
    raise OverlayError(f"{what}: no clear spot within {REACH[-1]} px inside the window (where it would stand it "
                       f"meets {sorted({w for h in here for w in h}) or 'nothing'})")


def station_clusters(frozen):
    """{station block: [Item]}: the station clusters of a frozen overlay (validated), each member sized as JMRI
    draws it; the clusters' boxes go to the plugin's label layer to be placed (station_extras)."""
    validate(frozen)
    out = defaultdict(list)
    for it in frozen_items(frozen):
        block = station_block(it.group)
        if block:
            out[block].append(it)
    return dict(out)


def panel_station_clusters(live_le):
    """{station block: [Item]} of the station clusters on the hand-drawn panel (--freeze: before the overlay is
    frozen, the same items as station_clusters gives from the frozen file)."""
    items = overlay_items(live_le)
    assign_groups(items)
    out = defaultdict(list)
    for it in items:
        if station_block(it.group):
            out[station_block(it.group)].append(it)
    return dict(out)


def cluster_box(its):
    """(x, y, w, h) of the members' bounding box, as they stand in the frozen file."""
    x0, y0 = min(i.x for i in its), min(i.y for i in its)
    return x0, y0, max(i.x + i.w for i in its) - x0, max(i.y + i.h for i in its) - y0


def station_extras(clusters):
    """The plugin's `extras` for the station clusters ({block: [Item]}, station_clusters or panel_station_clusters):
    one box per cluster, its id and block the station's track block, its size the members' bounding box as JMRI
    draws them. The label layer places each beside its own track with its labels and block contents icons."""
    return [dict(id=block, block=block, size=list(cluster_box(its)[2:])) for block, its in sorted(clusters.items())]


def station_shift(its, block, P):
    """(dx, dy) moving the station cluster `its` (as one) to where the plugin's label layer placed its box
    (P.extras); stops when the plugin placed none or a box of another size."""
    got = [e for e in getattr(P, "extras", ()) if e["id"] == block]
    if len(got) != 1:
        raise OverlayError(f"station cluster {block}: the plugin's label layer placed {len(got)} boxes for it "
                           "(build_layout_le.py passes each cluster as an extra)")
    x0, y0, w, h = cluster_box(its)
    bx, by, bw, bh = got[0]["box"]
    if got[0]["block"] != block or (round(bw, 1), round(bh, 1)) != (round(w, 1), round(h, 1)):
        raise OverlayError(f"station cluster {block}: the plugin placed a {bw:g}x{bh:g} px box by "
                           f"{got[0]['block']}, not its {w:g}x{h:g} px")
    return bx - x0, by - y0


# ---------------------------------------------------------------- carry

ORDER = ("station", "lamp", "slot", "turnout", "block", "label", "frame", "status", "backdrop")


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


# ---------------------------------------------------------------- the frozen overlay (overlay.json)

ANCHOR_FIELDS = {"backdrop": (), "frame": (), "slot": ("on", "ident", "slot", "offset"),
                 "turnout": ("ident", "block", "offset"), "block": ("block", "share", "side", "past")}
ITEM_FIELDS = {"index", "xml", "group", "anchor"}
FROZEN_FIELDS = {"_note", "frame", "dropped", "unchained", "items"}


def element_xml(el) -> str:
    """One item's XML as frozen: every attribute (x and y as on the hand-drawn panel) and child, no layout space."""
    e = copy.deepcopy(el)
    for c in e.iter():
        c.tail = None
        if c.text is not None and not c.text.strip():
            c.text = None
    return ET.tostring(e, encoding="unicode")


def anchor_json(anchor):
    kind = anchor[0]
    if kind == "slot":
        return dict(kind=kind, on=anchor[1], ident=anchor[2], slot=anchor[3], offset=list(anchor[4]))
    if kind == "turnout":
        return dict(kind=kind, ident=anchor[1], block=anchor[2], offset=list(anchor[3]))
    if kind == "block":
        return dict(kind=kind, block=anchor[1], share=anchor[2], side=anchor[3],
                    past=list(anchor[4]) if anchor[4] is not None else None)
    return dict(kind=kind)


def anchor_tuple(a: dict):
    kind = a["kind"]
    if kind == "slot":
        return (kind, a["on"], a["ident"], a["slot"], tuple(a["offset"]))
    if kind == "turnout":
        return (kind, a["ident"], a["block"], tuple(a["offset"]))
    if kind == "block":
        return (kind, a["block"], a["share"], a["side"], tuple(a["past"]) if a["past"] is not None else None)
    return (kind,)


def freeze(live_le, gen_le, root, le_mod, slots_mod, note: str, switch_prefix: str = "") -> dict:
    """The overlay of the hand-drawn panel `live_le` as overlay.json holds it: each carried item's XML, its cluster
    or what it is tied to and its offset from that, the hand-drawn track's bounding box (for the frame items and the
    status cluster), and under "dropped" what the generated panel gives instead (split_generated). `gen_le` is the
    generated panel the items go on: its labels decide which captions it gives. Reads `gen_le` only, and stops
    unless it gives everything dropped (given())."""
    live = Track(live_le, le_mod, slots_mod, "hand-drawn panel")
    live.le = live_le
    gen = generated(gen_le)
    items, dropped = split_generated(overlay_items(live_le), live, gen, switch_prefix)
    given(dropped, gen, "freeze", switch_prefix)
    tie(items, live, root)
    return {"_note": note, "frame": list(live.box), "dropped": dropped, "unchained": sorted(live.unchained),
            "items": [dict(index=it.index, xml=element_xml(it.el), group=it.group,
                           anchor=anchor_json(it.anchor) if it.anchor else None) for it in items]}


def validate(frozen, what="overlay.json", switch_prefix="") -> None:
    """Stop with OverlayError on a frozen overlay of the wrong shape (fields, kinds, numbers, XML), naming the item."""
    def need(cond, msg):
        if not cond:
            raise OverlayError(f"{what}: {msg}")

    def number(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

    def pair(v):
        return isinstance(v, list) and len(v) == 2 and all(number(x) for x in v)

    need(isinstance(frozen, dict), "not an object")
    need(set(frozen) <= FROZEN_FIELDS and FROZEN_FIELDS - {"_note"} <= set(frozen),
         f"fields {sorted(frozen)}, expected {sorted(FROZEN_FIELDS)}")
    need(isinstance(frozen["frame"], list) and len(frozen["frame"]) == 4 and all(number(v) for v in frozen["frame"]),
         "frame must be [x0, y0, x1, y1]")
    need(isinstance(frozen["unchained"], list) and all(isinstance(b, str) for b in frozen["unchained"]),
         "unchained must be a list of block names")
    dropped = frozen["dropped"]
    need(isinstance(dropped, dict) and set(dropped) == set(DROPPED), f"dropped must be an object of {list(DROPPED)}")
    for k in DROPPED:
        need(isinstance(dropped[k], list) and all(isinstance(v, str) and v for v in dropped[k]) and
             len(set(dropped[k])) == len(dropped[k]), f"dropped {k} must be a list of different names")
    need(isinstance(frozen["items"], list) and frozen["items"], "items must be a list of items")
    seen, groups = set(), set()
    for k, it in enumerate(frozen["items"]):
        name = f"item {k}"
        need(isinstance(it, dict) and set(it) == ITEM_FIELDS,
             f"{name}: fields {sorted(it) if isinstance(it, dict) else it}, expected {sorted(ITEM_FIELDS)}")
        need(isinstance(it["index"], int) and not isinstance(it["index"], bool) and it["index"] not in seen,
             f"{name}: index {it['index']!r} is not a new whole number")
        seen.add(it["index"])
        need(isinstance(it["xml"], str), f"{name}: xml must be text")
        try:
            el = ET.fromstring(it["xml"])
        except ET.ParseError as exc:
            raise OverlayError(f"{what}: {name}: xml does not parse ({exc})") from None
        need(el.tag in CARRIED_TAGS, f"{name}: {el.tag} is not an overlay item this build carries" +
             (" (the generated panel gives one per block)" if el.tag == "BlockContentsIcon" else ""))
        name = f"item {k} ({describe(el)})"
        need(not left_out(el), f"{name}: Entry/Exit sensor icons and yard ladder buttons are not carried (re-freeze)")
        need(not (el.tag == "positionablelabel" and switch_number((el.get("text") or "").strip(), switch_prefix)),
             f"{name}: the generated panel gives the switch numbers, so it is not carried (re-freeze)")
        Item(el, it["index"])           # its position, image size and font read, or a clear stop
        group, anchor = it["group"], it["anchor"]
        need((group is None) != (anchor is None), f"{name}: needs a group or an anchor, not both or neither")
        if group is not None:
            need(group == "status" or (isinstance(group, str) and group.startswith("station ")),
                 f"{name}: group {group!r} is neither status nor station <block>")
            groups.add(group)
            continue
        need(isinstance(anchor, dict) and anchor.get("kind") in ANCHOR_FIELDS,
             f"{name}: anchor kind {anchor.get('kind') if isinstance(anchor, dict) else anchor!r} not known "
             f"({', '.join(ANCHOR_FIELDS)})")
        fields = ANCHOR_FIELDS[anchor["kind"]]
        need(set(anchor) == {"kind", *fields}, f"{name}: a {anchor['kind']} anchor has fields {sorted(fields)}")
        for f in fields:
            v = anchor[f]
            if f == "offset":
                ok = pair(v)
            elif f in ("share", "side"):
                ok = number(v)
            elif f == "past":
                ok = v is None or pair(v)
            else:
                ok = isinstance(v, str) and bool(v)
            need(ok, f"{name}: anchor {f} {v!r} has the wrong type")
        if anchor["kind"] == "slot":
            need(anchor["on"] in ("point", "turnout"), f"{name}: a slot anchor is on a point or a turnout")
        if el.tag == "positionablelabel" and anchor["kind"] in ("block", "turnout"):
            need((el.get("text") or "").strip() != anchor["block"],
                 f"{name}: the generated panel gives the track names, so it is not carried (re-freeze)")
    for g in groups:
        need(g == "status" or len(g) > len("station "), f"group {g!r} names no station block")


def frozen_items(frozen):
    """Fresh Items of a frozen overlay (validated), with their clusters and anchors."""
    items = []
    for it in frozen["items"]:
        item = Item(ET.fromstring(it["xml"]), it["index"])
        item.group = it["group"]
        item.anchor = anchor_tuple(it["anchor"]) if it["anchor"] else None
        items.append(item)
    return items


def cluster_centre(its):
    box = (min(i.x for i in its), min(i.y for i in its), max(i.x + i.w for i in its), max(i.y + i.h for i in its))
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def station_block(group):
    """The block of a station cluster's group ("station <block>"), else None."""
    return group[len("station "):] if group and group.startswith("station ") else None


def repeats(items, gen):
    """Stop on a carried label that a generated label repeats (same text, any case): a caption the generator gives
    now, which a re-freeze leaves out."""
    lower = {name.lower(): name for kind, name, _r in gen if kind == "label"}
    bad = [f"{it.what} (generated {lower[it.text.strip().lower()]!r})" for it in items
           if it.el.tag == "positionablelabel" and it.text and it.text.strip().lower() in lower]
    if bad:
        raise OverlayError("carried labels the generated panel also gives (re-freeze with build_layout_le.py "
                           "--freeze to leave them out): " + ", ".join(bad))


def whole(it, p):
    """p as whole pixels, as JMRI stores them; an item off whole pixels on the hand-drawn panel stops."""
    if p != (round(p[0]), round(p[1])):
        raise OverlayError(f"{it.what}: placed at {p}, not on whole pixels")
    return (round(p[0]), round(p[1]))


def same_boxes(fixed, P):
    """Stop unless each generated label and block contents icon read from the XML (`fixed`: generated()) has the
    box the plugin placed it by (P.labels / P.bcis "box", when the plugin gives them): the overlay must keep clear
    of what JMRI draws, not of a guess."""
    want = defaultdict(list)
    for lb in P.labels:
        if lb.get("box") is not None:
            want[("label", lb["text"])].append(tuple(round(v, 1) for v in lb["box"]))
    sizes = {}
    for b in getattr(P, "bcis", ()):       # a plugin without the label layer has none (given() notes it)
        want[("block contents", b["block"])].append(tuple(round(v, 1) for v in b["box"]))
        sizes[b["block"]] = int(b["size"])
    bad = []
    for kind, name, r in fixed:
        boxes = want.get((kind, name))
        if boxes is None:
            if want:            # the plugin boxes what it places: an item it did not place is not its own
                bad.append(f"{kind} {name!r}: on the generated panel, but the plugin placed no such item")
            continue
        got = (round(r.x, 1), round(r.y, 1), round(r.w, 1), round(r.h, 1))
        if kind == "block contents":        # the plugin may have given it the short reserve: same left, top, height
            short = round(text_box(bci_text("block_contents_short"), sizes[name], False, name)[0], 1)
            ok = got in boxes or (got[0], got[1], short, got[3]) in boxes
        else:
            ok = got in boxes
        if not ok:
            bad.append(f"{kind} {name!r}: {got}, the plugin's {boxes}")
    if bad:
        raise OverlayError("generated items sized otherwise than the plugin placed them (x, y, w, h): " +
                           "; ".join(bad))


def carry(frozen, gen_le, P, le_mod, slots_mod, fit: tuple, switch_prefix: str = "", frame_blocks=None) -> dict:
    """Copy every frozen overlay item onto gen_le (see the module text). Returns a report: records [(item, anchor,
    hand-drawn xy, new xy, moved px)], the generated labels and block contents icons placed around ({kind: count}),
    notes, the new panel size and the blocks whose track is not one run. `frame_blocks`: the blocks of the band the
    frame items and the status cluster are tied to (default: every block drawn), so they keep their place against
    that band's track however the panel grows below it. A panel the plugin drew taller than the `fit` window
    (several bands at one band's grid) keeps its items inside the panel instead, and its window is `fit`."""
    validate(frozen, switch_prefix=switch_prefix)
    gen = Track(gen_le, le_mod, slots_mod, "new panel")
    gen_frame = gen.box if frame_blocks is None else gen.box_of(frame_blocks)
    items = frozen_items(frozen)
    frame = tuple(frozen["frame"])
    same_boxes(generated(list(gen_le)), P)     # the XML read alone agrees with the plugin's boxes
    bci_widths = {b["block"]: float(b["box"][2]) for b in getattr(P, "bcis", ())}
    fixed = generated(list(gen_le), bci_widths)     # obstacles as wide as the plugin cleared them
    notes = given(frozen["dropped"], fixed, "carry", switch_prefix)
    repeats(items, fixed)
    masts = [(m["mast"], Rect(*m["box"])) for m in P.masts]
    shapes = [(tuple(sh["centre"]), sh["r"]) for sh in P.shapes]
    obstacles = Obstacles(gen, masts, [(f"{k} {n}", r) for k, n, r in fixed], shapes)
    W, H = room(P, le_mod, fit)
    bounds = (0, TOP, W - EDGE, H - EDGE)       # inside the window (or panel), so fit_size never moves the panel

    # units: a group moves as one, every other item alone
    groups = defaultdict(list)
    for it in items:
        groups[it.group or f"item {it.index}"].append(it)
    units = sorted((dict(key=key, items=its) for key, its in groups.items()),
                   key=lambda u: (rank(u), u["items"][0].index))
    records = []
    for u in units:
        its = u["items"]
        if its[0].backdrop:
            for it in its:
                it.new = whole(it, (it.x, it.y))
                records.append(dict(item=it.what, anchor="backdrop", live=(it.x, it.y), new=it.new, nudged=0.0))
            continue
        what = u["key"] if not u["key"].startswith("item ") else its[0].what
        block = station_block(u["key"])
        if block:
            dx, dy = station_shift(its, block, P)
            dx, dy = round(dx), round(dy)       # whole pixels, as JMRI stores them
            moved = 0.0         # placed by the plugin, not tied to its hand-drawn place: no nudge to report
            rects = [Rect(i.x + dx, i.y + dy, i.w, i.h) for i in its]
            hit = sorted({x for r in rects for x in obstacles.hits(r, False, block)})
            if hit or not inside(rects, bounds):
                raise OverlayError(f"station cluster {block}: where the plugin placed it it meets "
                                   f"{hit or 'the window edge'}")
        else:
            if u["key"] == "status":
                start = cluster_centre(its)
                want = frame_point(start, frame, gen_frame)
            else:
                start = its[0].centre
                want = target(its[0], frame, gen, gen_frame)
            shift = (round(want[0] - start[0]), round(want[1] - start[1]))      # whole pixels, as JMRI stores
            rects = [Rect(i.x + shift[0], i.y + shift[1], i.w, i.h) for i in its]
            ndx, ndy = nudge(rects, obstacles, all(i.lamp for i in its), bounds, what)
            dx, dy = shift[0] + ndx, shift[1] + ndy
            moved = round(math.hypot(ndx, ndy), 1)
        for i in its:
            i.new = whole(i, (i.x + dx, i.y + dy))
            obstacles.add_rect(i.what, Rect(i.new[0], i.new[1], i.w, i.h))
            kind = "group " + u["key"] if i.group else i.anchor[0]
            records.append(dict(item=i.what, anchor=kind, live=(i.x, i.y), new=i.new, nudged=moved))

    if not any(not it.backdrop for it in items):
        raise OverlayError("the frozen overlay has no item to carry but its backdrop")
    carried = []
    for it in items:
        el = copy.deepcopy(it.el)
        el.set("x", str(it.new[0]))
        el.set("y", str(it.new[1]))
        gen_le.append(el)
        carried.append(el)
    size = fit_size(gen_le, items, P, le_mod, fit)
    for it, el in zip(items, carried):
        if (int(el.get("x")), int(el.get("y"))) != it.new:
            raise OverlayError(f"overlay check: {it.what} is not where it was placed")
    bad = check(gen_le, frozen, le_mod, slots_mod, {m["mast"]: m["size"] for m in P.masts}, switch_prefix,
                bci_widths)
    if bad:
        raise OverlayError("overlay check: " + "; ".join(bad))
    counts = defaultdict(int)
    for kind, _n, _r in fixed:
        counts[kind] += 1
    return dict(records=records, generated=dict(counts), dropped={k: len(v) for k, v in frozen["dropped"].items()},
                notes=notes, size=size, unchained=sorted(set(frozen["unchained"]) | set(gen.unchained)))


def room(P, le_mod, fit):
    """(width, height) px the panel may take: the `fit` window less its frame, or the plugin's panel where that is
    larger (drawn at a fixed grid, it scrolls in the window)."""
    W, H = fit[0] - le_mod.CHROME[0], fit[1] - le_mod.CHROME[1]
    if W <= 0 or H <= 0:
        raise OverlayError(f"a {fit[0]}x{fit[1]} px window leaves no room for a panel inside its frame")
    return max(W, P.size[0]), max(H, P.size[1])


def fit_size(le, items, P, le_mod, fit):
    """Grow the panel to hold every item (EDGE px beyond the furthest), within room(). The panel is never moved:
    carry() keeps every item inside that room, so a panel the plugin spreads over the full window height (one band)
    stays as drawn. The window is the panel and its frame, at most `fit` (a larger panel scrolls in it)."""
    W, H = room(P, le_mod, fit)
    right = max([P.size[0]] + [it.new[0] + it.w + EDGE for it in items if not it.backdrop])
    bottom = max([P.size[1]] + [it.new[1] + it.h + EDGE for it in items if not it.backdrop])
    w, h = math.ceil(right), math.ceil(bottom)
    if w > W or h > H:
        raise OverlayError(f"with its overlay the panel is {w}x{h} px, more than the {W}x{H} px it may take "
                           f"(the {fit[0]}x{fit[1]} window, or the drawn panel where larger)")
    le.set("panelwidth", str(w))
    le.set("panelheight", str(h))
    le.set("windowwidth", str(min(w + le_mod.CHROME[0], fit[0])))
    le.set("windowheight", str(min(h + le_mod.CHROME[1], fit[1])))
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


def check(gen_le, frozen, le_mod, slots_mod, mast_size, switch_prefix="", bci_widths=None) -> list[str]:
    """Problems with the overlay on a written panel, read from scratch: each frozen overlay item there exactly once
    with the same attributes and children but x and y, nothing else of the overlay kinds but the generated labels
    and block contents icons (and the hidden generated-panel marker); no item over track (lamps, and a station
    cluster on its own track, excepted), turnouts, mast icons (`mast_size`: mast name -> (w, h) upright), generated
    labels and block contents icons (at the sizes JMRI draws), shapes or another item (within one cluster excepted);
    every item on the panel."""
    validate(frozen, switch_prefix=switch_prefix)
    items = frozen_items(frozen)
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
    for el in extra:
        if not (el.tag == "BlockContentsIcon" or el.tag == "positionablelabel" and el.get("text")):
            bad.append(f"{describe(el)} is on the new panel but not in the frozen overlay")
    fixed = generated(extra, bci_widths)
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
    obstacles = Obstacles(Track(gen_le, le_mod, slots_mod, "new panel"), masts,
                          [(f"{k} {n}", r) for k, n, r in fixed], shapes)
    w, h = num(gen_le, "panelwidth", "panel"), num(gen_le, "panelheight", "panel")
    for it in items:
        if it.backdrop or not hasattr(it, "final"):
            continue
        r = Rect(it.final[0], it.final[1], it.w, it.h)
        if r.x < 0 or r.y < 0 or r.x + r.w > w or r.y + r.h > h:
            bad.append(f"{it.what} is off the panel")
        hit = obstacles.hits(r, it.lamp, station_block(it.group))
        hit += [n for (n, g), o in placed if r.overlaps(o) and not (it.group and g == it.group)]
        if hit:
            bad.append(f"{it.what} meets {sorted(set(hit))}")
        placed.append(((it.what, it.group), r))
    return bad
