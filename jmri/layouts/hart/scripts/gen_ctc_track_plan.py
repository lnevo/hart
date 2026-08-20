#!/usr/bin/env python3
"""Generate the CTC panel track diagram (v8 — 17 slots, 45deg yard ladders).

Machine slots are 65px wide (slot = x//65). Blank slots 0, 4, 8, 12 and 16
— four interlockings of three lever columns each: Brick/Plane slots 1-3
(SW101/100/102), Barn 5-7 (117/116/103), East End 9-11 (111/110/112 —
SW107/108/109 are hand-throw, no levers and no lamps), Princess 13-15
(113/114/115). Switch icons sit at slot*65 + 21.

The gold background is generated too: 12px left cap at x=0, one 65px tile
per slot at x=12+65*slot (Panel-blank-7 for blank slots, Panel-sw-sig-7
for lever slots), right cap at x=1117.

Rows (bar pixel ranges; scissor icons span exactly 23px between bars):

  N   88-92   Main West passing siding SW111 -> SW113 (straight through,
              one block: West Main Ext `Block 1-8`, lamp centered in blank
              slot 12), then SW113 -> SW115 DIRECT (no block, no lamp),
              SW115 / McKees Rocks / K-1. Main West approach lamp `Block
              2-1` centered in blank slot 8 west of SW111.
  S  111-115  yard run-through siding: SW102 leg -> Yard T1 (`Block 4-8`,
              lamp centered in blank slot 4) -> SW117 -> Yard T6 -> SW116
              -> SW103 -> Yard Track 1 (`Block 2-8`, lamp centered in
              blank slot 8) -> SW110 -> SW112 -> East Lead (`Block 1-7`,
              lamp centered in blank slot 12) -> SW113 -> SW114 -> K-2.
  M  134-138  main at Brick/Plane; East Main Ext lamp (`Block 4-7`)
              centered in blank slot 4; dips 45deg east of SW117 to a
              bottom straight (164-168) under the South Yard, rising into
              SW112's leg.

South Yard: straight 45deg thin ladders off SW103 (down-east) and SW110
(down-west, mirror) — the switch legs continue as ladder lines parallel
to the Main East 45deg legs — with THREE run-through yard tracks (9px
pitch) connecting the two ladders (SW104-109 are hand-throw, not drawn).
Engine Terminal: the same ladder rotated 180deg, up-west off SW116
(split = hand-throw SW118, treated like 104-109), three stub tracks
ending flush at x=330.

All east branch stubs (K-1, K-2, McKees Rocks, McKeesport) end flush at
x=1105 with their lamps aligned at x=1060 and labels centered on the
stubs; W-1/W-2 (WEST YARD) start flush at x=0 with lamps aligned at x=30.

Thin 2px gifs and the os-*-thin turnout icons (SW103/110/116) come from
"preference:ctc/icons/*.gif" — deploy to JMRI_UserFiles/ctc/icons/.

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

N_SLOTS = 17
BLANK_SLOTS = {0, 4, 8, 12, 16}

# (turnout name, x, y, icon kind) -- bar rows: y+6..10 (os-l-w/os-r-e top),
# y+29..33 (os-l-e/os-r-w bottom). "thin:" kinds are the custom 2px-leg
# icons from preference:ctc/icons/.
TURNOUTS = [
    ("Switch 101", 86,  128, T + "left/west/os-l-w"),    # main; W-2 leg down-west
    ("Switch 100", 151, 105, T + "left/east/os-l-e"),    # main (bar 134-138); Main West stub up-east
    ("Switch 102", 216, 105, T + "left/east/os-l-e"),    # main; yard siding diverges up-east
    ("Switch 117", 346, 105, X + "left/os-l-sc"),        # scissor: yard (111-115) <-> main (134-138)
    ("Switch 116", 411, 82,  "thin:os-r-w-thin"),        # yard row; Engine Terminal ladder up-west
    ("Switch 103", 476, 105, "thin:os-r-e-thin"),        # yard row; South Yard ladder down-east
    ("Switch 111", 606, 82,  X + "right/os-r-sc"),       # scissor: Main West (88-92) <-> yard (111-115)
    ("Switch 110", 671, 105, "thin:os-l-w-thin"),        # yard row; South Yard ladder down-west
    ("Switch 112", 736, 105, T + "left/west/os-l-w"),    # East Lead straight through; main joins via SW leg
    ("Switch 113", 866, 82,  X + "left/os-l-sc"),        # scissor: Main West (88-92) <-> East Lead (111-115)
    ("Switch 114", 931, 105, T + "right/east/os-r-e"),   # East Lead row; McKeesport branch down-east
    ("Switch 115", 996, 59,  T + "left/east/os-l-e"),    # Main West row (bar 88-92); McKees Rocks up-east
]

# (sensor, x, y, tooltip) -- lamp y = bar top - 8; connector lamps centered
# in their blank slot (slot center x = 65*slot + 26)
LAMPS = [
    ("Block 4-4",  30,  126, "W-1 (West Yard 1)"),
    ("Block 4-3",  30,  151, "W-2 (West Yard 2)"),
    ("Block 4-1",  98,  126, "OS 101 (Brick)"),
    ("Block 4-2",  163, 126, "OS 100 (Brick)"),
    ("Block 4-6",  197, 126, "Main West Brick-Plane"),
    ("Block 4-5",  228, 126, "OS 102 (Plane)"),
    ("Block 4-7",  286, 126, "East Main Ext"),
    ("Block 4-8",  286, 103, "Yard T1 (Plane-Barn diverging)"),
    ("Block 13-3", 358, 103, "OS 117 (yard side)"),
    ("Block 13-4", 358, 126, "OS 117b (main side)"),
    ("Block 13-1", 392, 103, "Yard T6"),
    ("Block 3-1",  423, 103, "OS 116 (Barn)"),
    ("Block 3-2",  488, 103, "OS 103 (South Yard)"),
    ("Block 2-8",  546, 103, "Yard Track 1"),
    ("Block 2-1",  546, 80,  "Main West (approach to 111)"),
    ("Block 2-3",  450, 156, "Main East"),
    ("Block 12-4", 607, 80,  "OS 111a (Main West side)"),
    ("Block 12-6", 607, 103, "OS 111b (yard side)"),
    ("Block 12-7", 683, 103, "OS 110 (East End)"),
    ("Block 12-8", 748, 103, "OS 112 (East End)"),
    ("Block 1-7",  806, 103, "East Lead"),
    ("Block 1-8",  806, 80,  "West Main Ext (111-113 siding)"),
    ("Block 1-5",  867, 80,  "OS 113b (Main West side)"),
    ("Block 1-6",  867, 103, "OS 113a (East Lead side)"),
    ("Block 1-3",  943, 103, "OS 114 + K-2 (one circuit)"),
    ("Block 1-4",  1008, 80, "OS 115 + K-1 (one circuit)"),
    ("Block 1-1",  1060, 57, "McKees Rocks branch"),
    ("Block 1-2",  1060, 131, "McKeesport branch"),
]

# (x, y, gif, rotation) -- line bar rows: line025 2-6, line050 3-7, line1 4-8,
# line25 9-13; b-45 30x30 "\" (rotation 1 -> "/"). thin* gifs are 2px lines
# from preference:ctc/icons/ (thin044 44px, thin085 85px, thin-45 15x15 "\",
# rotation 1 -> "/").
TRACKS = [
    # W-1 / W-2 (WEST YARD) stubs, flush to the west edge (line gifs have
    # intrinsic end margins: line025 1px, line050 2px, line1 7px, line25 12px)
    (0,   132, "line025.gif", 0),   # W-1 flush at x=0
    (0,   130, "line1.gif",   0),   # W-1: main continues west of SW101
    (0,   157, "line025.gif", 0),   # W-2 flush at x=0
    (0,   155, "line1.gif",   0),   # W-2: off SW101's diverging leg
    (72,  157, "line025.gif", 0),   # ...to the leg tip (95,161)
    # row M (main, bar 134-138) at Brick/Plane
    (117, 131, "line050.gif", 0),   # 101-100
    (181, 131, "line050.gif", 0),   # 100-102 (Main West Brick-Plane)
    (258, 131, "line1.gif",   0),   # 102-117 (East Main Ext, blank slot 4)
    # main dips under the South Yard and rises into SW112's leg
    (388, 136, "b-45.gif",    0),   # down: bar 134-138 -> bottom 164-168
    (407, 155, "line25.gif",  0),   # Main East bottom straight (drawn 419-597)
    (524, 155, "line25.gif",  0),   # overlapped: one block, no joint (to 714)
    (715, 136, "b-45.gif",    1),   # up: bottom -> SW112 leg tip (745,138)
    # row S (yard run-through / East Lead, bar 111-115)
    (175, 109, "line025.gif", 0),   # SW100 Main West stub (short, gapped)
    (243, 109, "line025.gif", 0),   # 102 leg -> 117: Yard T1 (blank slot 4)
    (250, 107, "line1.gif",   0),
    (325, 109, "line025.gif", 0),
    (388, 109, "line025.gif", 0),   # 117-116 (Yard T6)
    (452, 109, "line025.gif", 0),   # 116-103
    (518, 107, "line1.gif",   0),   # 103 -> 111 (Yard Track 1, blank slot 8)
    (648, 109, "line025.gif", 0),   # 111 lower -> 110
    (713, 109, "line025.gif", 0),   # 110 -> 112
    (778, 107, "line1.gif",   0),   # 112 -> 113 (East Lead, blank slot 12)
    (908, 109, "line025.gif", 0),   # 113 bottom -> 114
    (973, 107, "line1.gif",   0),   # 114 -> K-2 stub...
    (1020, 107, "line1.gif",  0),
    (1084, 109, "line025.gif", 0),  # ...flush to x=1106
    # South Yard: the 45deg icon legs continue as straight 45deg ladders
    # (east ladder line x = y + 379, west ladder x = 807 - y) with three
    # run-through yard tracks at 9px pitch connecting them
    (516, 137, "thin-45.gif", 0),   # east ladder off SW103 leg exit (516,137)...
    (528, 149, "thin4512.gif", 0),  # ...ending at yard track 4 (539,160)
    (657, 137, "thin-45.gif", 1),   # west ladder off SW110 leg exit (671,136)...
    (648, 149, "thin4512.gif", 1),  # ...ending at yard track 4 (648,160)
    (521, 142, "thin085.gif", 0),   # yard track 2 (521-665)
    (580, 142, "thin085.gif", 0),
    (530, 151, "thin085.gif", 0),   # yard track 3 (530-656)
    (571, 151, "thin085.gif", 0),
    (539, 160, "thin085.gif", 0),   # yard track 4 (539-647)
    (562, 160, "thin085.gif", 0),
    # Engine Terminal: same ladder rotated 180deg, up-west off SW116's leg
    # exit (411,90); ladder line x = y + 321, three stubs flush at x=330
    (397, 76,  "thin-45.gif", 0),   # ladder (411,90) up-west...
    (390, 69,  "thin4512.gif", 0),  # ...ending at terminal track 1 (390,69)
    (330, 68,  "thin044.gif", 0),   # terminal track 1 (330-389)
    (345, 68,  "thin044.gif", 0),
    (330, 77,  "thin044.gif", 0),   # terminal track 2 (330-398)
    (354, 77,  "thin044.gif", 0),
    (330, 86,  "thin044.gif", 0),   # terminal track 3 (330-407)
    (363, 86,  "thin044.gif", 0),
    # row N (Main West siding, bar 88-92)
    (519, 84,  "line1.gif",   0),   # Main West approach stub (blank slot 8)
    (645, 86,  "line025.gif", 0),   # 111 -> 113 (West Main Ext, one block)
    (648, 79,  "line25.gif",  0),
    (840, 86,  "line025.gif", 0),
    (908, 84,  "line1.gif",   0),   # 113 -> 115 direct (no block)
    (1020, 84, "line1.gif",   0),   # 115 -> K-1...
    (1084, 86, "line025.gif", 0),   # ...flush to x=1106
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
# (x, y, text, size, color)
TEXTS = [
    (105, 60, "BRICK",     12, WHITE),
    (205, 60, "PLANE",     12, WHITE),
    (415, 60, "BARN",      12, WHITE),
    (645, 60, "EAST END",  12, WHITE),
    (905, 60, "PRINCESS",  12, WHITE),
    (165, 95,  "MAIN WEST", 8, CREAM),
    (525, 68,  "MAIN WEST", 8, CREAM),
    (440, 174, "MAIN EAST", 8, CREAM),
    (552, 122, "SOUTH YARD", 8, CREAM),
    (2,   115, "WEST YARD", 8, CREAM),
    (300, 52,  "ENGINE TERMINAL", 8, CREAM),
    (1035, 148, "McKEESPORT", 8, CREAM),
    (1030, 44, "McKEES ROCKS", 8, CREAM),
    (34,  140, "W-1", 8, CREAM),
    (34,  166, "W-2", 8, CREAM),
    (1090, 74, "K-1", 8, CREAM),
    (1090, 96, "K-2", 8, CREAM),
]


def build_block():
    parts = []
    parts.append(BG.format(x=0, u=U, gif="Panel-left-7.gif"))
    for slot in range(N_SLOTS):
        gif = "Panel-blank-7.gif" if slot in BLANK_SLOTS else "Panel-sw-sig-7.gif"
        parts.append(BG.format(x=12 + 65 * slot, u=U, gif=gif))
    parts.append(BG.format(x=12 + 65 * N_SLOTS, u=U, gif="Panel-right-7.gif"))
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
