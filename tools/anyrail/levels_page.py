#!/usr/bin/env python3
"""Build the level-plans page: staging, main and upper level of plan 5.3b, drawn to scale.

    python3 levels_page.py SVG_DIR STAGING_SVG PANEL_IMG|- OUT_SITE_HTML OUT_ARTIFACT_HTML

SVG_DIR holds main.svg, upper.svg and levels_meta.json from levels_svg.py. STAGING_SVG is the
staging level's track drawing (staging_plan.svg here). The Switch 7 and 13 markers are added
here from the loop 2 timed passes (infer_block_lengths.py --route loop2 --locate).
"""
import base64
import csv
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine_terminal  # noqa: E402

BLOCK_CSV = Path(__file__).resolve().parents[2] / "jmri/layouts/hart/data/block_lengths.csv"
PIN_5, PIN_15 = 140, 5909     # Switch 5 and Switch 15 centres on the plan, mm from Switch 5's points (infer_block_lengths.py)

# loop 2 pass results, 2026-11-13: mm from Switch 5's points along Switch 5, Scale, 7, Barn, 13, 15
LOCATE = {"7": (4249, 4260, 4239, 1660), "13": (5457, 5444, 5470, 452)}
# the run Switch 5 to Switch 15 on the staging drawing, from Switch 5's points (cm)
RUN = [(72.9, 636.5), (94.9, 653.9)]
RUN_SEGS = [  # polylines of the run, in order from Switch 5, as drawn in staging_plan.svg
    ("141.8,666.2", "94.9,653.9"), ("141.8,666.2", "197.9,666.3"),
    ("270.3,593.9", "197.9,666.3"), ("197.9,521.5", "270.3,593.9"),
    ("103.0,521.5", "197.9,521.5"), ("103.0,521.5", "24.3,442.8")]
OLD_7B = (168.5, 515.1)   # Switch 7b from loop 1 (PR #399 pass), kept as a ring for comparison


def block_inches():
    return {r["user_name"]: float(r["inches"]) for r in csv.DictReader(open(BLOCK_CSV, newline=""))}


def derive(os5=24.6, os7=10.0):
    """Block lengths that follow from the timed centres of Switch 7 and 13 and the pins at Switch 5 and 15.
    Blocks tile the run, so half of OS 13 and half of OS 15 span the gap between their centres (split evenly,
    since the timing cannot split it), and Barn is what is left between Switch 7 and Switch 13. mm."""
    l7, l13 = LOCATE["7"][0], LOCATE["13"][0]
    gap = PIN_15 - l13
    scale = (l7 - PIN_5) - os5 * 25.4 / 2 - os7 * 25.4 / 2
    barn = (l13 - l7) - os7 * 25.4 / 2 - gap / 2
    return dict(scale=scale, barn=barn, os13=gap, os15=gap)


def run_path(staging):
    polys = {}
    for m in re.finditer(r'<polyline class="sw7" points="([^"]+)"', staging):
        q = [tuple(map(float, p.split(","))) for p in m.group(1).split()]
        polys[("%.1f,%.1f" % q[0], "%.1f,%.1f" % q[-1])] = q
    path = list(RUN)
    for a, b in RUN_SEGS:
        q = polys.get((a, b)) or polys[(b, a)][::-1]
        # orient so the piece continues from where the path is
        if math.dist(path[-1], q[0]) > math.dist(path[-1], q[-1]):
            q = q[::-1]
        path += q if path[-1] != q[0] else q[1:]
    return path


def point_at(path, d_cm):
    run = 0.0
    for i in range(1, len(path)):
        seg = math.dist(path[i - 1], path[i])
        if run + seg >= d_cm:
            t = (d_cm - run) / seg
            return [path[i - 1][j] + t * (path[i][j] - path[i - 1][j]) for j in range(2)]
        run += seg
    return list(path[-1])


