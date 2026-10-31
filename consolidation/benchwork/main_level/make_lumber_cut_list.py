"""Main-level 1x2 / 1x3 cut list: which stick every framing member comes out of.

Usage: make_lumber_cut_list.py <out.html> [<site copy>]

Lengths come from make_joist_construction_pdf.members() and riser_blocks(); the stick assignment below is by hand
(closet first, from the 1x3 on hand, so the 16 ft sticks keep their girder flanges). The script checks that every
member not yet built is cut exactly once and that every stick holds its parts with a 1/8 in kerf between cuts.
"""
import collections
import html
import runpy
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
J = runpy.run_path(str(HERE / "make_joist_construction_pdf.py"), run_name="lib")
KERF = 0.125
SPARE_MIN = 1.0   # a stick that ends closer than this to full is flagged

# Part catalogue: id -> (stock, length, name, measure-first?). Lengths match members(); "M" parts are cut to the
# drawing only if the field measurement agrees.
L = {}


def part(pid, stock, length, name, measure=False):
    L[pid] = (stock, length, name, measure)


# 1x3
part("FW", "1x3", 154.875, "West girder flange", True)
part("FN", "1x3", 153.75, "North girder flange", True)
part("CS-R", "1x3", 54.0, "South box: rail (recut)")
for i in range(1, 4):
    part(f"CS-J{i}", "1x3", 15.5, "South box: joist (recut)")
part("CN-L", "1x3", 54.0, "North box: wall ledger")
part("CN-R", "1x3", 54.0, "North box: front rail")
for i in range(1, 5):
    part(f"CN-J{i}", "1x3", 16.0, "North box: joist", True)
part("CE-L", "1x3", 49.5, "East box: wall ledger", True)
part("CE-R", "1x3", 49.5, "East box: front rail", True)
for i in range(1, 6):
    part(f"CE-J{i}", "1x3", 11.5, "East box: cross piece", True)
part("SW-R", "1x3", 54.75, "SW closet strip: rail", True)
part("SW-L", "1x3", 14.0, "SW closet strip: south wall ledger", True)
part("SW-W", "1x3", 35.125, "SW closet strip: west wall ledger", True)
part("SW-J1", "1x3", 19.25, "SW closet strip: north joist", True)
part("SW-J2", "1x3", 12.5, "SW closet strip: south joist", True)
part("B1", "1x3", 14.0, "B1 joist")
part("SB", "1x3", 4.0, "Seat block (detail G)")
NBLK = len(J["riser_blocks"]())
for i in range(1, NBLK + 1):
    part(f"RB{i}", "1x3", J["BLOCK_L"], "Riser block")

# 1x2
part("WN", "1x2", 153.75, "North girder web", True)
part("WW1", "1x2", 6.375, "West girder web, north end", True)
part("WW2", "1x2", 128.375, "West girder web, middle", True)
part("WW3", "1x2", 19.5, "West girder web, south end", True)
for i in range(1, 12):
    part(f"JN{i}", "1x2", 15.875, "North joist", True)
part("JW0", "1x2", 33.875, "West joist at the NW corner", True)
for i in range(1, 9):
    part(f"JW{i}", "1x2", 23.125, "West joist", True)
part("JW9", "1x2", 41.875, "West joist at the rim", True)
for i in range(1, 8):
    part(f"JP{i}", "1x2", 66.0, "Peninsula joist", True)
part("JP8", "1x2", 59.75, "Peninsula joist", True)
part("JP9", "1x2", 41.75, "Peninsula joist (south tip)", True)
part("BK1", "1x2", 14.1875, "Seam block, F3 / W2", True)
part("BK2", "1x2", 10.875, "Seam block, W2 / W3", True)
part("BK3", "1x2", 11.125, "Seam block, W2 / W3", True)
for pid, ln in (("LO1", 6.375), ("LO2", 6.375), ("LO3", 6.375), ("LO4", 6.75), ("LO5", 6.75), ("LO6", 6.75),
                ("LO7", 6.75), ("LO8", 6.75), ("LO9", 6.625), ("LO10", 3.375), ("LO11", 0.875)):
    part(pid, "1x2", ln, "North lookout", True)

# Already built and staying: the south box's good ledger and joist.
BUILT = {"1x3": [54.0, 15.5]}

