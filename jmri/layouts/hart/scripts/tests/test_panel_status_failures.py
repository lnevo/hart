"""panel_status.py: the JMRI reads that can fail are printed, and the lamps stay as they were.

No PowerManager, a power state that cannot be read, and a plant turnout that refuses a listener.
Run against an in-memory JMRI (jmri_fake); nothing reaches a broker.
"""
from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402
import test_panel_status as base  # noqa: E402

S = jf.Sensor


class Failures(unittest.TestCase):
    layout: Any
    ps: Any
    setUp = base.PanelStatus.setUp
    plant = base.PanelStatus.plant

    def boot(self) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            jf.fire_timers()
        return out.getvalue()

    def lamp(self) -> int:
        return self.layout.sensors.getSensor("IS:TRACK_POWER").state

    def test_no_power_manager_is_printed_and_the_lamp_is_not_driven(self) -> None:
        self.layout.power = None
        out = self.boot()
        self.assertIn("panel_status: no PowerManager -- the Track Power lamp is not driven", out)
        self.assertEqual(self.lamp(), S.UNKNOWN)
        self.assertTrue(self.ps["_armed"])                   # the Turnouts lamp still arms

    def test_an_unreadable_power_state_is_printed_and_leaves_the_lamp(self) -> None:
        def refuse() -> int:
            raise RuntimeError("no LCC")

        self.layout.power.getPower = refuse
        out = self.boot()
        self.assertIn("panel_status: Track Power state unreadable, lamp left as it is: no LCC", out)
        self.assertEqual(self.lamp(), S.UNKNOWN)

    def test_a_turnout_that_refuses_a_listener_is_named_and_the_rest_arm(self) -> None:
        stuck = self.layout.turnouts.getTurnout("M2T308")

        def refuse(listener: object) -> None:
            raise RuntimeError("locked")

        stuck.addPropertyChangeListener = refuse
        out = self.boot()
        self.assertIn("panel_status: listener not attached to M2T308: locked", out)
        other = self.layout.turnouts.getTurnout("M2T309")
        self.assertEqual(len([l for l in other.listeners if getattr(l, "hart_panel_status", False)]), 1)

    def test_a_listener_of_another_script_is_not_ours(self) -> None:
        ours = self.ps["_ours"]

        class _TurnoutListener:                              # this script's class, from before the mark
            pass

        class Other:
            pass

        self.assertTrue(ours(_TurnoutListener()))
        self.assertTrue(ours(self.ps["_PowerListener"]()))
        self.assertFalse(ours(Other()))


if __name__ == "__main__":
    unittest.main()
