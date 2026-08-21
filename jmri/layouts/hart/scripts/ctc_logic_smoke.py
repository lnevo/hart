# JMRI startup Jython: start CTC Logic and verify the machine loaded.
#
# Run through run_ctc_logic_smoke.sh. Python-2-compatible for Jython.

import os
import time
import traceback

import java.lang
import jmri
from java.awt.event import ActionEvent
from javax.swing import SwingUtilities
from jmri.jmrit.ctc import CtcManager, CtcRunAction


# Live machine is 12 interlocking columns; 116/103/110 are local ladder, not CTC.
EXPECTED_COLUMNS = 12
SIDI_MASTS = (
    "100L",
    "101RA",
    "101RB",
    "102LA",
    "102LB",
    "117RA",
    "117RB",
    "117LA",
    "117LB",
    "111RA",
    "111RB",
    "111L",
    "110R",
    "112R",
    "112L",
    "113RA",
    "113RB",
    "114R",
    "114LA",
    "114LB",
    "115R",
    "115LA",
    "115LB",
)


class CtcLogicSmoke(jmri.jmrit.automat.AbstractAutomaton):
    def handle(self):
        marker = os.environ.get(
            "HART_CTC_LOGIC_SMOKE_MARKER", "/tmp/hart_ctc_logic_smoke.done"
        )
        errors = []
        try:
            mast_manager = jmri.InstanceManager.getDefault(jmri.SignalMastManager)
            for name in SIDI_MASTS:
                if mast_manager.getByUserName(name) is None:
                    errors.append("missing mast %s" % name)

            holder = {"err": None}

            def start_ctc():
                try:
                    CtcRunAction().actionPerformed(ActionEvent(self, 0, "run"))
                except Exception as exc:
                    holder["err"] = exc

            SwingUtilities.invokeAndWait(start_ctc)
            if holder["err"] is not None:
                raise holder["err"]

            deadline = time.time() + 30
            columns = 0
            while time.time() < deadline:
                mgr = jmri.InstanceManager.getDefault(CtcManager)
                data = mgr.getCTCSerialData()
                if data is not None:
                    columns = data.getCodeButtonHandlerDataSize()
                    if columns == EXPECTED_COLUMNS:
                        break
                self.waitMsec(500)

            if columns != EXPECTED_COLUMNS:
                errors.append("CTC columns=%s expected=%s" % (columns, EXPECTED_COLUMNS))
        except Exception:
            errors.append(traceback.format_exc())

        handle = open(marker, "w")
        try:
            if errors:
                handle.write("fail\n")
                handle.write("\n".join(errors))
            else:
                handle.write("ok\n")
                handle.write("CTC Logic started; 12 columns; 23 SIDI masts\n")
        finally:
            handle.close()

        java.lang.System.exit(1 if errors else 0)
        return False


CtcLogicSmoke().start()
