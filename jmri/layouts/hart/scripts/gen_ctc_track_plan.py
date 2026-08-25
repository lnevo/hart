#!/usr/bin/env python3
"""Generate the CTC panel track diagram (v28 — Master 4 row order).

Match CATS Master 4 (`wiki/MASTER4_SCHEMATIC.md`): one straight focused main
on the TOP operating row, W-1/W-2 above it, Scale/Barn/S-1/K-2 on the middle
row, Main West gapped on the bottom row.

Diagram columns (west → east) follow the new schematic, not the live lever
map: blank col 1, col 2 = Brick / 100, 101 in the 2/3 gap (W-yard), col 4 = 102 Plane.
Live CTC UniqueIDs are unchanged (lever 1 still codes Switch 101).

  N  88-92   focused main: Brick 100 → 101 (W-yard above) → 102 → 117b →
             Main East → 112 → East Lead → 113a → 114 → McKeesport.
  S 111-115  Scale (off 102 only → 117) → Barn → 116 → S-1 → 103 →
             111b → 110 → K-2.
  M 134-138  GAP under 103 (vertical `\\` through empty M, not a MW frog);
             Main West → 111a → West Main Ext (110 diamond) → 113b → 115
             → McKees Rocks. Engine House is a single spur BELOW M under
             levers 7/9.

102 is a single turnout on the focused main (not a crossover): Closed =
through to 117b; Thrown = `\\` Scale → 117. There is no 100→102 Scale
siding — 100 is Brick OS on the main only (bar, no down-east spur).
113 skips S: 113a os-r-e and 113b os-r-w-thin stacked in the same column,
both `\\`. 103 and 110 are labeled SOUTH YD stubs (frog → horizontal →
bumper), not hanging slashes and not 104–109 frogs.

Previous (v26 — 100 Scale spur gone, 113 stacked; yard still thin slashes). v22 focused main on M. Original v8:

Machine slots are 65px wide (slot = x//65). Blank slots 0, 4, 8, 12 and 16
— four interlockings of three lever columns each: Brick/Plane slots 1-3
(SW101/100/102), Barn 5-7 (117/116/103), East End 9-11 (111/110/112 —
SW107/108/109 are hand-throw, no levers and no lamps), Princess 13-15
(113/114/115). Switch icons sit at slot*65 + 21.

The gold background is generated too: 12px left cap at x=0, one 65px tile
per slot at x=12+65*slot (Panel-blank-7 for blank slots,
Panel-switch-7 for 116/103 switch-only, Panel-sw-sig-7 for the rest),
right cap at x=1117.

South Yard body tracks are omitted. 103 and 110 are SOUTH YD stubs
(bumper + label), same grammar as Engine House / W-1.
East stubs (K-1, K-2, McKees Rocks, McKeesport) still end flush at x=1105
with lamps at x=1060. W-1/W-2 lamps stack on the Brick-Plane body (x=161).

Thin 2px gifs and the os-*-thin turnout icons (SW103/110/116) come from
"preference:ctc/icons/*.gif" — deploy to JMRI_UserFiles/ctc/icons/.

CTC-held signal masts sit on the diagram as Quaker Valley-style proto
lollipops (stock USS `sig-h-2` / `sig-d-1`, recolored by aspect). Two-head
homes are live `<signalmasticon>` imageset `ctc` / `ctc-w`; dwarfs are
`<signalheadicon>` on the single IH* head. 116/103 have no CTC homes.

Writes ctc/GUIObjects.xml and the embedded <paneleditor> in
tables/new_tables.xml (never tables.xml). Normalizes the panel window
to show all 17 slots.
"""
import re
import sys

U = "program:resources/icons/USS/"
THIN = "preference:ctc/icons/"

BG = """<positionablelabel x="{x}" y="0" level="1" forcecontroloff="false" hidden="no" positionable="false" showtooltip="false" editable="true" icon="yes" class="jmri.jmrit.display.configurexml.PositionableLabelXml">
      <icon url="{u}background/{gif}" scale="1.0">
        <rotation>0</rotation>
      </icon>
    </positionablelabel>"""

TURNOUT = """<turnouticon turnout="{name}" x="{x}" y="{y}" level="7" forcecontroloff="true" hidden="no" positionable="true" showtooltip="false" editable="true" tristate="false" momentary="false" directControl="false" class="jmri.jmrit.display.configurexml.TurnoutIconXml">
      <icons>
        <closed url="{closed}" scale="1.0">
          <rotation>{rot}</rotation>
        </closed>
        <thrown url="{thrown}" scale="1.0">
          <rotation>{rot}</rotation>
        </thrown>
        <unknown url="{unknown}" scale="1.0">
          <rotation>{rot}</rotation>
        </unknown>
        <inconsistent url="{inconsistent}" scale="1.0">
          <rotation>{rot}</rotation>
        </inconsistent>
      </icons>
      <iconmaps />
    </turnouticon>"""