def markers(staging):
    path = run_path(staging)
    p7 = point_at(path, LOCATE["7"][0] / 10)
    p13 = point_at(path, LOCATE["13"][0] / 10)
    out = []
    # the crossover joins the run (orange) to the loop's bottom straight, 6.4 cm above it
    out.append('<line class="m7" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (p7[0] - 7, p7[1], p7[0] + 7, p7[1] - 6.4))
    out.append('<circle class="m7dot" cx="%.1f" cy="%.1f" r="3.2"/>' % tuple(p7))
    out.append('<text class="m7t" x="%.1f" y="511">Sw 7</text>' % (p7[0] - 24))
    out.append('<circle class="m7old" cx="%.1f" cy="%.1f" r="3.2"/>' % OLD_7B)
    out.append('<text class="rl" x="%.1f" y="507">Sw 7b, loop 1 estimate</text>' % (OLD_7B[0] - 10))
    out.append('<circle class="m7dot" cx="%.1f" cy="%.1f" r="3.2"/>' % tuple(p13))
    out.append('<text class="m7t" x="%.1f" y="%.1f">Sw 13</text>' % (p13[0] + 14, p13[1] + 3))
    engine_terminal.SW13 = (p13[0], p13[1])      # one Switch 13: the one marked above
    out.append(engine_terminal.svg()[0])
    return "\n".join(out), p7, p13


def block_table():
    rows = [("OS Switch 5", 10, 24.6, 0.5), ("Track East Ext", 88, 140.8, 0.5), ("OS Switch 7b", 10, 9.2, 0.5),
            ("Track Main East", 185, 315.1, 0.8), ("OS Switch 33", 10, 12.4, 1.1), ("Track East Lead *", 172, 87.9, 1.5),
            ("OS Switch 35a", 10, 15.0, 0.8), ("OS Switch 37", 10, 16.5, 0.4), ("Track K-2", 122.5, 113.6, 0.8),
            ("Track K-1 *", 122.5, 108.0, 1.1), ("OS Switch 39", 10, 9.6, 0.6), ("OS Switch 35b", 10, 20.5, 1.1),
            ("Track West Ext", 160, 156.1, 0.6), ("OS Switch 23a", 10, 23.5, 0.9), ("Track Main West", 220, 217.3, 1.1),
            ("OS Switch 1", 10, 22.6, 0.6), ("Track Brick-Plane", 72, 58.1, 0.5)]
    h = '<table><thead><tr><th>Block</th><th class="n">Before</th><th class="n">Now</th><th class="n">Change</th><th class="n">&plusmn;</th></tr></thead><tbody>'
    for n, a, b, s in rows:
        h += '<tr><td>%s</td><td class="n">%g</td><td class="n">%.1f</td><td class="n">%+.1f</td><td class="n">%.1f</td></tr>' % (n, a, b, b - a, s)
    return h + '<tr><td><b>Loop total</b> (with the hidden stubs, 31.5 in)</td><td class="n"><b>1232</b></td><td class="n"><b>1382</b></td><td class="n"><b>+150</b></td><td></td></tr></tbody></table>'


def figure(vb, body, label, extra=""):
    x, y, w, hgt = vb
    bar = '<line class="scale" x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f"/><text class="rl" x="%.0f" y="%.0f">100 cm</text>' % (
        x + 6, y + hgt - 8, x + 106, y + hgt - 8, x + 6, y + hgt - 11)
    return ('<div class="plan"><svg viewBox="%.0f %.0f %.0f %.0f" role="img" aria-label="%s">%s%s%s</svg></div>'
            % (x, y, w, hgt, label, body, extra, bar))


def sections(svg_dir, staging):
    meta = json.load(open(Path(svg_dir) / "levels_meta.json"))
    main = (Path(svg_dir) / "main.svg").read_text()
    upper = (Path(svg_dir) / "upper.svg").read_text()
    mk, p7, p13 = markers(staging)
    mb, ub = meta["main"]["bbox"], meta["upper"]["bbox"]
    pad = 12
    f_stage = figure((3, 112, 600, 684), staging, "Staging level of plan 5.3b", mk)
    f_main = figure((mb[0] - pad, mb[1] - pad, mb[2] - mb[0] + 2 * pad, mb[3] - mb[1] + 2 * pad), main, "Main level of plan 5.3b")
    f_upper = figure((ub[0] - pad, ub[1] - pad, ub[2] - ub[0] + 2 * pad, ub[3] - ub[1] + 2 * pad), upper, "Upper level of plan 5.3b")
    t = {}
    t["intro"] = ('<p>The track plans of all three levels, read from the layout plan (version 5.3b) and drawn to scale in centimetres. '
                  'Staging is 38.1 cm (15 in) below the main level, and the upper level is 10.8 cm (4.25 in) above it. '
                  'The helix joins them. Every drawing is track only, with the changes made to the plan applied: the unbuilt crossover is left out, '
                  'T300 is moved to the upper level, and the switches the plan lacks are added where the plan has room for them.</p>')
    t["stage_key"] = ('<div class="key"><span class="k-loop">test loop route</span><span class="k-sw7">run from Switch 5 to Switch 15</span>'
                      '<span class="k-trk">other track</span></div>')
    l7, a7, b7, before7 = LOCATE["7"]
    l13, a13, b13, before13 = LOCATE["13"]
    t["locate"] = (
        '<h3>Where Switch 7 and Switch 13 sit</h3>'
        '<p>Neither switch is in the plan. CSX 2121 ran Switch 5 to Switch 15 twice at different speeds, and the occupancy sensors timed each section. '
        'With the loco at constant speed between Switch 5 and Switch 15, each switch centre falls where its sensor lit, between the two. The two passes agree within 3 cm.</p>'
        '<div class="tw"><table><thead><tr><th>Switch</th><th class="n">Pass at step 24</th><th class="n">Pass at step 48</th><th class="n">Mean, from Switch 5&rsquo;s points</th><th class="n">Before Switch 15&rsquo;s centre</th></tr></thead><tbody>'
        '<tr><td>Switch 7</td><td class="n">%d mm</td><td class="n">%d mm</td><td class="n"><b>%d mm</b></td><td class="n">%d mm</td></tr>'
        '<tr><td>Switch 13</td><td class="n">%d mm</td><td class="n">%d mm</td><td class="n"><b>%d mm</b></td><td class="n">%d mm</td></tr></tbody></table></div>'
        '<p>On the drawing, Switch 7 is at x %.0f cm on the straight where the run lies 6.4 cm beside the loop (orange dot), and Switch 13 on the curve into the yard ladder at x %.0f, y %.0f cm. '
        'The ring is the earlier Switch 7b estimate from the loop timings, 35 cm further east on the same straight.</p>'
        % (a7, b7, l7, before7, a13, b13, l13, before13, p7[0], p13[0], p13[1]))
    t["diffs"] = (
        '<h3>Where the plan and the built layout differ</h3><ol>'
        '<li><b>No crossover near Switch 1.</b> The plan has a crossover (T41/T43) between Main West and Track S-R, about 27 in from Switch 1. It was not built, so both tracks are drawn plain: Main West runs from Switch 1 to Switch 23.</li>'
        '<li><b>The Switch 7 crossover is not in the plan.</b> It joins the two long parallel runs out of Switch 5.</li>'
        '<li><b>Switch 13 and the engine terminal are not in the plan</b> (Switches 9 and 11, Barn, Scale, EH-1 to EH-3). They sit on the run from Switch 5 to the yard ladder (Switch 5, Scale, Switch 7, Barn, Switch 13). The terminal is drawn as a placeholder from the built topology and a photo of the benchwork: the track radii and the length of the stubs are not measured. Switch 9&rsquo;s normal route goes to EH-2.</li>'
        '<li><b>The two long dead ends past Switches 37 and 39 are the helix lines.</b> On the layout they are the McKeesport and McKees Rocks stubs.</li></ol>')
    d = derive()
    now = block_inches()
    ft = lambda mm: "%.1f in (%d mm)" % (mm / 25.4, round(mm))
    t["terminal"] = (
        '<h3>Lengths in the Switch 5 to Switch 15 run, and the engine terminal</h3>'
        '<p>The blocks along the run tile it, so they must add up to the plan&rsquo;s distance between the Switch 5 and Switch 15 centres. '
        'The timed passes fix where the centres of Switch 7 and 13 fall. Scale is the distance from Switch 5 to Switch 7 less half of each switch&rsquo;s block. '
        'Switch 13 sits %d mm before Switch 15, so half of the Switch 13 block and half of the Switch 15 block span that gap: the timing cannot split it, so both are given the same length. '
        'Barn is what is left between Switch 7 and Switch 13. '
        'The terminal rows are measured on the drawing, between the switches as drawn. The EH track ends are not measured: the stub ends are placed at x 180 cm, so those lengths show what that placement gives, not what is built.</p>'
        '<div class="tw"><table><thead><tr><th>Block</th><th class="n">Before</th><th class="n">Recorded now</th><th class="n">From</th></tr></thead><tbody>'
        % (PIN_15 - LOCATE["13"][0]) +
        '<tr><td>Track Scale (Switch 5 to Switch 7)</td><td class="n">24 in</td><td class="n"><b>%s</b></td><td class="n">timed passes</td></tr>' % ("%.1f in" % now["Track Scale"]) +
        '<tr><td>Track Barn (Switch 7 to Switch 13)</td><td class="n">24 in</td><td class="n"><b>%s</b></td><td class="n">timed passes</td></tr>' % ("%.1f in" % now["Track Barn"]) +
        '<tr><td>OS Switch 13</td><td class="n">10 in</td><td class="n"><b>%s</b></td><td class="n">timed passes</td></tr>' % ("%.1f in" % now["OS Switch 13"]) +
        '<tr><td>OS Switch 15</td><td class="n">10 in</td><td class="n"><b>%s</b></td><td class="n">timed passes</td></tr>' % ("%.1f in" % now["OS Switch 15"]) +
        '<tr><td>Switch 13 to Switch 11</td><td class="n">&ndash;</td><td class="n">10.2 in</td><td class="n">drawing</td></tr>'
        '<tr><td>Switch 11 to Switch 9</td><td class="n">&ndash;</td><td class="n">14.7 in</td><td class="n">drawing</td></tr>'
        '<tr><td>Track EH-1 (Switch 11 to the bumper)</td><td class="n">24 in</td><td class="n">24 in (drawing: 48.3 in)</td><td class="n">drawing, bumper placed</td></tr>'
        '<tr><td>Track EH-2 (Switch 9 to the bumper)</td><td class="n">24 in</td><td class="n">24 in (drawing: 22.3 in)</td><td class="n">drawing, bumper placed</td></tr>'
        '<tr><td>Track EH-3 (Switch 9 to the bumper)</td><td class="n">24 in</td><td class="n">24 in (drawing: 22.2 in)</td><td class="n">drawing, bumper placed</td></tr>'
        '</tbody></table></div>')
    t["loop"] = ('<h3>Test loop length</h3><div class="tw"><table><thead><tr><th>Source</th><th class="n">Test loop</th></tr></thead><tbody>'
                 '<tr><td>Plan 5.3b, along the test route</td><td class="n">35,108 mm (1382 in)</td></tr>'
                 '<tr><td>Block table before the timed loop</td><td class="n">31,293 mm (1232 in)</td></tr>'
                 '<tr><td>Speeds recorded 2026-11-08</td><td class="n">about 12% low</td></tr></tbody></table></div>')
    t["blocks"] = ('<h3>Loop block lengths</h3><p class="muted">Inches, in the order a loco runs the loop from Switch 5. Each block is its timed share of the track between the plan turnouts either side of it '
                   '(Switches 5, 33, 35a, 35b, 23a and 1 sit at their plan positions). &plusmn; is the spread over 33 timed laps (16 for East Ext). '
                   '* The detector also covers a 15.7 in hidden stub with its own row (East Lead East, K-1 West).</p><div class="tw">' + block_table() + '</div>')
    t["main"] = (
        '<div class="key"><span class="k-trk">track</span><span class="k-ramp">helix and ramps up to the upper level and down to staging</span></div>'
        + f_main +
        '<p>%d turnouts and %.1f m of flex at the main level (T300 moved up), with the helix and its ramps in dotted orange (%.1f m of flex). '
        'Turnouts show their plan part number; the main level&rsquo;s own switch numbers and names are not assigned yet.</p>'
        '<ul><li><b>T251 runs on into the inner helix track</b> (McKeesport). The plan has T300 in that track at height 0; it is built on the upper level, so the main level has no T300.</li>'
        '<li>The two helix tracks start at T175 (McKees Rocks) and T251 (McKeesport).</li></ul>'
        % (meta["main"]["drawn"], meta["main"]["flex_m"], meta["ramp_m"]))
    t["upper"] = (
        '<div class="key"><span class="k-trk">track</span></div>' + f_upper +
        '<p>%d turnouts and %.1f m of flex at 4.25 in (10.8 cm), including the peninsula loop with its yard tracks, which the plan holds at 1 in and is built at 4.25 in. '
        'Turnouts show their plan part number; switch numbers and names for this level are not assigned yet.</p>'
        '<ul><li><b>Crossover 23</b> is the plan&rsquo;s double crossover at the east end of the peninsula. Its two tracks on the north side run round the east end together: one to T237 and the west, the other to <b>T300</b>, which joins it to the first (T300 is the turnout moved up from the main level; its plan run from the crossover is 292 cm).</li></ul>'
        % (meta["upper"]["drawn"], meta["upper"]["flex_m"]))
    return t, f_stage


CSS = """
.plan{background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:8px;overflow-x:auto}
.plan svg{width:100%;height:auto;min-width:520px;display:block}
polyline,line,circle{fill:none;stroke-linecap:round}
.trk{stroke:var(--track);stroke-width:1.6}
.loop{stroke:var(--loop);stroke-width:2.6}
.sw7{stroke:var(--sw7);stroke-width:2.6;stroke-dasharray:6 3}
.ramp{stroke:var(--sw7);stroke-width:1.5;stroke-dasharray:2 2.4}
.to{stroke:var(--fg);stroke-width:2}
.nb{stroke:var(--nb);stroke-width:2.8}
.lb{font:600 8px var(--display);fill:var(--fg)}
.lbnb{font:600 8px var(--display);fill:var(--nb)}
.rl{font:5.5px var(--body);fill:var(--muted)}
.tl{font:600 5px var(--display);fill:var(--muted)}
.scale{stroke:var(--fg);stroke-width:1.4}
.m7{stroke:var(--sw7);stroke-width:1.6}
.m7dot{fill:var(--sw7);stroke:none}
.m7old{stroke:var(--sw7);stroke-width:1.2}
.m7t{font:600 7px var(--display);fill:var(--sw7)}
.flag{stroke:var(--nb);stroke-width:1.6}
.key{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.85rem;color:var(--muted);margin-bottom:8px}
.key span::before{content:"";display:inline-block;width:22px;height:0;border-top:3px solid;vertical-align:middle;margin-right:6px}
.k-loop::before{border-color:var(--loop)!important}.k-sw7::before{border-color:var(--sw7)!important;border-top-style:dashed!important}.k-ramp::before{border-color:var(--sw7)!important;border-top-style:dotted!important}.k-nb::before,.k-flag::before{border-color:var(--nb)!important}.k-trk::before{border-color:var(--track)!important}
.lv h2{margin-top:2.2rem}
.tw{overflow-x:auto}
.lv table{border-collapse:collapse;width:100%;font-size:.9rem;font-variant-numeric:tabular-nums}
.lv td,.lv th{text-align:left;padding:4px 8px 4px 0;border-bottom:1px solid var(--rule);vertical-align:top}
.lv td.n,.lv th.n{text-align:right;padding-left:10px}
.lv th{font-weight:600;color:var(--muted);font-size:.78rem;text-transform:uppercase;letter-spacing:.04em}
.lv ol,.lv ul{padding-left:1.3em;display:flex;flex-direction:column;gap:8px}
.lv .jump{display:flex;gap:16px;flex-wrap:wrap;margin:.6rem 0 0}
"""


def body(t, f_stage):
    return ('<nav class="jump"><a href="#staging">Staging</a><a href="#main">Main level</a><a href="#upper">Upper level</a></nav>'
            + t["intro"] +
            '<section id="staging"><h2>Staging level</h2>' + t["stage_key"] + f_stage +
            t["locate"] + t["diffs"] + t["terminal"] + t["loop"] + t["blocks"] + '</section>'
            '<section id="main"><h2>Main level</h2>' + t["main"] + '</section>'
            '<section id="upper"><h2>Upper level</h2>' + t["upper"] + '</section>')


SITE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Level plans — HART</title>
  <link rel="stylesheet" href="../css/ops.css">
  <style>
    :root{--track:#6b7a86;--loop:#146377;--sw7:#a85a10;--nb:#b33a3a;--fg:var(--ink);--display:var(--font-display);--body:var(--font-body)}
    .lv{max-width:72rem;display:block;min-width:0}
    .lv section,.lv .plan{min-width:0;max-width:100%%}
    .lv h3{font-family:var(--font-display);font-size:1.15rem;margin:1.6rem 0 .4rem;color:var(--brand-2)}
%s
  </style>
</head>
<body>
  <header class="site-header" data-ops-header></header>
  <main>
    <div class="page-head">
      <h1>Level plans</h1>
      <p class="muted">Staging, main and upper level, drawn to scale from plan 5.3b</p>
    </div>
    <div class="guide-body lv prose">
%s
    </div>
  </main>
  <footer class="site-footer" data-ops-footer></footer>
  <script src="../js/nav.js"></script>
  <script>document.addEventListener("DOMContentLoaded", function () { HARTOps.mountChrome("layout-levels"); });</script>
</body>
</html>
"""

ART = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Level Plans 5.3b</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@600&display=swap">
<style>
:root{--bg:#f6f7f5;--fg:#1d2320;--muted:#5d6862;--rule:#d5dbd7;--track:#8d9892;--loop:#1f6f8b;--sw7:#b5651d;--nb:#c0392b;--card:#ffffff;--display:"Space Grotesk",system-ui,sans-serif;--body:"Inter",system-ui,sans-serif;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141816;--fg:#e4e9e6;--muted:#9aa59f;--rule:#2c3330;--track:#6b7570;--loop:#5fb3d0;--sw7:#e0994f;--nb:#ff7a6b;--card:#1b201e;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#141816;--fg:#e4e9e6;--muted:#9aa59f;--rule:#2c3330;--track:#6b7570;--loop:#5fb3d0;--sw7:#e0994f;--nb:#ff7a6b;--card:#1b201e;color-scheme:dark}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 var(--body)}
.wrap{max-width:1100px;margin:0 auto;padding:24px max(16px,env(safe-area-inset-right,0px)) 48px max(16px,env(safe-area-inset-left,0px))}
h1{font-family:var(--display);font-size:1.7rem;margin:0 0 4px;text-wrap:balance}
h2{font-family:var(--display);font-size:1.35rem;margin:2.2rem 0 8px}
h3{font-family:var(--display);font-size:1.05rem;margin:1.6rem 0 6px}
p{margin:.5rem 0;max-width:70ch}.muted{color:var(--muted)}
a{color:var(--loop)}
%s
.panel img{border:1px solid var(--rule);border-radius:6px;background:#121418;max-width:100%%}
</style></head><body><div class="wrap"><h1>Level plans from plan 5.3b</h1>
<p class="muted">Staging, main and upper level, drawn to scale from plan 5.3b.</p>
<div class="lv">
%s
</div>
%s
</div></body></html>
"""


def main(svg_dir, staging_file, panel, out_site, out_art):
    staging = Path(staging_file).read_text()
    t, f_stage = sections(svg_dir, staging)
    b = body(t, f_stage)
    Path(out_site).write_text(SITE % (CSS, b))
    extra = ""
    if panel != "-":
        data = base64.b64encode(Path(panel).read_bytes()).decode()
        extra = ('<section class="panel"><h3>The panel, for comparison</h3><p class="muted">Layout Editor view of the built staging level, not to scale.</p>'
                 '<img alt="Layout Editor panel" src="data:image/png;base64,%s"></section>' % data)
    Path(out_art).write_text(ART % (CSS, b, extra))


if __name__ == "__main__":
    main(*sys.argv[1:6])
