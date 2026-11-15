#!/usr/bin/env python3
"""Draw the MMR Electrical SOQ drawings (D1 to D5) into docs/ap/electrical/drawings/.

These drawings are for the NMRA Achievement Program package only. They copy from,
but never change, the railroad's own schematic (docs/ops/schematic-system-draft.svg)
and wiring decks (docs/wiring/). Facts:

- Reversing sections: Track Main West and the K-1 / K-2 loop at Princess, each on an
  auto-reverser (owner, 2026-11-14).
- Block gaps are in both rails; every section has at least one feeder (owner, 2026-11-14).
- Main West is on an AR-10; turnouts are Peco (owner, 2026-11-14).
- Switch machines are MTB MP4 with two SPDT contacts: one feeds the panel LED
  indication, the other powers the frog (stock rails to the two throws, the common
  to the frog) (owner, 2026-11-14).
- Both feeders of a section pass through one channel of its DNCT2B current sensor;
  each DNCT2B has two channels and serves two sections (owner, 2026-11-14).
- Detected sections and their node channels: jmri/layouts/hart/data/block_lengths.csv
  ("Block n-c" = node Cn, channel c).

    python3 docs/ap/electrical/make_drawings.py
"""
from __future__ import annotations

import csv
import re
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "drawings"
SCHEMATIC = ROOT / "docs/ops/schematic-system-draft.svg"
BLOCKS = ROOT / "jmri/layouts/hart/data/block_lengths.csv"

RED = "#c0392b"
BLUE = "#1f5fa8"
INK = "#121a22"
GREY = "#6b7a86"
FONT = "font-family=\"'Helvetica Neue',Helvetica,Arial,sans-serif\""


def svg(w: int, h: int, body: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" {FONT}>\n'
        f'<rect width="{w}" height="{h}" fill="#fff"/>\n'
        f'<text x="12" y="20" font-size="13" font-weight="bold" fill="{INK}">{escape(title)}</text>\n'
        f"{body}\n</svg>\n"
    )


def gap(x: float, y: float, vertical: bool = False, color: str = INK) -> str:
    """Insulated gap in both rails: two short bars across a two-rail track drawn at y-4 / y+4."""
    if vertical:
        return (f'<path d="M{x-7},{y-3} L{x+7},{y-3} M{x-7},{y+3} L{x+7},{y+3}" stroke="{color}" stroke-width="2.4"/>')
    return (f'<path d="M{x-3},{y-9} L{x-3},{y+9} M{x+3},{y-9} L{x+3},{y+9}" stroke="{color}" stroke-width="2.4"/>')


def rails(x1: float, x2: float, y: float, color: str = INK, w: float = 1.6) -> str:
    return (f'<path d="M{x1},{y-4} L{x2},{y-4} M{x1},{y+4} L{x2},{y+4}" stroke="{color}" stroke-width="{w}"/>')


def box(x, y, w, h, *lines, fill="#e4ebf0", stroke=INK, size=10) -> str:
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}"/>']
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


