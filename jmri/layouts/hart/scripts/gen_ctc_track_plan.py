#!/usr/bin/env python3
"""Generate the CTC panel track diagram (v26 — Master 4 row order).

Match CATS Master 4 (`wiki/MASTER4_SCHEMATIC.md`): one straight focused main
on the TOP operating row, W-1/W-2 above it, Scale/Barn/S-1/K-2 on the middle
row, Main West gapped on the bottom row.

Diagram columns (west → east) follow the new schematic, not the live lever
map: col 1 = Brick / 100, col 2 (levers 3/4) = 101 W-yard, col 3 = 102 Plane.
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
both `\\`. Yard leads at 103/110 are unchanged pending a USS-board study.

Previous (v25 — 100 still had a `\\` onto Scale, 113b shifted east). v22 focused main on M. Original v8:

Machine slots are 65px wide (slot = x//65). Blank slots 0, 4, 8, 12 and 16
— four interlockings of three lever columns each: Brick/Plane slots 1-3
(SW101/100/102), Barn 5-7 (117/116/103), East End 9-11 (111/110/112 —
SW107/108/109 are hand-throw, no levers and no lamps), Princess 13-15
(113/114/115). Switch icons sit at slot*65 + 21.

The gold background is generated too: 12px left cap at x=0, one 65px tile
per slot at x=12+65*slot (Panel-blank-7 for blank slots,
Panel-switch-7 for 116/103 switch-only, Panel-sw-sig-7 for the rest),
right cap at x=1117.

South Yard body tracks are omitted; 103 and 110 keep short leads that are
the yard turnouts. Engine House is a single spur under columns 7/9.
East stubs (K-1, K-2, McKees Rocks, McKeesport) still end flush at x=1105
with lamps at x=1060. W-1/W-2 lamps sit on the stubs east of 101.

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

TEXT = """<positionablelabel x="{x}" y="{y}" level="4" forcecontroloff="false" hidden="no" positionable="true" showtooltip="false" editable="true" text="{text}" fontname="Dialog.plain" size="{size}" style="1" red="{red}" green="{green}" blue="{blue}" hasBackground="no" justification="left" class="jmri.jmrit.display.configurexml.PositionableLabelXml">
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
TURNOUTS = [
    # 100: Brick OS on the main only. No Scale spur (that hairpin is omitted
    # on Master 4). Bar-only icon; swap so Thrown = through main.
    ("Switch 100", 86,  82,  "swap:thin:os-n-bar"),
    # 101: W-yard in sw 3 / sig 4 column. Bar N (bottom of os-l-e);
    # Thrown = up-east to W-1/W-2; Closed = through
    ("Switch 101", 151, 59,  T + "left/east/os-l-e"),
    # 102: Plane. Single turnout, both routes to 117 (through = 117b,
    # `\\` = Scale → 117). Not a crossover and not fed by a 100 spur.
    ("Switch 102", 216, 82,  T + "right/east/os-r-e"),
    ("Switch 117", 346, 82,  X + "left/os-l-sc"),        # N ↔ S (main ↔ Scale/Barn)
    ("Switch 116", 436, 105, "thin:os-l-w-thin"),        # S; down-west drop to EH spur
    ("Switch 103", 482, 105, "thin:os-r-e-thin-short"),  # S; `\\` stops above M (not MW)
    ("Switch 111", 606, 105, X + "right/os-r-sc"),       # S ↔ M (111b ↔ 111a)
    ("Switch 110", 671, 105, "thin:os-l-w-thin"),        # S; diamond with MW; yard is below
    # 112: bar N; swap Thrown = East Lead through, Closed = down-west OS 110
    ("Switch 112", 736, 82,  "swap:" + T + "left/west/os-l-w"),
    # 113 skips S: both `\\`, stacked in the 113 column (not a `>` chevron).
    ("Switch 113", 866, 82,  T + "right/east/os-r-e"),
    ("Switch 113", 866, 105, "thin:os-r-w-thin"),
    # 114: bar N; swap Thrown = McKeesport, Closed = K-2 on S
    ("Switch 114", 931, 82,  "swap:" + T + "right/east/os-r-e"),
    # 115: bar M; swap Thrown = McKees Rocks, Closed = K-1 below M
    ("Switch 115", 996, 128, "swap:" + T + "right/east/os-r-e"),
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
    ("Block 4-4",  185, 53,  "W-1"),
    ("Block 4-3",  185, 44,  "W-2"),
    ("Block 4-2",  99,  200, "OS 100"),
    ("Block 4-1",  164, 200, "OS 101"),
    ("Block 4-6",  200, 80,  "Brick-Plane (100–117b)"),  # focused main
    ("Block 4-5",  229, 200, "OS 102"),
    # East Main Ext (4-7) omitted on Master 4
    ("Block 4-8",  286, 103, "Scale"),
    ("Block 13-3", 347, 200, "OS 117 (yard side)"),
    ("Block 13-4", 371, 200, "OS 117b (main side)"),
    ("Block 13-1", 404, 103, "Barn"),
    ("Block 3-1",  424, 200, "OS 116 (Barn)"),
    ("Block 3-2",  489, 200, "OS 103"),
    ("Block 2-8",  546, 103, "S-1"),
    ("Block 2-1",  590, 126, "Main West (approach to 111)"),
    ("Block 2-3",  546, 80,  "Main East"),
    ("Block 12-4", 607, 200, "OS 111a (Main West side)"),
    ("Block 12-6", 631, 200, "OS 111b (yard side)"),
    ("Block 12-7", 684, 200, "OS 110"),
    ("Block 12-8", 749, 200, "OS 112"),
    ("Block 1-7",  800, 80,  "East Lead (112L–113RB)"),
    ("Block 1-8",  806, 126, "West Main Ext (111-113)"),
    ("Block 1-5",  867, 200, "OS 113b (Main West side)"),
    ("Block 1-6",  891, 200, "OS 113a (East Lead side)"),
    ("Block 1-3",  944, 200, "OS 114 + K-2 (one circuit)"),
    ("Block 1-4",  1009, 200, "OS 115 + K-1 (one circuit)"),
    ("Block 1-1",  1060, 126, "McKees Rocks (through 115 / 115LA)"),
    ("Block 1-4",  1060, 157, "K-1 (diverging 115 / 115LB)"),
    ("Block 1-2",  1060, 80,  "McKeesport (through 114 / 114LA)"),
    ("Block 1-3",  1060, 103, "K-2 (diverging 114 / 114LB)"),
]

