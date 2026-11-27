#!/usr/bin/env python3
"""Build the track plan article (www/build/track-plan.html): the staging, main and upper level of the plan, drawn to scale.

    python3 tools/anyrail/levels_page.py [--levels DIR] [--site HTML] [--artifact HTML [--panel PNG]] [--check]

DIR (default `tools/anyrail/levels/`) holds what levels_svg.py wrote from the plan: staging.svg, main.svg, upper.svg and
levels_meta.json, which names the plan version printed on the page. HTML (default www/build/track-plan.html) is the
Build section article; never edit it by hand, rerun this. Every number on the page comes from levels_meta.json, from
block_lengths.csv and block_lengths_measured.csv (plan and timed block lengths, hartlib.block_lengths) or from the helix tracks (hartlib.railroad.read_helix_tracks:
plan_overrides.json, and preferences.json's track_labels for the names shown); nothing is typed here. A figure that
disagrees with another source, or a source that is missing, raises LevelsPageError, which main() prints as the exit
message.

Staging is drawn and signalled on the plan's lengths. block_lengths_measured.csv holds a timed length only for the blocks a loco
was timed over (the test loop and the Switch 5 to Switch 15 run); the page sets those next to the plan's.
"""
from __future__ import annotations

import argparse
import base64
import collections
import json
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import NamedTuple, TypedDict, cast

HERE = Path(__file__).resolve().parent
_HARTLIB = [p / "tools/hartlib/src" for p in HERE.parents if (p / "tools/hartlib/src").is_dir()]
if not _HARTLIB:
    raise ImportError(f"no tools/hartlib/src above {__file__}")
sys.path.insert(0, str(_HARTLIB[0]))
from hartlib import block_lengths, paths, railroad  # noqa: E402

sys.path.insert(0, str(paths.LAYOUT_SCRIPTS / "speedmatch"))
import analyze  # noqa: E402  the test loop's blocks in running order (routes.json)

sys.path.insert(0, str(HERE))
from levels_svg import switch_key  # noqa: E402

HELIX_SOURCE = railroad.Sources.under().plan_overrides     # the helix tracks: hartlib.railroad.read_helix_tracks
SITE_HTML = paths.REPO_ROOT / "www/build/track-plan.html"
CM_PER_IN = 2.54
FITTED = re.compile(r"AnyRail (\d+(?:\.\d+)*[a-z]?) loop")
PASSES = re.compile(r"\(([^,()]+?), Switch 5 to Switch 15, steps (\d+) and (\d+)\)")
PASSES_ANY = re.compile(r"\([^()]*\bsteps\b[^()]*\)")   # a note that names passes in any wording
SPREAD = re.compile(r"\+-(\d+(?:\.\d+)?) in over (\d+) laps")
PLAN_VERSION = re.compile(r"\d+(\.\d+)*[a-z]?")
LOOP_START = "OS Switch 5"          # the page runs the test loop from here
LEVEL_NAMES = {"staging": "Staging", "main": "Main", "upper": "Upper"}
TERMINAL_SWITCHES = {"7", "9", "11", "13"}   # the staging text names these
HELIX_PLAN_TOLERANCE_IN = 0.06     # block_lengths.csv holds one decimal
META_KEYS = ("plan", "levels", "helix", "ramps", "max_grade_pct", "cut_cm")
LEVEL_KEYS = ("bbox", "crossovers", "threeways", "flex_m", "ramp_m", "height_cm", "switches", "labels")


class LevelMeta(TypedDict):
    """One level of levels_meta.json (levels_svg.py)."""
    bbox: list[float]
    crossovers: int
    threeways: int
    flex_m: float
    ramp_m: float
    height_cm: float
    switches: int
    labels: list[str]


class HelixRun(TypedDict):
    """A helix track's run in levels_meta.json: its end switches, length and the length below the cut."""
    foot: str
    top: str
    cm: float
    below_cut_cm: float


class Ramp(TypedDict):
    foot: str
    top: str
    flex_m: float


class Meta(TypedDict):
    """levels_meta.json: what levels_svg.py measured on the plan."""
    plan: str
    levels: dict[str, LevelMeta]
    helix: list[HelixRun]
    ramps: list[Ramp]
    max_grade_pct: float
    cut_cm: float


