#!/usr/bin/env python3
"""Draw the MMR Electrical SOQ drawings (D1 to D5) into docs/ap/electrical/drawings/.

These drawings are for the NMRA Achievement Program package only. They copy from,
but never change, the railroad's own schematic (docs/ops/schematic-system-draft.svg)
and wiring decks (docs/wiring/). Facts:

- Reversing sections: Track Main West and the K-1 / K-2 loop at Princess, each on an
  auto-reverser (owner, 2026-11-14).
- Block gaps are in both rails (owner, 2026-11-14).
- Switch machines are MTB MP4 with two SPDT contacts: one feeds the panel LED
  indication, the other powers the frog (stock rails to the two throws, the common
  to the frog) (owner, 2026-11-14).
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
    m = re.search(r'<g transform="translate\(([\d.]+),([\d.]+)\) scale\(([\d.]+)\)"', src)
    tx, ty, sc = map(float, m.groups())
    depth, i = 0, m.start()
    for t in re.finditer(r"<g[\s>]|</g>", src[m.start():]):
        depth += -1 if t.group(0) == "</g>" else 1
        if depth == 0:
            i = m.start() + t.end()
            break
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
    # Keep only the staging band (group y 0..335) of the sheet.
    y0, y1 = ty - 10, ty + 335 * sc
    legend_y = y1 + 14
    body = (
        f'<svg x="0" y="30" width="1056" height="{y1 - y0:.0f}" viewBox="0 {y0:.1f} 1056 {y1 - y0:.1f}">'
        f"{group}{''.join(ov)}</svg>\n"
        f'<g transform="translate(40,{legend_y + 30:.0f})">'
        f'<rect x="0" y="-9" width="26" height="10" fill="{RED}" opacity="0.45"/>'
        + label(34, 0, "Reversing section on an auto-reverser: Main West (Switch 1 to Switch 23), and the K-1 / K-2 loop at Princess", 10, INK)
        + f'<path d="M3,12 L3,30 M11,12 L11,30" stroke="{RED}" stroke-width="2.4"/>'
        + label(34, 25, "Gaps in both rails at each end of a reversing section (positions approximate on this schematic)", 10, INK)
        + f'<rect x="0" y="36" width="26" height="10" fill="{BLUE}" opacity="0.35"/>'
        + label(34, 45, "Mainline passing siding: West Ext beside East Lead, East End (Switches 23, 33) to Princess (Switch 35)", 10, INK)
        + label(34, 63, "Every other detected section is also gapped in both rails at both ends; see D2. Base drawing: system schematic REV 7, staging level, not to scale.", 9.5)
        + "</g>"
    )
    return svg(1056, int(legend_y + 110), body, "D1 · Staging level: reversing sections and passing siding")


# ---------------------------------------------------------------- D2
def blocks() -> list[tuple[str, str, str]]:
    rows = []
    with BLOCKS.open() as f:
        for r in csv.DictReader(f):
            m = re.match(r"Block (\d+)-(\d+)$", r["occupancy_sensor"])
            if m:
                rows.append((r["user_name"].replace("Track ", ""), f"C{m.group(1)}", m.group(2)))
    rows.sort(key=lambda t: (int(t[1][1:]), int(t[2])))
    return rows


def d2() -> str:
    """Typical detected section: district bus, feeder through a current transformer, gaps in both rails."""
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
    # feeders
    b.append(wire(f"M560,66 L560,150 L560,{y-4}", RED, 1.6))
    b.append(wire(f"M620,80 L620,{y+4}", INK, 1.6))
    b.append(f'<circle cx="560" cy="{y-4}" r="3" fill="{RED}"/><circle cx="620" cy="{y+4}" r="3" fill="{INK}"/>')
    b.append(f'<circle cx="560" cy="128" r="11" fill="none" stroke="{BLUE}" stroke-width="2"/>')
    b.append(box(430, 112, 100, 32, "DNCT2B", "current transformer", size=9))
    b.append(wire("M530,128 L549,128", BLUE, 1.4))
    b.append(box(430, 240, 140, 34, "LCOS node Cn", "block input, channel c", size=9))
    b.append(wire("M480,144 L480,240", BLUE, 1.4, "4 3"))
    b.append(label(474, 172, "occupied / clear", 9, BLUE, "end"))
    b.append(label(632, 120, "Feeder pair from the bus to the section;", 9.5, INK))
    b.append(label(632, 133, "one feeder passes through the detector", 9.5, INK))
    b.append(label(632, 146, "(one turn through the transformer).", 9.5, INK))
    # table
    rows = blocks()
    b.append(label(20, 306, f"Detected sections on the staging level and helix: {len(rows)} on LCOS nodes, each wired as above.", 10.5, INK, weight="bold"))
    b.append(label(20, 322, "The McKees Rocks and McKeesport stubs have their own sections, wired the same way but not yet on a node.", 9.5))
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
    """Powered frog and panel indication through the MTB MP4's two SPDT contacts."""
    b = []
    # turnout: points left, diverging up-right
    y = 210
    b.append(rails(60, 560, y))                       # straight route
    b.append(wire(f"M300,{y-4} L520,{y-96}", INK, 1.6))
    b.append(wire(f"M300,{y+4} L528,{y-88}", INK, 1.6))
    b.append(label(62, y + 24, "stock rails", 9.5))
    # frog
    fx, fy = 420, y - 40
    b.append(f'<path d="M{fx-22},{fy+14} L{fx},{fy} L{fx+40},{fy+36} M{fx},{fy} L{fx+44},{fy-18}" stroke="{RED}" stroke-width="3" fill="none"/>')
    b.append(label(fx + 30, fy - 24, "frog (insulated, powered)", 10, RED, weight="bold"))
    for gx, gy in [(470, y - 4), (470, y + 4)]:
        pass
    # gaps in both frog rails beyond the frog
    b.append(f'<path d="M478,{y-12} L478,{y+12} M484,{y-12} L484,{y+12}" stroke="{INK}" stroke-width="2.4"/>')
    b.append(f'<path d="M488,{y-74} L500,{y-86} M494,{y-68} L506,{y-80}" stroke="{INK}" stroke-width="2.4"/>')
    b.append(label(490, y + 26, "gaps in both frog rails", 9.5))
    # MP4
    b.append(f'<rect x="110" y="300" width="200" height="124" fill="#f3f6f8" stroke="{INK}"/>')
    b.append(label(210, 318, "MTB MP4 switch machine", 10.5, INK, "middle", "bold"))
    # SPDT 1 (frog)
    b.append(label(124, 340, "SPDT 1: frog power", 10, INK, weight="bold"))
    b.append(f'<circle cx="150" cy="362" r="3" fill="{INK}"/><circle cx="200" cy="352" r="3" fill="{INK}"/><circle cx="200" cy="372" r="3" fill="{INK}"/>')
    b.append(wire("M150,362 L198,353", INK, 1.6))
    b.append(label(124, 366, "C", 9, GREY))
    b.append(wire(f"M200,352 L250,352 L250,{y+4}", INK, 1.3))
    b.append(wire(f"M200,372 L270,372 L270,{y-4}", RED, 1.3))
    b.append(f'<circle cx="250" cy="{y+4}" r="3" fill="{INK}"/><circle cx="270" cy="{y-4}" r="3" fill="{RED}"/>')
    b.append(wire(f"M150,362 L140,362 L140,280 L{fx},280 L{fx},{fy+2}", RED, 1.6))
    b.append(label(150, 274, "common to the frog", 9.5, RED))
    b.append(label(278, 292, "throws to the two stock rails", 9.5))
    # SPDT 2 (indication)
    b.append(label(124, 396, "SPDT 2: panel indication", 10, INK, weight="bold"))
    b.append(f'<circle cx="150" cy="408" r="3" fill="{INK}"/><circle cx="200" cy="402" r="3" fill="{INK}"/><circle cx="200" cy="414" r="3" fill="{INK}"/>')
    b.append(wire("M150,408 L198,403", INK, 1.6))
    b.append(box(380, 380, 170, 44, "Panel indication", "Touch Toggle LED, normal / reverse", size=9))
    b.append(wire("M200,402 L380,396", BLUE, 1.3))
    b.append(wire("M200,414 L380,410", BLUE, 1.3))
    b.append(box(380, 316, 170, 44, "Motor drive", "LCOS 12 V output", size=9))
    b.append(wire("M310,338 L380,338", INK, 1.3, "4 3"))
    b.append(label(20, 456, "The frog always takes the polarity of the stock rail its points lie against, because the same throw of the machine that moves", 9.5, INK))
    b.append(label(20, 470, "the points also moves the SPDT 1 contact. Every staging turnout is wired this way. Indication follows the machine, so it is", 9.5, INK))
    b.append(label(20, 484, "correct whether the turnout is thrown from the panel, a DCC throttle or the computer.", 9.5, INK))
    return svg(620, 500, "\n".join(b), "D3 · Turnout: powered frog and panel indication (MTB MP4, two SPDT)")


