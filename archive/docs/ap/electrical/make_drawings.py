#!/usr/bin/env python3
"""Draw the figures for the MRE Electrical SOQ into docs/ap/electrical/drawings/.

Two kinds of figure:

- Plan clips P1 to P5: the staging level copied from the railroad's system schematic
  (docs/ops/schematic-system-draft.svg, never changed), with its own names, masts and
  station brackets taken out and generic labels drawn on top, so a reader who has
  never seen the layout can follow them. Switch numbers are kept, because they are
  what the witness finds on the fascia.
- Wiring drawings D1 to D6: drawn here for the SOQ only.

They are kept apart from the railroad's own schematics and wiring docs on purpose
(owner, 2026-11-14). Facts:

- Reversing sections: RS-1 (the west main, Switch 1 to Switch 23) on an AR10 and RS-2
  (the return loop at the east end) on a PSXX-AR (owner, 2026-11-14 and 2026-11-15).
- Block gaps are in both rails; every section has at least one feeder pair. The bus (or an
  auto-reverser) feeds a DNCT2B's rail input, both rails; each of its two outputs feeds one
  section's feeders; a DNCTA links up to four DNCT2Bs to an LCOS client node (owner, 2026-11-15).
- Turnouts are Peco. Switch machines are MTB MP4 with two SPDT contacts: one feeds the
  panel LED indication, the other powers the frog (stock rails to the two throws, the
  common to the frog) (owner, 2026-11-14).
- Six protected districts on staging and the helix: four PSX-series circuit breakers
  and the two auto-reversers (owner, 2026-11-14).
- Detected sections and their node channels: jmri/layouts/hart/data/block_lengths.csv, read through
  hartlib.railroad.read_block_lengths.

    python3 archive/docs/ap/electrical/make_drawings.py
"""
from __future__ import annotations

import sys
import textwrap
import re
from html import escape
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import railroad  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "drawings"
SCHEMATIC = ROOT / "docs/ops/schematic-system-draft.svg"

RED = "#b03a2e"
BLUE = "#1f5fa8"
GREEN = "#2e7d4f"
AMBER = "#a8650a"
INK = "#121a22"
GREY = "#5f6e7a"
FONT = "font-family=\"'Helvetica Neue',Helvetica,Arial,sans-serif\""