def turnout_urls(kind):
    """Resolve a TURNOUTS kind ("swap:"/"thin:" prefixes) to state gif urls."""
    swap = kind.startswith("swap:")
    if swap:
        kind = kind[5:]
    if kind.startswith("thin:"):
        base = THIN + kind[5:]
    else:
        base = U + kind
    urls = dict(closed=base + "-closed.gif", thrown=base + "-thrown.gif",
                unknown=base + "-unknown.gif", inconsistent=base + "-inconsistent.gif")
    if swap:
        urls["closed"], urls["thrown"] = urls["thrown"], urls["closed"]
    return urls

LAMP = """<sensoricon sensor="{sensor}" x="{x}" y="{y}" level="10" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" momentary="false" icon="yes" class="jmri.jmrit.display.configurexml.SensorIconXml">
      <tooltip>{tip}</tooltip>
      <active url="{u}sensor/red-on.gif" scale="1.0">
        <rotation>0</rotation>
      </active>
      <inactive url="{u}sensor/red-off.gif" scale="1.0">
        <rotation>0</rotation>
      </inactive>
      <unknown url="{u}sensor/s-unknown.gif" scale="1.0">
        <rotation>0</rotation>
      </unknown>
      <inconsistent url="{u}sensor/s-inconsistent.gif" scale="1.0">
        <rotation>0</rotation>
      </inconsistent>
      <iconmaps />
    </sensoricon>"""

TRACK = """<positionablelabel x="{x}" y="{y}" level="3" forcecontroloff="false" hidden="no" positionable="true" showtooltip="false" editable="true" icon="yes" class="jmri.jmrit.display.configurexml.PositionableLabelXml">
      <icon url="{url}{gif}" degrees="0" scale="1.0">
        <rotation>{rot}</rotation>
      </icon>
    </positionablelabel>"""

TEXT = """<positionablelabel x="{x}" y="{y}" level="4" forcecontroloff="false" hidden="no" positionable="true" showtooltip="false" editable="true" text="{text}" fontname="Dialog.plain" size="{size}" style="1" red="{red}" green="{green}" blue="{blue}" hasBackground="no" justification="{just}" class="jmri.jmrit.display.configurexml.PositionableLabelXml">
      <tooltip>Text Label</tooltip>
    </positionablelabel>"""

T = "track/turnout/"
X = "track/crossover/"

N_SLOTS = 17
BLANK_SLOTS = {0, 4, 8, 12, 16}
# 116 and 103: switch lever only — no SIGNAL plate (brass blanks on the tile)
SWITCH_ONLY_SLOTS = {6, 7}

# (turnout name, x, y, icon kind[, rot]). Bar rows: y+6..10 (os-l-w/os-r-e top),
# y+29..33 (os-l-e/os-r-w bottom). "thin:" kinds are the custom 2px-leg
# icons from preference:ctc/icons/. "swap:" swaps the closed/thrown gifs:
# used where the drawn BAR is the mainline but JMRI Thrown (100/112/114/115
# are Thrown when set for the main). Lit route then matches field state.
# N/S/M sit 20px below v27 so W-1/W-2 are true horizontals under the
# station names (not a cramped `/` in the banner). 100 on slot 1 / col 2
# (x=86). 101 sits in the 2/3 gap on 100's `/` (x=114) — centering it in
# col 3 made the frog read as the 3/4 gap. 102 on slot 3 / col 4 (x=216).
# 113b is 30px east of 113a so the two `\\` continue (same-x put 113b's
# `\\` west of 113a's, the wrong way).
TURNOUTS = [
    # Blank = col 1. 100 centered in col 2 (slot 1). os-l-e: through on N,
    # `/` up-east is the diverging lead into 101.
    ("Switch 100", 86,  79,  "swap:" + T + "left/east/os-l-e"),
    # 101 in the 2/3 gap, on 100's `/`. os-ne-r: throat SW continues that `/`;
    # NE `/` flattens to W-1 (top); east bar is W-2 (between W-1 and main).
    ("Switch 101", 114, 55,  T + "right/ne/os-ne-r"),
    # 102 Plane, col 4 (slot 3).
    ("Switch 102", 216, 102, T + "right/east/os-r-e"),
    ("Switch 117", 346, 102, X + "right/os-r-sc"),  # `\\` (os-l-sc is `/`)
    ("Switch 116", 436, 125, "thin:os-l-w-thin"),
    ("Switch 103", 482, 125, "thin:os-r-e-thin"),
    ("Switch 111", 606, 125, X + "left/os-l-sc"),  # RH xover; os-r-sc is `\\` (117)
    ("Switch 110", 671, 125, "thin:os-l-w-thin"),
    ("Switch 112", 736, 102, "swap:" + T + "left/west/os-l-w"),
    ("Switch 113", 866, 102, T + "right/east/os-r-e"),
    ("Switch 113", 888, 125, T + "right/west/os-r-w"),  # stock `\\`; 8px west so it meets 113a
    ("Switch 114", 931, 102, "swap:" + T + "right/east/os-r-e"),  # slot 14 / 114 column
    ("Switch 115", 967, 148, "swap:" + T + "right/east/os-r-e"),  # 114|115 column gutter
]


