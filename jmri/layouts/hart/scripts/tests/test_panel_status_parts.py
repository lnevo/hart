"""panel_status.py's sibling modules (its PARTS), loaded through jython_siblings.py against jmri_fake.

The script imports each part as a module from preference:jython, reloading it on a re-run, so a re-run reads
each part afresh and starts from fresh state. A missing or broken part stops the script, naming it and the
folder, before it starts anything. The Turnouts lamp icon that lost its head is found by its tooltip.
"""
from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402
from hartlib import coordinator, hand_lists  # noqa: E402  (jmri_fake puts hartlib on sys.path)

PARTS = coordinator.panel_status_parts()
FILES = coordinator.files(coordinator.PANEL_STATUS)


class Parts(unittest.TestCase):
    def setUp(self) -> None:
        import __main__

        saved = getattr(__main__, "hart_panel_status_run", None)

        def restore():
            if saved is not None:
                __main__.hart_panel_status_run = saved
            elif hasattr(__main__, "hart_panel_status_run"):
                del __main__.hart_panel_status_run

        self.addCleanup(restore)
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.folder = Path(holder.name) / "jython"
        self.script = jf.stage_jython(coordinator.PANEL_STATUS, self.folder)
        self.layout = jf.Layout(mqtt=False)
        self.layout.jython_dir = self.folder

    def load(self) -> jf.ScriptGlobals:
        return jf.load_script(self.script, self.layout)

    def run_id(self):
        import __main__

        return getattr(__main__, "hart_panel_status_run", None)

    def assert_load_fails(self, *parts: str):
        before = self.run_id()
        with self.assertRaises(ImportError) as caught:
            self.load()
        self.assertEqual(type(caught.exception).__name__, "SiblingModuleError")
        for part in parts:
            self.assertIn(part, str(caught.exception))
        return before

    def assert_nothing_started(self, run_before) -> None:
        self.assertEqual(jf.Timer.pending, [])           # no arm timer
        self.assertEqual(self.run_id(), run_before)      # an earlier run's timers are not superseded

    def test_parts_are_modules_from_the_jython_folder(self) -> None:
        env = self.load()
        self.assertEqual(env["PARTS"], PARTS)
        for name in PARTS:
            self.assertEqual(Path(sys.modules[name].__file__).resolve().parent, self.folder.resolve(), name)
        self.assertIs(env["sync_turnout_fb_lamp"], sys.modules["panel_status_turnouts"].sync_turnout_fb_lamp)
        self.assertIs(env["_raise_block_labels"], sys.modules["panel_status_clicks"]._raise_block_labels)

    def test_a_rerun_reads_a_changed_part_and_starts_from_fresh_state(self) -> None:
        first = self.load()
        turnouts = sys.modules["panel_status_turnouts"]
        turnouts._plant_modes["M2T1"] = 1
        part = self.folder / "panel_status_turnouts.py"
        text = part.read_text(encoding="utf-8")
        self.assertEqual(text.count("\n_LAMP_AMBER_MS = 500\n"), 1)
        part.write_text(text.replace("\n_LAMP_AMBER_MS = 500\n", "\n_LAMP_AMBER_MS = 321\n"), encoding="utf-8")
        second = self.load()
        self.assertEqual(first["_LAMP_AMBER_MS"], 500)
        self.assertEqual(second["_LAMP_AMBER_MS"], 321)
        self.assertEqual(sys.modules["panel_status_turnouts"]._plant_modes, {})

    def test_a_missing_part_stops_the_script_before_it_starts(self) -> None:
        for name in PARTS:
            with self.subTest(name=name):
                moved = self.folder / f"{name}.py"
                kept = self.folder.parent / f"{name}.py"
                moved.rename(kept)
                try:
                    before = self.assert_load_fails(f"{name}.py is missing from {self.folder}")
                    self.assert_nothing_started(before)
                finally:
                    kept.rename(moved)

    def test_a_part_that_does_not_compile_stops_the_script_before_it_starts(self) -> None:
        last = self.folder / f"{PARTS[-1]}.py"
        last.write_text(last.read_text(encoding="utf-8") + "\ndef broken(:\n", encoding="utf-8")
        before = self.assert_load_fails(f"{PARTS[-1]}.py in {self.folder} does not compile")
        self.assert_nothing_started(before)

    def test_a_part_that_fails_to_import_names_it(self) -> None:
        first = self.folder / f"{PARTS[0]}.py"
        first.write_text(first.read_text(encoding="utf-8") + "\nraise RuntimeError('boom at import')\n",
                         encoding="utf-8")
        before = self.assert_load_fails(f"cannot import {PARTS[0]} from {self.folder}", "boom at import")
        self.assert_nothing_started(before)

    def test_no_jython_folder_stops_the_script(self) -> None:
        self.layout.jython_dir = self.folder.parent / "absent"
        before = self.run_id()
        with self.assertRaises(ImportError) as caught:
            self.load()
        self.assertIn("no jython_siblings.py in the jython folder", str(caught.exception))
        self.assertIn("absent", str(caught.exception))
        self.assert_nothing_started(before)


