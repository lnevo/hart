#!/usr/bin/env python3
"""Assemble the plywood cut-plan review page from plywood_cut_plan.py output."""
import html
import json
import sys
from pathlib import Path

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
S = json.loads((SRC / "summary.json").read_text())
PC = {p["id"]: p for p in S["pieces"]}
e = html.escape


def svg(name):
    t = (SRC / name).read_text()
    return t.replace('xmlns="http://www.w3.org/2000/svg"', 'xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet"')


def frac(v):
    q = round(v * 8) / 8
    w = int(q)
    f = round((q - w) * 8)
    if f == 0:
        return f"{w}"
    d = 8
    while f % 2 == 0:
        f //= 2
        d //= 2
    return f"{w}-{f}/{d}" if w else f"{f}/{d}"


def sheet_block(s):
    rows = "".join(
        f'<tr><td class="pid">{p}</td><td>{e(PC[p]["name"])}</td><td class="num">{PC[p]["w"]} × {PC[p]["h"]}</td>'
        f'<td class="note">{e(PC[p]["note"])}</td></tr>' for p in s["pieces"])
    tag = "Room to spare" if s["used"] < 45 else ""
    return f'''
<section class="sheet-card" id="sheet-{s["id"]}">
  <header class="sheet-head">
    <h3><span class="sheet-id l{s["level"]}">{s["id"]}</span>{e(s["title"])}</h3>
    <p class="used">{s["used"]}% used{f' · <b>{tag}</b>' if tag else ''}</p>
  </header>
  <div class="drawing">{svg(f"sheet_{s['id']}.svg")}</div>
  <div class="tbl"><table>
    <thead><tr><th>Piece</th><th>Where</th><th>Box (in)</th><th>Notes</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</section>'''


s34 = [s for s in S["sheets"] if s["level"] == "34"]
s12 = [s for s in S["sheets"] if s["level"] == "12"]
off_n = "".join(f"<tr><td class='num'>{frac(a)}</td><td class='num'>{frac(b)}</td></tr>" for a, b in S["offsets"]["N2"])
off_h = "".join(f"<tr><td class='num'>{frac(a)}</td><td class='num'>{frac(b)}</td></tr>" for a, b in S["offsets"]["H2"])
off_t = "".join(f"<tr><td class='num'>{frac(a)}</td><td class='num'>{frac(b)}</td></tr>" for a, b in S["offsets"]["T1"])