# ---------------------------------------------------------------- D4
def d4() -> str:
    """Crossover: two turnouts, gaps in both rails between the frogs."""
    b = []
    ya, yb = 110, 230
    b.append(rails(40, 700, ya))
    b.append(rails(40, 700, yb))
    b.append(wire(f"M230,{ya+4} L500,{yb-4}", INK, 1.6))
    b.append(wire(f"M240,{ya-4} L510,{yb+4}", INK, 1.6, ))
    # frogs
    b.append(f'<circle cx="300" cy="{ya+20}" r="6" fill="{RED}"/><circle cx="440" cy="{yb-20}" r="6" fill="{RED}"/>')
    b.append(label(312, ya + 34, "frog A", 9.5, RED, weight="bold"))
    b.append(label(380, yb - 30, "frog B", 9.5, RED, weight="bold"))
    # gaps both rails mid crossover
    b.append(f'<path d="M352,{ya+48} L376,{ya+62} M360,{ya+40} L384,{ya+54}" stroke="{INK}" stroke-width="2.6"/>')
    b.append(label(392, ya + 54, "gaps in both rails between the frogs", 10, INK, weight="bold"))
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
    b.append(box(300, 110, 160, 46, "Auto-reverser", "PSX-AR / AR-10", size=10))
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
    b.append(f'<circle cx="350" cy="200" r="10" fill="none" stroke="{BLUE}" stroke-width="2"/>')
    b.append(label(366, 204, "DNCT2B detector on the feeder, as D2", 9.5, BLUE))
    b.append(label(60, y - 16, "normal section", 9, GREY))
    b.append(label(620, y - 16, "normal section", 9, GREY))
    b.append(label(20, 320, "When a train's wheels bridge a gap with the polarity wrong, the short is seen by the auto-reverser, which swaps the section's two", 9.5, INK))
    b.append(label(20, 334, "outputs in milliseconds, faster than the district's breaker trips. Two sections are wired this way: Main West, and the K-1 / K-2 loop", 9.5, INK))
    b.append(label(20, 348, "at Princess (D1).", 9.5, INK))
    return svg(720, 364, "\n".join(b), "D5 · Reversing section on an auto-reverser")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, fn in [("D1-staging-reversing-sections", d1), ("D2-propulsion-sections", d2),
                     ("D3-turnout-frog-indication", d3), ("D4-crossover", d4), ("D5-reversing-section", d5)]:
        (OUT / f"{name}.svg").write_text(fn())
        print(OUT / f"{name}.svg")


if __name__ == "__main__":
    main()