class TimedRow(NamedTuple):
    """A timed block: its plan and timed lengths, and for a loop block the spread and laps its note gives."""
    name: str
    plan_in: float
    timed_in: float
    spread_in: float | None
    laps: int | None


class HelixRow(NamedTuple):
    """A helix track by the name shown for it, its end switches, its run and the run's share either side of the cut."""
    shown: str
    foot: str
    top: str
    run_in: float
    below_in: float
    above_in: float


class Sections(NamedTuple):
    """The article's parts, in page order."""
    intro: str
    staging: str
    lengths: str
    main: str
    upper: str
    helix: str


class LevelsPageError(Exception):
    """The plan, the block tables or the drawings disagree with what the page says; the message names the source and the fix."""


def inches(cm: float) -> float:
    return cm / CM_PER_IN


def height_text(cm: float) -> str:
    """"15 in (38.1 cm)" for a height read from the plan."""
    return "%g in (%.1f cm)" % (round(inches(abs(cm)), 2), abs(cm))


def read_meta(levels: Path) -> Meta:
    """levels_meta.json in `levels`, with every key the page reads."""
    path = levels / "levels_meta.json"
    try:
        meta = json.loads(path.read_text())
    except OSError as exc:
        raise LevelsPageError(f"cannot read {path} ({exc.strerror}); run levels_svg.py") from exc
    except json.JSONDecodeError as exc:
        raise LevelsPageError(f"{path} is not JSON ({exc}); rerun levels_svg.py") from exc
    if not isinstance(meta, dict):
        raise LevelsPageError(f"{path} is not an object; rerun levels_svg.py")
    for need in META_KEYS:
        if need not in meta:
            raise LevelsPageError(f"{path} has no {need!r}; rerun levels_svg.py")
    for level in LEVEL_NAMES:
        lv = meta["levels"].get(level)
        if lv is None:
            raise LevelsPageError(f"{path} has no {level} level; rerun levels_svg.py")
        missing = [k for k in LEVEL_KEYS if k not in lv]
        if missing:
            raise LevelsPageError(f"{path}: the {level} level has no {', '.join(missing)}; rerun levels_svg.py")
    return cast(Meta, meta)     # its keys are checked above


def block_rows() -> tuple[dict[str, block_lengths.Block], dict[str, block_lengths.Measured]]:
    """{user_name: Block} of block_lengths.csv (the plan lengths), and {user_name: Measured} of the timed blocks
    (block_lengths_measured.csv), which the page prints beside them."""
    try:
        return block_lengths.plan_blocks(), block_lengths.measured_lengths()     # this checkout's files
    except railroad.FactsError as exc:
        raise LevelsPageError(str(exc)) from exc


def timed_rows(blocks: Mapping[str, block_lengths.Block], measured: Mapping[str, block_lengths.Measured],
               names: Iterable[str]) -> list[TimedRow]:
    """The TimedRow of each block in `names`, each of which must be a timed block with a plan length. A loop
    block's note gives its spread and laps ("+-0.4 in over 33 laps"); a run block's has none."""
    out = []
    for name in names:
        if name not in measured:
            raise LevelsPageError(f"block_lengths_measured.csv: {name} is not a timed block")
        if name not in blocks:
            raise LevelsPageError(f"block_lengths.csv has no plan length for the timed block {name}")
        m = SPREAD.search(measured[name].note)
        out.append(TimedRow(name, blocks[name].plan_in, measured[name].measured_in,
                            float(m.group(1)) if m else None, int(m.group(2)) if m else None))
    return out


def loop_names() -> list[str]:
    """The test loop's blocks in running order from LOOP_START."""
    names = [name for _sensor, name in analyze.route_loop("loop1")]
    if LOOP_START not in names:
        raise LevelsPageError(f"{LOOP_START} is not in the test loop's blocks")
    first = names.index(LOOP_START)
    return names[first:] + names[:first]


def loop_fit_plan(names: Iterable[str], notes: Mapping[str, str]) -> str:
    """The plan version the loop timings were fitted to, from the blocks' notes ("timed share of the AnyRail 5.3b loop")."""
    found = {m.group(1) for name in names for m in [FITTED.search(notes[name])] if m}
    if len(found) != 1:
        raise LevelsPageError(f"the loop blocks' notes name {sorted(found) or 'no'} plan versions; expected one")
    return found.pop()