class TurnoutsIconRebind(unittest.TestCase):
    """_rebind_turnout_fb_icons re-points the SignalHeadIcon whose tooltip is the Turnouts lamp's."""

    def setUp(self) -> None:
        self.layout = jf.Layout(mqtt=False)
        self.ps = jf.load_script(coordinator.PANEL_STATUS, self.layout)
        self.turnouts = sys.modules["panel_status_turnouts"]
        running = jf.running(self.layout)
        running.__enter__()
        self.addCleanup(running.__exit__, None, None, None)

    def icon(self, tip, head=None, fail=None):
        display = sys.modules["jmri.jmrit.display"]
        set_to = []

        class Icon(display.SignalHeadIcon):
            def getSignalHead(self): return head
            def getToolTip(self):
                if fail:
                    raise RuntimeError(fail)
                return None if tip is None else types.SimpleNamespace(getText=lambda: tip)
            def setSignalHead(self, value): set_to.append(value)

        icon = Icon()
        icon.set_to = set_to
        return icon

    def rebind(self, *icons):
        self.layout.editors.append(types.SimpleNamespace(getContents=lambda: list(icons)))
        self.turnouts._rebind_turnout_fb_icons(self.ps["_ensure_turnout_fb_head"]())

    def test_the_icon_with_the_lamps_tooltip_gets_the_head(self) -> None:
        lamp = self.icon(self.turnouts.TURNOUT_FB_TOOLTIP)
        other = self.icon("another lamp")
        bare = self.icon(None)
        self.rebind(other, bare, lamp)
        self.assertEqual(lamp.set_to, ["IH9990"])
        self.assertEqual(other.set_to, [])
        self.assertEqual(bare.set_to, [])
        self.assertTrue(self.turnouts._icon_rebound)

    def test_an_icon_that_already_shows_the_head_is_left_alone(self) -> None:
        head = self.ps["_ensure_turnout_fb_head"]()
        lamp = self.icon(self.turnouts.TURNOUT_FB_TOOLTIP, head=head)
        self.rebind(lamp)
        self.assertEqual(lamp.set_to, [])
        self.assertTrue(self.turnouts._icon_rebound)

    def test_an_unreadable_tooltip_is_logged_and_skipped(self) -> None:
        broken = self.icon(None, fail="no tooltip here")
        lamp = self.icon(self.turnouts.TURNOUT_FB_TOOLTIP)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.rebind(broken, lamp)
        self.assertIn("cannot read the tooltip", out.getvalue())
        self.assertIn("no tooltip here", out.getvalue())
        self.assertEqual(lamp.set_to, ["IH9990"])

    def test_a_failure_that_repeats_on_every_scan_is_logged_once(self) -> None:
        broken = self.icon(None, fail="no tooltip here")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            for _ in range(3):
                self.rebind(broken)
        self.assertEqual(out.getvalue().count("cannot read the tooltip"), 1)
        self.assertFalse(self.turnouts._icon_rebound)

    def test_no_matching_icon_rebinds_nothing(self) -> None:
        other = self.icon("another lamp")
        self.rebind(other)
        self.assertEqual(other.set_to, [])
        self.assertFalse(self.turnouts._icon_rebound)

    def test_the_tooltip_is_the_panels(self) -> None:
        # the key the rebind looks for is the tooltip the panel gives the Turnouts lamp (hand_lists.PANEL_ITEMS)
        items = hand_lists.PANEL_ITEMS.read_text(encoding="utf-8")
        self.assertIn("<tooltip>%s</tooltip>" % self.turnouts.TURNOUT_FB_TOOLTIP, items)


