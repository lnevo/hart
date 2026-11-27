"""sml_beans.py (part of signal_coordinator.py): the reads of the SML table's Enabled boxes.

_dest_states is the one walk of a source logic's destinations; the count, the map and the
"still on" failure line are built on it. A destination or a list that cannot be read is left
out (counted as off) and printed once. Run against an in-memory JMRI (jmri_fake); nothing
reaches a broker.
"""
from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_signal_coordinator_behaviour as base  # noqa: E402


class _Refuses:
    """A destination list whose iterator fails at once."""

    def isEmpty(self) -> bool:
        return False

    def iterator(self) -> object:
        raise RuntimeError("list gone")


class DestStates(unittest.TestCase):
    c: Any
    mast: Any
    setUp = base.Coordinator.setUp

    def capture(self) -> io.StringIO:
        out = io.StringIO()
        stack = contextlib.ExitStack()
        stack.enter_context(contextlib.redirect_stdout(out))
        self.addCleanup(stack.close)
        return out

    def two_dests(self) -> base.FakeLogic:
        logic = base.FakeLogic(self.mast, "Mast 8RA", "Mast 10RA")
        self.c._sml_by_mast = {self.mast: logic}
        self.c._smls = [logic]
        return logic

    def test_count_map_and_still_on_follow_the_boxes(self) -> None:
        logic = self.two_dests()
        logic.enabled["Mast 10RA"] = False
        c = self.c
        self.assertEqual(c._enabled_dest_count(self.mast), 1)
        self.assertTrue(c._mast_logic_enabled(self.mast))
        self.assertEqual(c._dest_enable_map(logic), {"Mast 8RA": True, "Mast 10RA": False})
        self.assertEqual(c._pairs_still_on(), "Mast 6LB -> Mast 8RA")
        logic.enabled["Mast 8RA"] = False
        self.assertFalse(c._mast_logic_enabled(self.mast))
        self.assertEqual(c._pairs_still_on(), "none listed")

    def test_no_mast_or_no_logic_counts_none(self) -> None:
        c = self.c
        self.assertEqual(c._enabled_dest_count(None), 0)
        c._sml_by_mast = {}
        self.assertEqual(c._enabled_dest_count(self.mast), 0)
        self.assertEqual(c._dest_enable_map(None), {})

    def test_an_unreadable_destination_is_left_out_and_printed_once(self) -> None:
        out = self.capture()
        logic = self.two_dests()
        real = logic.isEnabled

        def is_enabled(dest: object) -> bool:
            if dest.getSystemName() == "Mast 8RA":  # type: ignore[attr-defined]
                raise RuntimeError("bean gone")
            return real(dest)

        logic.isEnabled = is_enabled  # type: ignore[method-assign]
        c = self.c
        self.assertEqual(c._enabled_dest_count(self.mast), 1)  # the readable one
        self.assertEqual(c._dest_enable_map(logic), {"Mast 10RA": True})
        self.assertEqual(c._pairs_still_on(), "Mast 6LB -> Mast 10RA")
        lines = [l for l in out.getvalue().splitlines() if "cannot read SML" in l]
        self.assertEqual(lines, ["mqtt_signalhead: cannot read SML Mast 6LB -> Mast 8RA "
                                 "(left out, counted as off): bean gone"])

    def test_an_unreadable_list_counts_as_off_and_is_printed_once(self) -> None:
        out = self.capture()
        logic = self.two_dests()
        logic.getDestinationList = lambda: _Refuses()  # type: ignore[method-assign]
        c = self.c
        self.assertFalse(c._mast_logic_enabled(self.mast))
        self.assertEqual(c._dest_enable_map(logic), {})
        self.assertEqual(c._pairs_still_on(), "none listed")
        self.assertEqual(out.getvalue().count("cannot read SML Mast 6LB -> its destination list"), 1)

    def test_an_unreadable_logic_makes_the_field_own_its_mast(self) -> None:
        self.capture()
        logic = self.two_dests()
        logic.getDestinationList = lambda: _Refuses()  # type: ignore[method-assign]
        self.c._global_enabled = True
        self.c._source_field_owned = {}
        self.assertTrue(self.c._field_owns_mast(self.mast))


if __name__ == "__main__":
    unittest.main()
