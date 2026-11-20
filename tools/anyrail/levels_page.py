#!/usr/bin/env python3
"""Build the track plan article (www/build/track-plan.html): staging, main and upper level of the plan, drawn to scale.

    python3 levels_page.py SVG_DIR STAGING_SVG PANEL_IMG|- OUT_SITE_HTML OUT_ARTIFACT_HTML PLAN_VERSION

PLAN_VERSION is the plan the two level SVGs and the staging drawing were read from (5.3b today); it is printed on
the page. OUT_SITE_HTML is www/build/track-plan.html (the Build section article; never edit it by hand, rerun this).
PANEL_IMG goes into the artifact copy only, never into the site article.

SVG_DIR holds main.svg, upper.svg and levels_meta.json from levels_svg.py. STAGING_SVG is the
staging level's track drawing (staging_plan.svg here). The Switch 7 and 13 markers are added
here from the loop 2 timed passes (loop2_locate.csv, from infer_block_lengths.py --route loop2 --locate) and the
run itself is read off the staging drawing (staging_run.py). Block lengths come from block_lengths.csv; the "before"
column is block_lengths_before.csv.
"""
import base64
import collections
import csv
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine_terminal  # noqa: E402
import staging_run  # noqa: E402
from staging_run import point_at  # noqa: E402
from hartlib import paths  # noqa: E402  (staging_run has put hartlib on the path)

sys.path.insert(0, str(paths.LAYOUT_SCRIPTS / "speedmatch"))
import analyze  # noqa: E402  the loop's blocks in running order (routes.json)

BLOCK_CSV = staging_run.BLOCK_CSV
BEFORE_CSV = paths.LAYOUT_DATA / "block_lengths_before.csv"
MM_PER_IN = staging_run.MM_PER_IN
SPREAD = re.compile(r"\+-(\d+(?:\.\d+)?) in over (\d+) laps")
PLAN_LOOP_MM = staging_run.infer.PLAN_LOOP_MM     # the plan's test loop along the route of the 2026-11-08 runs
LABEL_ABOVE = 10.5, 8.1   # cm above the run, and above the loop straight, for the Switch 7 and 7b labels


def block_rows():
    """{user_name: csv row} of block_lengths.csv."""
    with open(BLOCK_CSV, newline="") as f:
        return {r["user_name"]: r for r in csv.DictReader(f)}