# Sticks: (id, stock, length, where it comes from, [part ids], note)
RB = [f"RB{i}" for i in range(1, NBLK + 1)]
STICKS = [
    # closet first: the 12 ft sticks on hand and the two offcuts, plus one new 16 that otherwise only carries spare
    ("A", "1x3", 144.0, "on hand, 12 ft", ["CS-R", "CS-J1", "CS-J2", "CS-J3", "CN-J1", "CN-J2"] + RB[0:3],
     "Finishes the south box, then two north-box joists. Cut the north joists after measuring the opening."),
    ("B", "1x3", 144.0, "on hand, 12 ft", ["CN-L", "CN-R", "CN-J3", "CN-J4"],
     "The rest of the north box."),
    ("C", "1x3", 42.0, "on hand, 42 in offcut", ["CE-J1", "CE-J2", "CE-J3"] + RB[3:5],
     "East box cross pieces."),
    ("D", "1x3", 38.0, "on hand, 38 in offcut", ["CE-J4", "CE-J5", "B1"],
     "Last two cross pieces and the B1 joist."),
    ("E", "1x3", 192.0, "new 16 ft", ["CE-L", "CE-R", "SW-W"],
     "East box long pieces and the SW strip's west ledger from one end. Keep the rest whole: it is the spare for the whole job."),
    # main shelf: girder flanges first, the SW strip and the blocks round them out
    ("F", "1x3", 192.0, "new 16 ft, straightest", ["FW", "SW-J1", "SW-J2"],
     "West flange first, from the straight end. Sight it before you pick it."),
    ("G", "1x3", 192.0, "new 16 ft, second straightest", ["FN", "SW-L", "SB"] + RB[5:10],
     "North flange first."),
    ("H", "1x3", 192.0, "new 16 ft", ["SW-R"] + RB[10:],
     "Riser blocks against the stop (pattern, sheet 6)."),
    ("1", "1x2", 192.0, "new 16 ft, straightest", ["WN", "JW0"], "North girder web first."),
    ("2", "1x2", 192.0, "new 16 ft, second straightest", ["WW2", "JP8"],
     "West web middle piece: mark it on the flange in place before cutting."),
    ("3", "1x2", 192.0, "new 16 ft", ["JP1", "JP2", "JW9"], ""),
    ("4", "1x2", 192.0, "new 16 ft", ["JP3", "JP4", "JP9"], ""),
    ("5", "1x2", 192.0, "new 16 ft", ["JP5", "JP6", "JW1", "JW2"], ""),
    ("6", "1x2", 192.0, "new 16 ft", ["JP7", "JW3", "JW4", "JW5", "JW6", "JW7"], ""),
    ("7", "1x2", 192.0, "new 16 ft", [f"JN{i}" for i in range(1, 12)] + ["WW1"],
     "North joists: measure each wall to web; the back wall may not be straight."),
    ("8", "1x2", 192.0, "new 16 ft", ["JW8", "WW3", "BK1", "BK2", "BK3"] + [f"LO{i}" for i in range(1, 12)],
     "Short pieces last: the lookouts are cut to the deck edge once the girder is up."),
]


def frac(v, den=16):
    n = round(v * den)
    w, r = divmod(n, den)
    if r == 0:
        return f"{w}"
    g = 1
    for d in (8, 4, 2):
        if r % d == 0 and den % d == 0:
            g = d
            break
    f = f"{r // g}/{den // g}"
    return f"{w}-{f}" if w else f


def check():
    used = collections.Counter(p for s in STICKS for p in s[4])
    dup = [p for p, n in used.items() if n > 1]
    assert not dup, f"cut twice: {dup}"
    missing = set(L) - set(used)
    assert not missing, f"not on any stick: {sorted(missing)}"
    for stock in ("1x2", "1x3"):
        drawn = sorted(round(m[5], 2) for m in J["members"]() if m[6] == stock)
        planned = sorted([round(L[p][1], 2) for p in L if L[p][0] == stock and not p.startswith(("RB", "SB"))]
                         + BUILT.get(stock, []))
        assert len(drawn) == len(planned), (stock, len(drawn), len(planned))
        for a, b in zip(drawn, planned):
            assert abs(a - b) < 0.07, (stock, a, b)
    out = []
    for sid, stock, cap, src, parts, note in STICKS:
        assert all(L[p][0] == stock for p in parts), sid
        used_len = sum(L[p][1] for p in parts) + KERF * len(parts)
        left = cap - used_len
        assert left >= 0, f"stick {sid} over by {-left:.2f}"
        out.append((sid, stock, cap, src, parts, note, used_len, left))
    return out