def run_passes(names: Iterable[str], notes: Mapping[str, str]) -> tuple[str, str, str]:
    """(loco, first step, second step) of the timed passes over the Switch 5 to Switch 15 run, as the run blocks' notes
    in block_lengths_measured.csv give them ("timed passes of 2026-11-13 (CSX 2121, Switch 5 to Switch 15, steps 24 and 48)").
    A note that names passes in other words, or two equal steps, stops the build."""
    found: set[tuple[str, str, str]] = set()
    for name in names:
        for text in PASSES_ANY.findall(notes[name]):
            m = PASSES.fullmatch(text)
            if not m:
                raise LevelsPageError(f"{name}'s note names passes as {text!r}; write it as "
                                      "'(LOCO, Switch 5 to Switch 15, steps N and M)'")
            loco, a, b = m.groups()
            found.add((loco, a, b))
    if len(found) != 1:
        raise LevelsPageError(f"the run blocks' notes name {sorted(found) or 'no'} timed passes (loco and two steps); "
                              "expected one")
    loco, first, second = found.pop()
    if first == second:
        raise LevelsPageError(f"the run's two timed passes are both at step {first}; the page says they ran at different speeds")
    return loco, first, second


def laps_note(rows: list[TimedRow]) -> str:
    """"33 laps (16 for East Ext)": the laps most blocks were timed over, and the exceptions."""
    laps = collections.Counter(r.laps for r in rows if r.laps)
    if not laps:
        raise LevelsPageError("no loop block's note in block_lengths_measured.csv gives its laps ('+-N in over M laps')")
    common = laps.most_common(1)[0][0]
    odd = ["%d for %s" % (r.laps, r.name.removeprefix("Track ").rstrip(" *")) for r in rows if r.laps and r.laps != common]
    return "%d laps%s" % (common, " (%s)" % ", ".join(odd) if odd else "")


def length_table(rows: list[TimedRow], total_label: str | None = None) -> str:
    h = ('<div class="tw"><table><thead><tr><th>Block</th><th class="n">Plan, in</th><th class="n">Timed, in</th>'
         '<th class="n">Difference</th><th class="n">&plusmn;</th></tr></thead><tbody>')
    for r in rows:
        h += '<tr><td>%s</td><td class="n">%.1f</td><td class="n">%.1f</td><td class="n">%+.1f</td><td class="n">%s</td></tr>' % (
            r.name, r.plan_in, r.timed_in, r.timed_in - r.plan_in, "%.1f" % r.spread_in if r.spread_in is not None else "&ndash;")
    if total_label:
        plan, timed = sum(r.plan_in for r in rows), sum(r.timed_in for r in rows)
        h += ('<tr><td><b>%s</b></td><td class="n"><b>%.1f</b></td><td class="n"><b>%.1f</b></td>'
              '<td class="n"><b>%+.1f</b></td><td></td></tr>') % (total_label, plan, timed, timed - plan)
    return h + "</tbody></table></div>"


def figure(svg: str, bbox: list[float], label: str) -> str:
    """The level's drawing, cropped to its bbox with a margin, and a 100 cm scale bar."""
    pad = 12
    x, y, w, hgt = bbox[0] - pad, bbox[1] - pad, bbox[2] - bbox[0] + 2 * pad, bbox[3] - bbox[1] + 2 * pad
    bar = '<line class="scale" x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f"/><text class="rl" x="%.0f" y="%.0f">100 cm</text>' % (
        x + 6, y + hgt - 8, x + 106, y + hgt - 8, x + 6, y + hgt - 11)
    return ('<div class="plan"><svg viewBox="%.0f %.0f %.0f %.0f" role="img" aria-label="%s">%s%s</svg></div>'
            % (x, y, w, hgt, label, svg, bar))