def block_inches():
    """{block: inches} of the lengths JMRI holds (block_lengths.csv: the measured length of a timed block)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hartlib/src"))
    from hartlib import railroad
    return {name: b.jmri_in for name, b in railroad.read_block_lengths(BLOCK_CSV).items()}


def before_inches(group):
    """{user_name: inches} of one group ("loop1": the loop's blocks, "run": the Switch 5 to Switch 15 run) of
    block_lengths_before.csv, the block table before the timed passes."""
    with open(BEFORE_CSV, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["group"] == group]
    if not rows:
        raise SystemExit("%s has no %r rows" % (BEFORE_CSV.name, group))
    return {r["user_name"]: float(r["before_in"]) for r in rows}


def markers(staging):
    locate = staging_run.load_locate()
    staging_run.check_block_lengths(locate)
    path, pieces = staging_run.run_path(staging)
    p7 = point_at(path, locate["7"]["mean"] / 10)
    p13 = point_at(path, locate["13"]["mean"] / 10)
    p7b = point_at(path, locate["7b"] / 10)
    run_y, rise = staging_run.straight_at(staging, pieces, p7)
    out = []
    # the crossover joins the run (orange) to the loop's bottom straight, `rise` cm above it
    out.append('<line class="m7" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (p7[0] - 7, p7[1], p7[0] + 7, p7[1] - rise))
    out.append('<circle class="m7dot" cx="%.1f" cy="%.1f" r="3.2"/>' % tuple(p7))
    out.append('<text class="m7t" x="%.1f" y="%g">Sw 7</text>' % (p7[0] - 24, run_y - LABEL_ABOVE[0]))
    out.append('<circle class="m7old" cx="%.1f" cy="%.1f" r="3.2"/>' % (p7b[0], run_y - rise))
    out.append('<text class="rl" x="%.1f" y="%g">Sw 7b, loop 1 estimate</text>' % (p7b[0] - 10, run_y - rise - LABEL_ABOVE[1]))
    out.append('<circle class="m7dot" cx="%.1f" cy="%.1f" r="3.2"/>' % tuple(p13))
    out.append('<text class="m7t" x="%.1f" y="%.1f">Sw 13</text>' % (p13[0] + 14, p13[1] + 3))
    out.append(engine_terminal.svg(staging)[0])       # one Switch 13: engine_terminal reads the same one
    return "\n".join(out), p7, p13, locate, rise


def loop_rows():
    """The loop's blocks in running order with what the page shows: [(label, before, now, spread, laps)]. Now is the
    block's measured length and the spread is in its note (block_lengths.csv, source timed); before is
    block_lengths_before.csv. A block of the loop with no before, no timed length or spread, or a row nobody listed
    stops the page."""
    rows = block_rows()
    before = before_inches("loop1")
    loop = analyze.route_loop("loop1")
    first = [sensor for sensor, _ in loop].index("BS Switch 5")      # the page runs the loop from Switch 5
    loop = loop[first:] + loop[:first]
    names = [name for _, name in loop]
    if sorted(before) != sorted(names):
        raise SystemExit("%s and the loop's blocks differ: %s" % (BEFORE_CSV.name, ", ".join(sorted(set(before) ^ set(names)))))
    out = []
    for _sensor, name in loop:
        row = rows[name]
        m = SPREAD.search(row["note"])
        if row["source"] != "timed" or not m:
            raise SystemExit("block_lengths.csv: %s has no timed spread in its note (%r)" % (name, row["note"]))
        out.append((name, before[name], float(row["measured_in"]), float(m.group(1)), int(m.group(2))))
    return out


def laps_note(rows):
    """"33 timed laps (16 for East Ext)": the laps most blocks were timed over, and the exceptions."""
    laps = collections.Counter(r[4] for r in rows)
    common = laps.most_common(1)[0][0]
    odd = ["%d for %s" % (r[4], r[0].removeprefix("Track ").rstrip(" *")) for r in rows if r[4] != common]
    return "%d timed laps%s" % (common, " (%s)" % ", ".join(odd) if odd else "")


def block_table(rows):
    h = '<table><thead><tr><th>Block</th><th class="n">Before</th><th class="n">Now</th><th class="n">Change</th><th class="n">&plusmn;</th></tr></thead><tbody>'
    for n, a, b, s, _ in rows:
        h += '<tr><td>%s</td><td class="n">%g</td><td class="n">%.1f</td><td class="n">%+.1f</td><td class="n">%.1f</td></tr>' % (n, a, b, b - a, s)
    before, now = sum(r[1] for r in rows), sum(r[2] for r in rows)
    if abs(now * MM_PER_IN - PLAN_LOOP_MM) > 3 * MM_PER_IN:
        raise SystemExit("the loop's blocks add up to %.0f mm, the plan's loop is %.0f mm" % (now * MM_PER_IN, PLAN_LOOP_MM))
    return h + ('<tr><td><b>Loop total</b></td><td class="n"><b>%.0f</b></td><td class="n"><b>%.0f</b></td>'
                '<td class="n"><b>%+.0f</b></td><td></td></tr></tbody></table>') % (before, now, now - before)


def figure(vb, body, label, extra=""):
    x, y, w, hgt = vb
    bar = '<line class="scale" x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f"/><text class="rl" x="%.0f" y="%.0f">100 cm</text>' % (
        x + 6, y + hgt - 8, x + 106, y + hgt - 8, x + 6, y + hgt - 11)
    return ('<div class="plan"><svg viewBox="%.0f %.0f %.0f %.0f" role="img" aria-label="%s">%s%s%s</svg></div>'
            % (x, y, w, hgt, label, body, extra, bar))


def sections(svg_dir, staging):
    meta = json.loads((Path(svg_dir) / "levels_meta.json").read_text())
    main = (Path(svg_dir) / "main.svg").read_text()
    upper = (Path(svg_dir) / "upper.svg").read_text()
    mk, p7, p13, locate, rise = markers(staging)
    loop = loop_rows()
    loop_in = PLAN_LOOP_MM / MM_PER_IN
    mb, ub = meta["main"]["bbox"], meta["upper"]["bbox"]
    pad = 12
    f_stage = figure((3, 112, 600, 684), staging, "Staging level of plan @PLAN@", mk)
    f_main = figure((mb[0] - pad, mb[1] - pad, mb[2] - mb[0] + 2 * pad, mb[3] - mb[1] + 2 * pad), main, "Main level of plan @PLAN@")
    f_upper = figure((ub[0] - pad, ub[1] - pad, ub[2] - ub[0] + 2 * pad, ub[3] - ub[1] + 2 * pad), upper, "Upper level of plan @PLAN@")
    t = {}
    t["intro"] = (
        '<p>Track plans of the staging, main and upper levels, read from layout plan version @PLAN@ and drawn to scale in centimetres. Staging is 38.1 cm (15 in) below the main level and the upper level is 10.8 cm (4.25 in) above it; the helix joins them. The main level has %d turnouts and %.1f m of flex, the upper level %d turnouts and %.1f m. The staging section adds the run from Switch 5 to Switch 15, the engine terminal and the block lengths, including the %.0f in (%s mm) test loop. Every drawing is track only.</p><p>AI read the geometry out of the plan file. The changes made since the plan was drawn had never been written down, and were filled in by talking them through with it: the unbuilt crossover is left out, T300 is moved to the upper level, and the switches the plan lacks are added where it has room for them.</p>'
        % (meta["main"]["drawn"], meta["main"]["flex_m"], meta["upper"]["drawn"], meta["upper"]["flex_m"],
           loop_in, format(round(PLAN_LOOP_MM), ",")))
    t["stage_key"] = ('<div class="key"><span class="k-loop">test loop route</span><span class="k-sw7">run from Switch 5 to Switch 15</span>'
                      '<span class="k-trk">other track</span></div>')
    l7, a7, b7, before7 = (locate["7"][k] for k in ("mean", "step24", "step48", "before"))
    l13, a13, b13, before13 = (locate["13"][k] for k in ("mean", "step24", "step48", "before"))
    spread_cm = math.ceil(max(abs(a7 - b7), abs(a13 - b13)) / 10)
    t["locate"] = (
        '<h3>Where Switch 7 and Switch 13 sit</h3>'
        '<p>Neither switch is in the plan. CSX 2121 ran Switch 5 to Switch 15 twice at different speeds, and the occupancy sensors timed each section. '
        'With the loco at constant speed between Switch 5 and Switch 15, each switch centre falls where its sensor lit, between the two. The two passes agree within %d cm.</p>'
        '<div class="tw"><table class="nw"><thead><tr><th>Switch</th><th class="n">Pass at step 24</th><th class="n">Pass at step 48</th><th class="n">Mean, from Switch 5&rsquo;s points</th><th class="n">Before Switch 15&rsquo;s centre</th></tr></thead><tbody>'
        '<tr><td>Switch 7</td><td class="n">%d mm</td><td class="n">%d mm</td><td class="n"><b>%d mm</b></td><td class="n">%d mm</td></tr>'
        '<tr><td>Switch 13</td><td class="n">%d mm</td><td class="n">%d mm</td><td class="n"><b>%d mm</b></td><td class="n">%d mm</td></tr></tbody></table></div>'
        '<p>On the drawing, Switch 7 is at x %.0f cm on the straight where the run lies %.1f cm beside the loop (orange dot), and Switch 13 on the curve into the yard ladder at x %.0f, y %.0f cm. '
        'The ring is the earlier Switch 7b estimate from the loop timings, %.0f cm further east on the same straight.</p>'
        % (spread_cm, a7, b7, l7, before7, a13, b13, l13, before13, p7[0], rise, p13[0], p13[1], (l7 - locate["7b"]) / 10))
    t["diffs"] = (
        '<h3>Where the plan and the built layout differ</h3><ol>'
        '<li><b>No crossover near Switch 1.</b> The plan has a crossover (T41/T43) between Main West and Track S-R, about 27 in from Switch 1. It was not built, so both tracks are drawn plain: Main West runs from Switch 1 to Switch 23.</li>'
        '<li><b>The Switch 7 crossover is not in the plan.</b> It joins the two long parallel runs out of Switch 5.</li>'
        '<li><b>Switch 13 and the engine terminal are not in the plan</b> (Switches 9 and 11, Barn, Scale, EH-1 to EH-3). They sit on the run from Switch 5 to the yard ladder (Switch 5, Scale, Switch 7, Barn, Switch 13). The terminal is drawn as a placeholder from the built topology and a photo of the benchwork: the track radii and the length of the stubs are not measured. Switch 9&rsquo;s normal route goes to EH-2.</li>'
        '<li><b>The two long dead ends past Switches 37 and 39 are the helix lines.</b> On the layout they are the McKeesport and McKees Rocks stubs.</li></ol>')
    now = block_inches()
    run_before = before_inches("run")
    et_in = engine_terminal.build(staging)[4]["lengths_in"]
    t["terminal"] = (
        '<h3>Lengths in the Switch 5 to Switch 15 run, and the engine terminal</h3>'
        '<p>The blocks along the run tile it, so they must add up to the plan&rsquo;s distance between the Switch 5 and Switch 15 centres. '
        'The timed passes fix where the centres of Switch 7 and 13 fall. Scale is the distance from Switch 5 to Switch 7 less half of each switch&rsquo;s block. '
        'Switch 13 sits %d mm before Switch 15, so half of the Switch 13 block and half of the Switch 15 block span that gap: the timing cannot split it, so both are given the same length. '
        'Barn is what is left between Switch 7 and Switch 13. '
        'The terminal rows are measured on the drawing, between the switches as drawn. The EH track ends are not measured: the stub ends are placed at x %.0f cm, so those lengths show what that placement gives, not what is built.</p>'
        '<div class="tw"><table><thead><tr><th>Block</th><th class="n">Before</th><th class="n">Recorded now</th><th class="n">From</th></tr></thead><tbody>'
        % (staging_run.PIN_15 - l13, engine_terminal.STUB_END) +
        '<tr><td>Track Scale (Switch 5 to Switch 7)</td><td class="n">%g in</td><td class="n"><b>%s</b></td><td class="n">timed passes</td></tr>' % (run_before["Track Scale"], "%.1f in" % now["Track Scale"]) +
        '<tr><td>Track Barn (Switch 7 to Switch 13)</td><td class="n">%g in</td><td class="n"><b>%s</b></td><td class="n">timed passes</td></tr>' % (run_before["Track Barn"], "%.1f in" % now["Track Barn"]) +
        '<tr><td>OS Switch 13</td><td class="n">%g in</td><td class="n"><b>%s</b></td><td class="n">timed passes</td></tr>' % (run_before["OS Switch 13"], "%.1f in" % now["OS Switch 13"]) +
        '<tr><td>OS Switch 15</td><td class="n">%g in</td><td class="n"><b>%s</b></td><td class="n">timed passes</td></tr>' % (run_before["OS Switch 15"], "%.1f in" % now["OS Switch 15"]) +
        '<tr><td>Switch 13 to Switch 11</td><td class="n">&ndash;</td><td class="n">%.1f in</td><td class="n">drawing</td></tr>' % et_in["13 to 11"] +
        '<tr><td>Switch 11 to Switch 9</td><td class="n">&ndash;</td><td class="n">%.1f in</td><td class="n">drawing</td></tr>' % et_in["11 to 9"] +
        '<tr><td>Track EH-1 (Switch 11 to the bumper)</td><td class="n">%g in</td><td class="n">%g in (drawing: %.1f in)</td><td class="n">drawing, bumper placed</td></tr>' % (run_before["Track EH-1"], now["Track EH-1"], et_in["EH-1"]) +
        '<tr><td>Track EH-2 (Switch 9 to the bumper)</td><td class="n">%g in</td><td class="n">%g in (drawing: %.1f in)</td><td class="n">drawing, bumper placed</td></tr>' % (run_before["Track EH-2"], now["Track EH-2"], et_in["EH-2"]) +
        '<tr><td>Track EH-3 (Switch 9 to the bumper)</td><td class="n">%g in</td><td class="n">%g in (drawing: %.1f in)</td><td class="n">drawing, bumper placed</td></tr>' % (run_before["Track EH-3"], now["Track EH-3"], et_in["EH-3"]) +
        '</tbody></table></div>')
    before_in = sum(r[1] for r in loop)
    t["loop"] = ('<h3>Test loop length</h3><div class="tw"><table><thead><tr><th>Source</th><th class="n">Test loop</th></tr></thead><tbody>'
                 '<tr><td>Plan @PLAN@, along the test route</td><td class="n">%s mm (%.0f in)</td></tr>'
                 '<tr><td>Block table before the timed loop</td><td class="n">%s mm (%.0f in)</td></tr>'
                 '<tr><td>Speeds recorded 2026-11-08</td><td class="n">about 12%% low</td></tr></tbody></table></div>'
                 % (format(round(PLAN_LOOP_MM), ","), loop_in, format(round(before_in * MM_PER_IN), ","), before_in))
    t["blocks"] = ('<h3>Loop block lengths</h3><p class="muted">Inches, in the order a loco runs the loop from Switch 5. Each block is its timed share of the track between the plan turnouts either side of it '
                   '(Switches 5, 33, 35a, 35b, 23a and 1 sit at their plan positions). &plusmn; is the spread over %s.</p><div class="tw">%s</div>'
                   % (laps_note(loop), block_table(loop)))
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
.feature-body.lv{max-width:none;font-family:var(--font-body);font-size:1rem;line-height:1.55}
.feature-body.lv h2{margin-top:0}
.feature-body.lv p{max-width:70ch}
.lv li{max-width:70ch}
.lv h2 .num{display:block;font-size:.85rem;letter-spacing:.12em;color:var(--muted)}
.tw{overflow-x:auto}
.lv table{border-collapse:collapse;width:100%;font-size:.9rem;font-variant-numeric:tabular-nums}
.lv td,.lv th{text-align:left;padding:4px 8px 4px 0;border-bottom:1px solid var(--rule);vertical-align:top}
.lv td.n,.lv th.n{text-align:right;padding-left:10px}
.lv table.nw td.n{white-space:nowrap}
@media (max-width:480px){.lv table{font-size:.84rem}.lv td,.lv th{padding-right:6px}.lv td.n,.lv th.n{padding-left:6px}}
.lv th{font-weight:600;color:var(--muted);font-size:.78rem;text-transform:uppercase;letter-spacing:.04em}
.lv ol,.lv ul{padding-left:1.3em;display:flex;flex-direction:column;gap:8px}
"""


def body(t, f_stage):
    return (t["intro"] +
            '<section id="staging"><h2><span class="num">01</span>Staging level</h2>' + t["stage_key"] + f_stage +
            t["locate"] + t["diffs"] + t["terminal"] + t["loop"] + t["blocks"] + '</section>'
            '<section id="main"><h2><span class="num">02</span>Main level</h2>' + t["main"] + '</section>'
            '<section id="upper"><h2><span class="num">03</span>Upper level</h2>' + t["upper"] + '</section>')


SITE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Track plan — HART</title>
  <meta name="description" content="Track plans of the staging, main and upper levels drawn to scale from plan @PLAN@, with the Switch 7 and 13 timings, plan and built differences, and loop and block lengths.">
  <link rel="stylesheet" href="../css/ops.css">
  <link rel="stylesheet" href="../css/article.css">
  <style>
    :root{--track:#6b7a86;--loop:#146377;--sw7:#a85a10;--nb:#b33a3a;--fg:var(--ink);--display:var(--font-display);--body:var(--font-body)}
    .lv section,.lv .plan{min-width:0;max-width:100%%}
    .lv h3{font-family:var(--font-display);font-size:1.15rem;margin:1.6rem 0 .4rem;color:var(--brand-2)}
%s
  </style>
</head>
<body>
  <header class="site-header" data-ops-header></header>
  <main>
    <article class="feature">
      <header class="feature-head">
        <h1>Track plan</h1>
        <p class="standfirst">Staging, main and upper level drawn to scale from plan @PLAN@, with the Switch 7 and 13 timings and the loop and block lengths.</p>
        <p class="byline">The Build · November 2026</p>
      </header>
      <nav class="feature-toc" aria-label="On this page">
        <h2>On this page</h2>
        <ol>
          <li><a href="#staging">Staging level</a></li>
          <li><a href="#main">Main level</a></li>
          <li><a href="#upper">Upper level</a></li>
        </ol>
      </nav>
      <div class="feature-body lv">
%s
      </div>
    </article>
  </main>
  <footer class="site-footer" data-ops-footer></footer>
  <script src="../js/nav.js"></script>
  <script>document.addEventListener("DOMContentLoaded", function () { HARTOps.mountChrome("build-track-plan"); });</script>
</body>
</html>
"""

ART = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Level Plans @PLAN@</title>
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
</style></head><body><div class="wrap"><h1>Level plans from plan @PLAN@</h1>
<p class="muted">Staging, main and upper level, drawn to scale from plan @PLAN@.</p>
<div class="lv">
%s
</div>
%s
</div></body></html>
"""


def main(svg_dir, staging_file, panel, out_site, out_art, plan):
    if not re.fullmatch(r"\d+(\.\d+)*[a-z]?", plan):
        raise SystemExit("the plan version is a number like 5.3c, not %r" % plan)
    staging = Path(staging_file).read_text()
    t, f_stage = sections(svg_dir, staging)
    b = body(t, f_stage)
    Path(out_site).write_text((SITE % (CSS, b)).replace("@PLAN@", plan))
    extra = ""
    if panel != "-":
        data = base64.b64encode(Path(panel).read_bytes()).decode()
        extra = ('<section class="panel"><h3>The panel, for comparison</h3><p class="muted">Layout Editor view of the built staging level, not to scale.</p>'
                 '<img alt="Layout Editor panel" src="data:image/png;base64,%s"></section>' % data)
    Path(out_art).write_text((ART % (CSS, b, extra)).replace("@PLAN@", plan))


if __name__ == "__main__":
    if len(sys.argv) != 7:
        sys.exit(__doc__)
    main(*sys.argv[1:7])
