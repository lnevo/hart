#!/usr/bin/env python3
"""Generate the CTC panel track diagram (v6 — straight rows, thin yard lines).

Machine slots are 65px wide (slot = x//65). Blank slots 0, 7, 11 and 15;
Brick/Plane occupy slots 1-3 (SW101/100/102), Barn 4-6 (117/116/103),
East End 8-10 (111/110/112 — SW107/108/109 are hand-throw, no levers and
no lamps on the board), Princess 12-14 (113/114/115). Switch icons sit at
slot*65 + 21.

Rows (bar pixel ranges; scissor icons span exactly 23px between bars):

  N   80-84   Main West passing siding SW111 -> SW113 (straight through),
              SW115 / McKees Rocks / K-1. Approach lamp `Block 2-1` (Main
              West) sits in blank slot 7 on the stub west of SW111.
  S  103-107  yard run-through siding, Plane/Barn -> East End (Yard Track
              1) -> SW110 -> SW112 -> East Lead -> SW113 -> SW114 -> K-2:
              one dead-straight line from SW103 to the K-2 stub. SW112 is
              drawn os-l-w (bar on this row) with its leg dropping SW to
              the main's 45deg rise. East Lead lamp `Block 1-7` sits in
              blank slot 11.
  M  126-130  main at Brick/Plane/Barn; dips 45deg east of SW117 to a
              bottom straight (156-160) under the South Yard, rising into
              SW112's leg (the main loops around the yard).

Yard symbols are thin 2px lines (QV style), served from ctc/icons/ via
"preference:ctc/icons/*.gif" (deploy them to JMRI_UserFiles/ctc/icons/):
a two-spur fan east off SW103, its mirror west off SW110, and a small
West Yard fan up-west off SW116.

Princess detection: OS 114 and K-2 are the SAME circuit (Block 1-3), as
are OS 115 and K-1 (Block 1-4) — one lamp each at the OS position.
McKeesport (Block 1-2) and McKees Rocks (Block 1-1) are separate circuits
with lamps on their long horizontal branch stubs. W-1/W-2 staging stubs
run west from Brick to the panel edge.

Writes both ctc/GUIObjects.xml and the embedded <paneleditor> in
tables.xml, and normalizes the panel window geometry to show all 16 slots.
"""
import re
import sys

U = "program:resources/icons/USS/"
THIN = "preference:ctc/icons/"

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

# (turnout name, x, y, icon kind) -- bar rows: y+6..10 (top) or y+29..33 (bottom)
TURNOUTS = [
    ("Switch 101", 86,  120, T + "left/west/os-l-w"),    # main; W-2 leg down-west
    ("Switch 100", 151, 97,  T + "left/east/os-l-e"),    # main (bar 126-130); Main West diverges up-east
    ("Switch 102", 216, 97,  T + "left/east/os-l-e"),    # main; yard siding diverges up-east
    ("Switch 117", 281, 97,  X + "left/os-l-sc"),        # scissor: yard (103-107) <-> main (126-130)
    ("Switch 116", 346, 74,  T + "right/west/os-r-w"),   # yard row; West Yard fan up-west
    ("Switch 103", 411, 97,  T + "right/east/os-r-e"),   # yard row; South Yard fan (spurs east)
    ("Switch 111", 541, 74,  X + "right/os-r-sc"),       # scissor: Main West (80-84) <-> yard (103-107)
    ("Switch 110", 606, 97,  T + "left/west/os-l-w"),    # yard row; South Yard fan (spurs west)
    ("Switch 112", 671, 97,  T + "left/west/os-l-w"),    # East Lead straight through; main joins via SW leg
    ("Switch 113", 801, 74,  X + "left/os-l-sc"),        # scissor: Main West (80-84) <-> East Lead (103-107)
    ("Switch 114", 866, 97,  T + "right/east/os-r-e"),   # East Lead row; McKeesport branch down-east
    ("Switch 115", 931, 51,  T + "left/east/os-l-e"),    # Main West row (bar 80-84); McKees Rocks up-east
]

