#!/usr/bin/env python3
"""Generate the CTC panel track diagram (v3 — main + sidings + East End ladder).

Rows (bar pixel ranges; scissor icons span exactly 23px between bars):

  N   80-84   Main West passing siding between SW111 and SW113 (stubs +
              labels at both ends), SW115 / McKees Rocks / K-1.
  S  103-107  yard run-through siding, Plane/Barn -> East End: SW102
              diverges up, SW117 scissor, 116, 103 (South Yard stub down),
              YT1, SW111 lower, SW110, rejoining the main at SW112.
              East of SW113 it carries East Lead / SW114 / McKeesport / K-2.
  L  123-127  East End yard ladder: hangs off SW110's stub, holds 109/108/
              107 with yard-track stubs down-west (dead-ends toward the
              South Yard, whose ladder stub descends from SW103 opposite).
  M  126-130  main at Brick/Plane/Barn (101, 100, 102, SW117 bottom) and at
              SW112; between them it dips 45deg to...
  B  156-160  ...a bottom straight (Main East) that loops under the yard,
              rising 45deg back up to SW112 (physically true: the main
              swings around the yard).

Everything sits 40px lower than v2 so the diagram clears the header band.
Writes both ctc/GUIObjects.xml and the embedded <paneleditor> in tables.xml.
"""
import re
import sys

U = "program:resources/icons/USS/"

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
      <icon url="{u}track/block/{gif}" degrees="0" scale="1.0">
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
    ("Switch 101", 21,  120, T + "left/west/os-l-w"),    # main; yard exit stubs down-west
    ("Switch 100", 86,  97,  T + "left/east/os-l-e"),    # main (bar 126-130); Main West diverges up-east
    ("Switch 102", 151, 97,  T + "left/east/os-l-e"),    # main; yard siding diverges up-east
    ("Switch 117", 216, 97,  X + "left/os-l-sc"),        # scissor: yard (103-107) <-> main (126-130)
    ("Switch 116", 281, 74,  T + "right/west/os-r-w"),   # yard row (bar 103-107); WY ladder stub up-west
    ("Switch 103", 346, 97,  T + "right/east/os-r-e"),   # yard row; South Yard ladder stub down-east
    ("Switch 107", 411, 117, T + "left/west/os-l-w"),    # ladder row (bar 127-131); yard stub down-west
    ("Switch 108", 476, 117, T + "left/west/os-l-w"),    # ladder row
    ("Switch 111", 552, 74,  X + "right/os-r-sc"),       # scissor: Main West (80-84) <-> yard (103-107)
    ("Switch 109", 606, 117, T + "left/west/os-l-w"),    # ladder row
    ("Switch 110", 671, 97,  T + "left/west/os-l-w"),    # yard row; stub descends onto the ladder row
    ("Switch 112", 736, 97,  T + "right/west/os-r-w"),   # main (bar 126-130); yard row joins up-west
    ("Switch 113", 801, 74,  X + "left/os-l-sc"),        # scissor: Main West (80-84) <-> East Lead (103-107)
    ("Switch 114", 866, 97,  T + "right/east/os-r-e"),   # East Lead row; McKeesport stub down-east
    ("Switch 115", 931, 51,  T + "left/east/os-l-e"),    # Main West row (bar 80-84); McKees Rocks up-east
]

# (sensor, x, y, tooltip) -- lamp y = bar top - 8
LAMPS = [
    ("Block 4-1",  33,  118, "OS 101 (Brick)"),
    ("Block 4-2",  98,  118, "OS 100 (Brick)"),
    ("Block 4-6",  133, 118, "Main West Brick-Plane"),
    ("Block 4-5",  163, 118, "OS 102 (Plane)"),
    ("Block 4-7",  199, 118, "East Main Ext"),
    ("Block 13-3", 228, 95,  "OS 117 (yard side)"),
    ("Block 13-4", 228, 118, "OS 117b (main side)"),
    ("Block 13-1", 263, 95,  "Yard T6"),
    ("Block 3-1",  293, 95,  "OS 116 (West Yard)"),
    ("Block 3-2",  358, 95,  "OS 103 (South Yard)"),
    ("Block 2-8",  393, 95,  "Yard Track 1"),
    ("Block 12-1", 423, 115, "OS 107 (East End ladder)"),
    ("Block 12-3", 488, 115, "OS 108 (East End ladder)"),
    ("Block 2-3",  450, 148, "Main East"),
    ("Block 12-4", 553, 72,  "OS 111a (Main West side)"),
    ("Block 12-6", 553, 95,  "OS 111b (yard side)"),
    ("Block 12-5", 618, 115, "OS 109 (East End ladder)"),
    ("Block 12-7", 683, 95,  "OS 110 (East End)"),
    ("Block 12-8", 748, 118, "OS 112 (East End)"),
    ("Block 1-7",  783, 108, "East Lead"),
    ("Block 1-5",  813, 72,  "OS 113b (Main West side)"),
    ("Block 1-6",  813, 95,  "OS 113a (East Lead side)"),
    ("Block 1-3",  878, 95,  "OS 114 (Princess)"),
    ("Block 1-4",  943, 72,  "OS 115 (Princess)"),
]