def unpack_turnout(t):
    name, x, y, kind = t[:4]
    rot = t[4] if len(t) > 4 else 0
    return name, x, y, kind, rot

# (sensor, x, y, tooltip). Block lamps sit embedded on their track line
# (y = bar top - 8). Turnout OS lamps form a machine row at y200, replacing
# the stock Unlocked indicators (stripped below; sensors still exist, GUI
# only) at x = 99/164/229, 359/424/489, 619/684/749, 879/944/1009, with the
# switch number labelled underneath; crossover columns get their two OS
# lamps side by side, centered on the column, UPPER track's lamp on the left.
LAMPS = [
    # Brick west stub: same Main West circuit as the lamp west of 111
    # (CATS fold SHARED to (1,6)). Westbound through 111 lights here too.
    ("Block 2-1",  24,  100, "Main West (Brick west / westbound of 111)"),
    ("Block 4-4",  161, 47,  "W-1"),
    ("Block 4-3",  161, 71,  "W-2"),
    ("Block 4-2",  99,  200, "OS 100"),
    ("Block 4-1",  164, 200, "OS 101"),
    ("Block 4-6",  161, 100, "Brick-Plane (100–102)"),  # midway 100 (86–126) and 102 (216–256)
    ("Block 4-7",  286, 100, "East Main Ext (102–117b)"),  # stacked on Scale
    ("Block 4-5",  229, 200, "OS 102"),
    ("Block 4-8",  286, 123, "Scale"),
    ("Block 13-3", 347, 200, "OS 117 (yard side)"),
    ("Block 13-4", 371, 200, "OS 117b (main side)"),
    ("Block 13-1", 404, 123, "Barn"),
    ("Block 3-1",  424, 200, "OS 116 (Barn)"),
    ("Block 3-2",  489, 200, "OS 103"),
    ("Block 2-8",  546, 123, "S-1"),
    # Column 5 west edge: between W-1/W-2 (161) and Scale (286), east of 102.
    ("Block 2-1",  272, 146, "Main West (approach to 111)"),
    ("Block 2-3",  546, 100, "Main East"),
    ("Block 12-4", 607, 200, "OS 111a (Main West side)"),
    ("Block 12-6", 631, 200, "OS 111b (yard side)"),
    ("Block 12-7", 684, 200, "OS 110"),
    ("Block 12-8", 749, 200, "OS 112"),
    ("Block 1-7",  806, 100, "East Lead (112L–113RB)"),
    ("Block 1-8",  806, 146, "West Main Ext (111-113)"),
    ("Block 1-5",  867, 200, "OS 113b (Main West side)"),
    ("Block 1-6",  891, 200, "OS 113a (East Lead side)"),
    ("Block 1-3",  944, 200, "OS 114 + K-2 (one circuit)"),
    ("Block 1-4",  1009, 200, "OS 115 + K-1 (one circuit)"),
    ("Block 1-1",  1043, 146, "McKees Rocks (through 115 / 115LB)"),
    ("Block 1-4",  1072, 172, "K-1 (diverging 115 / 115LA)"),
    ("Block 1-2",  1043, 100, "McKeesport (through 114 / 114LB)"),
    ("Block 1-3",  1072, 123, "K-2 (diverging 114 / 114LA)"),
]