class TurnoutsLamp(unittest.TestCase):
    """The Turnouts lamp's colour from the plants' feedback modes, the click that flips them, and the failures it
    logs instead of hiding."""

    def setUp(self) -> None:
        self.layout = jf.Layout(mqtt=False)
        self.ps = jf.load_script(coordinator.PANEL_STATUS, self.layout)
        self.turnouts = sys.modules["panel_status_turnouts"]
        running = jf.running(self.layout)
        running.__enter__()
        self.addCleanup(running.__exit__, None, None, None)
        jf.Timer.pending.clear()

    def plant(self, name: str, mode: int) -> jf.FakeTurnout:
        fb = (jf.FakeSensor(name + "N"), jf.FakeSensor(name + "R"))
        return self.layout.turnouts.add(jf.FakeTurnout(name, *fb, mode=mode))

    def lamp(self) -> int:
        self.turnouts.sync_turnout_fb_lamp()
        return self.layout.heads.beans[self.turnouts.TURNOUT_FB_HEAD].appearance

    def test_the_colour_follows_the_plants_modes(self) -> None:
        self.assertEqual(self.lamp(), jf.SignalHead.YELLOW)          # no plants
        self.plant("M2T1", jf.Turnout.TWOSENSOR)
        self.plant("MTT2", jf.Turnout.TWOSENSOR)
        self.layout.turnouts.add(jf.FakeTurnout("IT9", mode=jf.Turnout.DIRECT))   # not a plant
        self.plant("IT10", jf.Turnout.DIRECT)                                     # not a plant either
        self.assertEqual(self.lamp(), jf.SignalHead.GREEN)
        self.plant("M2T3", jf.Turnout.DIRECT)
        self.assertEqual(self.lamp(), jf.SignalHead.YELLOW)
        for name in ("M2T1", "MTT2"):
            self.layout.turnouts.beans[name].mode = jf.Turnout.DIRECT
        self.assertEqual(self.lamp(), jf.SignalHead.RED)

    def test_a_click_flips_every_plant_and_back(self) -> None:
        plants = [self.plant("M2T1", jf.Turnout.TWOSENSOR), self.plant("M2T2", jf.Turnout.TWOSENSOR)]
        self.turnouts.toggle_turnout_fb_mode()
        jf.fire_timers()
        self.assertEqual([t.mode for t in plants], [jf.Turnout.DIRECT] * 2)
        self.turnouts.toggle_turnout_fb_mode()
        jf.fire_timers()
        self.assertEqual([t.mode for t in plants], [jf.Turnout.TWOSENSOR] * 2)
        self.assertEqual([t.commanded for t in plants], [[], []])

    def test_an_unreadable_mode_is_logged_once_and_left_out_of_the_click(self) -> None:
        good = self.plant("M2T1", jf.Turnout.TWOSENSOR)
        bad = self.plant("M2T2", jf.Turnout.TWOSENSOR)

        def fail():
            raise RuntimeError("mode gone")
        bad.getFeedbackMode = fail
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.lamp(), jf.SignalHead.YELLOW)      # an unknown mode reads as mixed
            self.lamp()
            self.turnouts.toggle_turnout_fb_mode()
            jf.fire_timers()
        self.assertEqual(out.getvalue().count("cannot read the feedback mode of M2T2: mode gone"), 1)
        self.assertEqual(good.mode, jf.Turnout.DIRECT)                # the readable plants were all TWOSENSOR

    def test_unreadable_sensors_leave_the_turnout_out_with_a_message(self) -> None:
        bad = self.plant("M2T1", jf.Turnout.TWOSENSOR)

        def fail():
            raise RuntimeError("no sensors")
        bad.getFirstSensor = fail
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.lamp(), jf.SignalHead.YELLOW)      # no plant counted
        self.assertIn("cannot read the feedback sensors of M2T1: no sensors", out.getvalue())