def bar(parts, cap):
    """Stick as a horizontal bar, parts in cut order from the left end."""
    W, H = 960, 46
    k = W / cap
    s = [f'<svg viewBox="0 0 {W + 2} {H + 2}" role="img" aria-label="Stick layout" xmlns="http://www.w3.org/2000/svg">',
         f'<rect class="stick" x="1" y="1" width="{W}" height="{H}" rx="3"/>']
    x = 1.0
    run = []   # merge identical riser blocks into one labelled band
    for p in parts:
        if run and p.startswith("RB") and run[-1][0].startswith("RB"):
            run[-1][1].append(p)
        else:
            run.append((p, [p]))
    for p, grp in run:
        ln = sum(L[q][1] for q in grp) + KERF * (len(grp) - 1)
        w = ln * k
        cls = "seg blk" if p.startswith("RB") else "seg msr" if L[p][3] else "seg"
        s.append(f'<rect class="{cls}" x="{x:.1f}" y="1" width="{w:.1f}" height="{H}"/>')
        lab = f"{len(grp)} blocks" if p.startswith("RB") else p
        if w > 34:
            s.append(f'<text class="slbl" x="{x + w / 2:.1f}" y="21" text-anchor="middle">{lab}</text>')
            if w > 44:
                dim = f"{len(grp)} × {frac(L[p][1])}" if p.startswith("RB") else frac(L[p][1])
                s.append(f'<text class="sdim" x="{x + w / 2:.1f}" y="38" text-anchor="middle">{dim}</text>')
        x += w + KERF * k
    s.append("</svg>")
    return "".join(s)


def rows(parts):
    out, seen = [], []
    for p in parts:
        if p.startswith("RB"):
            continue
        st, ln, name, m = L[p]
        flag = '<span class="tag">measure first</span>' if m else ""
        out.append(f'<tr><td class="pid">{p}</td><td>{html.escape(name)} {flag}</td><td class="num">{frac(ln)}</td></tr>')
    blocks = [p for p in parts if p.startswith("RB")]
    if blocks:
        out.append(f'<tr><td class="pid">RB × {len(blocks)}</td><td>Riser blocks, 1 × 1 chamfer on the bottom front corner'
                   f'</td><td class="num">{frac(J["BLOCK_L"])}</td></tr>')
    return "".join(out)


VERIFY = [
    ("Stick count and length", "All the new sticks came as 16 ft. Count them once the bundle is open: the plan uses "
     "<b>4 of 1x3 and 8 of 1x2</b>. Hook a tape on one end of a few: most run 16 ft 1 in, which only adds spare. "
     "Check the two 12 ft 1x3s on hand are whole and the offcuts are 42 and 38 in."),
    ("North closet box joists, 16", "The south box needed 15-1/2, not the drawn 16. Set the north ledger and rail "
     "and measure between them at both ends before cutting CN-J1 to CN-J4."),
    ("East closet box, 49-1/2 and 11-1/2", "The east box fills the gap between the two built boxes. Measure between "
     "the north box's front rail and the south box's front rail for CE-L and CE-R, then the depth for the cross pieces."),
    ("SW closet strip", "Rail 54-3/4, ledgers 14 (south wall) and 35-1/8 (west wall), joists 19-1/4 and 12-1/2 all meet "
     "the walls and the peninsula girder. The west wall girder stops at the north peninsula girder, so the strip "
     "carries its own west ledger. Field fit them."),
    ("Girder flanges and webs", "Flanges 154-7/8 (west) and 153-3/4 (north), seat to seat. Measure in place with the "
     "seats on before cutting; sticks F, G and 1 have about 4 in spare for a longer cut. Mark the west web's three "
     "pieces on its flange where the NW joist and the rim cross, then cut."),
    ("Main shelf joists", "North 15-7/8 and west 23-1/8 run from the back wall to the web: measure each, the wall is "
     "not dead straight. The peninsula joists (66, 59-3/4, 41-3/4) run girder to girder: measure each once the "
     "girders are set."),
    ("Lookouts and seam blocks", "Cut the lookouts to the deck edge once the north girder is up (up to 6-3/4; the "
     "7/8 one can be skipped). Cut the three seam blocks to fit between their joists."),
]