def summary_table(meta: Meta) -> str:
    h = ('<div class="tw"><table><thead><tr><th>Level</th><th class="n">Height above main</th>'
         '<th class="n">Switch parts</th><th class="n">Flex track</th></tr></thead><tbody>')
    for level in LEVEL_NAMES:
        lv = meta["levels"][level]
        flex = lv["flex_m"] + lv["ramp_m"]
        h += '<tr><td>%s</td><td class="n">%s</td><td class="n">%d</td><td class="n">%.1f m</td></tr>' % (
            LEVEL_NAMES[level], ("%+.1f cm" % lv["height_cm"]) if lv["height_cm"] else "0 cm", lv["switches"], flex)
    return h + "</tbody></table></div>"


def switch_note(lv: LevelMeta) -> str:
    """What the level's switch parts are: the double crossover and three-way, and the numbers two parts share."""
    if lv["threeways"] > 1 or lv["crossovers"] > 1:
        raise LevelsPageError("the level has more than one three-way or double crossover; switch_note needs a rewrite")
    bits = [name for name, n in (("a three-way", lv["threeways"]), ("a double crossover", lv["crossovers"])) if n]
    twice = sorted((s for s, n in collections.Counter(lv["labels"]).items() if n > 1), key=switch_key)
    note = ""
    if bits:
        note += " %s counts as one part." % " and ".join(bits).capitalize() if len(bits) == 1 else \
            " %s each count as one part." % " and ".join(bits).capitalize()
    if twice:
        note += " Switches %s each have two turnouts that carry the one number." % _and(twice)
    return note


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def helix_rows(meta: Meta, blocks: Mapping[str, block_lengths.Block]) -> list[HelixRow]:
    """The HelixRow of each helix track by the name shown for it (preferences.json track_labels), from the plan's
    runs; every run must match its block's plan length."""
    try:
        helix = railroad.read_helix_tracks(HELIX_SOURCE)
    except railroad.FactsError as exc:
        raise LevelsPageError(str(exc)) from exc
    named = {(h.staging_switch, h.level_switch): h for h in helix.values()}
    rows = []
    for t in meta["helix"]:
        h = named.get((t["foot"], t["top"]))
        if h is None:
            raise LevelsPageError(f"{HELIX_SOURCE.name} has no helix track from Switch {t['foot']} to Switch {t['top']}")
        if h.block not in blocks:
            raise LevelsPageError(f"block_lengths.csv has no plan length for the helix block {h.block}")
        run = inches(t["cm"])
        if abs(run - blocks[h.block].plan_in) > HELIX_PLAN_TOLERANCE_IN:
            raise LevelsPageError(f"the plan's run from Switch {t['foot']} to {t['top']} is {run:.1f} in; "
                                  f"block_lengths.csv has {blocks[h.block].plan_in} in for {h.block}")
        below = inches(t["below_cut_cm"])
        rows.append(HelixRow(h.shown, t["foot"], t["top"], run, below, run - below))
    return rows


def climb(meta: Meta) -> Ramp:
    """The one ramp from main to upper, once the plan's ramps are checked to be the two helix tracks and it."""
    climbs = [r for r in meta["ramps"] if r["foot"] == "main" and r["top"] == "upper"]
    if len(meta["helix"]) != 2 or len(climbs) != 1 or len(meta["ramps"]) != 3:
        raise LevelsPageError("the plan's ramps are not two helix tracks and one climb from main to upper; the helix text needs a rewrite")
    return climbs[0]


def figures(levels: Path, meta: Meta) -> dict[str, str]:
    """{level: its drawing}, from the level's svg in `levels`."""
    out = {}
    for k in LEVEL_NAMES:
        lv = meta["levels"][k]
        path = levels / (k + ".svg")
        try:
            svg = path.read_text()
        except OSError as exc:
            raise LevelsPageError(f"cannot read {path} ({exc.strerror}); run levels_svg.py") from exc
        out[k] = figure(svg, lv["bbox"], "%s level of plan %s" % (LEVEL_NAMES[k], meta["plan"]))
    return out


def intro_text(meta: Meta) -> str:
    lv = meta["levels"]
    return (
        '<p>Track plans of the staging, main and upper levels, drawn to scale in centimetres from layout plan version %s. '
        'Staging lies %s below the main level and the upper level %s above it. Two helix tracks join staging to the main level, '
        'and a ramp of %.1f m of flex climbs from the main level to the upper level. The drawings show track only and are generated from the plan file by script; '
        'each turnout carries its switch number on the railroad.</p>' % (
            meta["plan"], height_text(lv["staging"]["height_cm"]), height_text(lv["upper"]["height_cm"]), climb(meta)["flex_m"])
        + summary_table(meta)
        + '<p class="muted">Switch parts are the plan&rsquo;s turnouts. Flex track is the total length of the flex pieces on the level, ramps included.</p>')


