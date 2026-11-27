"""sml_ui.py, signal_coordinator.py's Swing side: the main-window button's attach and retries, and the failures it
catches (a Java RuntimeException, a JMRI without the dialog) against those it lets through.

Run against an in-memory JMRI (jmri_fake): a fake Java call fails with RuntimeError, the fake's
java.lang.RuntimeException.
"""
from __future__ import annotations

import contextlib
import io
import sys
import types
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402
from test_signal_coordinator_behaviour import FakeLogic, _Space  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[5] / "jmri/scripts/signal_coordinator.py"
GIVE_UP = "mqtt_signalhead: giving up on main-window SML button (panel Signals lamp still works)"


class _BadComponent:
    """A strip component whose text cannot be read."""

    def __init__(self, error):
        self.error = error

    def getText(self):
        raise self.error

    def __repr__(self):
        return "BadComponent"


class SmlUi(unittest.TestCase):
    def setUp(self) -> None:
        import __main__

        saved = getattr(__main__, "digicon_sml_controller", None)
        if saved is not None:
            del __main__.digicon_sml_controller

        def restore() -> None:
            if saved is not None:
                __main__.digicon_sml_controller = saved
            elif hasattr(__main__, "digicon_sml_controller"):
                del __main__.digicon_sml_controller

        self.addCleanup(restore)
        self.layout = jf.Layout(mqtt=False)
        self.sc = jf.load_script(SCRIPT, self.layout)
        stack = contextlib.ExitStack()
        stack.enter_context(jf.running(self.layout))
        self.addCleanup(stack.close)
        self.mast = self.layout.masts.add(jf.FakeMast("IF$shsm:basic:one-searchlight(IH432)", "Mast 6LB"))
        self.logic = FakeLogic(self.mast, "Mast 8RA", "Mast 8RB")
        c = self.sc["DigiconMqttSml"]()
        c._masts = [self.mast]
        c._sml_by_mast = {self.mast: self.logic}
        self.labels: list[int] = []
        c._set_button_label = lambda: self.labels.append(1)
        self.c = c
        self.ui: Any = sys.modules["sml_ui"]
        jf.Thread.started.clear()

    def run_attach(self) -> list[str]:
        """_add_toggle_button from its first attempt, every retry thread run in turn; the lines it printed."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.c._add_toggle_button()
            jf.run_threads()
        return out.getvalue().splitlines()

    def test_the_button_goes_on_the_strip(self) -> None:
        space = self.layout.button_space = _Space()
        lines = self.run_attach()
        self.assertEqual(space.components, [self.c._button])
        self.assertEqual(self.c._button.getText(), "SML Disabled")
        self.assertEqual(lines, ["mqtt_signalhead: SML toggle on PanelPro button strip"])
        self.assertEqual(self.labels, [1])
        clicks = []
        self.c._on_toggle = lambda: clicks.append(1)
        self.c._button.click()
        self.assertEqual(clicks, [1])

    def test_no_strip_retries_then_gives_up(self) -> None:
        self.layout.button_space = None
        lines = self.run_attach()
        self.assertEqual(lines, ["mqtt_signalhead: buttonSpace attempt %d failed: Apps.buttonSpace() is None" % n
                                 for n in range(1, self.ui._BUTTON_ATTEMPTS + 1)] + [GIVE_UP])
        self.assertEqual(self.labels, [])

    def test_a_strip_that_appears_on_a_retry_gets_the_button(self) -> None:
        space = _Space()
        tries = []

        def button_space():
            tries.append(1)
            return space if len(tries) == 3 else None

        apps: Any = sys.modules["apps"]
        saved = apps.Apps
        apps.Apps = types.SimpleNamespace(buttonSpace=button_space)
        self.addCleanup(setattr, apps, "Apps", saved)
        lines = self.run_attach()
        self.assertEqual(len(tries), 3)
        self.assertEqual(space.components, [self.c._button])
        self.assertEqual(lines[-1], "mqtt_signalhead: SML toggle on PanelPro button strip")
        self.assertEqual(self.labels, [1])

    def test_a_detached_controller_stops_retrying(self) -> None:
        self.layout.button_space = None
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.c._add_toggle_button()
            self.c._shutting_down = True
            jf.run_threads()
        self.assertEqual(out.getvalue().splitlines(),
                         ["mqtt_signalhead: buttonSpace attempt 1 failed: Apps.buttonSpace() is None"])

    def test_a_swing_failure_on_the_strip_is_a_failed_attempt(self) -> None:
        space = _Space()
        space.add = lambda c: (_ for _ in ()).throw(RuntimeError("strip gone"))
        self.layout.button_space = space
        lines = self.run_attach()
        self.assertEqual(lines[0], "mqtt_signalhead: buttonSpace attempt 1 failed: strip gone")
        self.assertEqual(lines[-1], GIVE_UP)

    def test_a_python_error_on_the_strip_is_a_failed_attempt_and_the_retry_goes_on(self) -> None:
        space = _Space()
        space.add = lambda c: (_ for _ in ()).throw(AttributeError("no add"))
        self.layout.button_space = space
        lines = self.run_attach()
        self.assertEqual(lines[0], "mqtt_signalhead: buttonSpace attempt 1 failed: no add")
        self.assertEqual(lines[-1], GIVE_UP)

    def test_an_unreadable_component_is_printed_once_and_skipped(self) -> None:
        space = _Space()
        space.components.append(_BadComponent(RuntimeError("no text")))
        self.layout.button_space = space
        lines = self.run_attach()
        self.assertEqual(lines, ["mqtt_signalhead: cannot read button-strip component BadComponent: no text",
                                 "mqtt_signalhead: SML toggle on PanelPro button strip"])
        self.assertIn(self.c._button, space.components)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(self.c._button_on_strip(space))      # a retry: the same failure is not printed again
        self.assertEqual(out.getvalue(), "")

    def test_a_python_error_on_the_strip_is_not_swallowed(self) -> None:
        space = _Space()
        space.components.append(_BadComponent(TypeError("a bug")))
        self.layout.button_space = space
        with self.assertRaisesRegex(TypeError, "a bug"):
            self.run_attach()

    def test_a_mast_whose_name_cannot_be_read_is_named_question_mark(self) -> None:
        self.mast.getUserName = lambda: (_ for _ in ()).throw(RuntimeError("bean gone"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            n, names = self.c._stored_enabled_source_names()
        self.assertEqual((n, names), (2, ["?"]))
        self.assertIn(": bean gone", out.getvalue())

    def test_a_missing_jmri_dialog_falls_back_to_the_plain_one(self) -> None:
        shown: list[str] = []

        def confirm(parent: object, msg: str, title: str, opts: int, kind: int) -> int:
            shown.append(title)
            return 0

        swing: Any = sys.modules["javax.swing"]
        saved = swing.JOptionPane
        swing.JOptionPane = types.SimpleNamespace(
            WARNING_MESSAGE=2, YES_NO_OPTION=0, YES_OPTION=0, NO_OPTION=1,
            showMessageDialog=lambda parent, msg, title, kind: shown.append(title),
            showConfirmDialog=confirm)
        self.addCleanup(setattr, swing, "JOptionPane", saved)
        self.ui.JOptionPane = swing.JOptionPane
        self.addCleanup(setattr, self.ui, "JOptionPane", saved)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):        # the fake JmriJOptionPane has no methods: AttributeError
            self.assertTrue(self.c._warn_if_stored_sml_enabled())
            self.assertTrue(self.c._ask_force_override_edt())
        self.assertEqual(shown, ["Digicon SML stored Enabled", "SML Enabled"])
        self.assertEqual(out.getvalue().count("JMRI dialog failed"), 2)

    def test_an_override_dialog_that_fails_counts_as_no(self) -> None:
        swing: Any = sys.modules["jmri.util.swing"]
        saved = swing.JmriJOptionPane
        swing.JmriJOptionPane = types.SimpleNamespace(
            YES_NO_OPTION=0, WARNING_MESSAGE=2,
            showConfirmDialog=lambda *a: (_ for _ in ()).throw(RuntimeError("headless")))
        self.addCleanup(setattr, swing, "JmriJOptionPane", saved)
        plain = types.SimpleNamespace(YES_NO_OPTION=0, WARNING_MESSAGE=2, YES_OPTION=0, NO_OPTION=1,
                                      showConfirmDialog=lambda *a: (_ for _ in ()).throw(RuntimeError("headless")))
        saved_plain = self.ui.JOptionPane
        self.ui.JOptionPane = plain
        self.addCleanup(setattr, self.ui, "JOptionPane", saved_plain)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertFalse(self.c._ask_force_override_edt())
        self.assertIn("mqtt_signalhead: override dialog failed: headless", out.getvalue())


if __name__ == "__main__":
    unittest.main()