# (x, y, gif, rotation) -- line bar rows: line025 2-6, line050 3-7, line1 4-8,
# line25 9-13; b-45 30x30 "\" (rotation 1 -> "/"). thin* gifs are 2px lines
# from preference:ctc/icons/ (thin044 44px, thin085 85px, thin-45 15x15 "\",
# rotation 1 -> "/").
# line1.gif is 85px wide but ink is only x+7..x+78 (71px). Adjacent tiles
# placed 85px apart leave a ~14px hole — step 70 so ink overlaps.
TRACKS = [
    # W-1 / W-2: stop west of East Main Ext (label left ~256).
    (145, 52,  "line050.gif", 0),   # W-1
    (175, 52,  "line050.gif", 0),   # through lamp 161, ink ends 216
    (214, 50,  "thin-end.gif", 0),
    (152, 76,  "line050.gif", 0),   # W-2
    (182, 76,  "line050.gif", 0),
    (221, 74,  "thin-end.gif", 0),
    # N main cols 1–3 through 100 into 102 (col 4 / slot 3), then east
    (0,   105, "line050.gif", 0),   # west stub to the frame
    (21,  105, "line050.gif", 0),   # col 1 approach
    (58,  106, "line025.gif", 0),
    (126, 105, "line050.gif", 0),   # Brick-Plane after OS 100 (86–126)
    (155, 105, "line050.gif", 0),   # stop before OS 102 (216)
    (168, 105, "line050.gif", 0),
    (258, 104, "line1.gif",   0),   # East Main Ext (after OS 102, before OS 117)
    (392, 104, "line1.gif",   0),   # Main East after OS 117b
    (462, 104, "line1.gif",   0),   # join — line1 ink is only 71 of 85px
    (477, 104, "line1.gif",   0),
    (524, 99,  "line25.gif",  0),
    (650, 104, "line1.gif",   0),   # Main East to OS 112 (736)
    (778, 104, "line1.gif",   0),   # East Lead after OS 112
    (820, 105, "line050.gif", 0),   # into 113a
    (906, 105, "line050.gif", 0),   # East Lead 113a → 114 (was a 25px hole)
    (965, 104, "line1.gif",   0),   # McKeesport after OS 114 (931–971)
    (1032, 104, "line1.gif",  0),
    (1102, 104, "line1.gif",   0),   # to east frame (overlap, no tile hole)
    # S Scale off 102 then Barn / S-1 / K-2
    (248, 127, "line1.gif",   0),   # Scale off 102 (icon at x216)
    (321, 129, "line025.gif", 0),
    (392, 129, "line025.gif", 0),
    (394, 128, "line050.gif", 0),
    (522, 127, "line1.gif",   0),
    (648, 129, "line025.gif", 0),
    (713, 129, "line025.gif", 0),
    (965, 127, "line1.gif",   0),   # K-2 spur after OS 114 (no bumper)
    (1024, 128, "line050.gif", 0),
    (1058, 128, "line050.gif", 0),  # through K-2 lamp
    (1090, 129, "line025.gif", 0),
    # M: Main West is one circuit (Block 2-1) from the west frame through
    # the South Yard OS lamp into 111 — no mid-block gaps. line1 tiles
    # step 70px so ink overlaps. OS cut after 111L, then West Main Ext.
    (0,   151, "line050.gif", 0),
    (0,   150, "line1.gif",   0),
    (70,  150, "line1.gif",   0),
    (140, 150, "line1.gif",   0),
    (210, 150, "line1.gif",   0),
    (280, 150, "line1.gif",   0),
    (350, 150, "line1.gif",   0),
    (420, 150, "line1.gif",   0),
    (490, 150, "line1.gif",   0),
    (546, 151, "line050.gif", 0),
    (562, 151, "line050.gif", 0),   # into 111 (icon 606–646)
    (655, 151, "line050.gif", 0),   # WME just east of 111L
    (690, 150, "line1.gif",   0),
    (760, 150, "line1.gif",   0),
    (820, 151, "line050.gif", 0),
    (838, 151, "line050.gif", 0),   # WME up to OS 113b (888)
    (927, 151, "line050.gif", 0),   # McKees Rocks after 113b, into 115 (967)
    (1000, 150, "line1.gif",   0),   # McKees Rocks after OS 115
    (1070, 150, "line1.gif",   0),
    (1110, 150, "line1.gif",   0),
    # K-1 spur below M (diverging 115); no bumper
    (1000, 177, "line1.gif",   0),
    (1058, 178, "line050.gif", 0),
    (1090, 179, "line025.gif", 0),
    # Engine House: two thin stalls off 116
    (422, 156, "thin-45.gif", 1),
    (378, 169, "thin044.gif", 0),
    (374, 164, "thin-end.gif", 0),
    (410, 168, "thin-45.gif", 1),
    (366, 181, "thin044.gif", 0),
    (362, 176, "thin-end.gif", 0),
    # 103 `\\` and 110 `/` are colinear 15px tiles into one SOUTH YD
    # that ends at the east ladder (no overshoot).
    (520, 155, "thin-45.gif", 0),   # 103 `\\`
    (534, 169, "thin-45.gif", 0),
    (548, 183, "thin-45.gif", 0),
    (562, 195, "thin044.gif", 0),   # SY bar 562–630
    (595, 195, "thin035.gif", 0),
    (658, 155, "thin-45.gif", 1),   # 110 `/` (straight)
    (644, 169, "thin-45.gif", 1),
    (630, 183, "thin-45.gif", 1),
]

