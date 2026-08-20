#!/usr/bin/env python3
"""Generate the CTC panel track diagram (v7 — background tiles + thin turnout legs).

Machine slots are 65px wide (slot = x//65). Blank slots 0, 7, 11 and 15;
Brick/Plane occupy slots 1-3 (SW101/100/102), Barn 4-6 (117/116/103),
East End 8-10 (111/110/112 — SW107/108/109 are hand-throw, no levers and
no lamps on the board), Princess 12-14 (113/114/115). Switch icons sit at
slot*65 + 21.

The gold panel background is tiled here too (it used to be the stale
15-column row from the first CTC build, which left the new blank slot 15
uncovered — the "hidden" right column): a 12px left cap at x=0, one 65px
tile per slot at x=12+65*slot (Panel-blank-7 for blank slots, Panel-sw-sig-7
for lever slots), and a 12px right cap at x=1052.

Rows (bar pixel ranges; scissor icons span exactly 23px between bars):

  N   88-92   Main West passing siding SW111 -> SW113 (straight through),
              SW115 / McKees Rocks / K-1. Approach lamp `Block 2-1` (Main
              West) sits in blank slot 7 on the stub west of SW111; lamp
              `Block 1-8` (West Main Ext) is on the 113-115 stretch.
  S  111-115  yard run-through siding, Plane/Barn -> East End (Yard Track
              1) -> SW110 -> SW112 -> East Lead -> SW113 -> SW114 -> K-2:
              one dead-straight line from SW103 to the K-2 stub. SW112 is
              drawn os-l-w (bar on this row) with its leg dropping SW to
              the main's 45deg rise. East Lead lamp `Block 1-7` sits in
              blank slot 11.
  M  134-138  main at Brick/Plane/Barn; dips 45deg east of SW117 to a
              bottom straight (164-168) under the South Yard, rising into
              SW112's leg (the main loops around the yard).

Yard symbols are thin 2px lines (QV style), served from ctc/icons/ via
"preference:ctc/icons/*.gif" (deploy them to JMRI_UserFiles/ctc/icons/).
SW103/110/116 use custom os-*-thin turnout icons (stock bar, 2px diverging
leg, stock unknown/inconsistent glyphs) so the legs into the yards match:
a two-spur fan east off SW103 (South Yard), its mirror west off SW110, and
the Engine Terminal fan up-west off SW116 (split = hand-throw SW118).

"WEST YARD" labels the W-1/W-2 staging stubs west of Brick (blocks West
Yard 1/2). Princess detection: OS 114 and K-2 are the SAME circuit (Block
1-3), as are OS 115 and K-1 (Block 1-4) — one lamp each at the OS
position. McKeesport (Block 1-2) and McKees Rocks (Block 1-1) are separate
circuits with lamps on their long horizontal branch stubs.

Writes both ctc/GUIObjects.xml and the embedded <paneleditor> in
tables.xml, and normalizes the panel window geometry to show all 16 slots.
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
        <closed url="{u}{kind}-closed.gif" scale="1.0">
          <rotation>0</rotation>
        </closed>
        <thrown url="{u}{kind}-thrown.gif" scale="1.0">
          <rotation>0</rotation>
        </thrown>
        <unknown url="{u}{kind}-unknown.gif" scale="1.0">
          <rotation>0</rotation>
        </unknown>
        <inconsistent url="{u}{kind}-inconsistent.gif" scale="1.0">
          <rotation>0</rotation>
        </inconsistent>
      </icons>
      <iconmaps />
    </turnouticon>"""

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

BLANK_SLOTS = {0, 7, 11, 15}

# (turnout name, x, y, icon kind) -- bar rows: y+6..10 (top) or y+29..33
# (bottom). Kinds prefixed "thin:" are the custom 2px-leg icons from
# preference:ctc/icons/.
TURNOUTS = [
    ("Switch 101", 86,  128, T + "left/west/os-l-w"),    # main; W-2 leg down-west
    ("Switch 100", 151, 105, T + "left/east/os-l-e"),    # main (bar 134-138); Main West diverges up-east
    ("Switch 102", 216, 105, T + "left/east/os-l-e"),    # main; yard siding diverges up-east
    ("Switch 117", 281, 105, X + "left/os-l-sc"),        # scissor: yard (111-115) <-> main (134-138)
    ("Switch 116", 346, 82,  "thin:os-r-w-thin"),        # yard row; Engine Terminal fan up-west
    ("Switch 103", 411, 105, "thin:os-r-e-thin"),        # yard row; South Yard fan (spurs east)
    ("Switch 111", 541, 82,  X + "right/os-r-sc"),       # scissor: Main West (88-92) <-> yard (111-115)
    ("Switch 110", 606, 105, "thin:os-l-w-thin"),        # yard row; South Yard fan (spurs west)
    ("Switch 112", 671, 105, T + "left/west/os-l-w"),    # East Lead straight through; main joins via SW leg
    ("Switch 113", 801, 82,  X + "left/os-l-sc"),        # scissor: Main West (88-92) <-> East Lead (111-115)
    ("Switch 114", 866, 105, T + "right/east/os-r-e"),   # East Lead row; McKeesport branch down-east
    ("Switch 115", 931, 59,  T + "left/east/os-l-e"),    # Main West row (bar 88-92); McKees Rocks up-east
]