# ---------------------------------------------------------------- D1
def d1() -> str:
    """Staging level from the REV schematic, with reversing sections and passing siding marked."""
    src = SCHEMATIC.read_text()
    m = re.search(r'<g transform="translate\(([-\d.]+),([-\d.]+)\) scale\(([\d.]+)\)"', src)
    if not m:
        raise SystemExit(f"{SCHEMATIC}: no <g transform=translate(..) scale(..)> group; update d1()")
    tx, ty, sc = map(float, m.groups())
    depth, i = 0, m.start()
    for t in re.finditer(r"<g[\s>]|</g>", src[m.start():]):
        depth += -1 if t.group(0) == "</g>" else 1
        if depth == 0:
            i = m.start() + t.end()
            break
    if depth != 0:
        raise SystemExit(f"{SCHEMATIC}: unbalanced <g> group; update d1()")
    group = src[m.start():i]
    # Overlays in the group's own coordinates (paths as drawn in the schematic).
    reverse = ["M236,130 L964,130",                                   # Main West, Switch 1 to Switch 23
               "M1356,102 L1580,102 L1594,116 L1594,172 L1580,186 L1356,186"]  # K-1, loop end, K-2
    siding = ["M964,130 L1300,130", "M1076,158 L1272,158"]           # West Ext and East Lead
    ov = [f'<g transform="translate({tx},{ty}) scale({sc})" fill="none" stroke-linecap="round">']
    for d in reverse:
        ov.append(f'<path d="{d}" stroke="{RED}" stroke-width="9" opacity="0.45"/>')
    for d in siding:
        ov.append(f'<path d="{d}" stroke="{BLUE}" stroke-width="9" opacity="0.35"/>')
    for x, y in [(236, 130), (964, 130), (1356, 102), (1356, 186)]:
        ov.append(f'<path d="M{x-5},{y-14} L{x-5},{y+14} M{x+5},{y-14} L{x+5},{y+14}" stroke="{RED}" stroke-width="3.2"/>')
    ov.append("</g>")
    # Keep only the staging band (group y 0..345) of the sheet.
    y0, y1 = ty - 10, ty + 345 * sc
    legend_y = 30 + (y1 - y0) + 26                  # outer-SVG coordinates, just below the map
    body = (
        f'<svg x="0" y="30" width="1056" height="{y1 - y0:.0f}" viewBox="0 {y0:.1f} 1056 {y1 - y0:.1f}">'
        f"{group}{''.join(ov)}</svg>\n"
        f'<g transform="translate(40,{legend_y:.0f})">'
        f'<rect x="0" y="-9" width="26" height="10" fill="{RED}" opacity="0.45"/>'
        + label(34, 0, "Reversing section on an auto-reverser: Main West (Switch 1 to Switch 23), and the K-1 / K-2 loop at Princess", 10, INK)
        + f'<path d="M3,12 L3,30 M11,12 L11,30" stroke="{RED}" stroke-width="2.4"/>'
        + label(34, 25, "Gaps in both rails at each end of a reversing section (positions approximate on this schematic)", 10, INK)
        + f'<rect x="0" y="36" width="26" height="10" fill="{BLUE}" opacity="0.35"/>'
        + label(34, 45, "Mainline passing siding: West Ext beside East Lead, East End (Switches 23, 33) to Princess (Switch 35)", 10, INK)
        + label(34, 63, "Every other detected section is also gapped in both rails at both ends; see D2. Base drawing: system schematic REV 7, staging level, not to scale.", 9.5)
        + "</g>"
    )
    return svg(1056, int(legend_y + 76), body, "D1 · Staging level: reversing sections and passing siding")


# ---------------------------------------------------------------- D2
def blocks() -> tuple[list[tuple[str, str, str]], list[str]]:
    """Detected sections on a node ("Block n-c"), and sections not yet on a node.

    Rows flagged "stub" are panel sub-blocks sharing another section's detector; they
    are not separate electrical sections and are left out.
    """
    rows, unnoded = [], []
    with BLOCKS.open() as f:
        for r in csv.DictReader(f):
            name = r["user_name"].replace("Track ", "")
            m = re.match(r"Block (\d+)-(\d+)$", r["occupancy_sensor"])
            if m:
                rows.append((name, f"C{m.group(1)}", m.group(2)))
            elif r["flag"] != "stub":
                unnoded.append(name)
    rows.sort(key=lambda t: (int(t[1][1:]), int(t[2])))
    return rows, unnoded