WHITE = dict(red=255, green=255, blue=255)
CREAM = dict(red=220, green=220, blue=180)
BLACK = dict(red=0, green=0, blue=0)
# McKeesport / McKees Rocks share a right edge over the stacked lamps.
# K-1 / K-2 sit on the spur bumpers, inside the gold cap (x=1117).
EAST_RAIL = 1076
K_RAIL = 1108
# Drop the plant below the gold header / CP names, and leave a gap
# between SOUTH YD and the OS lamp row (was ~5px).
Y_PLANT = 40
Y_OS = 84  # plant drop + extra air under the schematic


def map_y(y):
    """Header/CP names stay; plant drops; OS lamps + numbers drop further."""
    if y <= 36:
        return y
    if y >= 200:
        return y + Y_OS
    return y + Y_PLANT


def unpack_text(t):
    x, y, text, size, col = t[:5]
    just = t[5] if len(t) > 5 else "left"
    return x, y, text, size, col, just


def _text_width(text, size):
    from PIL import ImageFont
    try:
        pt = 12 if size >= 12 else 9
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", pt)
    except OSError:
        return int(round(size * 0.62 * len(text)))
    box = font.getbbox(text)
    return box[2] - box[0]


def label_origin(x, text, size, just):
    """JMRI x is the left of the label. 'right' x is the east rail edge;
    'center' x is the midpoint (e.g. occupancy lamp center)."""
    w = _text_width(text, size)
    if just == "right":
        return x - w
    if just == "center":
        return x - w // 2
    return x


# (x, y, text, size, color[, justification])
# Princess stubs: x is the RIGHT edge (just="right"); others are left origin.
TEXTS = [
    # banner engraved in the gold band (tile rows 0-33)
    (415, 8, "HART RAILROAD - NEVILLE ISLAND", 16, BLACK),
    (78,  36, "BRICK",     12, WHITE),
    (205, 36, "PLANE",     12, WHITE),
    (347, 36, "BARN",      12, WHITE),
    (645, 36, "EAST END",  12, WHITE),
    (905, 36, "PRINCESS",  12, WHITE),
    (218, 47,  "W-1", 8, CREAM),
    (225, 71,  "W-2", 8, CREAM),
    (24,  88,  "MAIN", 8, CREAM),
    (525, 88,  "MAIN EAST", 8, CREAM),
    (296, 88,  "EAST MAIN EXT", 8, CREAM, "center"),  # over East Main Ext / Scale stack
    (282, 174, "MAIN WEST", 8, CREAM, "center"),  # under Block 2-1 (column 5)
    (816, 174, "MAIN WEST EXT", 8, CREAM, "center"),  # under West Main Ext lamp (x=806)
    (816, 88,  "EAST LEAD", 8, CREAM, "center"),  # above East Lead lamp (x=806)
    (348, 194, "ENGINE HOUSE", 8, CREAM),
    (572, 186, "SOUTH YD", 8, CREAM),
    # Princess: McKeesport and McKees Rocks share a right edge over their
    # stacked lamps. K-1 / K-2 sit on the spur bumpers.
    (EAST_RAIL, 88,  "McKeesport", 8, CREAM, "right"),
    (K_RAIL, 118, "K-2", 8, CREAM, "center"),  # 9px above S rail, same as K-1 vs MK
    (EAST_RAIL, 137, "McKees Rocks", 8, CREAM, "right"),
    (K_RAIL, 168, "K-1", 8, CREAM, "center"),
    (102, 223, "100", 8, WHITE),
    (167, 223, "101", 8, WHITE),
    (232, 223, "102", 8, WHITE),
    (362, 223, "117", 8, WHITE),
    (427, 223, "116", 8, WHITE),
    (492, 223, "103", 8, WHITE),
    (622, 223, "111", 8, WHITE),
    (687, 223, "110", 8, WHITE),
    (752, 223, "112", 8, WHITE),
    (882, 223, "113", 8, WHITE),
    (947, 223, "114", 8, WHITE),
    (1012, 223, "115", 8, WHITE),
]