# (x, y, gif, rotation) -- line bar rows: line025 2-6, line050 3-7, line1 4-8,
# line25 9-13; b-45 30x30 "\" (rotation 1 -> "/"). thin* gifs are 2px lines
# from preference:ctc/icons/ (thin044 44px, thin085 85px, thin-45 15x15 "\",
# rotation 1 -> "/").
TRACKS = [
    # W-1 / W-2 above N, east of 101 in the 3/4 column (Master 4 Y=4/5).
    (182, 52,  "line050.gif", 0),   # W-2
    (216, 52,  "line025.gif", 0),
    (182, 61,  "line050.gif", 0),   # W-1
    (216, 61,  "line025.gif", 0),
    # N focused main (bar 88-92)
    (21,  85,  "line050.gif", 0),   # Brick approach into 100
    (60,  86,  "line025.gif", 0),
    (117, 85,  "line050.gif", 0),   # 100-101
    (183, 86,  "line025.gif", 0),   # 101-102
    (194, 84,  "line1.gif",   0),
    (258, 84,  "line1.gif",   0),   # through 102, into 117 (Main East Ext)
    (392, 84,  "line1.gif",   0),   # Main East
    (477, 84,  "line1.gif",   0),
    (524, 79,  "line25.gif",  0),   # into 112
    (778, 84,  "line1.gif",   0),   # East Lead 112-113
    (820, 85,  "line050.gif", 0),
    (908, 86,  "line025.gif", 0),   # 113a-114
    (973, 84,  "line1.gif",   0),   # 114 -> McKeesport
    (1020, 84, "line1.gif",   0),
    (1084, 86, "line025.gif", 0),
    # S Scale starts at 102's `\` (~x248) then Barn / S-1 / K-2
    (248, 107, "line1.gif",   0),   # Scale off 102 → 117
    (321, 109, "line025.gif", 0),
    (392, 109, "line025.gif", 0),   # Barn 117-116
    (394, 108, "line050.gif", 0),
    (522, 107, "line1.gif",   0),   # S-1 103-111
    (648, 109, "line025.gif", 0),   # 111b-110
    (713, 109, "line025.gif", 0),   # 110 east stub
    (956, 107, "line1.gif",   0),   # K-2 off 114
    (1020, 107, "line1.gif",  0),
    (1084, 109, "line025.gif", 0),
    # M: GAP under 103 (no rail), MW starts at 111. 113b stacked at x866.
    (584, 130, "line1.gif",   0),   # Main West approach to 111
    (645, 132, "line025.gif", 0),   # 111a-113 WME (diamond through 110)
    (648, 125, "line25.gif",  0),
    (820, 131, "line050.gif", 0),   # into 113b (icon at 866)
    (908, 132, "line025.gif", 0),   # 113b-115
    (908, 130, "line1.gif",   0),
    (1037, 131, "line050.gif", 0),  # 115 -> McKees Rocks
    (1065, 131, "line050.gif", 0),
    # K-1 below M
    (1037, 157, "line050.gif", 0),
    (1065, 157, "line050.gif", 0),
    (1084, 158, "line025.gif", 0),
    # 116 `/` continues below empty M to a single EH spur under levers 7/9
    (422, 136, "thin-45.gif", 1),
    (378, 147, "line050.gif", 0),
    # 103 `\\` through the MW-row gap (no MW rail) into a compact 104 frog
    (513, 128, "thin-45.gif", 0),
    (526, 142, "thin035.gif", 0),   # 104 bar (yard turnout, no body tracks)
    (538, 142, "thin-45.gif", 0),   # 104 `\\` into south yard
    # 110 diamond: `/` continues below MW into a compact 109 frog
    (657, 136, "thin-45.gif", 1),
    (640, 151, "thin035.gif", 0),   # 109 bar (yard turnout, no body tracks)
    (640, 151, "thin-45.gif", 1),   # 109 `/` into south yard
]