def staging_text(low: LevelMeta, fig: str) -> str:
    if not TERMINAL_SWITCHES <= set(low["labels"]):
        raise LevelsPageError("the staging drawing has no Switch 7, 9, 11 and 13; the engine terminal text needs them")
    return (
        '<div class="key"><span class="k-trk">track</span><span class="k-ramp">helix, below its top layer</span></div>'
        + fig +
        '<p>%d switch parts and %.1f m of flex, with %.1f m of helix below its top layer drawn dotted. '
        'The plan includes the Switch 7 crossover, Switches 9, 11 and 13, and the engine terminal tracks EH-1 to EH-3.%s</p>'
        % (low["switches"], low["flex_m"], low["ramp_m"], switch_note(low)))


def timed_groups(blocks: Mapping[str, block_lengths.Block],
                 measured: Mapping[str, block_lengths.Measured]) -> tuple[list[TimedRow], list[TimedRow]]:
    """(the test loop's rows, the Switch 5 to 15 run's rows), each in running order. Every timed block is on one."""
    loop = timed_rows(blocks, measured, loop_names())
    on_loop = {r.name for r in loop}
    run_names = [n for _sensor, n in analyze.route_loop("loop2")
                 if n not in on_loop and n in measured]  # in running order
    stray = sorted(n for n in measured if n not in on_loop and n not in run_names)
    if stray:
        raise LevelsPageError(f"timed blocks on neither the test loop nor the Switch 5 to 15 run: {', '.join(stray)}; "
                              "the lengths section needs a row group for them")
    return loop, timed_rows(blocks, measured, run_names)


def lengths_text(plan: str, loop: list[TimedRow], run: list[TimedRow], notes: Mapping[str, str]) -> str:
    laps = laps_note(loop)
    loop_plan = loop_fit_plan((r.name for r in loop), notes)
    loco, slow, fast = run_passes((r.name for r in run), notes)
    return (
        '<h3>Plan lengths and timed lengths</h3>'
        '<p>Staging is drawn and signalled on the plan&rsquo;s lengths. JMRI holds a timed length for the blocks a loco was timed over and the plan length for the rest. '
        'The test loop was timed over %s with each block taken as its share of the loop, fitted to the turnout positions of plan %s. '
        '%s timed the Switch 5 to Switch 15 run on two passes at different speeds (steps %s and %s). '
        'The loop blocks add up to %s in timed against %s in on plan %s.</p>'
        '<h3>Test loop</h3><p class="muted">Inches, in the order a loco runs the loop from Switch 5. &plusmn; is the spread over the laps.</p>'
        % (laps, loop_plan, loco, slow, fast, format(sum(r.timed_in for r in loop), ",.1f"),
           format(sum(r.plan_in for r in loop), ",.1f"), plan)
        + length_table(loop, "Loop total")
        + '<h3>Switch 5 to Switch 15 run</h3>' + length_table(run))


def main_text(mid: LevelMeta, fig: str) -> str:
    return (
        '<div class="key"><span class="k-trk">track</span><span class="k-ramp">the helix&rsquo;s top layer, and the climb to the upper level</span></div>'
        + fig +
        '<p>%d switch parts and %.1f m of flex, with %.1f m of ramp drawn dotted.%s</p>'
        % (mid["switches"], mid["flex_m"], mid["ramp_m"], switch_note(mid)))


def upper_text(high: LevelMeta, fig: str) -> str:
    return (
        '<div class="key"><span class="k-trk">track</span></div>' + fig +
        '<p>%d switch parts and %.1f m of flex at %s above the main level.%s</p>'
        % (high["switches"], high["flex_m"], height_text(high["height_cm"]), switch_note(high)))


