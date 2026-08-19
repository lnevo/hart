#!/usr/bin/env python3
"""Redraw the CTC panel track plan in GUIObjects.xml.

- Barn (SW117) and Princess (SW113) crossovers: replace the two separated
  half-turnout icons with a single left-hand scissor graphic (like East End's
  SW111 right-hand one), so the crossover is drawn connected.
- East End SW111 scissor: move from y=40 down to y=80 so it sits under the
  OS lamps like every other column.
- Second-track crossover lamps (13-4, 1-6, 12-6): move onto the lower bar of
  the scissor graphic (y=101).
- Add straight-track fillers (line050.gif) between every adjacent turnout icon
  so the plant reads as one contiguous track line.
- Add OS lamps for the connector blocks between interlockings:
  Main West Brick-Plane (4-6), East Main Ext (4-7), Yard T6 (13-1),
  Yard Track 1 (2-8), East Lead (1-7).

Run against jmri/layouts/hart/ctc/GUIObjects.xml, then reload the panel.
"""
import re
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "jmri/layouts/hart/ctc/GUIObjects.xml"

txt = open(PATH).read()

SCISSOR_LH = """<turnouticon turnout="{name}" x="{x}" y="80" level="7" forcecontroloff="true" hidden="no" positionable="true" showtooltip="false" editable="true" tristate="false" momentary="false" directControl="false" class="jmri.jmrit.display.configurexml.TurnoutIconXml">
      <icons>
        <closed url="program:resources/icons/USS/track/crossover/left/os-l-sc-closed.gif" scale="1.0">
          <rotation>0</rotation>
        </closed>
        <thrown url="program:resources/icons/USS/track/crossover/left/os-l-sc-thrown.gif" scale="1.0">
          <rotation>0</rotation>
        </thrown>
        <unknown url="program:resources/icons/USS/track/crossover/left/os-l-sc-unknown.gif" scale="1.0">
          <rotation>0</rotation>
        </unknown>
        <inconsistent url="program:resources/icons/USS/track/crossover/left/os-l-sc-inconsistent.gif" scale="1.0">
          <rotation>0</rotation>
        </inconsistent>
      </icons>
      <iconmaps />
    </turnouticon>"""

# 1. Replace the two half-icons of SW117 and SW113 with one scissor each.
for name, x in (("Switch 117", 216), ("Switch 113", 801)):
    pat = re.compile(r'<turnouticon[^>]*turnout="%s".*?</turnouticon>\s*' % name, re.S)
    hits = pat.findall(txt)
    assert len(hits) == 2, "%s: expected 2 icons, found %d" % (name, len(hits))
    txt = pat.sub("", txt, count=1)          # drop first (upper half)
    txt = pat.sub(SCISSOR_LH.format(name=name, x=x) + "\n    ", txt, count=1)

# 2. Drop SW111 scissor to the main row.
txt = txt.replace('turnout="Switch 111" x="552" y="40"',
                  'turnout="Switch 111" x="552" y="80"')

# 3. Second-track lamps onto the scissor lower bar (rows 29-33 -> y=101).
for sensor, x in (("Block 13-4", 228), ("Block 1-6", 813), ("Block 12-6", 553)):
    pat = re.compile(r'(<sensoricon[^>]*sensor="%s"[^>]*x=")\d+(" y=")\d+(")' % sensor)
    txt, n = pat.subn(r'\g<1>%d\g<2>101\g<3>' % x, txt)
    assert n == 1, sensor

# 4. Straight fillers between adjacent turnout icons (main row bar at y=86-90;
#    line050.gif bar rows 3-7 -> place at y=83, centered on each gap).
cols = [21, 86, 151, 216, 281, 346, 411, 476, 552, 606, 671, 736, 801, 866, 931]
FILLER = """<positionablelabel x="{x}" y="83" level="3" forcecontroloff="false" hidden="no" positionable="true" showtooltip="false" editable="true" icon="yes" class="jmri.jmrit.display.configurexml.PositionableLabelXml">
      <icon url="program:resources/icons/USS/track/block/line050.gif" degrees="0" scale="1.0">
        <rotation>0</rotation>
      </icon>
    </positionablelabel>"""
fillers = []
for a, b in zip(cols, cols[1:]):
    mid = (a + 40 + b) // 2
    fillers.append(FILLER.format(x=mid - 22))

# 5. Connector-block lamps centered in the inter-plant gaps.
LAMP = """<sensoricon sensor="{sensor}" x="{x}" y="78" level="10" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" momentary="false" icon="yes" class="jmri.jmrit.display.configurexml.SensorIconXml">
      <tooltip>{tip}</tooltip>
      <active url="program:resources/icons/USS/sensor/red-on.gif" scale="1.0">
        <rotation>0</rotation>
      </active>
      <inactive url="program:resources/icons/USS/sensor/red-off.gif" scale="1.0">
        <rotation>0</rotation>
      </inactive>
      <unknown url="program:resources/icons/USS/sensor/s-unknown.gif" scale="1.0">
        <rotation>0</rotation>
      </unknown>
      <inconsistent url="program:resources/icons/USS/sensor/s-inconsistent.gif" scale="1.0">
        <rotation>0</rotation>
      </inconsistent>
      <iconmaps />
    </sensoricon>"""
lamps = [
    ("Block 4-6", 133, "Main West Brick-Plane"),
    ("Block 4-7", 199, "East Main Ext"),
    ("Block 13-1", 263, "Yard T6"),
    ("Block 2-8", 393, "Yard Track 1"),
    ("Block 1-7", 789, "East Lead"),
]
for sensor, x, tip in lamps:
    fillers.append(LAMP.format(sensor=sensor, x=x, tip=tip))

txt = txt.replace("</paneleditor>",
                  "    " + "\n    ".join(fillers) + "\n  </paneleditor>")

open(PATH, "w").write(txt)
print("redraw complete: %d fillers/lamps added" % len(fillers))