CSS = """
:root {
  --bg: #f6f5f1; --panel: #ffffff; --ink: #1f2326; --muted: #5f666b; --rule: #d9d6cc;
  --pine: #ecd9ae; --pine-edge: #a8874a; --blk: #d9c08a; --stick: #f3eee2; --accent: #b4532a; --flag: #fbe7dc;
  --f-display: "Barlow Condensed", "Arial Narrow", sans-serif;
  --f-body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --f-mono: "JetBrains Mono", ui-monospace, Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #16191b; --panel: #1e2225; --ink: #e9e7e1; --muted: #a2a8ab; --rule: #33393d;
  --pine: #7a6338; --pine-edge: #e3c48f; --blk: #5f4d2b; --stick: #23282b; --accent: #e08a5f; --flag: #3a2a22;
  color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #16191b; --panel: #1e2225; --ink: #e9e7e1; --muted: #a2a8ab; --rule: #33393d;
  --pine: #7a6338; --pine-edge: #e3c48f; --blk: #5f4d2b; --stick: #23282b; --accent: #e08a5f; --flag: #3a2a22;
  color-scheme: dark; }
body { background: var(--bg); color: var(--ink); font: 16px/1.5 var(--f-body); margin: 0; }
.wrap { max-width: 1120px; margin: 0 auto; padding-block: 28px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 36px; }
h1, h2, h3 { font-family: var(--f-display); font-weight: 700; letter-spacing: .01em; text-wrap: balance; margin: 0; }
h1 { font-size: clamp(2.2rem, 5vw, 3.2rem); line-height: 1; }
h2 { font-size: 1.9rem; line-height: 1.1; }
h3 { font-size: 1.3rem; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
p { margin: 0; max-width: 72ch; }
a { color: inherit; }
.eyebrow { font: 600 .78rem/1 var(--f-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }
.intro, .section { display: grid; gap: 14px; }
.small { font-size: .9rem; color: var(--muted); }
.totals { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
.total { background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 16px 18px; display: grid; gap: 6px; }
.total .big { font: 700 2.4rem/1 var(--f-display); }
.total .big small { font-size: 1.05rem; color: var(--muted); font-weight: 600; }
.verify { background: var(--panel); border: 1px solid var(--rule); border-left: 4px solid var(--accent); border-radius: 6px;
  padding: 16px 18px; display: grid; gap: 12px; }
.verify ol { margin: 0; padding-left: 1.3em; display: grid; gap: 8px; }
.sticks { display: grid; gap: 18px; }
.card { background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 14px 16px 16px; display: grid;
  gap: 10px; min-width: 0; }
.card.first { border-color: var(--pine-edge); }
.sid { font: 700 1.05rem/1 var(--f-mono); min-width: 2rem; height: 2rem; padding: 0 6px; display: inline-grid;
  place-items: center; border-radius: 4px; background: var(--pine); color: var(--ink); }
.src { font: .85rem var(--f-mono); color: var(--muted); }
.drawing { overflow-x: auto; }
.drawing svg { min-width: 560px; width: 100%; height: auto; display: block; }
.stick { fill: var(--stick); stroke: var(--muted); stroke-width: 1; stroke-dasharray: 4 3; }
.seg { fill: var(--pine); stroke: var(--pine-edge); stroke-width: 1.2; }
.seg.msr { fill: var(--flag); stroke: var(--accent); }
.seg.blk { fill: var(--blk); }
.slbl { fill: var(--ink); font: 700 13px var(--f-mono); }
.sdim { fill: var(--ink); font: 12px var(--f-mono); opacity: .8; }
.tbl { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: .92rem; }
th { text-align: left; font: 600 .72rem/1.2 var(--f-mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted);
  padding: 6px 10px 6px 0; border-bottom: 1px solid var(--rule); }
td { padding: 6px 10px 6px 0; border-bottom: 1px solid var(--rule); vertical-align: top; }
td.pid { font: 600 .9rem var(--f-mono); white-space: nowrap; }
td.num { font-family: var(--f-mono); font-variant-numeric: tabular-nums; white-space: nowrap; }
.tag { display: inline-block; font: 600 .7rem/1.4 var(--f-mono); letter-spacing: .04em; text-transform: uppercase;
  color: var(--accent); border: 1px solid var(--accent); border-radius: 3px; padding: 0 5px; margin-left: 4px; }
.key { display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: .9rem; color: var(--muted); }
.key span::before { content: ""; display: inline-block; width: 14px; height: 12px; vertical-align: -1px; margin-right: 6px;
  border: 1px solid var(--pine-edge); background: var(--pine); border-radius: 2px; }
.key .k-m::before { background: var(--flag); border-color: var(--accent); }
.key .k-b::before { background: var(--blk); }
.key .k-s::before { background: var(--stick); border: 1px dashed var(--muted); }
"""


