"""signal_coordinator.py's parts (jmri/scripts sml_beans, sml_ui, sml_events): a bean read or set that fails.

The reads and paints run on every property change and field report, so each failure is printed once per
distinct message and the rest of the work still runs. Run against an in-memory JMRI (jmri_fake); the MQTT
adapter only records and nothing reaches a broker.
"""
from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402
import test_signal_coordinator_behaviour as base  # noqa: E402

H = jf.SignalHead


def _fail(message: str) -> Any:
    def call(*_args: object) -> None:
        raise RuntimeError(message)
    return call


class _Logics:
    """SignalMastLogicManager with a fixed list of logics."""

    def __init__(self, *logics: object) -> None:
        self.logics = list(logics)

    def getSignalMastLogicList(self) -> list[object]:
        return self.logics


class Failures(unittest.TestCase):
    c: Any
    mast: Any
    head: Any
    logic: Any
    setUp = base.Coordinator.setUp
    enroll = base.Coordinator.enroll

    def run_out(self, fn: Any, times: int = 2) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for _ in range(times):
                fn()
        return out.getvalue()

    # --- sml_beans -------------------------------------------------------------------

    def test_ascii_replaces_non_ascii(self) -> None:
        f = sys.modules["sml_beans"]._ascii
        self.assertEqual(f(None), "")
        self.assertEqual(f("Mast 6LB"), "Mast 6LB")
        self.assertEqual(f("Gare é"), "Gare ?")
        self.assertEqual(f(42), "42")

    def test_ascii_of_a_bean_whose_text_throws_still_gives_a_line(self) -> None:
        f = sys.modules["sml_beans"]._ascii

        class Broken:
            def __str__(self) -> str:
                raise RuntimeError("toString failed")

        class Worse(Broken):
            def __repr__(self) -> str:
                raise RuntimeError("repr failed")

        self.assertIn("Broken", f(Broken()))
        self.assertEqual(f(Worse()), "?")

    def test_a_logic_whose_mast_cannot_be_named_still_gets_a_label(self) -> None:
        beans = sys.modules["sml_beans"]

        class NamelessMast:
            getUserName = getSystemName = staticmethod(_fail("name gone"))

            def __str__(self) -> str:
                raise RuntimeError("toString failed")

        out = self.run_out(lambda: beans._logic_label(base.FakeLogic(NamelessMast(), "Mast 8RA")), times=1)
        self.assertIn("cannot read getUserName", out)
        self.assertIn("NamelessMast", beans._logic_label(base.FakeLogic(NamelessMast(), "Mast 8RA")))

    def test_a_bean_name_that_cannot_be_read_falls_to_the_next_and_is_printed_once(self) -> None:
        beans = sys.modules["sml_beans"]
        mast = jf.FakeMast("IF$shsm:x(IH440)")
        mast.getUserName = _fail("user name gone")  # type: ignore[method-assign]
        labels = []
        out = self.run_out(lambda: labels.append(beans._bean_label(mast)))
        self.assertEqual(labels, ["IF$shsm:x(IH440)"] * 2)
        self.assertEqual(out.count("cannot read getUserName of"), 1)
        self.assertIn("user name gone", out)

    def test_a_logic_whose_source_cannot_be_read_is_not_watched_and_printed_once(self) -> None:
        beans = sys.modules["sml_beans"]
        broken = base.FakeLogic(self.mast, "Mast 10RA")
        broken.getSourceMast = _fail("source gone")  # type: ignore[method-assign]
        good = base.FakeLogic(self.mast, "Mast 8RA")
        with mock.patch.object(beans, "_sml_manager", lambda: _Logics(broken, good)):
            out = self.run_out(lambda: self.c._attach_sml_listeners(quiet=True))
        self.assertEqual(self.c._smls, [good])
        self.assertIs(self.c._sml_by_mast[self.mast], good)
        self.assertEqual(out.count("cannot read the source mast of SML"), 1)
        self.assertIn("not watched: source gone", out)

    def test_a_logic_that_refuses_to_stop_watching_is_printed_once_and_the_rest_rewired(self) -> None:
        beans = sys.modules["sml_beans"]
        stuck = base.FakeLogic(self.mast, "Mast 8RA")
        stuck.removePropertyChangeListener = _fail("listener stuck")  # type: ignore[method-assign]

        def rewire() -> None:
            self.c._smls = [stuck]
            self.c._attach_sml_listeners(quiet=True)

        with mock.patch.object(beans, "_sml_manager", lambda: _Logics(stuck)):
            out = self.run_out(rewire)
        self.assertEqual(self.c._smls, [stuck])
        self.assertEqual(out.count("cannot stop watching SML Mast 6LB: listener stuck"), 1)

    def test_a_node_that_is_not_octal_is_not_an_lcos_signal(self) -> None:
        f = sys.modules["sml_beans"]._packed_is_lcos_signal
        self.assertFalse(f("932"))
        self.assertTrue(f("732"))

    # --- sml_events ------------------------------------------------------------------

    def test_a_head_that_refuses_its_appearance_is_printed_once_and_the_mast_still_painted(self) -> None:
        self.enroll()
        self.head.setAppearance = _fail("head locked")
        out = self.run_out(lambda: self.c.notifyMqttMessage("track/signalmast/432", "Approach"))
        self.assertEqual(out.count("setAppearance IH432 Yellow: head locked"), 1)
        self.assertEqual(self.mast.aspect, "Approach")

    def test_an_unreadable_mast_aspect_is_printed_once_and_the_aspect_still_set(self) -> None:
        self.enroll()
        self.mast.getAspect = _fail("aspect unknown")
        out = self.run_out(lambda: self.c.notifyMqttMessage("track/signalmast/432", "Clear"))
        self.assertEqual(self.mast.aspect, "Clear")
        self.assertEqual(out.count("cannot read the aspect of Mast 6LB (set anyway): aspect unknown"), 1)

    def test_a_refused_state_word_is_printed_once_and_the_next_word_still_applied(self) -> None:
        self.enroll()
        self.mast.setHeld = _fail("held stuck")
        out = self.run_out(lambda: self.c.notifyMqttMessage("track/signalmast/432", "Stop;Held;Unlit"))
        self.assertFalse(self.mast.lit)
        self.assertEqual(out.count("setHeld(True) Mast 6LB: held stuck"), 1)

    def test_a_changed_logic_whose_source_cannot_be_read_is_ignored_and_printed_once(self) -> None:
        self.c._global_enabled = True
        self.logic.getSourceMast = _fail("source gone")
        out = self.run_out(lambda: self.c._on_sml_property(self.logic))
        self.assertEqual(out.count("change ignored: source gone"), 1)

    # --- sml_ui ----------------------------------------------------------------------

    def test_a_mast_name_that_cannot_be_read_shows_a_question_mark_and_is_printed_once(self) -> None:
        self.mast.getUserName = _fail("name gone")
        names = []
        out = self.run_out(lambda: names.append(self.c._stored_enabled_source_names()))
        self.assertEqual(names, [(1, ["?"])] * 2)
        self.assertEqual(out.count("cannot read the name of mast"), 1)

    def test_an_unreadable_strip_component_is_printed_once_and_the_old_button_still_removed(self) -> None:
        space = base._Space()
        broken = jf.FakeButton("Other")
        broken.getText = _fail("no text")  # type: ignore[method-assign]
        stale = jf.FakeButton("SML Enabled")
        space.add(stale)
        space.add(broken)
        found = []
        out = self.run_out(lambda: found.append(self.c._button_on_strip(space)))
        self.assertEqual(found, [False, False])
        self.assertEqual(space.components, [broken])
        self.assertEqual(out.count("cannot read button-strip component"), 1)
        self.assertEqual(out.count("removed SML button left by an earlier run"), 1)
        self.c._button = broken
        self.assertTrue(self.c._button_on_strip(space))

    def test_a_strip_component_with_no_text_is_skipped_quietly(self) -> None:
        space = base._Space()

        class Panel:
            pass

        stale = jf.FakeButton("SML Disabled")
        space.add(Panel())
        space.add(stale)
        out = self.run_out(lambda: self.c._button_on_strip(space), times=1)
        self.assertNotIn("cannot read button-strip component", out)
        self.assertEqual(out.count("removed SML button left by an earlier run"), 1)


if __name__ == "__main__":
    unittest.main()