# Live signal masts on the diagram (QV style). stem_x is where the mast
# attaches to the rail; facing E = heads east of the stem (eastbound /
# Right lever), W = heads west (westbound / Left lever). kind h2 = 2-head
# home (signalmasticon, hart-aar ctc imageset); d1 = dwarf (signalheadicon
# on the IH* head). Bar centers: N 90, S 113, M 136; W-1/W-2 above N;
# K-1 below M. 116/103 are switch-only — no icons.
N, S, M, MR, MK, W1, W2, SY = 110, 133, 156, 156, 183, 57, 81, 199
# (mast, stem_x, bar_center, facing, kind, head_or_None)
SIGNALS = [
    # W-1/W-2: occupancy stacked on Brick-Plane (x=161); dwarfs facing the plant.
    ("101RA",       168, W1, "W", "d1", "IH436"),
    ("101RB",       168, W2, "W", "d1", "IH437"),
    # Brick 100L: west of 100, facing east into the plant (eastbound home).
    ("100L",        52,  N,  "E", "h2", None),
    ("102LA",          265,  S,  "W", "h2", None),
    ("102LB",          265,  N,  "W", "h2", None),
    ("117RA",      328,  S,  "E", "h2", None),
    ("117RB",      328,  N,  "E", "h2", None),
    ("117LB",     396,  S,  "W", "d1", "IH1334"),
    ("117LA",     396,  N,  "W", "h2", None),
    ("111RA",    588,  M,  "E", "h2", None),
    ("111RB",    588,  S,  "E", "d1", "IH1236"),
    ("111L",      650,  M,  "W", "h2", None),
    ("110R",      618, SY + 6, "E", "d1", "IH1239"),  # SY lead; a few px below SOUTH YD
    ("112R",      708,  N,  "E", "h2", None),
    ("112L",      780,  N,  "W", "h2", None),
    ("113RA",      848,  M,  "E", "h2", None),  # MW / 113b
    ("113RB",      848,  N,  "E", "h2", None),  # main / 113a
    # Princess westbounds match CATS Master 4 + live masts (NX comments):
    # McKeesport / McKees Rocks = 2-head mains (114LB / 115LB);
    # K-2 / K-1 = 1-head dwarfs (114LA / IH143, 115LA / IH142).
    # 114 sits a bit west of slot 14 so the 2-lamp fits on McKeesport;
    # 115's 2-lamp sits east of that frog. 114R / 115R are the east
    # balloon intermediates (CATS LAMP1, SIGORIENT RIGHT on McKeesport / Rocks).
    ("114R",  1096,  N,  "E", "d1", "IH134"),
    ("115R",  1096,  M,  "E", "d1", "IH141"),
    ("114LB",  993,  N,  "W", "h2", None),   # McKeesport 2-lamp (114 at 931)
    ("114LA",  993,  S,  "W", "d1", "IH143"),  # K-2 1-lamp
    ("115LB", 1029,  M,  "W", "h2", None),   # McKees Rocks 2-lamp (moves with 115)
    ("115LA", 1029, MK,  "W", "d1", "IH142"),  # K-1 1-lamp
]

MAST = """<signalmasticon signalmast="{name}" x="{x}" y="{y}" level="9" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" degrees="0" clickmode="0" litmode="false" scale="1.0" imageset="{imageset}" class="jmri.jmrit.display.configurexml.SignalMastIconXml">
      <tooltip>{name}</tooltip>
    </signalmasticon>"""

HEAD = """<signalheadicon signalhead="{head}" x="{x}" y="{y}" level="9" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" clickmode="0" litmode="false" degrees="0" class="jmri.jmrit.display.configurexml.SignalHeadIconXml">
      <tooltip>{name}</tooltip>
      <icons>
        <held url="{stop}" scale="1.0">
          <rotation>0</rotation>
        </held>
        <dark url="{unk}" scale="1.0">
          <rotation>0</rotation>
        </dark>
        <red url="{stop}" scale="1.0">
          <rotation>0</rotation>
        </red>
        <yellow url="{rest}" scale="1.0">
          <rotation>0</rotation>
        </yellow>
        <green url="{clr}" scale="1.0">
          <rotation>0</rotation>
        </green>
        <lunar url="{rest}" scale="1.0">
          <rotation>0</rotation>
        </lunar>
        <flashred url="{stop}" scale="1.0">
          <rotation>0</rotation>
        </flashred>
        <flashyellow url="{rest}" scale="1.0">
          <rotation>0</rotation>
        </flashyellow>
        <flashgreen url="{clr}" scale="1.0">
          <rotation>0</rotation>
        </flashgreen>
        <flashlunar url="{rest}" scale="1.0">
          <rotation>0</rotation>
        </flashlunar>
      </icons>
      <iconmaps />
    </signalheadicon>"""


def sig_url(kind, aspect, facing):
    suf = "-w" if facing == "W" else ""
    return "preference:ctc/icons/sig-%s-%s%s.gif" % (kind, aspect, suf)


def signal_xy(stem_x, bar_c, facing, kind):
    width = 21 if kind == "h2" else 12
    x = stem_x if facing == "E" else stem_x - width + 1
    return x, bar_c - 3


