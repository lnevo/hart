# Add East End + Princess interlockings to the JMRI CTC configuration
# (columns 4-12, extending the Brick+Plane pilot from build_ctc_brick_plane.py),
# then regenerate the full USS panel prototype-style: no signal heads on the
# track board (SIGNALS_ON_PANEL.NONE) - signal state shows on the lever lamps.
#
# Columns west-to-east (levers odd switch / even signal):
#   col  4  SW  7/8    Switch 25  RH   OS Switch 25 (yard ladder, switch-only)
#   col  5  SW  9/10   Switch 27  RH   OS Switch 27 (yard ladder, switch-only)
#   col  6  SW 11/12   Switch 23  RH XOVER  OS Switch 23a + OS Switch 23b
#   col  7  SW 13/14   Switch 29  RH   OS Switch 29 (yard ladder, switch-only)
#   col  8  SW 15/16   Switch 31  LH   OS Switch 31
#   col  9  SW 17/18   Switch 33  LH   OS Switch 33
#   col 10  SW 19/20   Switch 35  LH XOVER  OS Switch 35b + OS Switch 35a
#   col 11  SW 21/22   Switch 37  RH   OS Switch 37
#   col 12  SW 23/24   Switch 39  LH   OS Switch 39
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
    add_os(7, 4, "Block 12-1", "Switch 25", [], [])
    add_os(9, 5, "Block 12-3", "Switch 27", [], [])
    add_os(11, 6, "Block 12-4", "Switch 23",
           ["Mast 24RA", "Mast 24RB"],
           ["Mast 24L"],
           secondary="Block 12-6", ttype=CROSSOVER)
    add_os(13, 7, "Block 12-5", "Switch 29", [], [])
    add_os(15, 8, "Block 12-7", "Switch 31",
           ["Mast 32R"], [], left_hand=True)
    add_os(17, 9, "Block 12-8", "Switch 33",
           ["Mast 34R"], ["Mast 34L"], left_hand=True)
    # Princess
    add_os(19, 10, "Block 1-5", "Switch 35",
           ["Mast 36RA", "Mast 36RB"], [],
           secondary="Block 1-6", ttype=CROSSOVER, left_hand=True)
    add_os(21, 11, "Block 1-3", "Switch 37",
           [], ["Mast 38LA", "Mast 38LB"])
    add_os(23, 12, "Block 1-4", "Switch 39",
           [], ["Mast 40LA", "Mast 40LB"], left_hand=True)

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