def page(sticks):
    def card(s, first=False):
        sid, stock, cap, src, parts, note, used_len, left = s
        tight = ' <span class="tag">tight</span>' if left < SPARE_MIN else ""
        return (f'<article class="card{" first" if first else ""}"><h3><span class="sid">{sid}</span>{stock} · '
                f'{frac(cap)} in <span class="src">{html.escape(src)} · {frac(left, 8)} in left{tight}</span></h3>'
                f'{f"<p class=small>{html.escape(note)}</p>" if note else ""}'
                f'<div class="drawing">{bar(parts, cap)}</div>'
                f'<div class="tbl"><table><thead><tr><th>Part</th><th>What</th><th>Length</th></tr></thead>'
                f'<tbody>{rows(parts)}</tbody></table></div></article>')

    closet = [s for s in sticks if s[0] in "ABCDE"]
    x3 = [s for s in sticks if s[1] == "1x3" and s[0] not in "ABCDE"]
    x2 = [s for s in sticks if s[1] == "1x2"]
    n16 = collections.Counter(s[1] for s in sticks if s[2] == 192.0)
    spare = {st: sum(s[7] for s in sticks if s[1] == st) for st in ("1x2", "1x3")}
    e_left = next(s for s in sticks if s[0] == "E")[7]
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Main Level Lumber</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap">
<style>{CSS}</style>
<div class="wrap">
  <header class="intro">
    <p class="small"><a href="../index.html#main-level">&larr; The Build</a></p>
    <p class="eyebrow">HART main level · cut list</p>
    <h1>Main level 1x2 and 1x3</h1>
    <p>Every framing member from the framing drawings, assigned to a stick. The closet boxes come first, out of the
    1x3 already in the shop and one new stick, so the 16 ft sticks keep the lengths the girder flanges need. Each stick
    was checked in code with a 1/8 in kerf between cuts. Cut each stick left to right, longest piece first.</p>
    <div class="key"><span>cut to the drawing</span><span class="k-m">measure first</span><span class="k-b">riser blocks</span><span class="k-s">left over</span></div>
  </header>

  <div class="totals">
    <div class="total"><span class="eyebrow">1x3</span><span class="big">{n16["1x3"]} <small>× 16 ft new</small></span>
      <p class="small">Plus the two 12 ft sticks and the 42 and 38 in offcuts on hand. About {frac(spare["1x3"] / 12, 2)} ft
      left over, most of it the {frac(e_left, 8)} in end of stick E.</p></div>
    <div class="total"><span class="eyebrow">1x2</span><span class="big">{n16["1x2"]} <small>× 16 ft new</small></span>
      <p class="small">About {frac(spare["1x2"] / 12, 2)} ft left over, most of it on stick 8. A ninth stick, if they
      sent one, is all spare.</p></div>
  </div>

  <section class="verify" aria-labelledby="verify-title">
    <h2 id="verify-title">Measure before cutting</h2>
    <p class="small">These come from the drawing, not the room. Every part marked <span class="tag">measure first</span>
    below falls under one of them.</p>
    <ol>{"".join(f"<li><b>{t}.</b> {d}</li>" for t, d in VERIFY)}</ol>
  </section>

  <section class="section">
    <h2>Closet first</h2>
    <p>Sticks A to E finish the closet: the south box's missing rail and three 15-1/2 joists, then the north box,
    the east box and the B1 joist. They use only the 1x3 on hand and one end of stick E, so nothing on the main shelf
    is affected. Leave the rest of E whole: it is the spare for a miscut anywhere on the job. The split 54 in rail
    and the damaged joists are not in the plan; cut riser blocks from their clean parts and you will have extras.</p>
    <div class="sticks">{"".join(card(s, True) for s in closet)}</div>
  </section>

  <section class="section">
    <h2>1x3 for the main shelf</h2>
    <p>Pick the two straightest sticks for the girder flanges (F and G) and cut those first.</p>
    <div class="sticks">{"".join(card(s) for s in x3)}</div>
  </section>

  <section class="section">
    <h2>1x2 for the main shelf</h2>
    <p>The two straightest sticks carry the girder webs (1 and 2). The joists are cut after the girders are up, to
    the measured lengths.</p>
    <div class="sticks">{"".join(card(s) for s in x2)}</div>
  </section>
</div>
</html>
"""


if __name__ == "__main__":
    out = Path(sys.argv[1])
    sticks = check()
    out.write_text(page(sticks))
    for s in sticks:
        print(f"{s[0]:>2} {s[1]} {s[2]:6.1f} used {s[6]:6.2f} left {s[7]:6.2f}  {' '.join(s[4])}")
    if len(sys.argv) > 2:
        shutil.copyfile(out, sys.argv[2])