WHITE = dict(red=255, green=255, blue=255)
CREAM = dict(red=220, green=220, blue=180)
BLACK = dict(red=0, green=0, blue=0)
# (x, y, text, size, color)
TEXTS = [
    # banner engraved in the gold band (tile rows 0-33)
    (415, 8, "HART RAILROAD - NEVILLE ISLAND", 16, BLACK),
    (40,  36, "BRICK",     12, WHITE),
    (205, 36, "PLANE",     12, WHITE),
    (347, 36, "BARN",      12, WHITE),
    (645, 36, "EAST END",  12, WHITE),
    (905, 36, "PRINCESS",  12, WHITE),
    (182, 48,  "W-2", 8, CREAM),
    (182, 58,  "W-1", 8, CREAM),
    (200, 68,  "MAIN", 8, CREAM),
    (525, 68,  "MAIN EAST", 8, CREAM),
    (584, 140, "MAIN WEST", 8, CREAM),
    (355, 163, "ENGINE HOUSE", 8, CREAM),
    (1035, 68,  "McKEESPORT", 8, CREAM),
    (1030, 140, "McKEES ROCKS", 8, CREAM),
    (1090, 118, "K-2", 8, CREAM),
    (1090, 174, "K-1", 8, CREAM),
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
N, S, M, MR, MK, W1, W2 = 90, 113, 136, 136, 163, 66, 57
# (mast, stem_x, bar_center, facing, kind, head_or_None)
SIGNALS = [
    # Brick 101: yard exits on the stubs east of 101, facing west toward the plant
    ("101RA",           185, W1, "W", "d1", "IH436"),
    ("101RB",           185, W2, "W", "d1", "IH437"),
    ("100L",       130,  N,  "W", "h2", None),
    ("102LA",          265,  S,  "W", "h2", None),
    ("102LB",          265,  N,  "W", "h2", None),
    ("117RA",      328,  S,  "E", "h2", None),
    ("117RB",      328,  N,  "E", "h2", None),
    ("117LB",     396,  S,  "W", "d1", "IH1334"),
    ("117LA",     396,  N,  "W", "h2", None),
    ("111RA",    588,  M,  "E", "h2", None),
    ("111RB",    588,  S,  "E", "d1", "IH1236"),
    ("111L",      650,  M,  "W", "h2", None),
    ("110R",      658,  S,  "E", "d1", "IH1239"),
    ("112R",      708,  N,  "E", "h2", None),
    ("112L",      780,  N,  "W", "h2", None),
    ("113RA",      848,  M,  "E", "h2", None),  # MW / 113b
    ("113RB",      848,  N,  "E", "h2", None),  # main / 113a
    ("114R",  1088,  N,  "E", "d1", "IH134"),
    ("114LA", 1050,  N,  "W", "d1", "IH143"),
    ("114LB", 1050,  S,  "W", "h2", None),
    ("115R", 1088, M, "E", "d1", "IH141"),
    ("115LA", 1050, M, "W", "h2", None),
    ("115LB", 1050, MK, "W", "d1", "IH142"),
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
            name=name, x=x, y=y, rot=rot, **turnout_urls(kind)))
    for sensor, x, y, tip in LAMPS:
        parts.append(LAMP.format(sensor=sensor, x=x, y=y, tip=tip, u=U))
    for x, y, gif, rot in TRACKS:
        url = THIN if gif.startswith(("thin", "thick", "os-")) else U + "track/block/"
        parts.append(TRACK.format(x=x, y=y, gif=gif, rot=rot, url=url))
    for x, y, text, size, col in TEXTS:
        parts.append(TEXT.format(x=x, y=y, text=text, size=size, **col))
    for name, stem_x, bar_c, facing, kind, head in SIGNALS:
        x, y = signal_xy(stem_x, bar_c, facing, kind)
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
    re.compile(r'\s*<positionablelabel\b[^>]*text="(?:BRICK|PLANE|BARN|EAST END|PRINCESS|MAIN WEST|MAIN EAST|MAIN|SOUTH YARD|WEST YARD|ENGINE TERMINAL|ENGINE HOUSE|YARD|McKEESPORT|McKEES ROCKS|K-1|K-2|W-1|W-2|1[01][0-9]|HART RAILROAD[^"]*)".*?</positionablelabel>', re.S),
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
    im = Image.new("RGBA", (1190, 250), (0, 0, 0, 255))

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
        blit(src, x, y, rot)
    for t in TURNOUTS:
        _name, x, y, kind, rot = unpack_turnout(t)
        # swap: kinds: preview the mainline (Thrown) artwork
        state = "thrown" if kind.startswith("swap:") else "closed"
        blit(_gif(kind, state), x, y, rot)
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 12)
        font_s = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 9)
    except OSError:
        font = font_s = ImageFont.load_default()
    for x, y, text, size, col in TEXTS:
        f = font if size >= 12 else font_s
        rgb = (col["red"], col["green"], col["blue"])
        draw.text((x, y), text, fill=rgb + (255,), font=f)
    im.convert("RGB").save(path)
    print("%s: preview written" % path)


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

    write_preview("cats/screenshots/master4/uss_ctc_v26_preview.png")


if __name__ == "__main__":
    main()