class ClickFailures(unittest.TestCase):
    """panel_status_clicks prints each icon or editor it cannot read and goes on; nothing fails in silence."""

    def setUp(self) -> None:
        self.layout = jf.Layout(mqtt=False)
        jf.load_script(coordinator.PANEL_STATUS, self.layout)
        self.clicks = sys.modules["panel_status_clicks"]
        running = jf.running(self.layout)
        running.__enter__()
        self.addCleanup(running.__exit__, None, None, None)
        self.display = sys.modules["jmri.jmrit.display"]

    def editor(self, contents=None, fail=None, title="HART"):
        def get_contents():
            if fail:
                raise RuntimeError(fail)
            return list(contents or ())
        ed = types.SimpleNamespace(getContents=get_contents, getTitle=lambda: title, getTargetFrame=lambda: None)
        self.layout.editors.append(ed)
        return ed

    def test_a_lamp_icon_with_unreadable_bounds_is_printed_and_the_others_still_hit(self) -> None:
        class Icon:
            def __init__(self, fail=False): self.fail = fail
            def getX(self):
                if self.fail:
                    raise RuntimeError("no bounds")
                return 0
            def getY(self): return 0
            def getWidth(self): return 20
            def getHeight(self): return 20
            def getDisplayLevel(self): return 10

        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.clicks._lamp_at([(Icon(fail=True), "bad"), (Icon(), "good")], 1.0, 5, 5), "good")
        self.assertIn("cannot read the bounds of lamp icon", out.getvalue())
        self.assertIn("no bounds", out.getvalue())

    def test_an_icon_that_refuses_its_click_settings_is_printed(self) -> None:
        class Icon:
            def setControlling(self, value): raise RuntimeError("locked")
            def setClickMode(self, value): raise RuntimeError("no mode")

        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.clicks._disable_icon_control(Icon())
        self.assertIn("cannot turn off the click control", out.getvalue())
        self.assertIn("cannot clear the click mode", out.getvalue())

    def test_an_unreadable_editor_is_printed_when_arming_and_raising_labels(self) -> None:
        self.editor(fail="contents gone")
        label = type("Label", (self.display.BlockContentsIcon,), {
            "getDisplayLevel": lambda self: 0, "setDisplayLevel": lambda self, n: setattr(self, "level", n)})()
        self.editor([label])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(self.clicks.arm_status_lamp_clicks({"IS1": ("LCOS", lambda: None)}, {}, lambda *a: None))
            self.assertEqual(self.clicks._raise_block_labels(), 1)
        self.assertIn("cannot read the contents of", out.getvalue())
        self.assertIn("for lamp clicks: contents gone", out.getvalue())
        self.assertIn("to raise BlockContentsIcon labels: contents gone", out.getvalue())
        self.assertEqual(label.level, self.clicks._BCI_LEVEL)

    def test_no_editor_manager_is_printed(self) -> None:
        im = self.clicks.jmri.InstanceManager      # the one panel_status_turnouts imported too
        with mock.patch.object(self.clicks, "_clicks_armed", False), \
                mock.patch.object(self.clicks, "_bci_raised", False), \
                mock.patch.object(im, "getNullableDefault", lambda cls: None), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(self.clicks.arm_status_lamp_clicks({}, {}, lambda *a: None))
            self.assertEqual(self.clicks._raise_block_labels(), 0)
            sys.modules["panel_status_turnouts"]._rebind_turnout_fb_icons(object())
        self.assertIn("no EditorManager yet, status lamp clicks not armed", out.getvalue())
        self.assertIn("no EditorManager yet, BlockContentsIcon labels not raised", out.getvalue())
        self.assertIn("Turnouts icon rebind: no EditorManager yet", out.getvalue())


class TurnoutsHeadCalls(unittest.TestCase):
    """Each call on the Turnouts lamp head runs on its own: one that fails is printed once and the rest still run."""

    def setUp(self) -> None:
        self.layout = jf.Layout(mqtt=False)
        jf.load_script(coordinator.PANEL_STATUS, self.layout)
        self.turnouts = sys.modules["panel_status_turnouts"]
        running = jf.running(self.layout)
        running.__enter__()
        self.addCleanup(running.__exit__, None, None, None)

    def test_a_failing_held_or_lit_call_still_sets_the_appearance(self) -> None:
        set_to = []

        class Head:
            def setHeld(self, value): raise RuntimeError("held stuck")
            def setLit(self, value): raise RuntimeError("lit stuck")
            def setAppearance(self, value): set_to.append(value)

        with contextlib.redirect_stdout(io.StringIO()) as out:
            for _ in range(2):
                self.turnouts._set_head_appearance(Head(), jf.SignalHead.GREEN)
            jf.fire_timers()
        self.assertEqual(set_to, [jf.SignalHead.GREEN] * 2)
        self.assertEqual(out.getvalue().count("Turnouts lamp setHeld(False) failed: held stuck"), 1)
        self.assertEqual(out.getvalue().count("Turnouts lamp setLit(True) failed: lit stuck"), 1)

    def test_a_failing_appearance_is_printed(self) -> None:
        class Head:
            def setHeld(self, value): pass
            def setLit(self, value): pass
            def setAppearance(self, value): raise RuntimeError("no such appearance")

        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.turnouts._set_head_appearance(Head(), jf.SignalHead.RED)
            jf.fire_timers()
        self.assertIn("Turnouts lamp setAppearance(%s) failed: no such appearance" % jf.SignalHead.RED,
                      out.getvalue())

    def test_an_icon_whose_head_cannot_be_read_is_printed_and_skipped(self) -> None:
        icon_class: Any = sys.modules["jmri.jmrit.display"].SignalHeadIcon
        set_to = []

        class Broken(icon_class):
            def getSignalHead(self): raise RuntimeError("head gone")

        class Lamp(icon_class):
            def getSignalHead(self): return None
            def getToolTip(self): return types.SimpleNamespace(getText=lambda: sys.modules[
                "panel_status_turnouts"].TURNOUT_FB_TOOLTIP)
            def setSignalHead(self, value): set_to.append(value)

        self.layout.editors.append(types.SimpleNamespace(getContents=lambda: [Broken(), Lamp()]))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.turnouts._rebind_turnout_fb_icons(object())
        self.assertIn("cannot read the head of", out.getvalue())
        self.assertIn("head gone", out.getvalue())
        self.assertEqual(set_to, [self.turnouts.TURNOUT_FB_HEAD])