# (x, y, gif, rotation) -- line bar rows: line025 2-6, line050 3-7, line1 4-8,
# line2 7-11, line25 9-13, line5 18-22; b-45 30x30 "\" (rotation 1 -> "/")
TRACKS = [
    # row M (main, bar 126-130) at Brick/Plane/Barn
    (52,  123, "line050.gif", 0),   # 101-100
    (116, 123, "line050.gif", 0),   # 100-102 (Brick-Plane)
    (182, 123, "line050.gif", 0),   # 102-117 (East Main Ext)
    # main dips under the East End yard and comes back up at SW112
    (258, 128, "b-45.gif",    0),   # down: bar 126-130 -> bottom 156-160
    (287, 138, "line5.gif",   0),   # Main East bottom straight (287-688)
    (688, 128, "b-45.gif",    1),   # up: bottom -> bar 126-130
    (714, 124, "line025.gif", 0),   # short run into SW112
    # row S (yard run-through, bar 103-107)
    (178, 100, "line050.gif", 0),   # 102 diverging leg -> 117 top bar
    (246, 100, "line050.gif", 0),   # 117-116 (Yard T6)
    (311, 100, "line050.gif", 0),   # 116-103
    (388, 96,  "line2.gif",   0),   # 103 -> 111 lower (Yard Track 1)
    (592, 99,  "line1.gif",   0),   # 111 lower -> 110
    (700, 100, "line050.gif", 0),   # 110 -> 112 diverging leg
    (838, 100, "line050.gif", 0),   # 113 bottom -> 114 (East Lead row)
    (906, 100, "line050.gif", 0),   # 114 -> K-2 stub
    # row L (East End ladder, bar 127-131)
    (441, 120, "line050.gif", 0),   # 107-108
    (518, 119, "line1.gif",   0),   # 108-109 (under SW111's column)
    (640, 120, "line050.gif", 0),   # 109 -> SW110's descending stub
    # row N (Main West siding, bar 80-84)
    (110, 100, "line025.gif", 0),   # SW100 Main West stub (short, gapped)
    (508, 77,  "line050.gif", 0),   # Main West stub west of 111
    (594, 71,  "line25.gif",  0),   # 111 -> 113 passing siding
    (843, 76,  "line1.gif",   0),   # 113 -> 115
    (971, 77,  "line050.gif", 0),   # 115 -> K-1 stub
    # East Lead rise: SW112 (main) up to SW113's lower bar
    (773, 100, "b-45.gif",    1),
]

WHITE = dict(red=255, green=255, blue=255)
CREAM = dict(red=220, green=220, blue=180)
# (x, y, text, size, color)
TEXTS = [
    (40,  52, "BRICK",     12, WHITE),
    (148, 52, "PLANE",     12, WHITE),
    (285, 52, "BARN",      12, WHITE),
    (520, 52, "EAST END",  12, WHITE),
    (838, 52, "PRINCESS",  12, WHITE),
    (100, 87,  "MAIN WEST", 8, CREAM),
    (450, 67,  "MAIN WEST", 8, CREAM),
    (425, 166, "MAIN EAST", 8, CREAM),
    (370, 138, "YARD",      8, CREAM),
    (878, 124, "McKEESPORT", 8, CREAM),
    (920, 42,  "McKEES ROCKS", 8, CREAM),
    (1018, 76, "K-1", 8, CREAM),
    (953, 97,  "K-2", 8, CREAM),
]


def build_block():
    parts = []
    for name, x, y, kind in TURNOUTS:
        parts.append(TURNOUT.format(name=name, x=x, y=y, u=U, kind=kind))
    for sensor, x, y, tip in LAMPS:
        parts.append(LAMP.format(sensor=sensor, x=x, y=y, tip=tip, u=U))
    for x, y, gif, rot in TRACKS:
        parts.append(TRACK.format(x=x, y=y, gif=gif, rot=rot, u=U))
    for x, y, text, size, col in TEXTS:
        parts.append(TEXT.format(x=x, y=y, text=text, size=size, **col))
    return "    " + "\n    ".join(parts) + "\n"


STRIP = [
    re.compile(r'\s*<turnouticon\b[^>]*>.*?</turnouticon>', re.S),
    re.compile(r'\s*<sensoricon\b[^>]*sensor="Block [^"]*".*?</sensoricon>', re.S),
    re.compile(r'\s*<positionablelabel\b[^>]*>\s*<icon url="[^"]*USS/track/block/[^"]*".*?</positionablelabel>', re.S),
    re.compile(r'\s*<positionablelabel\b[^>]*text="(?:BRICK|PLANE|BARN|EAST END|PRINCESS|MAIN WEST|MAIN EAST|YARD|McKEESPORT|McKEES ROCKS|K-1|K-2)".*?</positionablelabel>', re.S),
]


def apply(text, close_tag="</paneleditor>"):
    """Strip old diagram elements and insert the new block before close_tag."""
    for pat in STRIP:
        text = pat.sub("", text)
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