page = f'''<title>Main Level Plywood</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
/* Shop drawing set: a sheet-goods yard. Two ply tones encode the two decks; everything else is drafting neutral. */
:root {{
  --bg: #f6f5f1; --panel: #ffffff; --ink: #1f2326; --muted: #5f666b; --rule: #d9d6cc;
  --ply34: #e3c48f; --ply34-edge: #9a7434; --ply12: #a9c6c0; --ply12-edge: #3f7268;
  --sheet: #fbfaf6; --grid: #e7e3d8; --reserve: #ece8dc; --wall: #b9b4a8; --bench: #efece3; --accent: #b4532a;
  --f-display: "Barlow Condensed", "Arial Narrow", sans-serif;
  --f-body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --f-mono: "JetBrains Mono", ui-monospace, Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #16191b; --panel: #1e2225; --ink: #e9e7e1; --muted: #a2a8ab; --rule: #33393d;
  --ply34: #8a6a37; --ply34-edge: #e3c48f; --ply12: #3d6660; --ply12-edge: #a9d6cc;
  --sheet: #23282b; --grid: #2e3438; --reserve: #2a2f2c; --wall: #5d625f; --bench: #25292b; --accent: #e08a5f; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #16191b; --panel: #1e2225; --ink: #e9e7e1; --muted: #a2a8ab; --rule: #33393d;
  --ply34: #8a6a37; --ply34-edge: #e3c48f; --ply12: #3d6660; --ply12-edge: #a9d6cc;
  --sheet: #23282b; --grid: #2e3438; --reserve: #2a2f2c; --wall: #5d625f; --bench: #25292b; --accent: #e08a5f; color-scheme: dark; }}
body {{ background: var(--bg); color: var(--ink); font: 16px/1.5 var(--f-body); }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding-block: 28px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 40px; }}
h1, h2, h3 {{ font-family: var(--f-display); font-weight: 700; letter-spacing: .01em; text-wrap: balance; margin: 0; }}
h1 {{ font-size: clamp(2.2rem, 5vw, 3.2rem); line-height: 1; }}
h2 {{ font-size: 1.9rem; line-height: 1.1; }}
h3 {{ font-size: 1.35rem; display: flex; align-items: center; gap: 10px; }}
p {{ margin: 0; max-width: 68ch; }}
.eyebrow {{ font: 600 .78rem/1 var(--f-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }}
.intro {{ display: grid; gap: 12px; }}
.totals {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
.total {{ background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 16px 18px; display: grid; gap: 6px; }}
.total .big {{ font: 700 2.6rem/1 var(--f-display); }}
.total .big small {{ font-size: 1.1rem; color: var(--muted); font-weight: 600; }}
.swatch {{ display: inline-block; width: 12px; height: 12px; border-radius: 2px; vertical-align: -1px; margin-right: 6px; }}
.sw34 {{ background: var(--ply34); outline: 1px solid var(--ply34-edge); }}
.sw12 {{ background: var(--ply12); outline: 1px solid var(--ply12-edge); }}
.section {{ display: grid; gap: 18px; }}
.maps {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }}
figure {{ margin: 0; background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 12px; display: grid; gap: 8px; min-width: 0; }}
figcaption {{ font-size: .9rem; color: var(--muted); }}
svg {{ width: 100%; height: auto; display: block; }}
.review {{ background: var(--panel); border: 1px solid var(--rule); border-left: 4px solid var(--accent); border-radius: 6px; padding: 16px 18px; display: grid; gap: 10px; }}
.review ol {{ margin: 0; padding-left: 1.3em; display: grid; gap: 6px; }}
.sheets {{ display: grid; gap: 22px; }}
.sheet-card {{ background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 14px 16px 16px; display: grid; gap: 12px; min-width: 0; }}
.sheet-head {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 6px 16px; }}
.sheet-id {{ font: 700 1.1rem/1 var(--f-mono); width: 2rem; height: 2rem; display: inline-grid; place-items: center; border-radius: 4px; }}
.sheet-id.l34 {{ background: var(--ply34); color: var(--ink); }}
.sheet-id.l12 {{ background: var(--ply12); color: var(--ink); }}
.used {{ font: .85rem var(--f-mono); color: var(--muted); }}
.drawing {{ overflow-x: auto; }}
.drawing svg {{ min-width: 560px; }}
.tbl {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: .92rem; }}
th {{ text-align: left; font: 600 .72rem/1.2 var(--f-mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); padding: 6px 10px 6px 0; border-bottom: 1px solid var(--rule); }}
td {{ padding: 6px 10px 6px 0; border-bottom: 1px solid var(--rule); vertical-align: top; }}
td.pid {{ font: 600 .9rem var(--f-mono); white-space: nowrap; }}
td.num {{ font-family: var(--f-mono); font-variant-numeric: tabular-nums; white-space: nowrap; }}
td.note {{ color: var(--muted); }}
.shop {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
.shop .box {{ background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 14px 16px; display: grid; gap: 8px; min-width: 0; }}
.shop h3 {{ font-size: 1.15rem; }}
.small {{ font-size: .9rem; color: var(--muted); }}
/* svg parts */
.sheet {{ fill: var(--sheet); stroke: var(--ink); stroke-width: 1.5; }}
.grid {{ stroke: var(--grid); stroke-width: 1; }}
.reserve {{ fill: var(--reserve); stroke: var(--muted); stroke-width: 1; stroke-dasharray: 5 4; }}
.rlbl {{ fill: var(--muted); font: italic 13px var(--f-body); }}
.pivot {{ stroke: var(--accent, #b4532a); stroke-width: 2; }}
.pc {{ stroke-width: 1.4; }}
.pc.l34 {{ fill: var(--ply34); stroke: var(--ply34-edge); }}
.pc.l12 {{ fill: var(--ply12); stroke: var(--ply12-edge); }}
.plbl {{ fill: var(--ink); font: 700 17px var(--f-mono); }}
.plbl.sm {{ font-size: 12px; }}
.pdim {{ fill: var(--ink); font: 13px var(--f-mono); opacity: .8; }}
.axis {{ fill: var(--muted); font: 12px var(--f-mono); }}
.bench {{ fill: var(--bench); stroke: var(--rule); stroke-width: 1; }}
.wall {{ fill: var(--wall); }}
.mlbl {{ fill: var(--ink); font: 600 11px var(--f-mono); }}
.ctr {{ fill: var(--accent); }}
</style>
<div class="wrap">
  <header class="intro">
    <p class="eyebrow">HART main level · cut plan for review</p>
    <h1>Main level plywood</h1>
    <p>Every piece of plywood for the main level, laid out on 4 × 8 sheets. Sizes come from the AnyRail plan: the
    benchwork outlines, the helix bulb, and the two outer main-line tracks for the +4.25 ledge. Each layout was checked
    in code so every piece fits its sheet with a 1/8 in saw kerf and nothing overlaps.</p>
  </header>

  <div class="totals">
    <div class="total"><span class="eyebrow"><span class="swatch sw34"></span>3/4 in · 0 in level deck</span>
      <span class="big">{len(s34)} <small>sheets</small></span>
      <p class="small">{S["area34"]} sq ft of pieces. Includes the balloon-loop subroadbed.</p></div>
    <div class="total"><span class="eyebrow"><span class="swatch sw12"></span>1/2 in · +4.25 level</span>
      <span class="big">{len(s12)} <small>sheets</small></span>
      <p class="small">{S["area12"]} sq ft of pieces. The offcuts on the last two sheets are where the 0 to 4.25 ramp
      pieces come from.</p></div>
  </div>

  <section class="section">
    <h2>Where the pieces go</h2>
    <div class="maps">
      <figure>{svg("room_34.svg")}<figcaption><span class="swatch sw34"></span>3/4 in at 0 in: solid deck on the north and
      west walls, the closet strip and the turnback; a 6 in board for the double track from the helix through both wall
      openings; 9-1/4 in subroadbed for the balloon loop on the SW peninsula. Dots mark curve centres.</figcaption></figure>
      <figure>{svg("room_12.svg")}<figcaption><span class="swatch sw12"></span>1/2 in at +4.25: the helix top over the whole
      peninsula, the SW top over the peninsula and W3, and the 8 in ledge for the two outer tracks. Dots mark the
      curve centres.</figcaption></figure>
    </div>
  </section>

  <section class="review">
    <h2>Please check</h2>
    <ol>
      <li><b>The 6 in board (B1, N2)</b> follows the middle of AnyRail's "Helix Top Turn 1" tracks out of the helix,
      along the neck and through the south opening, and back through the north opening into the north wall deck. It
      meets the closet deck at the alcove face of each opening. B1 starts square, 1-1/2 in outside the helix edge. Fit
      that end to the helix exit roadbed.</li>
      <li><b>Closet deck (B2, B3)</b> is now full over the grid: both alcoves and the turnback, split at the middle of the
      aisle end so the halves mirror each other. The aisle curve is AnyRail's exact outline.</li>
      <li><b>Balloon loop (F3, G1 to G4)</b> is 9-1/4 in subroadbed, all four pieces the same width, on the AnyRail branchline loop: 28.6 in radius off the
      west wall, 31 in round the tip, 29 in back to the wall. F3 is a square-cornered block in the SW inside corner
      (with the 18 in fillet on the aisle side) that carries the loop's first curve, so G1 is a plain rectangle. G4 is
      a plain rectangle wide enough for the last curve, and G1 to G3 match its width. Their outer edge stays on the 4 in
      roadbed edge; the extra width is on the inside of the loop. G2 and G3 are pure quarter circles round the tip, nested on
      sheet D the way the helix roadbed was: chord across the 48 in width, both facing the same way.</li>
      <li><b>North wall overlap.</b> The 0 in track nearest the north wall (about 7-1/2 in off it) runs under the front edge of
      the 8 in ledge, which leaves about 3-3/8 in from that railhead to the ledge underside. Narrow the ledge to 7 in
      there if you want the two to clear.</li>
      <li><b>Helix top (H1, H2, L7)</b> uses AnyRail's exact peninsula outline, including the curved south edge. H1 is
      the west half of the bulb, 48 × 72. The south-alcove ledge's top edge carries straight west to H1, so L7 is one
      83 in piece: the south side of the bulb and neck plus the ledge through the south opening. H2 is the rest, the
      north-east bulb and the neck's north side out to the wall stubs. Add any access hatch before cutting.</li>
      <li><b>SW top (S1 to S4)</b> covers the peninsula and runs west over W3 to the wall. It's split along the backdrop
      (AnyRail's view block, 1-1/2 in wide, from the wall to 68-3/4 in out). S2 and S4 are 96 in long, from the tip back
      toward the wall; the wall strip S1 is one 11-5/8 × 66 piece that the backdrop stands on. The SW corner ledge is one piece (L9) with a
      straight edge on the SW top, so L9, S1, S2 and S4 meet on straight lines. Put risers under every seam.</li>
      <li><b>Longer pieces.</b> W3 runs on through the closet strip as one 96 in piece (W1 grew to 39-1/2 in to make
      that work), N2 carries the board through the north opening, W1 includes the NW fillet, and the turnback ledge L5
      is one 30 × 84 piece. Two joints stay because removing them costs a sheet: the NW corner ledge L2 on its own
      (merging it with the north ledge needs a sixth 1/2 in sheet) and the balloon loop's joint at the tip (one half
      circle needs a fifth 3/4 in sheet).</li>
      <li><b>The 0 to 4.25 ramp</b> still isn't drawn: I don't know where it runs. At 2% it's about 18 ft of track.</li>
    </ol>
  </section>

  <section class="section">
    <h2><span class="swatch sw34"></span>3/4 in sheets</h2>
    <p class="small">Each sheet is laid out for the saw: the big piece sits against the factory edges, straight strips are
    full-length rips, and small pieces sit centred in the big piece's curved offcut with room for the saw. Make the
    rips first, then the curves.
    The deck stops 1/8 in off the walls, like the joists, so two 23-7/8 in rips plus the kerf come out of one 48 in
    sheet. Every butt joint lands on a joist.</p>
    <div class="sheets">{"".join(sheet_block(s) for s in s34)}</div>
  </section>

  <section class="section">
    <h2><span class="swatch sw12"></span>1/2 in sheets</h2>
    <p class="small">Every seam needs a riser or cleat under it. The ledge ends meet square, at right angles to the track.</p>
    <div class="sheets">{"".join(sheet_block(s) for s in s12)}</div>
  </section>

  <section class="section">
    <h2>Laying out the curves</h2>
    <div class="shop">
      <div class="box"><h3>Trammel radii</h3>
        <table><tbody>
          <tr><td class="pid">H1 H2</td><td>Bulb west side about 36-1/2 in from the bulb centre; south edge from the offsets</td></tr>
          <tr><td class="pid">B1</td><td>S-curve out of the helix: lay it out from the track. On sheet C it is flipped with its square end in the bottom-left corner: the straight run and the square end at the south opening are both factory edges. Plain ply, so either face can go up</td></tr>
          <tr><td class="pid">B2 B3</td><td>Inside edge is the aisle end: use the offsets</td></tr>
          <tr><td class="pid">S2 S4</td><td>33 in, round end of the SW peninsula</td></tr>
          <tr><td class="pid">F3</td><td>18 in fillet, aisle side only</td></tr>
          <tr><td class="pid">G2 G3</td><td>23-3/4 and 33 in edges (31 in track centre line). Both arcs bulge toward the sheet edge, so each centre is on the plywood: nail the trammel at the cross marked on sheet D and swing 23-3/4 and 33 in</td></tr>
                    <tr><td class="pid">L2 L5</td><td>26-1/2 in inside edge, track curve centre</td></tr>
          <tr><td class="pid">L9</td><td>40.2 in inside radius, centre (52.7, 160.3)</td></tr>
          <tr><td class="pid">W1 W3</td><td>10 and 6 in fillets</td></tr>
        </tbody></table>
        <p class="small">For the 36 in radius, 1/8 in of error changes the circumference by 3/4 in. Strike every bulb arc from the same nail.</p>
      </div>
      <div class="box"><h3>N2 front edge</h3>
        <p class="small">Depth from the north wall, measured from the west wall. Bend a batten through the points.</p>
        <table><thead><tr><th>From west wall</th><th>Depth</th></tr></thead><tbody>{off_n}</tbody></table>
      </div>
      <div class="box"><h3>Helix top south edge</h3>
        <p class="small">Depth south of the neck's north edge (in line with the wall stubs), measured west from the wall stubs.</p>
        <table><thead><tr><th>From wall stubs</th><th>Depth</th></tr></thead><tbody>{off_h}</tbody></table>
      </div>
      <div class="box"><h3>B2 / B3 inside edge</h3>
        <p class="small">Width from the east wall, measured from the north wall. B2 and B3 mirror each other about the middle row.</p>
        <table><thead><tr><th>From north wall</th><th>Width</th></tr></thead><tbody>{off_t}</tbody></table>
      </div>
    </div>
  </section>
</div>
'''
OUT.write_text(page)
print(OUT, len(page))

# Optional third argument: a standalone copy for the website's Build page (the artifact host supplies the document
# skeleton; the site needs its own), with a link back to The Build.
if len(sys.argv) > 3:
    site = Path(sys.argv[3])
    body = (page.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "")
            .replace("HART main level · cut plan for review", "HART main level · cut plan")
            .replace('<header class="intro">',
                     '<header class="intro">\n    <p class="small"><a href="../index.html#main-level">&larr; The Build</a></p>', 1))
    site.write_text('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
                    '<meta name="viewport" content="width=device-width, initial-scale=1">\n' + body + "</html>\n")
    print(site, site.stat().st_size)
