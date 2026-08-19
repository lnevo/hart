# Add East End + Princess interlockings to the JMRI CTC configuration
# (columns 4-12, extending the Brick+Plane pilot from build_ctc_brick_plane.py),
# then regenerate the full USS panel prototype-style: no signal heads on the
# track board (SIGNALS_ON_PANEL.NONE) - signal state shows on the lever lamps.
#
# Columns west-to-east (levers odd switch / even signal):
#   col  4  SW  7/8    Switch 107  RH   OS 107 (yard ladder, switch-only)
#   col  5  SW  9/10   Switch 108  RH   OS 108 (yard ladder, switch-only)
#   col  6  SW 11/12   Switch 111  RH XOVER  OS 111a + OS 111b
#   col  7  SW 13/14   Switch 109  RH   OS 109 (yard ladder, switch-only)
#   col  8  SW 15/16   Switch 110  LH   OS 110
#   col  9  SW 17/18   Switch 112  LH   OS 112
#   col 10  SW 19/20   Switch 113  LH XOVER  OS 113b + OS 113a
#   col 11  SW 21/22   Switch 114  RH   OS 114
#   col 12  SW 23/24   Switch 115  LH   OS 115
#
# Run inside PanelPro. Refuses to run if these switch numbers already exist.

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

existing = [data.getCodeButtonHandlerData(i)._mSwitchNumber
            for i in range(data.getCodeButtonHandlerDataSize())]
if any(sw >= 7 for sw in existing):
    RESULT = "REFUSING: switch numbers >= 7 already exist: %s" % existing
else:
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
        c._mSWDI_GUITurnoutLeftHand = left_hand
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

    # East End
    add_os(7, 4, "Block 12-1", "Switch 107", [], [])
    add_os(9, 5, "Block 12-3", "Switch 108", [], [])
    add_os(11, 6, "Block 12-4", "Switch 111",
           ["East End West Main West", "East End West Yard Track 1"],
           ["East End East OS 111a"],
           secondary="Block 12-6", ttype=CROSSOVER)
    add_os(13, 7, "Block 12-5", "Switch 109", [], [])
    add_os(15, 8, "Block 12-7", "Switch 110",
           ["East End South OS 110"], [], left_hand=True)
    add_os(17, 9, "Block 12-8", "Switch 112",
           ["East End South OS 112"], ["East End East Lead"], left_hand=True)
    # Princess
    add_os(19, 10, "Block 1-5", "Switch 113",
           ["Princess West OS 113b", "Princess West OS 113a"], [],
           secondary="Block 1-6", ttype=CROSSOVER, left_hand=True)
    add_os(21, 11, "Block 1-3", "Switch 114",
           [], ["Princess East K-2", "Princess South McKeesport"])
    add_os(23, 12, "Block 1-4", "Switch 115",
           [], ["Princess East K-1", "Princess North McKees Rocks"], left_hand=True)

    # Traffic locking auto-generate for every signal-equipped column
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

    # Prototype board: no signal heads on the track diagram
    data.getOtherData()._mGUIDesign_SignalsOnPanel = OtherData.SIGNALS_ON_PANEL.NONE
    # Regenerate the full panel (all columns) on next writeGUIObjects
    for i in range(data.getCodeButtonHandlerDataSize()):
        data.getCodeButtonHandlerData(i)._mGUIGeneratedAtLeastOnceAlready = False

    RESULT = "\n".join(out)