def svg(w: int, h: int, body: str, title: str, desc: str) -> str:
    """A standalone SVG with an accessible title and description."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-labelledby="t d" {FONT}>\n'
        f'<title id="t">{escape(title)}</title><desc id="d">{escape(desc)}</desc>\n'
        f'<rect width="{w}" height="{h}" fill="#fff"/>\n'
        f"{body}\n</svg>\n"
    )


def gap(x: float, y: float, color: str = INK) -> str:
    """Insulated gap in both rails: two short bars across a two-rail track drawn at y-4 / y+4."""
    return (f'<path d="M{x-3},{y-9} L{x-3},{y+9} M{x+3},{y-9} L{x+3},{y+9}" stroke="{color}" stroke-width="2.4"/>')


def rails(x1: float, x2: float, y: float, color: str = INK, w: float = 1.6) -> str:
    return (f'<path d="M{x1},{y-4} L{x2},{y-4} M{x1},{y+4} L{x2},{y+4}" stroke="{color}" stroke-width="{w}"/>')


def box(x, y, w, h, *lines, fill="#e4ebf0", stroke=INK, size=10) -> str:
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="{fill}" stroke="{stroke}"/>']
    n = len(lines)
    for i, t in enumerate(lines):
        ty = y + h / 2 + (i - (n - 1) / 2) * (size + 2) + size / 3
        weight = ' font-weight="bold"' if i == 0 else ""
        out.append(f'<text x="{x + w / 2}" y="{ty:.1f}" font-size="{size}" text-anchor="middle"{weight} fill="{INK}">{escape(t)}</text>')
    return "\n".join(out)


def wire(d: str, color: str = INK, w: float = 1.3, dash: str = "") -> str:
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}"{da}/>'


def label(x, y, t, size=9.5, color=GREY, anchor="start", weight="normal") -> str:
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}" font-weight="{weight}">{escape(t)}</text>')


# ---------------------------------------------------------------- plan clips
# Paths below are in the staging group's own coordinates, as drawn in the schematic.
MAIN = ["M40,158 L208,158 L236,130 L1468,130", "M40,158 L26,172 L26,284 L40,298 L936,298 L1076,158 L1468,158"]
RS1 = ["M236,130 L964,130"]                                            # west main, Switch 1 to Switch 23
RS2 = ["M1356,102 L1580,102 L1594,116 L1594,172 L1580,186 L1356,186"]  # return loop
RS_GAPS = [(236, 130), (964, 130), (1356, 102), (1356, 186)]
SIDING = ["M292,298 L320,270 L432,270"]                                # passing siding, Switch 5 to Switch 7
SIDING_MAIN = ["M292,298 L432,298"]
YARD = ["M712,158 L992,158", "M740,186 L1020,186", "M768,214 L992,214", "M796,242 L964,242",
        "M824,270 L936,270", "M712,158 L824,270", "M992,158 L1076,158", "M936,270 L1048,158"]
LEAD = ["M460,270 L572,270 L684,158 L712,158"]                         # yard lead, Switch 7 to Switch 15
ENGINE = ["M572,158 L656,158", "M544,186 L628,186 L656,158", "M516,214 L600,214 L628,186"]


def track_segments() -> list[tuple[float, float, float, float]]:
    """Straight segments of the staging track in the schematic (paths of track stroke width)."""
    src = SCHEMATIC.read_text()
    segs = []
    for d, w in re.findall(r'<path d="([^"]+)" stroke-width="(1\.4|3\.2)"', src):
        pts = [tuple(map(float, p)) for p in re.findall(r"([\d.]+),([\d.]+)", d)]
        segs += [(*a, *b) for a, b in zip(pts, pts[1:])]
    return segs


def check_overlays() -> None:
    """Every vertex of the hand-placed highlights must lie on the schematic's track, so a
    schematic revision that moves the staging level stops the build instead of drawing the
    highlights beside the track."""
    segs = track_segments()

    def on_track(x: float, y: float) -> bool:
        for x1, y1, x2, y2 in segs:
            dx, dy = x2 - x1, y2 - y1
            t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy or 1)
            if 0 <= t <= 1 and abs(x1 + t * dx - x) < 0.6 and abs(y1 + t * dy - y) < 0.6:
                return True
        return False
    for d in MAIN + RS1 + RS2 + SIDING + SIDING_MAIN + YARD + LEAD + ENGINE:
        for x, y in re.findall(r"([\d.]+),([\d.]+)", d):
            if not on_track(float(x), float(y)):
                raise SystemExit(f"{SCHEMATIC}: highlight point {x},{y} is off the track; update the plan clip paths")
    for x, y in RS_GAPS:
        if not on_track(x, y):
            raise SystemExit(f"{SCHEMATIC}: gap mark {x},{y} is off the track; update RS_GAPS")


def staging_group(k: float = 1.0) -> str:
    """The staging group of the system schematic, with its names, masts and brackets removed.

    Kept: track, end bumpers, and the bold switch numbers (digits, optionally a/b).
    """
    src = SCHEMATIC.read_text()
    m = re.search(r'<g transform="translate\(([-\d.]+),([-\d.]+)\) scale\(([\d.]+)\)"[^>]*>', src)
    if not m:
        raise SystemExit(f"{SCHEMATIC}: no <g transform=translate(..) scale(..)> group; update staging_group()")
    depth, end = 0, None
    for t in re.finditer(r"<g[\s>]|</g>", src[m.start():]):
        depth += -1 if t.group(0) == "</g>" else 1
        if depth == 0:
            end = m.start() + t.start()
            break
    if end is None:
        raise SystemExit(f"{SCHEMATIC}: unbalanced <g> group; update staging_group()")
    inner = src[m.end():end]
    inner = re.sub(r'<g transform="translate\([^)]*\) rotate\([^)]*\)">.*?</g>', "", inner, flags=re.S)  # masts
    inner = re.sub(r"<circle[^>]*/>", "", inner)                                                        # mast lamps
    inner = re.sub(r'<path d="[^"]*Z" stroke-width="1"[^>]*/>', "", inner)                             # milepost marks
    inner = re.sub(r'<path d="[^"]*" stroke-width="0\.9"[^>]*/>', "", inner)                           # mast stems
    inner = re.sub(r'<path d="M[\d.]+,3[2-9]\d[^"]*"[^>]*/>', "", inner)                               # station brackets

    nudge = {"13": -9, "15": 9, "31": -9, "33": 9}       # pairs drawn side by side in the schematic

    def keep(t: re.Match) -> str:
        attrs, body = t.group(1), t.group(2)
        if 'font-weight="bold"' in attrs and re.fullmatch(r"\d{1,2}[ab]?", body):
            x = float(re.search(r'x="([\d.]+)"', attrs).group(1)) + nudge.get(body, 0) * k
            attrs = re.sub(r'x="[\d.]+"', f'x="{x:.1f}"', attrs)
            attrs = attrs.replace('font-size="8"', f'font-size="{13 * k:.1f}"').replace('fill="#000"', f'fill="{GREY}"')
            return f"<text{attrs}>{body}</text>"
        return ""
    inner = re.sub(r"<text([^>]*)>([^<]*)</text>", keep, inner)
    inner = re.sub(r"<(polygon|polyline|rect)[^>]*/>", "", inner)
    if "<text" in inner and not re.search(r">\d{1,2}[ab]?</text>", inner):
        raise SystemExit("staging_group(): unexpected text left in the copy")
    # The plan is printed small: thicken the lines so they hold up on paper.
    inner = (inner.replace('stroke-width="1.4"', f'stroke-width="{2.4 * k:.2f}"')
             .replace('stroke-width="3.2"', f'stroke-width="{4.6 * k:.2f}"')
             .replace('stroke-width="2.4"', f'stroke-width="{2.4 * k:.2f}"'))
    return f'<g fill="none" stroke="{INK}" stroke-linecap="round" stroke-linejoin="round">{inner}</g>'


def tag(u, x, y, text, color=INK, px=15, anchor="middle", weight="bold") -> str:
    """A plan label with a white halo so it reads over track. px is the printed size at full width."""
    t, size = escape(text), px * u
    return (f'<text x="{x}" y="{y}" font-size="{size:.1f}" text-anchor="{anchor}" font-weight="{weight}" '
            f'stroke="#fff" stroke-width="{4 * u:.1f}" stroke-linejoin="round" fill="#fff">{t}</text>'
            f'<text x="{x}" y="{y}" font-size="{size:.1f}" text-anchor="{anchor}" font-weight="{weight}" fill="{color}">{t}</text>')


def hl(u, paths, color, px=9, opacity=0.38) -> str:
    return "".join(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{px * u:.1f}" stroke-linecap="round" '
                   f'stroke-linejoin="round" opacity="{opacity}"/>' for d in paths)


def gaps_at(u, points, color=RED) -> str:
    a, h = 4 * u, 11 * u
    return "".join(f'<path d="M{x-a:.1f},{y-h:.1f} L{x-a:.1f},{y+h:.1f} M{x+a:.1f},{y-h:.1f} L{x+a:.1f},{y+h:.1f}" '
                   f'stroke="{color}" stroke-width="{2.6 * u:.1f}"/>' for x, y in points)


WIDTH = 1000          # every plan clip is drawn 1000 units wide and printed at full text width


def plan(view, layers, legend, title, desc) -> str:
    """A clip of the staging level. layers(u) returns (under, over); u = schematic units per printed unit."""
    vx, vy, vw, vh = view
    u = vw / WIDTH
    under, over = layers(u)
    h_map = WIDTH * vh / vw
    body = [f'<svg x="0" y="0" width="{WIDTH}" height="{h_map:.0f}" viewBox="{vx} {vy} {vw} {vh}">',
            under, staging_group(max(u / 1.64, 0.3)), over, "</svg>"]
    y = h_map + 30
    for color, text in legend:
        if color == "gap":
            body.append(f'<path d="M14,{y-15} L14,{y+3} M23,{y-15} L23,{y+3}" stroke="{RED}" stroke-width="3"/>')
        else:
            body.append(f'<rect x="4" y="{y-14}" width="30" height="15" fill="{color}" opacity="0.5"/>')
        body.append(label(46, y, text, 17, INK))
        y += 32
    return svg(WIDTH, int(y - 8), "\n".join(body), title, desc)


def p1() -> str:
    def layers(u):
        under = (hl(u, MAIN, "#9aa7b1", 6, 0.25) + hl(u, RS1 + RS2, RED) + hl(u, SIDING, BLUE) + hl(u, YARD, GREEN)
                 + hl(u, LEAD + ENGINE, AMBER))
        over = "".join([
            tag(u, 420, 114, "MAIN LINE", INK, 19), tag(u, 680, 334, "MAIN LINE", INK, 19),
            tag(u, 800, 114, "RS-1", RED, 19), tag(u, 1440, 84, "RS-2 return loop", RED, 19),
            tag(u, 372, 256, "Passing siding", BLUE, 17), tag(u, 880, 300, "Yard Y1–Y5", GREEN, 17),
            tag(u, 596, 256, "Yard lead", AMBER, 16, "start"), tag(u, 500, 196, "Engine storage", AMBER, 16, "end"),
            tag(u, 150, 88, "Holding tracks", GREY, 14), tag(u, 1440, 148, "to helix", GREY, 14),
            tag(u, 1170, 116, "Double track", GREY, 14),
            tag(u, 80, 232, "WEST", GREY, 16), tag(u, 1560, 232, "EAST", GREY, 16),
        ]) + gaps_at(u, RS_GAPS)
        return under, over
    return plan((0, 66, 1640, 280), layers, [
        (RED, "RS-1 and RS-2: reversing sections, each on its own auto-reverser (Section 3.3)"),
        (BLUE, "Passing siding beside the main line, Switch 5 to Switch 7 (Section 3.4)"),
        (GREEN, "Yard of five tracks, Y1 to Y5 (Section 3.6)"),
        (AMBER, "Yard lead and the engine storage tracks E1 to E3 (Sections 3.5 and 3.6)"),
        ("gap", "Gaps in both rails at the ends of each reversing section (positions schematic)"),
    ], "Plan P1: the staging level with generic labels",
        "Track diagram of the staging level, west at left. The main line runs as a long loop. Highlighted: two reversing "
        "sections in red, a passing siding in blue, a five-track yard in green, and the yard lead with three engine "
        "storage tracks in amber. Switch numbers are shown as on the layout fascia.")


def p2() -> str:
    def layers(u):
        over = "".join([tag(u, 600, 112, "RS-1 (AR10)", RED, 19), tag(u, 1420, 84, "RS-2 return loop (PSXX-AR)", RED, 19),
                        tag(u, 250, 168, "gap", RED, 14), tag(u, 964, 168, "gap", RED, 14),
                        tag(u, 1316, 110, "gap", RED, 14), tag(u, 1316, 206, "gap", RED, 14),
                        tag(u, 1170, 118, "main line", GREY, 14), tag(u, 1170, 182, "main line", GREY, 14)])
        return hl(u, RS1 + RS2, RED), over + gaps_at(u, RS_GAPS)
    return plan((0, 62, 1640, 170), layers, [
        (RED, "Reversing section: gapped in both rails at both ends, fed through its own auto-reverser"),
        ("gap", "Insulated gaps in both rails (positions schematic; the witness sees the real gaps)"),
    ], "Plan P2: the two reversing sections",
        "Track diagram of the staging level with the two reversing sections highlighted in red: RS-1 on the west main "
        "line between Switch 1 and Switch 23, and RS-2, the return loop at the east end. Each is gapped at both ends.")


def p3() -> str:
    def layers(u):
        over = "".join([tag(u, 372, 258, "Passing siding", BLUE, 22), tag(u, 362, 318, "Main line", INK, 22)])
        return hl(u, SIDING, BLUE, 12) + hl(u, SIDING_MAIN, "#9aa7b1", 8, 0.3), over
    return plan((240, 240, 280, 92), layers, [
        (BLUE, "Passing siding, 144 in long (about 19 cars), joined to the main line at both ends"),
    ], "Plan P3: the passing siding",
        "Close-up of the passing siding beside the main line, between Switch 5 at the west end and Switch 7 at the east "
        "end. A train can hold on the siding while another passes on the main.")


def p4() -> str:
    def layers(u):
        over = "".join([tag(u, 852, 152, "Y1", GREEN, 13), tag(u, 880, 180, "Y2", GREEN, 13), tag(u, 880, 208, "Y3", GREEN, 13),
                        tag(u, 880, 236, "Y4", GREEN, 13), tag(u, 880, 264, "Y5", GREEN, 13),
                        tag(u, 560, 292, "Yard lead", AMBER, 14),
                        tag(u, 700, 320, "Main line", INK, 13), tag(u, 1190, 150, "Main line", INK, 13)])
        return hl(u, YARD, GREEN, 10) + hl(u, LEAD, AMBER, 10), over
    return plan((440, 128, 800, 205), layers, [
        (GREEN, "Yard tracks Y1 to Y5, 100 to 218 in long"),
        (AMBER, "Yard lead: a switcher works the west ladder from here without occupying the main line"),
    ], "Plan P4: the yard and its lead",
        "Close-up of the five-track yard. Its west ladder (Switches 15 to 21) is reached from the yard lead, which leaves "
        "the main line at Switch 7 and does not use it. The east ladder joins the main line at the east end.")


def p5() -> str:
    def layers(u):
        over = "".join([tag(u, 540, 150, "E1", AMBER, 22), tag(u, 512, 180, "E2", AMBER, 22), tag(u, 486, 208, "E3", AMBER, 22),
                        tag(u, 590, 262, "Yard lead", AMBER, 20)])
        return hl(u, ENGINE, AMBER, 12) + hl(u, LEAD, AMBER, 8, 0.18), over
    return plan((450, 136, 290, 140), layers, [
        (AMBER, "Engine storage tracks E1 to E3, each its own detected section, off the yard lead"),
    ], "Plan P5: engine storage",
        "Close-up of three stub-ended engine storage tracks E1 to E3, reached through Switches 9 and 11 from the yard "
        "lead.")


# ---------------------------------------------------------------- wiring drawings
def detected_sections() -> list[dict]:
    """Every detected section on an LCOS node ("Block n-c"), sorted by node and channel.

    Length is the whole detected section: each detector is one block (the hidden yard throat
    blocks are gone, 2026-11-20), at the length JMRI holds (measured, else the plan's).
    """
    out = []
    for b in railroad.read_block_lengths().values():     # this checkout's file, in file order
        m = re.fullmatch(r"Block (\d+)-(\d+)", b.occupancy_sensor)
        if not m:
            continue
        timed = b.source == "timed"             # JMRI's length: the measured one, else the plan's
        inches = b.measured_in if timed else b.plan_in
        out.append({"name": b.user_name.replace("Track ", ""), "node": int(m.group(1)), "ch": int(m.group(2)),
                    "inches": inches, "estimate": not timed})
    out.sort(key=lambda s: (s["node"], s["ch"]))
    return out


def d1() -> str:
    """Propulsion one-line: throttles to command station, booster, protection, district buses, sections."""
    b = []
    b.append(box(20, 40, 150, 50, "DCC throttles", "speed and direction", "per locomotive address", size=9.5))
    b.append(box(220, 40, 170, 50, "Command station", "TCS CS-105", "(also a track output)", size=9.5))
    b.append(box(220, 120, 170, 50, "Booster", "TCS B-106 (a second", "is planned if needed)", size=9.5))
    b.append(wire("M170,65 L220,65", BLUE, 1.8))
    b.append(label(176, 58, "throttle bus", 8.5, BLUE))
    b.append(wire("M305,90 L305,120", BLUE, 1.8))
    b.append(label(312, 108, "DCC control signal", 8.5, BLUE))
    b.append(box(440, 60, 120, 90, "Booster matrix", "terminal strips:", "any output to", "any district", size=9))
    b.append(wire("M390,65 L440,80", INK, 2))
    b.append(wire("M390,145 L440,130", INK, 2))
    rows = [("District A", "PSX-series breaker"), ("District B", "PSX-series breaker"), ("District C", "PSX-series breaker"),
            ("District D", "PSX-series breaker"), ("RS-1", "AR10 auto-reverser"), ("RS-2", "PSXX-AR auto-reverser")]
    for i, (name, dev) in enumerate(rows):
        y = 30 + i * 46
        col = RED if name.startswith("RS") else INK
        b.append(box(610, y, 150, 36, dev, "short protection", size=9, fill="#fbeeee" if col == RED else "#e4ebf0"))
        b.append(wire(f"M560,105 L585,105 L585,{y+18} L610,{y+18}", INK, 1.4))
        b.append(wire(f"M760,{y+14} L840,{y+14}", RED, 1.8))
        b.append(wire(f"M760,{y+22} L840,{y+22}", INK, 1.8))
        b.append(label(846, y + 22, f"{name} bus → sections", 10.5, col, weight="bold" if col == RED else "normal"))
    return svg(1000, 312, "\n".join(b), "D1 · Propulsion one-line: control, power and protection",
               "Block diagram. Throttles feed the command station, which sends the DCC signal to the booster. The command "
               "station and booster feed a booster matrix, which feeds four circuit breakers and two auto-reversers. Each "
               "feeds its own district bus.")


def detection_chain(b, x: float, y: float, cable: str) -> None:
    """DNCTA and LCOS client node boxes at (x, y), the DNCT2B's cable drawn along the path given."""
    b.append(box(x, y, 130, 40, "DNCTA", "up to 4 DNCT2Bs", size=9.5))
    b.append(box(x + 160, y, 130, 40, "LCOS client node", "block inputs", size=9.5))
    b.append(wire(f"M{x + 130},{y + 20} L{x + 160},{y + 20}", BLUE, 1.6))
    b.append(wire(cable, BLUE, 1.4, "4 3"))
    b.append(label(x + 72, y + 64, "network cable", 9, BLUE))


def d2() -> str:
    """Typical detected section: the district bus feeds a DNCT2B's rail input (both rails); each of
    its two outputs feeds one section's feeder pair; the DNCT2B reports through a DNCTA, which links
    up to four DNCT2Bs to an LCOS client node (owner, 2026-11-15)."""
    b = []
    b.append(box(20, 40, 130, 46, "Command station", "and booster (D1)"))
    b.append(box(190, 40, 140, 46, "Protection device", "breaker or auto-reverser"))
    b.append(wire("M150,63 L190,63", INK, 2))
    b.append(wire("M330,56 L560,56", RED, 2.2))
    b.append(wire("M330,70 L560,70", INK, 2.2))
    b.append(label(340, 50, "District bus (both rails)", 9.5, INK))
    # DNCT2B: rail input from the bus, two outputs
    b.append(box(380, 110, 180, 58, "DNCT2B", "rail in: both rails", "output 1 · output 2", size=9.5))
    b.append(wire("M420,56 L420,110", RED, 1.6))
    b.append(wire("M436,70 L436,110", INK, 1.6))
    b.append(f'<circle cx="420" cy="56" r="3" fill="{RED}"/><circle cx="436" cy="70" r="3" fill="{INK}"/>')
    y = 246
    b.append(rails(170, 528, y))
    b.append(rails(532, 880, y))
    b.append(rails(100, 166, y, GREY))
    b.append(gap(168, y))
    b.append(gap(530, y))
    b.append(gap(882, y))
    # output 1 -> section A feeders, output 2 -> section B feeders
    b.append(wire(f"M400,168 L400,190 L330,190 L330,{y - 4}", RED, 1.6))
    b.append(wire(f"M414,168 L414,202 L346,202 L346,{y + 4}", INK, 1.6))
    b.append(wire(f"M560,128 L716,128 L716,{y + 4}", INK, 1.6))   # outer wire to the lower rail, so the pair
    b.append(wire(f"M560,142 L700,142 L700,{y - 4}", RED, 1.6))   # does not cross on its way down
    for x, yy, c in ((330, y - 4, RED), (346, y + 4, INK), (700, y - 4, RED), (716, y + 4, INK)):
        b.append(f'<circle cx="{x}" cy="{yy}" r="3" fill="{c}"/>')
    b.append(label(352, 186, "output 1", 9.5, BLUE))
    b.append(label(724, 124, "output 2", 9.5, BLUE))
    b.append(label(349, y + 28, "Section A: gapped in both rails at both ends", 10, INK, "middle"))
    b.append(label(706, y + 28, "Section B (the board's second output)", 10, INK, "middle"))
    detection_chain(b, 600, 30, "M560,118 L665,118 L665,70")
    rows = detected_sections()
    b.append(label(20, 300, "The DNCT2B senses the current", 9.5, INK))
    b.append(label(20, 313, "on each output, so a train in", 9.5, INK))
    b.append(label(20, 326, "a section shows as occupied.", 9.5, INK))
    b.append(label(20, 360, f"All {len(rows)} detected sections on the staging level and helix are wired this way; Appendix B lists them.", 10, INK, weight="bold"))
    return svg(920, 376, "\n".join(b), "D2 · Propulsion: typical detected section",
               "The district bus, both rails, feeds the rail input of a DNCT2B detector. Each of its two outputs feeds the "
               "feeder pair of one section, gapped in both rails at both ends. The DNCT2B connects to a DNCTA, which links up "
               "to four DNCT2Bs to an LCOS client node.")


def d3() -> str:
    """Powered frog and panel indication through the MTB MP4's two SPDT contacts.

    Straight route: top rail at y=206, bottom rail at y=214. The diverging route leaves
    up and to the right; its lower rail crosses the straight top rail at the frog.
    """
    b = []
    yt, yb = 206, 214
    k = -90 / 220
    def dy(x0, y0, x):
        return y0 + k * (x - x0)
    fx = 300 + (yt - yb) / k
    b.append(wire(f"M60,{yt} L560,{yt}", INK, 1.6))
    b.append(wire(f"M60,{yb} L560,{yb}", INK, 1.6))
    b.append(wire(f"M280,{yt} L520,{dy(280, yt, 520):.1f}", INK, 1.6))
    b.append(wire(f"M300,{yb} L540,{dy(300, yb, 540):.1f}", INK, 1.6))
    gx = 400
    b.append(wire(f"M{fx:.1f},{yt} L{gx},{yt}", RED, 3.2))
    b.append(wire(f"M{fx:.1f},{yt} L{gx},{dy(300, yb, gx):.1f}", RED, 3.2))
    b.append(f'<circle cx="{fx:.1f}" cy="{yt}" r="3.5" fill="{RED}"/>')
    b.append(label(fx - 6, yt - 46, "frog", 10, RED, "end", "bold"))
    b.append(wire(f"M{fx-8:.1f},{yt-42} L{fx:.1f},{yt-4}", RED, 0.8))
    b.append(wire(f"M{gx},{yt-3.5} L{gx},{yt+3.5} M{gx+4},{yt-3.5} L{gx+4},{yt+3.5}", INK, 2.2))
    yd = dy(300, yb, gx)
    b.append(wire(f"M{gx-1.5},{yd-3.5} L{gx+1.5},{yd+3.5} M{gx+2.5},{yd-5} L{gx+5.5},{yd+2}", INK, 2.2))
    b.append(label(gx + 10, yt + 26, "a gap in each frog rail (stock rails continuous)", 9.5))
    b.append(label(62, yb + 24, "stock rails", 9.5))
    b.append(f'<rect x="110" y="300" width="200" height="130" fill="#f3f6f8" stroke="{INK}"/>')
    b.append(label(210, 318, "MTB MP4 switch machine", 10.5, INK, "middle", "bold"))
    b.append(label(124, 340, "SPDT 1: frog power", 10, INK, weight="bold"))
    b.append(f'<circle cx="150" cy="362" r="3" fill="{INK}"/><circle cx="200" cy="352" r="3" fill="{INK}"/><circle cx="200" cy="372" r="3" fill="{INK}"/>')
    b.append(wire("M150,362 L198,353", INK, 1.6))
    b.append(label(124, 366, "C", 9, GREY))
    b.append(wire(f"M200,352 L250,352 L250,{yb}", INK, 1.3))
    b.append(wire(f"M200,372 L270,372 L270,280 L230,280 L230,{yt}", INK, 1.3))
    b.append(f'<circle cx="250" cy="{yb}" r="3" fill="{INK}"/><circle cx="230" cy="{yt}" r="3" fill="{INK}"/>')
    b.append(label(276, 292, "throws to the two stock rails", 9.5))
    b.append(wire(f"M150,362 L140,362 L140,262 L{fx + 25:.1f},262 L{fx + 25:.1f},{yt}", RED, 1.6))
    b.append(f'<circle cx="{fx + 25:.1f}" cy="{yt}" r="3" fill="{RED}"/>')
    b.append(label(150, 256, "common to the frog", 9.5, RED))
    b.append(label(124, 396, "SPDT 2: panel indication", 10, INK, weight="bold"))
    b.append(f'<circle cx="150" cy="410" r="3" fill="{INK}"/><circle cx="200" cy="402" r="3" fill="{INK}"/><circle cx="200" cy="416" r="3" fill="{INK}"/>')
    b.append(wire("M150,410 L198,403", INK, 1.6))
    b.append(box(380, 380, 190, 44, "Indication input", "Universal Translator / node input", size=9))
    b.append(wire("M200,402 L380,396", BLUE, 1.3))
    b.append(wire("M200,416 L380,410", BLUE, 1.3))
    b.append(wire("M150,410 L150,444 L475,444 L475,424", BLUE, 1.3))
    b.append(label(160, 440, "signal common", 9, BLUE))
    b.append(box(380, 316, 190, 44, "Motor drive", "LCOS 12 V output board", size=9))
    b.append(wire("M310,338 L380,338", INK, 1.3, "4 3"))
    b.append(label(20, 472, "The frog always takes the polarity of the stock rail its points lie against, because the same throw of the machine that moves", 9.5, INK))
    b.append(label(20, 486, "the points also moves the SPDT 1 contact. Every staging turnout is wired this way. Indication follows the machine, so it is", 9.5, INK))
    b.append(label(20, 500, "correct whether the turnout is thrown from the fascia, a DCC throttle or the computer (Section 5.1).", 9.5, INK))
    return svg(620, 516, "\n".join(b), "D3 · Turnout: powered frog and position contact (MTB MP4, two SPDT)",
               "A turnout with its frog rails in red, gapped beyond the frog. Contact 1 of the switch machine connects the "
               "frog to one stock rail or the other. Contact 2 reports the position to the indication circuit.")


def d5() -> str:
    """Reversing section on an auto-reverser, with its detection.

    The auto-reverser's output feeds the rail input of a DNCT2B (both rails); the DNCT2B's two
    outputs feed the two detected sections, K-1 and K-2 on RS-2 (owner, 2026-11-15). Both are fed
    by the one PSXX-AR, so they change polarity together.
    """
    b = []
    b.append(wire("M40,66 L700,66", RED, 2.2))
    b.append(wire("M40,80 L700,80", INK, 2.2))
    b.append(label(44, 58, "DCC from the booster matrix (D1)", 9.5, INK))
    b.append(box(255, 100, 250, 44, "Auto-reverser", "NCE AR10 (RS-1) or PSXX-AR (RS-2)", size=10))
    b.append(wire("M360,80 L360,100", INK, 1.4))
    b.append(wire("M400,66 L400,100", RED, 1.4))
    b.append(f'<circle cx="360" cy="80" r="3" fill="{INK}"/><circle cx="400" cy="66" r="3" fill="{RED}"/>')
    b.append(label(512, 122, "output: both rails change polarity together", 9, RED))
    # auto-reverser output -> DNCT2B rail input
    b.append(wire("M350,144 L350,170", RED, 1.6))
    b.append(wire("M410,144 L410,170", INK, 1.6))
    b.append(box(290, 170, 180, 48, "DNCT2B", "rail in: both rails", "output 1 · output 2", size=9))
    y = 270
    b.append(rails(120, 378, y, RED, 2))
    b.append(rails(382, 640, y, RED, 2))
    b.append(rails(40, 116, y, GREY))
    b.append(rails(644, 720, y, GREY))
    b.append(gap(118, y, color=RED))
    b.append(gap(642, y, color=RED))
    b.append(gap(380, y, color=BLUE))
    # output 1 -> section 1, output 2 -> section 2
    b.append(wire(f"M290,186 L210,186 L210,{y - 4}", RED, 1.6))
    b.append(wire(f"M290,202 L226,202 L226,{y + 4}", INK, 1.6))
    b.append(wire(f"M470,186 L550,186 L550,{y - 4}", RED, 1.6))
    b.append(wire(f"M470,202 L534,202 L534,{y + 4}", INK, 1.6))
    for xx, yy, c in ((210, y - 4, RED), (226, y + 4, INK), (550, y - 4, RED), (534, y + 4, INK)):
        b.append(f'<circle cx="{xx}" cy="{yy}" r="3" fill="{c}"/>')
    b.append(label(206, 180, "output 1", 9, BLUE, "end"))
    b.append(label(556, 180, "output 2", 9, BLUE))
    b.append(label(240, y + 28, "section 1 (K-1 on RS-2)", 10, RED, "middle", "bold"))
    b.append(label(520, y + 28, "section 2 (K-2 on RS-2)", 10, RED, "middle", "bold"))
    b.append(label(380, y - 16, "detection gap", 9, BLUE, "middle"))
    b.append(label(380, y + 44, "Reversing section: both rails gapped at both ends (red), longer than the longest train", 9.5, GREY, "middle"))
    b.append(label(60, y - 16, "normal section", 9, GREY))
    b.append(label(650, y - 16, "normal section", 9, GREY))
    b.append(wire("M380,218 L380,236", BLUE, 1.2, "4 3"))
    b.append(label(388, 232, "to DNCTA and LCOS node (as D2)", 9, BLUE))
    b.append(label(20, 350, "The auto-reverser's output feeds the DNCT2B's rail input, both rails. Each of the DNCT2B's two outputs feeds one section,", 9.5, INK))
    b.append(label(20, 364, "so the reversing section is detected like any other. RS-2 is two detected sections, K-1 and K-2, on the two outputs of one", 9.5, INK))
    b.append(label(20, 378, "DNCT2B. Both are fed by the one auto-reverser, so they always change polarity together: for wiring and troubleshooting", 9.5, INK))
    b.append(label(20, 392, "they are one reversing section. RS-1 is wired the same way with one detected section on an NCE AR10.", 9.5, INK))
    b.append(label(20, 410, "When a train's wheels bridge an outer gap with the polarity wrong, the auto-reverser sees the short and swaps its output in", 9.5, INK))
    b.append(label(20, 424, "milliseconds, before any breaker trips, so the train runs through without stopping.", 9.5, INK))
    return svg(740, 440, "\n".join(b), "D5 · Reversing section on an auto-reverser, with detection",
               "DCC feeds an auto-reverser. Its output feeds the rail input of a DNCT2B detector, whose two outputs feed the two "
               "detected sections of one reversing section, gapped in both rails at both outer ends. Both sections change "
               "polarity together.")


def d6() -> str:
    """Computer-to-railroad interface: the owner's LCOS-to-MQTT bridge (external/lcos-bridge)."""
    b = []
    b.append(box(20, 60, 170, 56, "JMRI (Raspberry Pi)", "turnouts, sensors, signals", "MQTT connection", size=9.5))
    b.append(box(250, 60, 150, 56, "MQTT broker", "Mosquitto", "topics track/...", size=9.5))
    b.append(box(460, 50, 200, 76, "Bridge program (PC)", "serial_to_mqtt.py", "serial lines <-> MQTT topics", "my own work", size=9.5, fill="#fdf3e3"))
    b.append(box(460, 190, 200, 76, "Bridge node", "Arduino Nano + nRF24 radio", "bridge firmware", "my own work", size=9.5, fill="#fdf3e3"))
    b.append(box(250, 190, 150, 76, "LCOS field nodes", "Nano + radio + input,", "output, detector boards", size=9.5))
    b.append(box(20, 196, 170, 64, "Railroad", "switch machines, signals,", "block detectors", size=9.5))
    for d in ("M190,88 L250,88", "M400,88 L460,88", "M560,126 L560,190", "M460,228 L400,228", "M250,228 L190,228"):
        b.append(wire(d, BLUE, 1.8))
    b.append(label(200, 82, "TCP/IP", 9))
    b.append(label(408, 82, "TCP/IP", 9))
    b.append(label(568, 160, "USB serial, 250000 baud", 9))
    b.append(label(408, 222, "2.4 GHz", 9))
    b.append(label(196, 222, "wired", 9))
    b.append(label(20, 300, "Turnout commands from JMRI go out as MQTT messages, which the bridge program writes to the bridge node as serial lines; the node sends", 9.5, INK))
    b.append(label(20, 314, "them by radio to the field node beside the switch. Field events (switch position, block occupied or clear, button presses) come back", 9.5, INK))
    b.append(label(20, 328, "the same way and appear in JMRI as sensors and turnout feedback. The shaded parts were designed and written by me and are", 9.5, INK))
    b.append(label(20, 342, "published as open source; LCOS (the radio protocol and boards), JMRI and Mosquitto are existing products.", 9.5, INK))
    return svg(680, 358, "\n".join(b), "D6 · Computer-to-railroad interface: LCOS radio network to JMRI over MQTT",
               "Block diagram: JMRI talks to an MQTT broker, which talks to the bridge program on a PC, which talks over USB "
               "to the bridge node, which talks by radio to the LCOS field nodes wired to the railroad. The bridge program "
               "and bridge node firmware were written by me.")


def spdt(cx: float, cy: float, mirror: bool, set_to: str) -> tuple[str, dict[str, tuple[float, float]]]:
    """One SPDT contact: common C and throws N (upper) and R (lower). Returns svg and terminal points."""
    sx = -1 if mirror else 1
    c, n, r = (cx, cy), (cx + 70 * sx, cy - 30), (cx + 70 * sx, cy + 30)
    tip = n if set_to == "N" else r
    out = [f'<circle cx="{x}" cy="{y}" r="4" fill="#fff" stroke="{INK}" stroke-width="1.6"/>' for x, y in (c, n, r)]
    out.append(wire(f"M{c[0]},{c[1]} L{tip[0] - 5 * sx},{tip[1] + (4 if set_to == 'N' else -4)}", INK, 2.4))
    out.append(label(c[0] - 10 * sx, c[1] + 4, "C", 10, INK, "end" if not mirror else "start", "bold"))
    out.append(label(n[0] + 14 * sx, n[1] - 8, "N", 10, INK, "middle", "bold"))
    out.append(label(r[0], r[1] + 20, "R", 10, INK, "middle", "bold"))
    return "".join(out), {"C": c, "N": n, "R": r}


def d4() -> str:
    """Crossover: track, frogs and gaps (top), and the position indication of its two machines (bottom).

    Each half is a turnout wired as D3 on its own MP4. Contact 1 of each machine powers its
    own frog, so both rails between the frogs are gapped. Contact 2 of the two machines are
    wired in series on the crossover's one N/R input pair (turnout summary; tables.xml
    TWOSENSOR "FB Switch n N/R"): the commons are tied together, N comes from half a's N
    throw, R from half b's R throw, and a's R and b's N go to the input common, so N closes
    only when both halves are normal, R only when both are reverse, and neither when they
    disagree. Drawn from the owner's description and confirmed against the wiring by the
    owner (2026-11-15).
    """
    b = []
    # ---- track: two parallel tracks joined by two turnouts
    ya, yb = 60, 170
    b.append(rails(40, 700, ya))
    b.append(rails(40, 700, yb))
    x1, x2, off = 220, 500, 20
    p1_ = ((x1, ya + 4), (x2, yb - 4))
    p2_ = ((x1 + off, ya + 4), (x2 + off, yb - 4))
    for (sx, sy), (ex, ey) in (p1_, p2_):
        b.append(wire(f"M{sx},{sy} L{ex},{ey}", INK, 1.6))

    def at(p, t):
        (sx, sy), (ex, ey) = p
        return sx + (ex - sx) * t, sy + (ey - sy) * t
    fa, fb = at(p2_, 0.12), at(p1_, 0.88)
    b.append(f'<circle cx="{fa[0]:.1f}" cy="{fa[1]:.1f}" r="5" fill="{RED}"/><circle cx="{fb[0]:.1f}" cy="{fb[1]:.1f}" r="5" fill="{RED}"/>')
    b.append(label(fa[0] + 10, fa[1] + 4, "frog A (half a)", 10, RED, weight="bold"))
    b.append(label(fb[0] - 10, fb[1] + 4, "frog B (half b)", 10, RED, "end", "bold"))
    for p in (p1_, p2_):
        cx, cy = at(p, 0.5)
        b.append(wire(f"M{cx-4},{cy-6} L{cx+4},{cy+6} M{cx+1},{cy-8} L{cx+9},{cy+4}", INK, 2.2))
    mx, my = at(p2_, 0.5)
    b.append(label(mx + 18, my, "gap in both crossover rails, between the frogs", 10, INK, weight="bold"))
    for x in (150, 600):
        b.append(gap(x, ya, color=GREY))
        b.append(gap(x, yb, color=GREY))
    b.append(label(40, ya - 16, "track a: half a is its own detected section", 9.5))
    b.append(label(40, yb + 28, "track b: half b is its own detected section", 9.5))
    b.append(wire("M20,222 L720,222", GREY, 0.8, "3 3"))
    b.append(label(20, 240, "Position indication: contact 2 of each machine, in series on the crossover's one N/R input pair", 10.5, INK, weight="bold"))
    # ---- indication circuit (the two MP4 position contacts)
    dy = 220
    sa, a = spdt(170, 190 + dy, False, "N")
    sb, bb = spdt(570, 190 + dy, True, "N")
    b += [sa, sb]
    b.append(box(15, 248 + dy, 150, 52, "Half a: MP4", "contact 1 to frog A", "contact 2 (shown normal)", size=10))
    b.append(box(575, 248 + dy, 150, 52, "Half b: MP4", "contact 1 to frog B", "contact 2 (shown normal)", size=10))
    top, h = 50 + dy, 40                                     # the three node-input boxes: x, width
    n_box, com_box, r_box = (30, 150), (295, 150), (560, 150)
    b.append(box(n_box[0], top, n_box[1], h, "Node input: N", "FB Switch n N", size=10))
    b.append(box(r_box[0], top, r_box[1], h, "Node input: R", "FB Switch n R", size=10))
    b.append(box(com_box[0], top, com_box[1], h, "Node input common", "", size=10))
    mid, bottom = top + h / 2, top + h
    com_l, com_r = com_box[0] + 5, com_box[0] + com_box[1] - 25      # where the two common leads land
    r_in = r_box[0] + r_box[1] - 50
    b.append(wire(f"M{a['N'][0]},{a['N'][1]} L{a['N'][0]},{mid} L{n_box[0] + n_box[1]},{mid}", BLUE, 2.2))
    b.append(wire(f"M{a['C'][0]},{a['C'][1]} L{a['C'][0]},{330 + dy} L{bb['C'][0]},{330 + dy} L{bb['C'][0]},{bb['C'][1]}", BLUE, 2.2))
    b.append(wire(f"M{bb['N'][0]},{bb['N'][1]} L{bb['N'][0]},{bottom + 30} L{com_r},{bottom + 30} L{com_r},{bottom}", BLUE, 2.2))
    b.append(wire(f"M{a['R'][0]},{a['R'][1]} L{com_l},{a['R'][1]} L{com_l},{bottom}", INK, 1.5))
    x, y = bb['C'][0], bb['R'][1]
    b.append(wire(f"M{bb['R'][0]},{y} L{x - 6},{y} A6,6 0 0 1 {x + 6},{y} L{r_in},{y} L{r_in},{bottom}", INK, 1.5))
    b.append(label(370, 346 + dy, "commons of the two contacts tied together", 9.5, INK, "middle"))
    # ---- right column: truth table and notes
    X, H = 745, 580
    b.append(label(X, 40, "What the panel shows", 12, INK, weight="bold"))
    rows = [("Half a", "Half b", "N", "R", "Panel"), ("Normal", "Normal", "closed", "open", "Normal"),
            ("Reverse", "Reverse", "open", "closed", "Reverse"), ("Normal", "Reverse", "open", "open", "Inconsistent"),
            ("Reverse", "Normal", "open", "open", "Inconsistent")]
    for i, row in enumerate(rows):
        for xo, t in zip((0, 52, 104, 146, 184), row):
            b.append(label(X + xo, 62 + i * 18, t, 10.5, INK, weight="bold" if i == 0 else "normal"))
    notes = [
        ("Frogs", "Each half is wired as D3. Contact 1 of each machine powers its own frog, so the rails between the frogs are gapped."),
        ("Detection", "Each half is its own detected section (grey gaps)."),
        ("Indication", "Both machines throw together. Their contact 2s are in series: N closes only when both halves are normal, R only when both are reverse (blue: both normal). If they disagree, neither closes and JMRI shows Inconsistent."),
        ("Mixed", "Half a normal and half b reverse joins N to R with no common. That is expected, not a fault."),
        ("Where", "Switches 7, 23 (23a, 23b) and 35 (35a, 35b)."),
    ]
    y = 170
    for head, text in notes:
        b.append(label(X, y, head, 11.5, INK, weight="bold"))
        y += 16
        for line in textwrap.wrap(text, 38):
            b.append(label(X, y, line, 11, INK))
            y += 14.5
        y += 7
    if y > H:
        raise SystemExit(f"D4 notes run to y={y:.0f}, past the drawing's height {H}; shorten them or enlarge D4")
    return svg(1000, H, "\n".join(b), "D4 · Crossover: frogs, gaps and position indication",
               "Top: two parallel tracks joined by a crossover of two turnouts, each frog powered by its own machine, with both "
               "crossover rails gapped between the frogs. Bottom: the position contacts of the two machines wired in series to "
               "one normal and one reverse input, so the panel shows a position only when both halves agree.")


FIGURES = [("P1-staging-plan", p1), ("P2-reversing-sections", p2), ("P3-passing-siding", p3), ("P4-yard", p4),
           ("P5-engine-storage", p5), ("D1-propulsion-one-line", d1), ("D2-propulsion-sections", d2),
           ("D3-turnout-frog-indication", d3), ("D4-crossover", d4), ("D5-reversing-section", d5),
           ("D6-computer-interface", d6)]


def main() -> None:
    check_overlays()
    OUT.mkdir(exist_ok=True)
    for retired in ("D1-staging-reversing-sections.svg", "D7-crossover-indication.svg"):
        (OUT / retired).unlink(missing_ok=True)
    for name, fn in FIGURES:
        (OUT / f"{name}.svg").write_text(fn())
        print(OUT / f"{name}.svg")


if __name__ == "__main__":
    main()
