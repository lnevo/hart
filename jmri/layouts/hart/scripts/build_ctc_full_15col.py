# Rebuild the complete JMRI CTC machine: 15 columns in geographic order
# west -> east, replacing the previous 12-column config (Barn inserted as
# cols 4-6 between Plane and East End).
#
#   col  1  SW 1/2    Switch 101  LH        Brick     (yard exits)
#   col  2  SW 3/4    Switch 100  LH        Brick
#   col  3  SW 5/6    Switch 102  LH        Plane
#   col  4  SW 7/8    Switch 117  LH XOVER  Barn      OS 117 + OS 117b
#   col  5  SW 9/10   Switch 116  RH        Barn      (ladder, switch-only + local)
#   col  6  SW 11/12  Switch 103  RH        Barn      (ladder, switch-only + local)
#   col  7  SW 13/14  Switch 107  RH        East End  (ladder, switch-only)
#   col  8  SW 15/16  Switch 108  RH        East End  (ladder, switch-only)
#   col  9  SW 17/18  Switch 111  RH XOVER  East End  OS 111a + OS 111b
#   col 10  SW 19/20  Switch 109  RH        East End  (ladder, switch-only)
#   col 11  SW 21/22  Switch 110  LH        East End
#   col 12  SW 23/24  Switch 112  LH        East End
#   col 13  SW 25/26  Switch 113  LH XOVER  Princess  OS 113b + OS 113a
#   col 14  SW 27/28  Switch 114  RH        Princess
#   col 15  SW 29/30  Switch 115  LH        Princess
#
# Run inside PanelPro (command watcher). Existing columns are removed first.

import jmri
from jmri.jmrit.ctc import CtcManager
from jmri.jmrit.ctc.ctcserialdata import CodeButtonHandlerData, OtherData, TrafficLockingData
from jmri.jmrit.ctc.editor.code import CodeButtonHandlerDataRoutines, CommonSubs
from jmri.jmrit.ctc.topology import Topology
from java.util import ArrayList

out = []
mgr = jmri.InstanceManager.getDefault(CtcManager)
props = mgr.getProgramProperties()
data = mgr.getCTCSerialData()

while data.getCodeButtonHandlerDataSize() > 0:
    data.removeCodeButtonHandlerData(0)
out.append("cleared existing columns")

other = data.getOtherData()
other._mSignalSystemType = OtherData.SIGNAL_SYSTEM_TYPE.SIGNALMAST
other._mGUIDesign_SignalsOnPanel = OtherData.SIGNALS_ON_PANEL.NONE

TURNOUT = CodeButtonHandlerData.TURNOUT_TYPE.TURNOUT
CROSSOVER = CodeButtonHandlerData.TURNOUT_TYPE.CROSSOVER
BOTH = CodeButtonHandlerData.TRAFFIC_DIRECTION.BOTH
LEFT = CodeButtonHandlerData.TRAFFIC_DIRECTION.LEFT
RIGHT = CodeButtonHandlerData.TRAFFIC_DIRECTION.RIGHT


def add_os(sw_num, col, os_sensor, turnout, ltr_masts, rtl_masts,
           secondary=None, ttype=TURNOUT, left_hand=False):
    uid = data.getUniqueNumber()
    c = CodeButtonHandlerDataRoutines.createNewCodeButtonHandlerData(
        uid, sw_num, sw_num + 1, col, props)
    c._mOSSectionOccupiedExternalSensor = CommonSubs.getNBHSensor(os_sensor, False)
    if secondary:
        c._mOSSectionOccupiedExternalSensor2 = CommonSubs.getNBHSensor(secondary, False)
    c._mSWDI_Enabled = True
    c._mSWDI_ExternalTurnout = CommonSubs.getNBHTurnout(turnout, False)
    c._mSWDI_GUITurnoutType = ttype
    c._mSWDI_GUITurnoutLeftHand = left_hand and ttype == TURNOUT
    c._mSWDI_GUICrossoverLeftHand = left_hand and ttype == CROSSOVER
    c._mSWDL_Enabled = True
    c._mTUL_Enabled = True
    c._mTUL_ExternalTurnout = CommonSubs.getNBHTurnout(turnout, False)
    if ltr_masts or rtl_masts:
        c._mSIDI_Enabled = True
        c._mSIDL_Enabled = True
        c._mTRL_Enabled = True
        if ltr_masts and rtl_masts:
            c._mSIDI_TrafficDirection = BOTH
        elif ltr_masts:
            c._mSIDI_TrafficDirection = RIGHT
        else:
            c._mSIDI_TrafficDirection = LEFT
        for m in ltr_masts:
            c._mSIDI_LeftRightTrafficSignals.add(CommonSubs.getNBHSignal(m))
        for m in rtl_masts:
            c._mSIDI_RightLeftTrafficSignals.add(CommonSubs.getNBHSignal(m))
    data.addCodeButtonHandlerData(c)
    out.append("added %s" % c.myString())
    return c


