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


# Live machine is 20 packed columns; yard ladders are switch-only (default Local).
EXPECTED_COLUMNS = 20
SIDI_MASTS = (
    "Mast 2L",
    "Mast 4RA",
    "Mast 4RB",
    "Mast 6LA",
    "Mast 6LB",
    "Mast 8RA",
    "Mast 8RB",
    "Mast 8LA",
    "Mast 8LB",
    "Mast 24RA",
    "Mast 24RB",
    "Mast 24L",
    "Mast 32R",
    "Mast 34R",
    "Mast 34L",
    "Mast 36RA",
    "Mast 36RB",
    "Mast 2036",
    "Mast 38LA",
    "Mast 38LB",
    "Mast 2035",
    "Mast 40LA",
    "Mast 40LB",
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
                handle.write("CTC Logic started; 20 columns; 23 SIDI masts\n")
        finally:
            handle.close()

        java.lang.System.exit(1 if errors else 0)
        return False


CtcLogicSmoke().start()