# (sensor, x, y, tooltip) -- lamp y = bar top - 8
LAMPS = [
    ("Block 4-4",  60,  126, "W-1 (West Yard 1)"),
    ("Block 4-3",  45,  151, "W-2 (West Yard 2)"),
    ("Block 4-1",  98,  126, "OS 101 (Brick)"),
    ("Block 4-2",  163, 126, "OS 100 (Brick)"),
    ("Block 4-6",  198, 126, "Main West Brick-Plane"),
    ("Block 4-5",  228, 126, "OS 102 (Plane)"),
    ("Block 4-7",  264, 126, "East Main Ext"),
    ("Block 13-3", 293, 103, "OS 117 (yard side)"),
    ("Block 13-4", 293, 126, "OS 117b (main side)"),
    ("Block 13-1", 328, 103, "Yard T6"),
    ("Block 3-1",  358, 103, "OS 116 (West Yard)"),
    ("Block 3-2",  423, 103, "OS 103 (South Yard)"),
    ("Block 2-8",  462, 103, "Yard Track 1"),
    ("Block 2-1",  480, 80,  "Main West (approach to 111)"),
    ("Block 2-3",  390, 156, "Main East"),
    ("Block 12-4", 542, 80,  "OS 111a (Main West side)"),
    ("Block 12-6", 542, 103, "OS 111b (yard side)"),
    ("Block 12-7", 618, 103, "OS 110 (East End)"),
    ("Block 12-8", 683, 103, "OS 112 (East End)"),
    ("Block 1-7",  740, 103, "East Lead"),
    ("Block 1-5",  813, 80,  "OS 113b (Main West side)"),
    ("Block 1-6",  813, 103, "OS 113a (East Lead side)"),
    ("Block 1-8",  885, 80,  "West Main Ext"),
    ("Block 1-3",  878, 103, "OS 114 + K-2 (one circuit)"),
    ("Block 1-2",  930, 131, "McKeesport branch"),
    ("Block 1-4",  943, 80,  "OS 115 + K-1 (one circuit)"),
    ("Block 1-1",  975, 57,  "McKees Rocks branch"),
]

# (x, y, gif, rotation) -- line bar rows: line025 2-6, line050 3-7, line1 4-8,
# line25 9-13; b-45 30x30 "\" (rotation 1 -> "/"). thin* gifs come from
# preference:ctc/icons/ (2px lines: thin044 44x4, thin085 85x4, thin-45 15x15).
TRACKS = [
    # W-1 / W-2 staging stubs (WEST YARD), long horizontals to the panel edge
    (3,   130, "line1.gif",   0),   # W-1: main continues west of SW101
    (10,  155, "line1.gif",   0),   # W-2: off SW101's diverging leg
    # row M (main, bar 134-138) at Brick/Plane/Barn
    (117, 131, "line050.gif", 0),   # 101-100
    (181, 131, "line050.gif", 0),   # 100-102 (Brick-Plane)
    (247, 131, "line050.gif", 0),   # 102-117 (East Main Ext)
    # main dips under the South Yard and rises into SW112's leg
    (323, 136, "b-45.gif",    0),   # down: bar 134-138 -> bottom 164-168
    (360, 155, "line25.gif",  0),   # Main East bottom straight (360-563)
    (565, 160, "line1.gif",   0),   # bottom straight (565-650)
    (650, 136, "b-45.gif",    1),   # up: bottom -> SW112 leg tip (680,138)
    # row S (yard run-through / East Lead, bar 111-115): straight 103 -> K-2
    (175, 108, "line025.gif", 0),   # SW100 Main West stub (short, gapped)
    (243, 108, "line050.gif", 0),   # 102 diverging leg -> 117 top bar
    (311, 108, "line050.gif", 0),   # 117-116 (Yard T6)
    (376, 108, "line050.gif", 0),   # 116-103
    (453, 107, "line1.gif",   0),   # 103 -> 111 lower (Yard Track 1)
    (528, 108, "line050.gif", 0),   # into SW111's lower bar
    (578, 108, "line025.gif", 0),   # 111 lower -> 110
    (640, 108, "line050.gif", 0),   # 110 -> 112
    (709, 107, "line1.gif",   0),   # 112 -> 113 (East Lead, lamp 1-7)
    (790, 108, "line025.gif", 0),
    (838, 108, "line050.gif", 0),   # 113 bottom -> 114
    (906, 108, "line050.gif", 0),   # 114 -> K-2 stub...
    (948, 108, "line050.gif", 0),
    (992, 108, "line050.gif", 0),   # ...to the panel edge
    # South Yard fan off SW103 (thin QV-style, spurs east)
    (443, 137, "thin044.gif", 0),
    (443, 140, "thin-45.gif", 0),
    (457, 153, "thin044.gif", 0),
    # South Yard fan off SW110 (mirror: step at the switch, spurs west)
    (573, 137, "thin044.gif", 0),
    (602, 140, "thin-45.gif", 1),
    (559, 153, "thin044.gif", 0),
    # Engine Terminal fan off SW116 (thin, up-west; split = SW118)
    (309, 86,  "thin044.gif", 0),
    (294, 72,  "thin-45.gif", 0),
    (252, 70,  "thin044.gif", 0),
    # row N (Main West siding, bar 88-92)
    (456, 84,  "line1.gif",   0),   # Main West approach stub (lamp 2-1)
    (583, 79,  "line25.gif",  0),   # 111 -> 113 passing siding
    (780, 86,  "line025.gif", 0),
    (843, 84,  "line1.gif",   0),   # 113 -> 115 (West Main Ext, lamp 1-8)
    (971, 85,  "line050.gif", 0),   # 115 -> K-1 stub...
    (1013, 86, "line025.gif", 0),   # ...to the panel edge
    # McKees Rocks branch (bar 65-69) off SW115's riser
    (959, 62,  "line050.gif", 0),
    (1001, 63, "line025.gif", 0),
    # McKeesport branch (bar 139-143) off SW114's leg
    (891, 135, "line1.gif",   0),
    (974, 136, "line050.gif", 0),
]