# Brick + Plane
add_os(1, 1, "Block 4-1", "Switch 101",
       ["Brick West Yard 1", "Brick West Yard 2"], [], left_hand=True)
add_os(3, 2, "Block 4-2", "Switch 100",
       [], ["Brick East Main West"], left_hand=True)
add_os(5, 3, "Block 4-5", "Switch 102",
       [], ["Plane East East Main Ext", "Plane East OS 102"], left_hand=True)
# Barn
add_os(7, 4, "Block 13-3", "Switch 117",
       ["West Yard West OS 117", "West Yard West East Main Ext"],
       ["West Yard East OS 117b", "West Yard East Yard T6"],
       secondary="Block 13-4", ttype=CROSSOVER, left_hand=True)
# Yard ladder is switch-only (no CTC homes). Lock toggles default Local
# via ctc_default_reverse_levers.py / IX:CTC:REVDEF.
add_os(9, 5, "Block 3-1", "Switch 116", [], [])
add_os(11, 6, "Block 3-2", "Switch 103", [], [])
# East End
add_os(13, 7, "Block 12-1", "Switch 107", [], [])
add_os(15, 8, "Block 12-3", "Switch 108", [], [])
add_os(17, 9, "Block 12-4", "Switch 111",
       ["East End West Main West", "East End West Yard Track 1"],
       ["East End East OS 111a"],
       secondary="Block 12-6", ttype=CROSSOVER)
add_os(19, 10, "Block 12-5", "Switch 109", [], [])
add_os(21, 11, "Block 12-7", "Switch 110",
       ["East End South OS 110"], [], left_hand=True)
add_os(23, 12, "Block 12-8", "Switch 112",
       ["East End South OS 112"], ["East End East Lead"], left_hand=True)
# Princess
add_os(25, 13, "Block 1-5", "Switch 113",
       ["Princess West OS 113b", "Princess West OS 113a"], [],
       secondary="Block 1-6", ttype=CROSSOVER, left_hand=True)
# Balloon: 114/115 BOTH. Each SIDI list needs a unique mast (JMRI
# rejects empty lists and forbids sharing a mast across columns).
# Eastbound homes on the loop were previously unlisted.
c114 = add_os(27, 14, "Block 1-3", "Switch 114",
       ["Princess East McKees Rocks"],
       ["Princess East K-2", "Princess South McKeesport"])
c115 = add_os(29, 15, "Block 1-4", "Switch 115",
       ["Princess East McKeesport"],
       ["Princess East K-1", "Princess North McKees Rocks"], left_hand=True)
c114._mSIDI_TrafficDirection = BOTH
c115._mSIDI_TrafficDirection = BOTH

# Traffic locking auto-generation from SML topology
for i in range(data.getCodeButtonHandlerDataSize()):
    c = data.getCodeButtonHandlerData(i)
    if not c._mTRL_Enabled:
        continue
    sensors = ArrayList()
    sensors.add(c._mOSSectionOccupiedExternalSensor.getHandleName())
    if c._mOSSectionOccupiedExternalSensor2.valid():
        sensors.add(c._mOSSectionOccupiedExternalSensor2.getHandleName())
    topo = Topology(data, sensors, "Normal", "Reverse")
    if not topo.isTopologyAvailable():
        out.append("%s: topology NOT available" % c.myShortStringNoComma())
        continue
    for left in (True, False):
        infos = topo.getTrafficLockingRules(left)
        rules = c._mTRL_LeftTrafficLockingRules if left else c._mTRL_RightTrafficLockingRules
        rules.clear()
        for j in range(infos.size()):
            ti = infos.get(j)
            rules.add(TrafficLockingData(j + 1, ti.getDestinationSignalMast(), ti))
        out.append("%s %s rules: %d" % (
            c.myShortStringNoComma(), "left" if left else "right", rules.size()))

RESULT = "\n".join(out)
