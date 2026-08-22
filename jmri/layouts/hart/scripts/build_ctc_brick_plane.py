# Build the JMRI CTC (Tools -> CTC) configuration for the Brick + Plane pilot.
#
# Creates three O.S. sections using the same factory routines the CTC Editor
# uses, so all internal IS#: sensors are generated from the standard USS
# patterns, then auto-generates Traffic Locking rules from the Layout Editor
# topology / SML (same code path as the editor's "Auto-Generate" button).
#
# Columns (levers odd switch / even signal), panel left-to-right:
#   col 1  SW 1/SIG 2   Switch 101, OS 101  - yard tracks converge
#   col 2  SW 3/SIG 4   Switch 100, OS 100  - Main West / Brick-Plane
#   col 3  SW 5/SIG 6   Switch 102, OS 102  - East Main Ext / Scale
#
# Traffic direction sense: JMRI CTC "left" = west. Signals here are
# directional (sparse Digicon ABS), so sections are uni-directional.
#
# Run inside PanelPro (jmri_cmd_watcher or script console). Idempotent:
# refuses to run if any CTC columns already exist.

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

if data.getCodeButtonHandlerDataSize() > 0:
    RESULT = "REFUSING: %d CTC columns already exist" % data.getCodeButtonHandlerDataSize()
else:
    other = data.getOtherData()
    other._mSignalSystemType = OtherData.SIGNAL_SYSTEM_TYPE.SIGNALMAST

    BOTH = CodeButtonHandlerData.TRAFFIC_DIRECTION.BOTH
    LEFT = CodeButtonHandlerData.TRAFFIC_DIRECTION.LEFT
    RIGHT = CodeButtonHandlerData.TRAFFIC_DIRECTION.RIGHT

    def add_os(sw_num, col, os_sensor, turnout, ltr_masts, rtl_masts):
        uid = data.getUniqueNumber()
        c = CodeButtonHandlerDataRoutines.createNewCodeButtonHandlerData(
            uid, sw_num, sw_num + 1, col, props)
        c._mOSSectionOccupiedExternalSensor = CommonSubs.getNBHSensor(os_sensor, False)
        # Switch lever + indicators
        c._mSWDI_Enabled = True
        c._mSWDI_ExternalTurnout = CommonSubs.getNBHTurnout(turnout, False)
        c._mSWDI_GUITurnoutType = CodeButtonHandlerData.TURNOUT_TYPE.TURNOUT
        c._mSWDI_GUITurnoutLeftHand = True  # all three are LH_TURNOUT in LE
        c._mSWDL_Enabled = True
        # Signal lever + indicators
        c._mSIDI_Enabled = True
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
        c._mSIDL_Enabled = True
        # Turnout locking
        c._mTUL_Enabled = True
        c._mTUL_ExternalTurnout = CommonSubs.getNBHTurnout(turnout, False)
        # Traffic locking rules filled in below
        c._mTRL_Enabled = True
        data.addCodeButtonHandlerData(c)
        out.append("added %s" % c.myString())
        return c

    cols = [
        add_os(1, 1, "Block 4-1", "Switch 101",
               ["101RA", "101RB"], []),
        add_os(3, 2, "Block 4-2", "Switch 100",
               [], ["100L"]),
        add_os(5, 3, "Block 4-5", "Switch 102",
               [], ["102LB", "102LA"]),
    ]

    # Traffic locking auto-generate (same as editor's Auto-Generate button)
    for c in cols:
        sensors = ArrayList()
        sensors.add(c._mOSSectionOccupiedExternalSensor.getHandleName())
        topo = Topology(data, sensors, "Normal", "Reverse")
        if not topo.isTopologyAvailable():
            out.append("%s: topology NOT available" % c.myShortStringNoComma())
            continue
        for left in (True, False):
            infos = topo.getTrafficLockingRules(left)
            rules = c._mTRL_LeftTrafficLockingRules if left else c._mTRL_RightTrafficLockingRules
            rules.clear()
            for i in range(infos.size()):
                ti = infos.get(i)
                rules.add(TrafficLockingData(i + 1, ti.getDestinationSignalMast(), ti))
            out.append("%s %s rules: %d" % (
                c.myShortStringNoComma(), "left" if left else "right", rules.size()))

    RESULT = "\n".join(out)
