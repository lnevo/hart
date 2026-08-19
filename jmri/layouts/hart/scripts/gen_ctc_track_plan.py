#!/usr/bin/env python3
"""Generate the CTC panel track diagram (v2 — main + sidings, QV style).

Layout (three track rows, bars at y 40-44 / 63-67 / 86-90):

  row N (upper): Main West passing siding between SW111 and SW113 (with
                 Main West stubs), plus SW115 / McKees Rocks / K-1.
  row S (yard):  the yard run-through siding from Plane/Barn to East End:
                 SW102 diverges up, SW117 crossover, 116, 103 (South Yard
                 ladder stub down), YT1, East End ladder switches 107/108/
                 109/110 (yard stubs down), rejoining the main at SW112.
                 East of SW113 it carries East Lead / SW114 / McKeesport / K-2.
  row M (main):  Brick 101/100 - Plane 102 - SW117 bottom - Main East -
                 SW112 - then rises 45deg to the SW113 crossover.

The scissor crossover icons span exactly 23px between bars, which matches
adjacent rows: SW117 at y=57 joins yard<->main, SW111 and SW113 at y=34 join
the upper siding to the yard/East Lead row.

Writes the element block used both for ctc/GUIObjects.xml and for the
embedded <paneleditor> in tables.xml (see apply()).
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

# (turnout name, x, y, icon kind)  -- bar rows: y+6..10 (top) or y+29..33 (bottom)
TURNOUTS = [
    ("Switch 101", 21,  80, T + "left/west/os-l-w"),     # main; yard exit stubs down-west
    ("Switch 100", 86,  57, T + "left/east/os-l-e"),     # main (bar 86-90); Main West diverges up-east
    ("Switch 102", 151, 57, T + "left/east/os-l-e"),     # main; yard siding diverges up-east
    ("Switch 117", 216, 57, X + "left/os-l-sc"),         # scissor: yard (63-67) <-> main (86-90)
    ("Switch 116", 281, 34, T + "right/west/os-r-w"),    # yard row (bar 63-67); WY ladder stub up-west
    ("Switch 103", 346, 57, T + "right/east/os-r-e"),    # yard row; South Yard ladder stub down-east
    ("Switch 107", 411, 57, T + "left/west/os-l-w"),     # yard row; yard track stub down-west
    ("Switch 108", 476, 57, T + "left/west/os-l-w"),
    ("Switch 111", 552, 34, X + "right/os-r-sc"),        # scissor: Main West (40-44) <-> yard (63-67)
    ("Switch 109", 606, 57, T + "left/west/os-l-w"),
    ("Switch 110", 671, 57, T + "left/west/os-l-w"),
    ("Switch 112", 736, 57, T + "right/west/os-r-w"),    # main (bar 86-90); yard row joins up-west
    ("Switch 113", 801, 34, X + "left/os-l-sc"),         # scissor: Main West (40-44) <-> East Lead (63-67)
    ("Switch 114", 866, 57, T + "right/east/os-r-e"),    # East Lead row; McKeesport stub down-east
    ("Switch 115", 931, 11, T + "left/east/os-l-e"),     # Main West row (bar 40-44); McKees Rocks up-east
]

# (sensor, x, y, tooltip)
LAMPS = [
    ("Block 4-1",  33,  78, "OS 101 (Brick)"),
    ("Block 4-2",  98,  78, "OS 100 (Brick)"),
    ("Block 4-6",  133, 78, "Main West Brick-Plane"),
    ("Block 4-5",  163, 78, "OS 102 (Plane)"),
    ("Block 4-7",  199, 78, "East Main Ext"),
    ("Block 13-3", 228, 55, "OS 117 (yard side)"),
    ("Block 13-4", 228, 78, "OS 117b (main side)"),
    ("Block 13-1", 263, 55, "Yard T6"),
    ("Block 3-1",  293, 55, "OS 116 (West Yard)"),
    ("Block 3-2",  358, 55, "OS 103 (South Yard)"),
    ("Block 2-8",  393, 55, "Yard Track 1"),
    ("Block 12-1", 423, 55, "OS 107 (East End)"),
    ("Block 12-3", 488, 55, "OS 108 (East End)"),
    ("Block 2-3",  450, 78, "Main East"),
    ("Block 12-4", 553, 32, "OS 111a (Main West side)"),
    ("Block 12-6", 553, 55, "OS 111b (yard side)"),
    ("Block 12-5", 618, 55, "OS 109 (East End)"),
    ("Block 12-7", 683, 55, "OS 110 (East End)"),
    ("Block 12-8", 748, 78, "OS 112 (East End)"),
    ("Block 1-7",  781, 64, "East Lead"),
    ("Block 1-5",  813, 32, "OS 113b (Main West side)"),
    ("Block 1-6",  813, 55, "OS 113a (East Lead side)"),
    ("Block 1-3",  878, 55, "OS 114 (Princess)"),
    ("Block 1-4",  943, 32, "OS 115 (Princess)"),
]

B = "track/block/"
# (x, y, gif, rotation) -- line bars: line050 rows 3-7, line1 4-8, line25 9-13, line6 22-26
TRACKS = [
    # row M (main, bar 86-90)
    (52,  83, "line050.gif", 0),   # 101-100
    (116, 83, "line050.gif", 0),   # 100-102 (Brick-Plane)
    (182, 83, "line050.gif", 0),   # 102-117 (East Main Ext)
    (256, 64, "line6.gif",   0),   # Main East: 117 bottom -> 112 (481px)
    # row S (yard siding, bar 63-67)
    (178, 60, "line050.gif", 0),   # 102 diverging leg -> 117 top bar
    (246, 60, "line050.gif", 0),   # 117-116 (Yard T6)
    (311, 60, "line050.gif", 0),   # 116-103
    (376, 60, "line050.gif", 0),   # 103-107 (Yard Track 1)
    (442, 60, "line050.gif", 0),   # 107-108
    (512, 60, "line050.gif", 0),   # 108-111
    (577, 60, "line050.gif", 0),   # 111-109
    (642, 60, "line050.gif", 0),   # 109-110
    (700, 60, "line050.gif", 0),   # 110 -> 112 diverging leg
    (838, 60, "line050.gif", 0),   # 113 bottom -> 114 (East Lead row)
    (906, 60, "line050.gif", 0),   # 114 -> K-2 stub
    # row N (Main West siding, bar 40-44)
    (110, 60, "line025.gif", 0),   # SW100 Main West stub (bar 62-66; short, gapped)
    (508, 37, "line050.gif", 0),   # Main West stub west of 111
    (594, 31, "line25.gif",  0),   # 111 -> 113 passing siding (203px)
    (843, 36, "line1.gif",   0),   # 113 -> 115 (85px)
    (971, 37, "line050.gif", 0),   # 115 -> K-1 stub
    # East Lead rise: 112 (main) up to 113 lower bar, 45 degrees "/"
    (773, 60, "b-45.gif",    1),
]

WHITE = dict(red=255, green=255, blue=255)
CREAM = dict(red=220, green=220, blue=180)
# (x, y, text, size, color)
TEXTS = [
    (40,  12, "BRICK",     12, WHITE),
    (148, 12, "PLANE",     12, WHITE),
    (285, 12, "BARN",      12, WHITE),
    (520, 12, "EAST END",  12, WHITE),
    (838, 12, "PRINCESS",  12, WHITE),
    (100, 47, "MAIN WEST", 8,  CREAM),
    (450, 27, "MAIN WEST", 8,  CREAM),
    (418, 94, "MAIN EAST", 8,  CREAM),
    (878, 84, "McKEESPORT", 8, CREAM),
    (890, 2,  "McKEES ROCKS", 8, CREAM),
    (1018, 36, "K-1", 8, CREAM),
    (953, 57, "K-2", 8, CREAM),
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
    # every turnout icon (all 15 are being repositioned)
    re.compile(r'\s*<turnouticon\b[^>]*>.*?</turnouticon>', re.S),
    # every Block-* occupancy lamp on the diagram
    re.compile(r'\s*<sensoricon\b[^>]*sensor="Block [^"]*".*?</sensoricon>', re.S),
    # every track graphic label (line fillers, 45s)
    re.compile(r'\s*<positionablelabel\b[^>]*>\s*<icon url="[^"]*USS/track/block/[^"]*".*?</positionablelabel>', re.S),
    # plant/name texts previously generated by this script (idempotent reruns)
    re.compile(r'\s*<positionablelabel\b[^>]*text="(?:BRICK|PLANE|BARN|EAST END|PRINCESS|MAIN WEST|MAIN EAST|McKEESPORT|McKEES ROCKS|K-1|K-2)".*?</positionablelabel>', re.S),
]


def apply(text, close_tag="</paneleditor>"):
    """Strip old diagram elements and insert the new block before close_tag."""
    for pat in STRIP:
        text = pat.sub("", text)
    idx = text.rindex(close_tag)
    return text[:idx] + build_block() + "  " + close_tag[:0] + text[idx:]


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