def d2() -> str:
    """Typical detected section: district bus, feeder pair through one DNCT2B channel, gaps in both rails."""
    b = []
    b.append(box(20, 50, 120, 46, "Command station", "CS-105 + boosters"))
    b.append(box(190, 50, 130, 46, "Circuit breaker", "PSX / PSXX, per district"))
    b.append(wire("M140,73 L190,73", INK, 2))
    b.append(label(145, 66, "DCC"))
    # district bus
    b.append(wire("M320,66 L860,66", RED, 2.2))
    b.append(wire("M320,80 L860,80", INK, 2.2))
    b.append(label(330, 60, "District bus (two wires, one per rail)", 9.5, INK))
    # one section
    y = 200
    b.append(rails(360, 820, y))
    b.append(gap(380, y))
    b.append(gap(800, y))
    b.append(label(590, y + 26, "Detected section (one block): both rails gapped at both ends", 10, INK, "middle"))
    b.append(rails(300, 376, y, GREY))
    b.append(rails(804, 880, y, GREY))
    b.append(label(300, y - 14, "next section", 9, GREY))
    b.append(label(820, y - 14, "next section", 9, GREY))
    # feeders: both wires of the pair pass through one DNCT2B channel
    b.append(wire(f"M560,66 L560,{y-4}", RED, 1.6))
    b.append(wire(f"M580,80 L580,{y+4}", INK, 1.6))
    b.append(f'<circle cx="560" cy="{y-4}" r="3" fill="{RED}"/><circle cx="580" cy="{y+4}" r="3" fill="{INK}"/>')
    b.append(f'<ellipse cx="570" cy="128" rx="20" ry="9" fill="none" stroke="{BLUE}" stroke-width="2.2"/>')
    b.append(label(596, 124, "channel 1", 9, BLUE))
    # the board's second channel serves the next section the same way
    b.append(wire(f"M836,66 L836,{y-4}", GREY, 1.3))
    b.append(wire(f"M856,80 L856,{y+4}", GREY, 1.3))
    b.append(f'<ellipse cx="846" cy="128" rx="20" ry="9" fill="none" stroke="{BLUE}" stroke-width="2.2" opacity="0.6"/>')
    b.append(label(870, 132, "channel 2", 9, BLUE))
    b.append(box(400, 112, 110, 32, "DNCT2B", "two-channel sensor", size=9))
    b.append(wire("M510,128 L550,128", BLUE, 1.4))
    b.append(wire("M455,112 L455,100 L846,100 L846,119", BLUE, 1.2, "4 3"))
    b.append(box(400, 240, 140, 34, "LCOS node Cn", "block input, channel c", size=9))
    b.append(wire("M450,144 L450,240", BLUE, 1.4, "4 3"))
    b.append(label(444, 172, "occupied / clear", 9, BLUE, "end"))
    b.append(label(600, 150, "Both feeders of the section pass through the", 9.5, INK))
    b.append(label(600, 163, "same sensor channel; each section has at least", 9.5, INK))
    b.append(label(600, 176, "one feeder pair. One DNCT2B serves two sections.", 9.5, INK))
    # table
    rows, unnoded = blocks()
    b.append(label(20, 306, f"Detected sections on LCOS nodes: {len(rows)}, each wired as above.", 10.5, INK, weight="bold"))
    if unnoded:
        names = " and ".join(unnoded) if len(unnoded) < 3 else ", ".join(unnoded)
        b.append(label(20, 322, f"{names}: own sections, wired the same way but not yet on a node.", 9.5))
    cols, per = 3, -(-len(rows) // 3)
    for i, (name, node, ch) in enumerate(rows):
        c, r = divmod(i, per)
        x, yy = 20 + c * 300, 344 + r * 14.5
        b.append(f'<text x="{x}" y="{yy:.1f}" font-size="9.5" fill="{INK}">{escape(name)}</text>')
        b.append(f'<text x="{x + 190}" y="{yy:.1f}" font-size="9.5" fill="{GREY}">{node} · ch {ch}</text>')
    h = int(344 + per * 14.5 + 20)
    return svg(920, h, "\n".join(b), "D2 · Propulsion: typical detected section, and every section on its detector")


# ---------------------------------------------------------------- D3
def d3() -> str:
    """Powered frog and panel indication through the MTB MP4's two SPDT contacts.

    Straight route: top rail at y=206, bottom rail at y=214. The diverging route leaves
    up and to the right; its lower rail crosses the straight top rail at the frog.
    """
    b = []
    yt, yb = 206, 214
    k = -90 / 220                                   # slope of the diverging route
    def dy(x0, y0, x):                              # y on a diverging rail through (x0, y0)
        return y0 + k * (x - x0)
    fx = 300 + (yt - yb) / k + 0                    # lower diverging rail from (300, 214) meets y=206
    b.append(wire(f"M60,{yt} L560,{yt}", INK, 1.6))                     # straight top rail
    b.append(wire(f"M60,{yb} L560,{yb}", INK, 1.6))                     # straight bottom rail (stock)
    b.append(wire(f"M280,{yt} L520,{dy(280, yt, 520):.1f}", INK, 1.6))  # diverging outer rail (stock)
    b.append(wire(f"M300,{yb} L540,{dy(300, yb, 540):.1f}", INK, 1.6))  # diverging inner rail
    # frog rails: from the crossing to the gaps, in red
    gx = 400
    b.append(wire(f"M{fx:.1f},{yt} L{gx},{yt}", RED, 3.2))
    b.append(wire(f"M{fx:.1f},{yt} L{gx},{dy(300, yb, gx):.1f}", RED, 3.2))
    b.append(f'<circle cx="{fx:.1f}" cy="{yt}" r="3.5" fill="{RED}"/>')
    b.append(label(fx - 6, yt - 46, "frog", 10, RED, "end", "bold"))
    b.append(wire(f"M{fx-8:.1f},{yt-42} L{fx:.1f},{yt-4}", RED, 0.8))
    # one gap in each frog rail, the stock rails untouched
    b.append(wire(f"M{gx},{yt-3.5} L{gx},{yt+3.5} M{gx+4},{yt-3.5} L{gx+4},{yt+3.5}", INK, 2.2))
    yd = dy(300, yb, gx)
    b.append(wire(f"M{gx-1.5},{yd-3.5} L{gx+1.5},{yd+3.5} M{gx+2.5},{yd-5} L{gx+5.5},{yd+2}", INK, 2.2))
    b.append(label(gx + 10, yt + 26, "a gap in each frog rail (stock rails continuous)", 9.5))
    b.append(label(62, yb + 24, "stock rails", 9.5))
    # MP4
    b.append(f'<rect x="110" y="300" width="200" height="130" fill="#f3f6f8" stroke="{INK}"/>')
    b.append(label(210, 318, "MTB MP4 switch machine", 10.5, INK, "middle", "bold"))
    # SPDT 1 (frog)
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
    # SPDT 2 (indication)
    b.append(label(124, 396, "SPDT 2: panel indication", 10, INK, weight="bold"))
    b.append(f'<circle cx="150" cy="410" r="3" fill="{INK}"/><circle cx="200" cy="402" r="3" fill="{INK}"/><circle cx="200" cy="416" r="3" fill="{INK}"/>')
    b.append(wire("M150,410 L198,403", INK, 1.6))
    b.append(box(380, 380, 190, 44, "Panel indication", "Touch Toggle LED: normal / reverse", size=9))
    b.append(wire("M200,402 L380,396", BLUE, 1.3))
    b.append(wire("M200,416 L380,410", BLUE, 1.3))
    b.append(wire("M150,410 L150,444 L475,444 L475,424", BLUE, 1.3))
    b.append(label(160, 440, "LED supply to the common", 9, BLUE))
    b.append(box(380, 316, 190, 44, "Motor drive", "LCOS 12 V output", size=9))
    b.append(wire("M310,338 L380,338", INK, 1.3, "4 3"))
    b.append(label(20, 472, "The frog always takes the polarity of the stock rail its points lie against, because the same throw of the machine that moves", 9.5, INK))
    b.append(label(20, 486, "the points also moves the SPDT 1 contact. Every staging turnout is wired this way. Indication follows the machine, so it is", 9.5, INK))
    b.append(label(20, 500, "correct whether the turnout is thrown from the panel, a DCC throttle or the computer.", 9.5, INK))
    return svg(620, 516, "\n".join(b), "D3 · Turnout: powered frog and panel indication (MTB MP4, two SPDT)")


# ---------------------------------------------------------------- D4
def d4() -> str:
    """Crossover: two turnouts joined by a pair of parallel rails, gapped between the frogs."""
    b = []
    ya, yb = 110, 230
    b.append(rails(40, 700, ya))
    b.append(rails(40, 700, yb))
    # crossover rails: parallel, from the lower rail of track a to the upper rail of track b
    x1, x2 = 220, 500
    off = 20                                        # horizontal offset gives two parallel rails
    p1 = ((x1, ya + 4), (x2, yb - 4))
    p2 = ((x1 + off, ya + 4), (x2 + off, yb - 4))
    for (sx, sy), (ex, ey) in (p1, p2):
        b.append(wire(f"M{sx},{sy} L{ex},{ey}", INK, 1.6))
    def at(p, t):
        (sx, sy), (ex, ey) = p
        return sx + (ex - sx) * t, sy + (ey - sy) * t
    fa, fb = at(p2, 0.12), at(p1, 0.88)
    b.append(f'<circle cx="{fa[0]:.1f}" cy="{fa[1]:.1f}" r="5" fill="{RED}"/><circle cx="{fb[0]:.1f}" cy="{fb[1]:.1f}" r="5" fill="{RED}"/>')
    b.append(label(fa[0] + 10, fa[1] + 4, "frog A", 9.5, RED, weight="bold"))
    b.append(label(fb[0] - 10, fb[1] + 4, "frog B", 9.5, RED, "end", "bold"))
    # a gap in each crossover rail at mid-length
    for p in (p1, p2):
        cx, cy = at(p, 0.5)
        b.append(wire(f"M{cx-4},{cy-6} L{cx+4},{cy+6} M{cx+1},{cy-8} L{cx+9},{cy+4}", INK, 2.2))
    mx, my = at(p2, 0.5)
    b.append(label(mx + 18, my, "gap in both crossover rails, between the frogs", 10, INK, weight="bold"))
    for x in (150, 600):
        b.append(gap(x, ya, color=GREY))
        b.append(gap(x, yb, color=GREY))
    b.append(label(40, ya - 18, "section a (for example OS Switch 23a)", 9.5))
    b.append(label(40, yb + 30, "section b (for example OS Switch 23b)", 9.5))
    b.append(box(40, 280, 200, 40, "MP4 half a", "SPDT 1 to frog A, SPDT 2 to panel", size=9))
    b.append(box(480, 280, 200, 40, "MP4 half b", "SPDT 1 to frog B, SPDT 2 to panel", size=9))
    b.append(label(20, 350, "Each half is a turnout wired as D3, on its own machine; both machines are thrown together. Because each frog takes its own", 9.5, INK))
    b.append(label(20, 364, "polarity, the crossover rails are gapped between the frogs. Each half is its own detected section, gapped in both rails (grey).", 9.5, INK))
    b.append(label(20, 378, "Built at Switches 23 (23a / 23b) and 35 (35a / 35b) in staging, and at Switch 7 (7 / 7b).", 9.5, INK))
    return svg(720, 394, "\n".join(b), "D4 · Crossover: two powered-frog turnouts, gapped between the frogs")


# ---------------------------------------------------------------- D5
def d5() -> str:
    """Reversing section on an auto-reverser."""
    b = []
    b.append(wire("M40,66 L700,66", RED, 2.2))
    b.append(wire("M40,80 L700,80", INK, 2.2))
    b.append(label(44, 58, "District bus from its circuit breaker", 9.5, INK))
    b.append(box(260, 110, 240, 46, "Auto-reverser", "AR-10 (Main West), PSX-AR (K-1 / K-2)", size=10))
    b.append(wire("M360,80 L360,110", INK, 1.4))
    b.append(wire("M400,66 L400,110", RED, 1.4))
    y = 250
    b.append(rails(160, 600, y, RED, 2))
    b.append(rails(60, 156, y, GREY))
    b.append(rails(604, 700, y, GREY))
    b.append(gap(158, y, color=RED))
    b.append(gap(602, y, color=RED))
    b.append(label(380, y + 28, "Reversing section: both rails gapped at both ends", 10, RED, "middle", "bold"))
    b.append(label(380, y + 42, "(longer than the longest train)", 9.5, GREY, "middle"))
    b.append(wire(f"M350,156 L350,{y-4}", RED, 1.4))
    b.append(wire(f"M410,156 L410,{y+4}", INK, 1.4))
    b.append(f'<circle cx="350" cy="{y-4}" r="3" fill="{RED}"/><circle cx="410" cy="{y+4}" r="3" fill="{INK}"/>')
    b.append(f'<ellipse cx="380" cy="200" rx="42" ry="9" fill="none" stroke="{BLUE}" stroke-width="2"/>')
    b.append(label(430, 204, "both feeders through one DNCT2B channel, as D2", 9.5, BLUE))
    b.append(label(60, y - 16, "normal section", 9, GREY))
    b.append(label(620, y - 16, "normal section", 9, GREY))
    b.append(label(20, 320, "When a train's wheels bridge a gap with the polarity wrong, the short is seen by the auto-reverser, which swaps the section's two", 9.5, INK))
    b.append(label(20, 334, "outputs in milliseconds, faster than the district's breaker trips. Two sections are wired this way: Main West, and the K-1 / K-2 loop", 9.5, INK))
    b.append(label(20, 348, "at Princess (D1).", 9.5, INK))
    return svg(720, 364, "\n".join(b), "D5 · Reversing section on an auto-reverser")


# ---------------------------------------------------------------- D6
def d6() -> str:
    """Computer-to-railroad interface: the owner's LCOS-to-MQTT bridge (external/lcos-bridge)."""
    b = []
    b.append(box(20, 60, 170, 56, "JMRI (Raspberry Pi)", "turnouts, sensors, masts", "MQTT connection", size=9.5))
    b.append(box(250, 60, 150, 56, "MQTT broker", "Mosquitto on the Pi", "topics track/...", size=9.5))
    b.append(box(460, 50, 200, 76, "Bridge program (PC)", "serial_to_mqtt.py", "serial lines <-> MQTT topics", "written for HART", size=9.5))
    b.append(box(460, 190, 200, 76, "Bridge node", "Arduino Nano + nRF24 radio", "LCOS bridge firmware", "written for HART", size=9.5))
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
    b.append(label(20, 328, "the same way and appear in JMRI as sensors and turnout feedback. Both the firmware and the bridge program were written for this", 9.5, INK))
    b.append(label(20, 342, "railroad and are published as open source; LCOS (the radio protocol), JMRI and Mosquitto are existing software.", 9.5, INK))
    return svg(680, 358, "\n".join(b), "D6 · Computer-to-railroad interface: LCOS radio network to JMRI over MQTT")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, fn in [("D1-staging-reversing-sections", d1), ("D2-propulsion-sections", d2),
                     ("D3-turnout-frog-indication", d3), ("D4-crossover", d4), ("D5-reversing-section", d5), ("D6-computer-interface", d6)]:
        (OUT / f"{name}.svg").write_text(fn())
        print(OUT / f"{name}.svg")


if __name__ == "__main__":
    main()
