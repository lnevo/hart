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