WHITE = dict(red=255, green=255, blue=255)
CREAM = dict(red=220, green=220, blue=180)
# (x, y, text, size, color)
TEXTS = [
    (105, 60, "BRICK",     12, WHITE),
    (200, 60, "PLANE",     12, WHITE),
    (350, 60, "BARN",      12, WHITE),
    (580, 60, "EAST END",  12, WHITE),
    (838, 60, "PRINCESS",  12, WHITE),
    (165, 95,  "MAIN WEST", 8, CREAM),
    (395, 75,  "MAIN WEST", 8, CREAM),
    (370, 174, "MAIN EAST", 8, CREAM),
    (495, 142, "SOUTH YARD", 8, CREAM),
    (2,   115, "WEST YARD", 8, CREAM),
    (255, 58,  "ENGINE TERMINAL", 8, CREAM),
    (920, 148, "McKEESPORT", 8, CREAM),
    (930, 44,  "McKEES ROCKS", 8, CREAM),
    (28,  142, "W-1", 8, CREAM),
    (40,  166, "W-2", 8, CREAM),
    (1010, 72, "K-1", 8, CREAM),
    (1005, 96, "K-2", 8, CREAM),
]


def build_block():
    parts = []
    parts.append(BG.format(x=0, u=U, gif="Panel-left-7.gif"))
    for slot in range(16):
        gif = "Panel-blank-7.gif" if slot in BLANK_SLOTS else "Panel-sw-sig-7.gif"
        parts.append(BG.format(x=12 + 65 * slot, u=U, gif=gif))
    parts.append(BG.format(x=12 + 65 * 16, u=U, gif="Panel-right-7.gif"))
    for name, x, y, kind in TURNOUTS:
        if kind.startswith("thin:"):
            parts.append(TURNOUT.format(name=name, x=x, y=y, u=THIN, kind=kind[5:]))
        else:
            parts.append(TURNOUT.format(name=name, x=x, y=y, u=U, kind=kind))
    for sensor, x, y, tip in LAMPS:
        parts.append(LAMP.format(sensor=sensor, x=x, y=y, tip=tip, u=U))
    for x, y, gif, rot in TRACKS:
        url = THIN if gif.startswith("thin") else U + "track/block/"
        parts.append(TRACK.format(x=x, y=y, gif=gif, rot=rot, url=url))
    for x, y, text, size, col in TEXTS:
        parts.append(TEXT.format(x=x, y=y, text=text, size=size, **col))
    return "    " + "\n    ".join(parts) + "\n"


STRIP = [
    re.compile(r'\s*<turnouticon\b[^>]*>.*?</turnouticon>', re.S),
    re.compile(r'\s*<sensoricon\b[^>]*sensor="Block [^"]*".*?</sensoricon>', re.S),
    re.compile(r'\s*<positionablelabel\b[^>]*>\s*<icon url="(?:[^"]*USS/(?:track/block|background)/|preference:ctc/icons/)[^"]*".*?</positionablelabel>', re.S),
    re.compile(r'\s*<positionablelabel\b[^>]*text="(?:BRICK|PLANE|BARN|EAST END|PRINCESS|MAIN WEST|MAIN EAST|SOUTH YARD|WEST YARD|ENGINE TERMINAL|YARD|McKEESPORT|McKEES ROCKS|K-1|K-2|W-1|W-2)".*?</positionablelabel>', re.S),
]


def apply(text, close_tag="</paneleditor>"):
    """Strip old diagram elements, fix window geometry, insert new block."""
    for pat in STRIP:
        text = pat.sub("", text)
    text = re.sub(
        r'(<paneleditor\b[^>]*?) x="-?\d+" y="-?\d+" height="\d+" width="\d+"',
        r'\1 x="40" y="40" height="780" width="1120"', text, count=1)
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