# (sensor, x, y, tooltip) -- lamp y = bar top - 8
LAMPS = [
    ("Block 4-4",  35,  118, "W-1 (West Yard 1)"),
    ("Block 4-3",  45,  143, "W-2 (West Yard 2)"),
    ("Block 4-1",  98,  118, "OS 101 (Brick)"),
    ("Block 4-2",  163, 118, "OS 100 (Brick)"),
    ("Block 4-6",  198, 118, "Main West Brick-Plane"),
    ("Block 4-5",  228, 118, "OS 102 (Plane)"),
    ("Block 4-7",  264, 118, "East Main Ext"),
    ("Block 13-3", 293, 95,  "OS 117 (yard side)"),
    ("Block 13-4", 293, 118, "OS 117b (main side)"),
    ("Block 13-1", 328, 95,  "Yard T6"),
    ("Block 3-1",  358, 95,  "OS 116 (West Yard)"),
    ("Block 3-2",  423, 95,  "OS 103 (South Yard)"),
    ("Block 2-8",  462, 95,  "Yard Track 1"),
    ("Block 2-1",  480, 72,  "Main West (approach to 111)"),
    ("Block 2-3",  390, 148, "Main East"),
    ("Block 12-4", 542, 72,  "OS 111a (Main West side)"),
    ("Block 12-6", 542, 95,  "OS 111b (yard side)"),
    ("Block 12-7", 618, 95,  "OS 110 (East End)"),
    ("Block 12-8", 683, 95,  "OS 112 (East End)"),
    ("Block 1-7",  740, 95,  "East Lead"),
    ("Block 1-5",  813, 72,  "OS 113b (Main West side)"),
    ("Block 1-6",  813, 95,  "OS 113a (East Lead side)"),
    ("Block 1-3",  878, 95,  "OS 114 + K-2 (one circuit)"),
    ("Block 1-2",  930, 123, "McKeesport branch"),
    ("Block 1-4",  943, 72,  "OS 115 + K-1 (one circuit)"),
    ("Block 1-1",  975, 49,  "McKees Rocks branch"),
]