class TurnoutsRepeatedFailures(unittest.TestCase):
    """A failure that repeats on every turnout event or lamp paint is printed once."""

    def setUp(self) -> None:
        self.layout = jf.Layout(mqtt=False)
        jf.load_script(coordinator.PANEL_STATUS, self.layout)
        self.turnouts = sys.modules["panel_status_turnouts"]
        running = jf.running(self.layout)
        running.__enter__()
        self.addCleanup(running.__exit__, None, None, None)

    def test_a_turnout_scan_that_fails_is_printed_once(self) -> None:
        def fail():
            raise RuntimeError("manager gone")
        self.layout.turnouts.getNamedBeanSet = fail
        with contextlib.redirect_stdout(io.StringIO()) as out:
            for _ in range(3):
                self.turnouts.sync_turnout_fb_lamp()
        self.assertEqual(out.getvalue().count("scan turnouts failed: manager gone"), 1)
        self.assertEqual(self.layout.heads.beans[self.turnouts.TURNOUT_FB_HEAD].appearance, jf.SignalHead.YELLOW)

    def test_a_turnout_event_that_fails_is_printed_once(self) -> None:
        class Broken:
            def getSystemName(self): raise RuntimeError("name gone")

        with contextlib.redirect_stdout(io.StringIO()) as out:
            for _ in range(3):
                self.turnouts._note_plant(Broken())
        self.assertEqual(out.getvalue().count("plant update failed: name gone"), 1)

    def test_an_icon_that_refuses_both_rebinds_is_printed_once_and_tried_again(self) -> None:
        icon_class: Any = sys.modules["jmri.jmrit.display"].SignalHeadIcon
        tries = []

        class Lamp(icon_class):
            def getSignalHead(self): return None
            def getToolTip(self): return types.SimpleNamespace(getText=lambda: sys.modules[
                "panel_status_turnouts"].TURNOUT_FB_TOOLTIP)
            def setSignalHead(self, value):
                tries.append(value)
                raise RuntimeError("icon locked")

        self.layout.editors.append(types.SimpleNamespace(getContents=lambda: [Lamp()]))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            for _ in range(3):
                self.turnouts._rebind_turnout_fb_icons(object())
        self.assertEqual(len(tries), 6)                      # by name, then the head itself, on each scan
        self.assertEqual(out.getvalue().count("rebind by name failed (icon locked)"), 1)
        self.assertEqual(out.getvalue().count("Turnouts icon rebind failed on"), 1)
        self.assertFalse(self.turnouts._icon_rebound)


class PartText(unittest.TestCase):
    """The rules the script keeps (no plant turnout commands, no yard-ladder paint) hold for each part too."""

    def test_no_part_commands_a_plant_turnout_or_paints_yard_ladders(self) -> None:
        for path in FILES[1:]:
            text = path.read_text(encoding="utf-8")
            with self.subTest(part=path.name):
                self.assertNotIn("setCommandedState(", text)
                self.assertNotIn("IT:HART:YL:", text)
                self.assertNotIn("apply_maintain_mqtt", text)
                self.assertNotIn("_reload_mqtt_retain", text)

    def test_parts_are_ascii_or_declare_utf8_and_import_no_future(self) -> None:
        # Jython 2.7 imports a module under PEP 263: a non-ASCII byte needs a coding line. A __future__ import
        # would stay on in JMRI's shared engine (test_jython_no_print_function.py).
        coding = re.compile(rb"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")
        for path in [*FILES[1:], jf.SIBLING_LOADER]:
            data = path.read_bytes()
            with self.subTest(part=path.name):
                self.assertTrue(data.isascii() or any(coding.match(ln) for ln in data.splitlines()[:2]))
                self.assertNotRegex(data.decode("utf-8"), r"(?m)^\s*from\s+__future__\s+import")

    def test_each_part_is_named_after_the_script(self) -> None:
        self.assertTrue(PARTS)
        for name in PARTS:
            self.assertTrue(name.startswith("panel_status_"), name)


if __name__ == "__main__":
    unittest.main()
