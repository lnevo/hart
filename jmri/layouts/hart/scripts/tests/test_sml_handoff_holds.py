"""sml_handoff.py (part of signal_coordinator.py): mast Holds that fail, and the Disable worker's busy flag.

Run against an in-memory JMRI (jmri_fake), with the Hold wait and worker threads of
test_signal_coordinator_behaviour.Sequences; nothing reaches a broker.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402
import test_signal_coordinator_behaviour as base  # noqa: E402


class HeldMasts(unittest.TestCase):
    setUp = base.Sequences.setUp
    own = base.Sequences.own
    enroll = base.Sequences.enroll
    sent = base.Sequences.sent
    run_disable = base.Sequences.run_disable

    def add_stuck_mast(self) -> jf.FakeMast:
        """A second Digicon mast, listed first, whose setHeld always raises."""
        stuck = self.layout.masts.add(jf.FakeMast("IF$shsm:basic:one-searchlight(IH433)", "Mast 4RB"))

        def refuse(value: bool) -> None:
            raise RuntimeError("no hold")

        stuck.setHeld = refuse
        self.c._masts = [stuck, self.mast]
        return stuck

    def test_disable_prints_the_mast_that_cannot_hold_and_goes_on(self) -> None:
        self.own()
        self.add_stuck_mast()
        self.run_disable(True)
        out = self.out.getvalue()
        self.assertIn("Hold failed on Mast 4RB: no hold", out)
        self.assertIn("Hold release failed on Mast 4RB: no hold", out)
        self.assertEqual(self.bulk, [(False, True)])  # the other mast was held while its pairs went off
        self.assertFalse(self.mast.held)
        self.assertEqual(self.sent()[-1], ("track/bridge/sml_mode", "disabled", True))
        self.assertFalse(self.c._global_enabled)

    def test_enable_holds_the_other_masts_when_one_cannot_hold(self) -> None:
        self.add_stuck_mast()
        self.enroll()
        self.c._enter_enabled(force=True, from_boot=True)
        jf.run_threads()
        self.assertEqual(self.bulk, [(True, True)])
        self.assertFalse(self.mast.held)
        self.assertIn("Hold failed on Mast 4RB", self.out.getvalue())
        self.assertTrue(self.c._global_enabled)

    def test_disable_sets_busy_under_the_claim_lock(self) -> None:
        self.own()
        c = self.c
        seen = []

        class Lock:
            def __enter__(self) -> None:
                seen.append(("enter", c._busy))

            def __exit__(self, *exc: object) -> bool:
                seen.append(("exit", c._busy))
                return False

        c._claim_lock = Lock()
        c._enter_disabled(release=True)
        self.assertEqual(seen, [("enter", False), ("exit", True)])
        jf.run_threads()
        self.assertFalse(c._busy)

    def test_disable_while_busy_starts_nothing_under_the_lock(self) -> None:
        self.own()
        self.c._busy = True
        self.c._enter_disabled(release=True)
        self.assertEqual(jf.Thread.started, [])
        self.assertTrue(self.c._global_enabled)


if __name__ == "__main__":
    unittest.main()