def helix_text(meta: Meta, helix: list[HelixRow]) -> str:
    cut = meta["cut_cm"]
    low, mid = meta["levels"]["staging"], meta["levels"]["main"]
    h = ('<div class="tw"><table><thead><tr><th>Helix track</th><th class="n">From staging</th><th class="n">To main</th>'
         '<th class="n">Run, in</th><th class="n">Below %g cm, in</th><th class="n">Above, in</th></tr></thead><tbody>' % cut)
    for r in helix:
        h += ('<tr><td>%s</td><td class="n">Switch %s</td><td class="n">Switch %s</td><td class="n">%.1f</td>'
              '<td class="n">%.1f</td><td class="n">%.1f</td></tr>') % (r.shown, r.foot, r.top, r.run_in, r.below_in, r.above_in)
    return (
        '<p>The two helix tracks run from Switches %s on staging up to Switches %s on the main level, a rise of %s. '
        'The steepest piece of flex in any ramp is %.2f%%. The run is the plan&rsquo;s length from switch to switch, flex and straight track together; '
        'the schematic draws staging&rsquo;s share, up to the %g cm cut, and the main level&rsquo;s share above it. '
        'More on the <a href="../helix/index.html">helix page</a>.</p>'
        % (_and(sorted({r.foot for r in helix}, key=switch_key)), _and(sorted({r.top for r in helix}, key=switch_key)),
           height_text(mid["height_cm"] - low["height_cm"]), meta["max_grade_pct"], cut)
        + h + "</tbody></table></div>")


def sections(levels: Path, meta: Meta) -> Sections:
    """The article's parts from the drawings in `levels`, `meta` and the block tables."""
    blocks, measured = block_rows()
    lv = meta["levels"]
    fig = figures(levels, meta)
    helix = helix_rows(meta, blocks)
    staging = staging_text(lv["staging"], fig["staging"])
    intro = intro_text(meta)
    loop, run = timed_groups(blocks, measured)
    notes = {name: m.note for name, m in measured.items()}
    return Sections(intro=intro, staging=staging, lengths=lengths_text(meta["plan"], loop, run, notes),
                    main=main_text(lv["main"], fig["main"]), upper=upper_text(lv["upper"], fig["upper"]),
                    helix=helix_text(meta, helix))


CSS = """
.plan{background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:8px;overflow-x:auto}
.plan svg{width:100%;height:auto;min-width:520px;display:block}
polyline,line,circle{fill:none;stroke-linecap:round}
.trk{stroke:var(--track);stroke-width:1.6}
.ramp{stroke:var(--sw7);stroke-width:1.5;stroke-dasharray:2 2.4}
.to{stroke:var(--fg);stroke-width:2}
.rl{font:5.5px var(--body);fill:var(--muted)}
.tl{font:600 5px var(--display);fill:var(--muted)}
.scale{stroke:var(--fg);stroke-width:1.4}
.key{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.85rem;color:var(--muted);margin-bottom:8px}
.key span::before{content:"";display:inline-block;width:22px;height:0;border-top:3px solid;vertical-align:middle;margin-right:6px}
.k-ramp::before{border-color:var(--sw7)!important;border-top-style:dotted!important}.k-trk::before{border-color:var(--track)!important}
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


def body(t: Sections) -> str:
    return (t.intro +
            '<section id="staging"><h2><span class="num">01</span>Staging level</h2>' + t.staging + t.lengths + '</section>'
            '<section id="main"><h2><span class="num">02</span>Main level</h2>' + t.main + '</section>'
            '<section id="upper"><h2><span class="num">03</span>Upper level</h2>' + t.upper + '</section>'
            '<section id="helix"><h2><span class="num">04</span>Helix</h2>' + t.helix + '</section>')


SITE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Track plan — HART</title>
  <meta name="description" content="Track plans of the staging, main and upper levels drawn to scale from plan @PLAN@, with the helix and the plan and timed block lengths.">
  <link rel="stylesheet" href="../css/ops.css">
  <link rel="stylesheet" href="../css/article.css">
  <style>
    :root{--track:#6b7a86;--sw7:#a85a10;--fg:var(--ink);--display:var(--font-display);--body:var(--font-body)}
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
        <p class="standfirst">Staging, main and upper level drawn to scale from plan @PLAN@, with the helix and the plan and timed block lengths.</p>
        <p class="byline">The Build · November 2026</p>
      </header>
      <nav class="feature-toc" aria-label="On this page">
        <h2>On this page</h2>
        <ol>
          <li><a href="#staging">Staging level</a></li>
          <li><a href="#main">Main level</a></li>
          <li><a href="#upper">Upper level</a></li>
          <li><a href="#helix">Helix</a></li>
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
:root{--bg:#f6f7f5;--fg:#1d2320;--muted:#5d6862;--rule:#d5dbd7;--track:#8d9892;--sw7:#b5651d;--card:#ffffff;--display:"Space Grotesk",system-ui,sans-serif;--body:"Inter",system-ui,sans-serif;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141816;--fg:#e4e9e6;--muted:#9aa59f;--rule:#2c3330;--track:#6b7570;--sw7:#e0994f;--card:#1b201e;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#141816;--fg:#e4e9e6;--muted:#9aa59f;--rule:#2c3330;--track:#6b7570;--sw7:#e0994f;--card:#1b201e;color-scheme:dark}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 var(--body)}
.wrap{max-width:1100px;margin:0 auto;padding:24px max(16px,env(safe-area-inset-right,0px)) 48px max(16px,env(safe-area-inset-left,0px))}
h1{font-family:var(--display);font-size:1.7rem;margin:0 0 4px;text-wrap:balance}
h2{font-family:var(--display);font-size:1.35rem;margin:2.2rem 0 8px}
h3{font-family:var(--display);font-size:1.05rem;margin:1.6rem 0 6px}
p{margin:.5rem 0;max-width:70ch}.muted{color:var(--muted)}
a{color:var(--track)}
%s
.panel img{border:1px solid var(--rule);border-radius:6px;background:#121418;max-width:100%%}
</style></head><body><div class="wrap"><h1>Level plans from plan @PLAN@</h1>
<p class="muted">Staging, main and upper level, drawn to scale from plan @PLAN@.</p>
<div class="lv">
%s
</div>
@PANEL@
</div></body></html>
"""