def build_block():
    parts = []
    parts.append(BG.format(x=0, u=U, gif="Panel-left-7.gif"))
    for slot in range(N_SLOTS):
        if slot in BLANK_SLOTS:
            gif = "Panel-blank-7.gif"
        elif slot in SWITCH_ONLY_SLOTS:
            gif = "Panel-switch-7.gif"
        else:
            gif = "Panel-sw-sig-7.gif"
        parts.append(BG.format(x=12 + 65 * slot, u=U, gif=gif))
    parts.append(BG.format(x=12 + 65 * N_SLOTS, u=U, gif="Panel-right-7.gif"))
    for t in TURNOUTS:
        name, x, y, kind, rot = unpack_turnout(t)
        parts.append(TURNOUT.format(
            name=name, x=x, y=map_y(y), rot=rot, **turnout_urls(kind)))
    for sensor, x, y, tip in LAMPS:
        parts.append(LAMP.format(sensor=sensor, x=x, y=map_y(y), tip=tip, u=U))
    for x, y, gif, rot in TRACKS:
        url = THIN if gif.startswith(("thin", "thick", "os-")) else U + "track/block/"
        parts.append(TRACK.format(x=x, y=map_y(y), gif=gif, rot=rot, url=url))
    for t in TEXTS:
        x, y, text, size, col, just = unpack_text(t)
        parts.append(TEXT.format(
            x=label_origin(x, text, size, just), y=map_y(y), text=text,
            size=size, just=just, **col))
    for name, stem_x, bar_c, facing, kind, head in SIGNALS:
        x, y = signal_xy(stem_x, map_y(bar_c), facing, kind)
        if kind == "h2":
            parts.append(MAST.format(
                name=name, x=x, y=y,
                imageset="ctc-w" if facing == "W" else "ctc"))
        else:
            parts.append(HEAD.format(
                name=name, head=head, x=x, y=y,
                stop=sig_url("d1", "stop", facing),
                rest=sig_url("d1", "restricting", facing),
                clr=sig_url("d1", "slow-clear", facing),
                unk=sig_url("d1", "unknown", facing)))
    return "    " + "\n    ".join(parts) + "\n"


STRIP = [
    re.compile(r'\s*<turnouticon\b[^>]*>.*?</turnouticon>', re.S),
    re.compile(r'\s*<sensoricon\b[^>]*sensor="Block [^"]*".*?</sensoricon>', re.S),
    re.compile(r'\s*<positionablelabel\b[^>]*>\s*<icon url="(?:[^"]*USS/(?:track/block|background)/|preference:ctc/icons/)[^"]*".*?</positionablelabel>', re.S),
    re.compile(r'\s*<positionablelabel\b[^>]*text="(?:BRICK|PLANE|BARN|EAST END|PRINCESS|MAIN WEST EXT|MAIN WEST|MAIN EAST|EAST MAIN EXT|EAST LEAD|MAIN|SOUTH YARD|SOUTH YD|WEST YARD|ENGINE TERMINAL|ENGINE HOUSE|YARD|McKEESPORT|McKEES ROCKS|McKeesport|McKees Rocks|K-1|K-2|W-1|W-2|1[01][0-9]|HART RAILROAD[^"]*)".*?</positionablelabel>', re.S),
    # stock CTC Unlocked indicators + labels, replaced by the OS lamp row
    # (GUI only -- the IS*:UNLOCKEDINDICATOR sensors still exist; delete
    # these two patterns to bring the buttons back)
    re.compile(r'\s*<sensoricon\b[^>]*sensor="IS\d+:UNLOCKEDINDICATOR".*?</sensoricon>', re.S),
    re.compile(r'\s*<positionablelabel\b[^>]*text="Unlocked".*?</positionablelabel>', re.S),
    re.compile(r'\s*<signalmasticon\b[^>]*/>', re.S),
    re.compile(r'\s*<signalmasticon\b[^>]*>.*?</signalmasticon>', re.S),
    re.compile(r'\s*<signalheadicon\b[^>]*>.*?</signalheadicon>', re.S),
]


def apply(text, close_tag="</paneleditor>"):
    """Strip old diagram elements, fix window geometry, insert new block."""
    for pat in STRIP:
        text = pat.sub("", text)
    text = re.sub(
        r'(<paneleditor\b[^>]*?) x="-?\d+" y="-?\d+" height="\d+" width="\d+"',
        r'\1 x="40" y="40" height="780" width="1190"', text, count=1)
    idx = text.rindex(close_tag)
    return text[:idx] + build_block() + "  " + text[idx:]


def _gif(kind, state="closed"):
    """Filesystem path for a turnout kind at the given state."""
    swap = kind.startswith("swap:")
    if swap:
        kind = kind[5:]
        state = "thrown" if state == "closed" else "closed"
    if kind.startswith("thin:"):
        root = "jmri/layouts/hart/ctc/icons/"
        return root + kind[5:] + "-%s.gif" % state
    return "/Applications/JMRI/resources/icons/USS/" + kind + "-%s.gif" % state


