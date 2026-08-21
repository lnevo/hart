#!/usr/bin/env python3
"""Generate the CTC panel track diagram (v8 — 17 slots, 45deg yard ladders).

Machine slots are 65px wide (slot = x//65). Blank slots 0, 4, 8, 12 and 16
— four interlockings of three lever columns each: Brick/Plane slots 1-3
(SW101/100/102), Barn 5-7 (117/116/103), East End 9-11 (111/110/112 —
SW107/108/109 are hand-throw, no levers and no lamps), Princess 13-15
(113/114/115). Switch icons sit at slot*65 + 21.

The gold background is generated too: 12px left cap at x=0, one 65px tile
per slot at x=12+65*slot (Panel-blank-7 for blank slots,
Panel-switch-7 for 116/103 switch-only, Panel-sw-sig-7 for the rest),
right cap at x=1117.

Rows (bar pixel ranges; scissor icons span exactly 23px between bars):

  N   88-92   the MAIN WEST level. At Brick: W-1 -> SW101 -> SW100, with
              Main West running east from SW100's throat as a gapped line
              (it loops around the room) at the SAME height as its restart
              in blank slot 8 (`Block 2-1` approach lamp) west of SW111.
              SW100's diverging leg hairpins "<" down to Main West
              Brick-Plane (`Block 4-6`) on row M into SW102. Then SW111 ->
              SW113 passing siding (one block: West Main Ext `Block 1-8`,
              lamp centered in blank slot 12), SW113 -> SW115 DIRECT (no
              block, no lamp), SW115 / McKees Rocks / K-1. W-2 stub is on
              the 111-115 level off SW101's leg.
  S  111-115  yard run-through: SW102's up-east leg -> South Yard Scale (`Block
              4-8`, lamp centered in blank slot 4) -> SW117 -> South Yard West ->
              SW116 -> SW103 -> South Yard 1 (`Block 2-8`, lamp centered
              in blank slot 8) -> SW110 -> SW112 -> South Yard East (`Block
              1-7`, lamp centered in blank slot 12) -> SW113 -> SW114 ->
              K-2.
  M  134-138  SW102's bar: Main West Brick–Plane (west, from the hairpin)
              <-> East Main Ext (east, `Block 4-7` lamp centered in blank
              slot 4, the continuing route curving back east) -> SW117;
              dips 45deg east of SW117 to a bottom straight (164-168)
              under the South Yard (`Block 2-3` Main East lamp centered in
              blank slot 8), rising into SW112's leg.

South Yard: straight 45deg thin ladders off SW103 (down-east) and SW110
(down-west, mirror) — the switch legs continue as ladder lines parallel
to the Main East 45deg legs — with THREE run-through yard tracks (9px
pitch) connecting the two ladders (SW104-109 are hand-throw, not drawn).
Engine House: the same ladder rotated 180deg, up-west off SW116
(split = hand-throw SW118, treated like 104-109), two stub tracks
ending flush at x=365, tucked close to the yard row. SW116 abuts SW103
directly (no block between them); South Yard West is the 117-116 stretch.

All east branch stubs (K-1, K-2, McKees Rocks, McKeesport) end flush at
x=1105 with their lamps aligned at x=1060 and labels centered on the
stubs; W-1/W-2 (WEST YARD) start flush at x=0 with lamps aligned at x=30.

Thin 2px gifs and the os-*-thin turnout icons (SW103/110/116) come from
"preference:ctc/icons/*.gif" — deploy to JMRI_UserFiles/ctc/icons/.

CTC-held signal masts sit on the diagram as Quaker Valley-style proto
lollipops (stock USS `sig-h-2` / `sig-d-1`, recolored by aspect). Two-head
homes are live `<signalmasticon>` imageset `ctc` / `ctc-w`; dwarfs are
`<signalheadicon>` on the single IH* head. 116/103 have no CTC homes.

Writes both ctc/GUIObjects.xml and the embedded <paneleditor> in
tables.xml, and normalizes the panel window geometry to show all 17 slots.
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
          <rotation>0</rotation>
        </closed>
        <thrown url="{thrown}" scale="1.0">
          <rotation>0</rotation>
        </thrown>
        <unknown url="{unknown}" scale="1.0">
          <rotation>0</rotation>
        </unknown>
        <inconsistent url="{inconsistent}" scale="1.0">
          <rotation>0</rotation>
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

# (turnout name, x, y, icon kind) -- bar rows: y+6..10 (os-l-w/os-r-e top),
# y+29..33 (os-l-e/os-r-w bottom). "thin:" kinds are the custom 2px-leg
# icons from preference:ctc/icons/. "swap:" swaps the closed/thrown gifs:
# used where the drawn BAR is the diverged route (LE continuing sense —
# SW100/112 have continuing=4, and SW102's continuing route is the drawn
# leg), so the lit route matches the actual turnout state.
TURNOUTS = [
    ("Switch 101", 86,  82,  T + "left/west/os-l-w"),    # Main West row; W-2 leg down-west
    ("Switch 100", 151, 82,  T + "left/west/os-l-w"),  # agree with JMRI Closed/Thrown (rests Thrown)
    ("Switch 102", 216, 105, T + "left/east/os-l-e"),    # bar row M = Brick-Plane<->East Main Ext (continuing); leg up-east = South Yard Scale
    ("Switch 117", 346, 105, X + "left/os-l-sc"),        # scissor: yard (111-115) <-> main (134-138)
    ("Switch 116", 436, 82,  "thin:os-r-w-thin"),        # yard row, abuts SW103 (direct, no block); Engine House ladder up-west
    ("Switch 103", 482, 105, "thin:os-r-e-thin"),        # yard row; 6px gap after SW116 (no block)
    ("Switch 111", 606, 82,  X + "right/os-r-sc"),       # scissor: Main West (88-92) <-> yard (111-115)
    ("Switch 110", 671, 105, "thin:os-l-w-thin"),        # yard row; South Yard ladder down-west
    ("Switch 112", 736, 105, T + "left/west/os-l-w"),  # Closed = South Yard East ↔ 110; Thrown = Main East
    ("Switch 113", 866, 82,  X + "left/os-l-sc"),        # scissor: Main West (88-92) <-> South Yard East (111-115)
    ("Switch 114", 931, 105, T + "right/east/os-r-e"),   # South Yard East row; McKeesport branch down-east
    ("Switch 115", 996, 59,  T + "left/east/os-l-e"),    # Main West row (bar 88-92); McKees Rocks up-east
]

# (sensor, x, y, tooltip). Block lamps sit embedded on their track line
# (y = bar top - 8). Turnout OS lamps form a machine row at y200, replacing
# the stock Unlocked indicators (stripped below; sensors still exist, GUI
# only) at x = 99/164/229, 359/424/489, 619/684/749, 879/944/1009, with the
# switch number labelled underneath; crossover columns get their two OS
# lamps side by side, centered on the column, UPPER track's lamp on the left.
LAMPS = [
    ("Block 4-4",  48,  80,  "W-1 (West Yard 1)"),
    ("Block 4-3",  48,  103, "W-2 (West Yard 2)"),
    ("Block 4-1",  99,  200, "OS 101 (Brick)"),
    ("Block 4-2",  164, 200, "OS 100 (Brick)"),
    ("Block 4-6",  150, 103, "100-102 (Brick-Plane)"),  # on the hairpin "\" , T1 plane
    ("Block 4-5",  229, 200, "OS 102 (Plane)"),
    ("Block 2-1",  260, 80,  "Main West (east of Brick throat)"),
    ("Block 4-7",  286, 126, "East Main Ext"),
    ("Block 4-8",  286, 103, "South Yard Scale (Plane-Barn diverging)"),
    ("Block 13-3", 347, 200, "OS 117 (yard side)"),
    ("Block 13-4", 371, 200, "OS 117b (main side)"),
    ("Block 13-1", 404, 103, "South Yard West"),
    ("Block 3-1",  424, 200, "OS 116 (Barn)"),
    ("Block 3-2",  489, 200, "OS 103 (South Yard)"),
    ("Block 2-8",  546, 103, "South Yard 1"),
    ("Block 2-1",  546, 80,  "Main West (approach to 111)"),
    ("Block 2-3",  546, 156, "Main East"),
    ("Block 12-4", 607, 200, "OS 111a (Main West side)"),
    ("Block 12-6", 631, 200, "OS 111b (yard side)"),
    ("Block 12-7", 684, 200, "OS 110 (East End)"),
    ("Block 12-8", 749, 200, "OS 112 (East End)"),
    ("Block 1-7",  806, 103, "South Yard East"),
    ("Block 1-8",  806, 80,  "West Main Ext (111-113 siding)"),
    ("Block 1-5",  867, 200, "OS 113b (Main West side)"),
    ("Block 1-6",  891, 200, "OS 113a (South Yard East side)"),
    ("Block 1-3",  944, 200, "OS 114 + K-2 (one circuit)"),
    ("Block 1-4",  1009, 200, "OS 115 + K-1 (one circuit)"),
    ("Block 1-1",  1060, 57, "McKees Rocks branch"),
    ("Block 1-4",  1060, 80, "K-1 (same circuit as OS 115)"),
    ("Block 1-3",  1060, 103, "K-2 (same circuit as OS 114)"),
    ("Block 1-2",  1060, 131, "McKeesport branch"),
]

# (x, y, gif, rotation) -- line bar rows: line025 2-6, line050 3-7, line1 4-8,
# line25 9-13; b-45 30x30 "\" (rotation 1 -> "/"). thin* gifs are 2px lines
# from preference:ctc/icons/ (thin044 44px, thin085 85px, thin-45 15x15 "\",
# rotation 1 -> "/").
TRACKS = [
    # Brick on the Main West row (bar 88-92, same level as the column-9
    # restart): W-1 / W-2 stubs start at x=23 -- 11px margin after the left
    # cap (ends x=12), mirroring the east edge (flush 1106, right cap 1117).
    # Line gifs have intrinsic end margins: line025 1px, line050 2px,
    # line1 7px, line25 12px.
    # W-1 / W-2 end with a 3px block gap short of SW101 (bar at 86, leg
    # tip at (95,115)) -- W-1/W-2 are separate circuits from the Brick OS
    (21,  85,  "line050.gif", 0),   # W-1 (drawn 23-62...)
    (60,  86,  "line025.gif", 0),   # ...to 82, gap, icon at 86
    (21,  108, "line050.gif", 0),   # W-2 (drawn 23-62...)
    (47,  108, "line050.gif", 0),   # ...to 88, gap, leg graphics from ~92
    (117, 85,  "line050.gif", 0),   # 101-100
    (194, 84,  "line1.gif",   0),   # MAIN WEST east of SW100's throat (gapped;
    (264, 85,  "line050.gif", 0),   #  loops around the room to column 9)
    # SW100's diverging leg hairpins "<": leg down-west to (160,115), then
    # thick 45 back down-east to row M at (182,137) = Main West Brick–Plane
    (159, 114, "thick45-24.gif", 0),
    (183, 132, "line025.gif", 0),   # hairpin -> SW102
    # row M (main, bar 134-138): SW102 bar -> East Main Ext -> SW117
    (257, 132, "line025.gif", 0),   # gap after SW102's bar (icon ends 255)
    (258, 130, "line1.gif",   0),   # through blank slot 4, stop short of SW117
                                    #  (line1 bar 4-8: y130 -> 134-138, flat; drawn to 335)
    # main dips under the South Yard and rises into SW112's leg
    (392, 136, "b-45.gif",    0),   # down: gapped off SW117, bar 134-138 -> bottom 164-168
    (407, 155, "line25.gif",  0),   # Main East bottom straight (drawn 419-597)
    (524, 155, "line25.gif",  0),   # overlapped: one block, no joint (to 714)
    (715, 136, "b-45.gif",    1),   # up: bottom -> SW112 leg tip (745,138)
    # row S (yard run-through / South Yard East, bar 111-115)
    (252, 107, "line1.gif",   0),   # South Yard Scale (drawn 259-343): gap to 102's leg
    (321, 109, "line025.gif", 0),   #  tip (255) and gap to SW117's icon (346)
    (392, 109, "line025.gif", 0),   # 117-116: South Yard West, gapped off SW117 (ends 386)
    (394, 108, "line050.gif", 0),   # ...to SW116 (436); 6px empty to SW103
    (522, 107, "line1.gif",   0),   # 103 -> 111 (South Yard 1, blank slot 8)
    (648, 109, "line025.gif", 0),   # 111 lower -> 110
    (713, 109, "line025.gif", 0),   # 110 -> 112
    (778, 107, "line1.gif",   0),   # 112 -> 113 (South Yard East, blank slot 12)
    (908, 109, "line025.gif", 0),   # 113 bottom -> 114
    (973, 107, "line1.gif",   0),   # 114 -> K-2 stub...
    (1020, 107, "line1.gif",  0),
    (1084, 109, "line025.gif", 0),  # ...flush to x=1106
    # South Yard: the 45deg icon legs continue as straight 45deg ladders
    # (east ladder line x = y + 379, west ladder x = 807 - y); the three
    # run-through yard tracks (9px pitch) branch off the icon legs
    # themselves, tucked up close under South Yard 1
    (522, 137, "thin4512.gif", 0),  # east ladder tail (SW103 moved +6)
    (660, 137, "thin4512.gif", 1),  # west ladder tail, ends at track 4 (660,148)
    (514, 128, "thin085.gif", 0),   # yard track 2
    (593, 128, "thin085.gif", 0),
    (523, 137, "thin085.gif", 0),   # yard track 3
    (584, 137, "thin085.gif", 0),
    (532, 146, "thin085.gif", 0),   # yard track 4
    (575, 146, "thin085.gif", 0),
    # Engine House: two stubs, west ends even with T6 (drawn ~393).
    # Top spur stops at the ladder tip (428); track 2 meets SW116's leg (436).
    (428, 82,  "thin459.gif", 0),   # ladder (436,90) up-west, top even with track 1
    (393, 81,  "thin035.gif", 0),   # house track 1 (393-427, abuts ladder)
    (393, 90,  "thin044.gif", 0),   # house track 2 (393-436)
    # row N (Main West siding, bar 88-92)
    (519, 84,  "line1.gif",   0),   # Main West approach stub (blank slot 8)
    (645, 86,  "line025.gif", 0),   # 111 -> 113 (West Main Ext, one block,
    (648, 79,  "line25.gif",  0),   #  overlapped; block gap short of SW113)
    (820, 85,  "line050.gif", 0),   #  (drawn to 861, icon at 866)
    (904, 86,  "line025.gif", 0),   # 113 -> 115: flush to SW113 (ends 906),
    (908, 84,  "line1.gif",   0),   #  one gap before SW115 (drawn to 985, icon 996)
    (1037, 85, "line050.gif", 0),   # 115 -> K-1 (drawn 1039-1106): gap after
    (1065, 85, "line050.gif", 0),   #  SW115's icon (ends 1035), flush at 1106
    # McKees Rocks branch (bar 65-69) off SW115's riser, flush to x=1106
    (1028, 62, "line050.gif", 0),
    (1061, 62, "line050.gif", 0),
    (1084, 63, "line025.gif", 0),
    # McKeesport branch (bar 139-143) off SW114's leg, flush to x=1106
    (956, 135, "line1.gif",   0),
    (1020, 135, "line1.gif",  0),
    (1084, 137, "line025.gif", 0),
]

WHITE = dict(red=255, green=255, blue=255)
CREAM = dict(red=220, green=220, blue=180)
BLACK = dict(red=0, green=0, blue=0)
# (x, y, text, size, color)
TEXTS = [
    # banner engraved in the gold band (tile rows 0-33)
    (415, 8, "HART RAILROAD - NEVILLE ISLAND", 16, BLACK),
    (40,  60, "WEST YARD", 12, WHITE),   # promoted; between W-* lamps and SW101
    (149, 60, "BRICK",     12, WHITE),   # over SW100
    (205, 60, "PLANE",     12, WHITE),
    (347, 60, "BARN",      12, WHITE),   # over the SW117 crossover
    (645, 60, "EAST END",  12, WHITE),
    (905, 60, "PRINCESS",  12, WHITE),
    (205, 95,  "MAIN WEST", 8, CREAM),
    (525, 68,  "MAIN WEST", 8, CREAM),
    (525, 174, "MAIN EAST", 8, CREAM),
    (585, 152, "SOUTH YARD", 8, CREAM),
    (410, 68,  "ENGINE HOUSE", 8, CREAM),  # over the fan, where BARN used to be
    (1035, 153, "McKEESPORT", 8, CREAM),
    (1030, 44, "McKEES ROCKS", 8, CREAM),
    (24,  96,  "W-1", 8, CREAM),
    (24,  118, "W-2", 8, CREAM),
    (1090, 74, "K-1", 8, CREAM),
    (1090, 96, "K-2", 8, CREAM),
    # switch numbers under the OS lamp row (lamps 21px at y200 -> labels
    # y223), centered under the lamp / lamp pair
    (102, 223, "101", 8, WHITE),
    (167, 223, "100", 8, WHITE),
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
# on the IH* head). Bar centers: N 90, S 113, M 136, McRocks 67,
# McKeesport 141, Main East 166. 116/103 are switch-only — no icons.
N, S, M, MR, MK, ME = 90, 113, 136, 67, 141, 166
# (mast, stem_x, bar_center, facing, kind, head_or_None)
SIGNALS = [
    # Brick 101 Right: yard exits
    ("101RA",           72,  N,  "E", "d1", "IH436"),
    ("101RB",           72,  S,  "E", "d1", "IH437"),
    # Brick 100 Left
    ("100L",       210,  N,  "W", "h2", None),
    # Plane 102 Left
    ("102LA",          265,  S,  "W", "h2", None),
    ("102LB",   265,  M,  "W", "h2", None),
    # Barn 117 both ways (T6 is the westbound yard-lead home)
    ("117RA",      328,  S,  "E", "h2", None),
    ("117RB", 328, M, "E", "h2", None),
    ("117LB",     396,  S,  "W", "d1", "IH1334"),
    ("117LA",     396,  M,  "W", "h2", None),
    # East End 111 both ways
    ("111RA",    588,  N,  "E", "h2", None),
    ("111RB", 588,  S,  "E", "d1", "IH1236"),
    ("111L",      650,  N,  "W", "h2", None),
    # East End 110 Right (dwarf off the yard / ladder)
    ("110R",      658,  S,  "E", "d1", "IH1239"),
    # East End 112 both ways
    ("112R",      708,  ME, "E", "h2", None),
    ("112L",         780,  S,  "W", "h2", None),
    # Princess 113 Right
    ("113RA",      848,  N,  "E", "h2", None),
    ("113RB",      848,  S,  "E", "h2", None),
    # Princess 114 balloon
    ("114R",  1088,  MK, "E", "d1", "IH134"),
    ("114LA",         1050,  S,  "W", "d1", "IH143"),
    ("114LB", 1050,  MK, "W", "h2", None),
    # Princess 115 balloon
    ("115R", 1088, MR, "E", "d1", "IH141"),
    ("115LA",         1050,  N,  "W", "d1", "IH142"),
    ("115LB", 1050, MR, "W", "h2", None),
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
    for name, x, y, kind in TURNOUTS:
        parts.append(TURNOUT.format(name=name, x=x, y=y, **turnout_urls(kind)))
    for sensor, x, y, tip in LAMPS:
        parts.append(LAMP.format(sensor=sensor, x=x, y=y, tip=tip, u=U))
    for x, y, gif, rot in TRACKS:
        url = THIN if gif.startswith(("thin", "thick")) else U + "track/block/"
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
    re.compile(r'\s*<positionablelabel\b[^>]*text="(?:BRICK|PLANE|BARN|EAST END|PRINCESS|MAIN WEST|MAIN EAST|SOUTH YARD|WEST YARD|ENGINE TERMINAL|ENGINE HOUSE|YARD|McKEESPORT|McKEES ROCKS|K-1|K-2|W-1|W-2|1[01][0-9]|HART RAILROAD[^"]*)".*?</positionablelabel>', re.S),
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


if __name__ == "__main__":
    main()