# (x, y, gif, rotation) -- line bar rows: line025 2-6, line050 3-7, line1 4-8,
# line25 9-13; b-45 30x30 "\" (rotation 1 -> "/"). thin* gifs come from
# preference:ctc/icons/ (2px lines: thin044 44x4, thin085 85x4, thin-45 15x15).
TRACKS = [
    # W-1 / W-2 staging stubs, long horizontals to the panel edge
    (3,   122, "line1.gif",   0),   # W-1: main continues west of SW101
    (10,  147, "line1.gif",   0),   # W-2: off SW101's diverging leg
    # row M (main, bar 126-130) at Brick/Plane/Barn
    (117, 123, "line050.gif", 0),   # 101-100
    (181, 123, "line050.gif", 0),   # 100-102 (Brick-Plane)
    (247, 123, "line050.gif", 0),   # 102-117 (East Main Ext)
    # main dips under the South Yard and rises into SW112's leg
    (323, 128, "b-45.gif",    0),   # down: bar 126-130 -> bottom 156-160
    (360, 147, "line25.gif",  0),   # Main East bottom straight (360-563)
    (565, 152, "line1.gif",   0),   # bottom straight (565-650)
    (650, 128, "b-45.gif",    1),   # up: bottom -> SW112 leg tip (680,130)
    # row S (yard run-through / East Lead, bar 103-107): straight 103 -> K-2
    (175, 100, "line025.gif", 0),   # SW100 Main West stub (short, gapped)
    (243, 100, "line050.gif", 0),   # 102 diverging leg -> 117 top bar
    (311, 100, "line050.gif", 0),   # 117-116 (Yard T6)
    (376, 100, "line050.gif", 0),   # 116-103
    (453, 99,  "line1.gif",   0),   # 103 -> 111 lower (Yard Track 1)
    (528, 100, "line050.gif", 0),   # into SW111's lower bar
    (578, 100, "line025.gif", 0),   # 111 lower -> 110
    (640, 100, "line050.gif", 0),   # 110 -> 112
    (709, 99,  "line1.gif",   0),   # 112 -> 113 (East Lead, lamp 1-7)
    (790, 100, "line025.gif", 0),
    (838, 100, "line050.gif", 0),   # 113 bottom -> 114
    (906, 100, "line050.gif", 0),   # 114 -> K-2 stub...
    (948, 100, "line050.gif", 0),
    (992, 100, "line050.gif", 0),   # ...to the panel edge
    # South Yard fan off SW103 (thin QV-style, spurs east)
    (443, 129, "thin044.gif", 0),
    (443, 132, "thin-45.gif", 0),
    (457, 145, "thin044.gif", 0),
    # South Yard fan off SW110 (mirror: step at the switch, spurs west)
    (573, 129, "thin044.gif", 0),
    (602, 132, "thin-45.gif", 1),
    (559, 145, "thin044.gif", 0),
    # West Yard fan off SW116 (thin, up-west)
    (309, 78,  "thin044.gif", 0),
    (294, 64,  "thin-45.gif", 0),
    (252, 62,  "thin044.gif", 0),
    # row N (Main West siding, bar 80-84)
    (456, 76,  "line1.gif",   0),   # Main West approach stub (lamp 2-1)
    (583, 71,  "line25.gif",  0),   # 111 -> 113 passing siding
    (780, 78,  "line025.gif", 0),
    (843, 76,  "line1.gif",   0),   # 113 -> 115
    (971, 77,  "line050.gif", 0),   # 115 -> K-1 stub...
    (1013, 78, "line025.gif", 0),   # ...to the panel edge
    # McKees Rocks branch (bar 57-61) off SW115's riser
    (959, 54,  "line050.gif", 0),
    (1001, 55, "line025.gif", 0),
    # McKeesport branch (bar 131-135) off SW114's leg
    (891, 127, "line1.gif",   0),
    (974, 128, "line050.gif", 0),
]

WHITE = dict(red=255, green=255, blue=255)
CREAM = dict(red=220, green=220, blue=180)
# (x, y, text, size, color)
TEXTS = [
    (105, 52, "BRICK",     12, WHITE),
    (200, 52, "PLANE",     12, WHITE),
    (350, 52, "BARN",      12, WHITE),
    (580, 52, "EAST END",  12, WHITE),
    (838, 52, "PRINCESS",  12, WHITE),
    (165, 87,  "MAIN WEST", 8, CREAM),
    (395, 67,  "MAIN WEST", 8, CREAM),
    (370, 166, "MAIN EAST", 8, CREAM),
    (495, 134, "SOUTH YARD", 8, CREAM),
    (290, 50,  "WEST YARD", 8, CREAM),
    (920, 140, "McKEESPORT", 8, CREAM),
    (930, 36,  "McKEES ROCKS", 8, CREAM),
    (28,  134, "W-1", 8, CREAM),
    (40,  158, "W-2", 8, CREAM),
    (1010, 64, "K-1", 8, CREAM),
    (1005, 88, "K-2", 8, CREAM),
]


def build_block():
    parts = []
    for name, x, y, kind in TURNOUTS:
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
    re.compile(r'\s*<positionablelabel\b[^>]*>\s*<icon url="(?:[^"]*USS/track/block/|preference:ctc/icons/)[^"]*".*?</positionablelabel>', re.S),
    re.compile(r'\s*<positionablelabel\b[^>]*text="(?:BRICK|PLANE|BARN|EAST END|PRINCESS|MAIN WEST|MAIN EAST|SOUTH YARD|WEST YARD|YARD|McKEESPORT|McKEES ROCKS|K-1|K-2|W-1|W-2)".*?</positionablelabel>', re.S),
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