def write_preview(path):
    """Composite TRACKS + TURNOUTS + TEXTS onto a black PNG (no live JMRI)."""
    from PIL import Image, ImageDraw, ImageFont
    uss = "/Applications/JMRI/resources/icons/USS/track/block/"
    thin = "jmri/layouts/hart/ctc/icons/"
    im = Image.new("RGBA", (1190, 360), (0, 0, 0, 255))

    def blit(src, x, y, rot=0):
        try:
            g = Image.open(src).convert("RGBA")
        except OSError:
            print("missing icon:", src)
            return
        if rot:
            g = g.rotate(-90 * rot, expand=True)
        im.alpha_composite(g, (x, y))

    for x, y, gif, rot in TRACKS:
        src = (thin if gif.startswith(("thin", "thick", "os-")) else uss) + gif
        blit(src, x, map_y(y), rot)
    for t in TURNOUTS:
        _name, x, y, kind, rot = unpack_turnout(t)
        # swap: kinds: preview the mainline (Thrown) artwork
        state = "thrown" if kind.startswith("swap:") else "closed"
        blit(_gif(kind, state), x, map_y(y), rot)
    lamp_gif = "/Applications/JMRI/resources/icons/USS/sensor/red-off.gif"
    for _s, x, y, _tip in LAMPS:
        blit(lamp_gif, x, map_y(y), 0)
    sig_dir = "jmri/layouts/hart/ctc/icons/"
    for _name, stem_x, bar_c, facing, kind, _head in SIGNALS:
        x, y = signal_xy(stem_x, map_y(bar_c), facing, kind)
        suf = "-w" if facing == "W" else ""
        blit(sig_dir + "sig-%s-stop%s.gif" % (kind, suf), x, y)
    draw = ImageDraw.Draw(im)
    # Column guides (blank = 1) so Brick placement can be reviewed before XML.
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 12)
        font_s = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 9)
    except OSError:
        font = font_s = ImageFont.load_default()
    for i in range(6):
        x = 12 + 65 * i
        draw.line([(x, 34), (x, 310)], fill=(50, 50, 50, 255))
        if i < 5:
            draw.text((x + 22, 22), str(i + 1), fill=(90, 90, 90, 255), font=font_s)
    for t in TEXTS:
        x, y, text, size, col, just = unpack_text(t)
        f = font if size >= 12 else font_s
        rgb = (col["red"], col["green"], col["blue"])
        ox = label_origin(x, text, size, just)
        draw.text((ox, map_y(y)), text, fill=rgb + (255,), font=f)
    im.convert("RGB").save(path)
    print("%s: preview written" % path)


def install_thin_icons():
    """Copy ctc/icons into every local JMRI profile (preference:ctc/icons/)."""
    import os
    import shutil
    src = os.path.join("jmri", "layouts", "hart", "ctc", "icons")
    if not os.path.isdir(src):
        return
    dests = []
    for root in (
        os.path.expanduser("~/Library/Preferences/JMRI"),
        os.path.expanduser("~/.jmri"),
        os.path.expanduser("~/JMRI_UserFiles"),
    ):
        if not os.path.isdir(root):
            continue
        if root.endswith("JMRI_UserFiles"):
            dests.append(os.path.join(root, "ctc", "icons"))
            continue
        for name in os.listdir(root):
            if name.endswith(".jmri"):
                dests.append(os.path.join(root, name, "ctc", "icons"))
    for dest in dests:
        os.makedirs(dest, exist_ok=True)
        n = 0
        for fn in os.listdir(src):
            if fn.endswith(".gif"):
                shutil.copy2(os.path.join(src, fn), os.path.join(dest, fn))
                n += 1
        print("CTC icons -> %s (%d gifs)" % (dest, n))


def main():
    gui = sys.argv[1] if len(sys.argv) > 1 else "jmri/layouts/hart/ctc/GUIObjects.xml"
    txt = open(gui).read()
    open(gui, "w").write(apply(txt))
    print("%s: track plan regenerated" % gui)

    if len(sys.argv) > 2:
        tables = sys.argv[2]
        txt = open(tables).read()
        m = re.search(r'<paneleditor\b.*?</paneleditor>', txt, re.S)
        assert m, "no paneleditor in %s" % tables
        new_panel = apply(m.group(0))
        txt = txt[:m.start()] + new_panel + txt[m.end():]
        open(tables, "w").write(txt)
        print("%s: embedded paneleditor regenerated" % tables)

    install_thin_icons()
    write_preview("cats/screenshots/master4/uss_ctc_v55_preview.png")


if __name__ == "__main__":
    main()