def render(levels: Path) -> tuple[str, str]:
    """(site html, artifact html without a panel picture) for the drawings in `levels`."""
    meta = read_meta(levels)
    plan = meta["plan"]
    if not isinstance(plan, str) or not PLAN_VERSION.fullmatch(plan):
        raise LevelsPageError(f"the plan version is a number like 5.3c, not {plan!r}")
    b = body(sections(levels, meta))
    return (SITE % (CSS, b)).replace("@PLAN@", plan), (ART % (CSS, b)).replace("@PLAN@", plan)


def panel_section(png: Path) -> str:
    """The artifact copy's Layout Editor picture, embedded."""
    try:
        data = base64.b64encode(png.read_bytes()).decode()
    except OSError as exc:
        raise LevelsPageError(f"cannot read the panel picture {png} ({exc.strerror})") from exc
    return ('<section class="panel"><h3>The panel, for comparison</h3><p class="muted">Layout Editor view of the built staging level, not to scale.</p>'
            '<img alt="Layout Editor panel" src="data:image/png;base64,%s"></section>' % data)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--levels", default=str(HERE / "levels"), help="folder levels_svg.py wrote")
    ap.add_argument("--site", default=str(SITE_HTML), help="the Build article to write")
    ap.add_argument("--artifact", help="also write the standalone artifact copy here")
    ap.add_argument("--panel", help="a Layout Editor picture for the artifact copy only")
    ap.add_argument("--check", action="store_true", help="write nothing; fail if the site article differs")
    a = ap.parse_args(argv)
    if a.panel and not a.artifact:
        ap.error("--panel goes into the artifact copy only; give --artifact too")
    try:
        site, art = render(Path(a.levels))
    except LevelsPageError as exc:
        raise SystemExit(str(exc)) from exc
    if a.check:
        if not Path(a.site).is_file() or Path(a.site).read_text() != site:
            sys.exit(f"{a.site} differs from what levels_page.py builds; rerun it without --check")
        print("levels_page: the site article is current")
        return
    Path(a.site).write_text(site)
    if a.artifact:
        # the panel picture goes into the artifact copy only, so a missing one leaves the site article written
        try:
            extra = panel_section(Path(a.panel)) if a.panel else ""
        except LevelsPageError as exc:
            raise SystemExit(str(exc)) from exc
        Path(a.artifact).write_text(art.replace("@PANEL@", extra))


if __name__ == "__main__":
    main()
