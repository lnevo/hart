"""panel_status.py's parts (its PARTS), run against jmri_fake from a scratch jython folder.

The parts are not modules: the script reads each from preference:jython, compiles all of them before it does
anything, and runs each in its own namespace at the place it was cut from. So every name and global they set
is the script's (the behaviour tests in test_panel_status.py read them there), a re-run reads each part afresh,
and a missing, broken or unrun part stops the script with an error that names it and the folder.
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import coordinator  # noqa: E402

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
        self.folder.mkdir()
        for path in FILES:
            shutil.copy(path, self.folder / path.name)
        self.script = self.folder / coordinator.PANEL_STATUS.name
        self.layout = jf.Layout(mqtt=False)
        self.layout.jython_dir = self.folder

    def load(self) -> jf.ScriptGlobals:
        return jf.load_script(self.script, self.layout)

    def run_id(self):
        import __main__

        return getattr(__main__, "hart_panel_status_run", None)

    def assert_load_fails(self, *parts: str) -> None:
        before = self.run_id()
        with self.assertRaises(ImportError) as caught:
            self.load()
        self.assertEqual(type(caught.exception).__name__, "PanelStatusPartError")
        for part in parts:
            self.assertIn(part, str(caught.exception))
        return before

    def assert_nothing_started(self, run_before) -> None:
        self.assertEqual(jf.Timer.pending, [])           # no arm timer
        self.assertEqual(self.run_id(), run_before)      # an earlier run's timers are not superseded

    def test_parts_run_in_the_scripts_namespace(self) -> None:
        env = self.load()
        self.assertEqual(env["PARTS"], PARTS)
        self.assertEqual(env["_part_code"], {})          # each part ran once
        for name, path in (("_rescan_plant_modes", "panel_status_turnouts.py"),
                           ("toggle_turnout_fb_mode", "panel_status_turnouts.py"),
                           ("_arm_status_lamp_clicks", "panel_status_clicks.py"),
                           ("_raise_block_labels", "panel_status_clicks.py")):
            fn = env[name]
            self.assertIs(fn.__globals__, env, name)    # its globals are the script's
            self.assertEqual(Path(fn.__code__.co_filename), self.folder / path, name)
        self.assertEqual(env["_PanelLampClick"].__module__, env["__name__"])
        # a part's global write lands in the script's namespace
        env["_plant_modes"] = None
        with jf.running(self.layout):
            env["_rescan_plant_modes"]()
        self.assertEqual(env["_plant_modes"], {})

    def test_the_parts_run_where_they_were_cut(self) -> None:
        # each part runs after what it uses at load and before what uses it at load
        text = self.script.read_text(encoding="utf-8")
        at = {name: text.index('_run_part("%s")' % name) for name in PARTS}
        self.assertEqual(sorted(at, key=at.get), list(PARTS))
        self.assertLess(text.index("_part_code = _compile_parts(PARTS)"), text.index("_RUN_ID ="))
        self.assertLess(max(at.values()), text.index("if _part_code:"))
        self.assertLess(text.index("if _part_code:"), text.index("_t0.start()"))

    def test_a_rerun_reads_a_changed_part(self) -> None:
        first = self.load()
        part = self.folder / "panel_status_turnouts.py"
        text = part.read_text(encoding="utf-8")
        self.assertEqual(text.count("\n_LAMP_AMBER_MS = 500\n"), 1)
        part.write_text(text.replace("\n_LAMP_AMBER_MS = 500\n", "\n_LAMP_AMBER_MS = 321\n"), encoding="utf-8")
        second = self.load()
        self.assertEqual(first["_LAMP_AMBER_MS"], 500)
        self.assertEqual(second["_LAMP_AMBER_MS"], 321)

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

    def test_a_part_that_is_not_utf8_stops_the_script(self) -> None:
        first = self.folder / f"{PARTS[0]}.py"
        first.write_bytes(first.read_bytes() + b"\n# \xff\n")
        self.assert_load_fails(f"{PARTS[0]}.py in {self.folder} does not compile")

    def test_no_jython_folder_stops_the_script(self) -> None:
        self.layout.jython_dir = self.folder.parent / "absent"
        before = self.assert_load_fails("no jython folder", "absent")
        self.assert_nothing_started(before)

    def test_a_listed_part_that_never_runs_stops_the_script(self) -> None:
        (self.folder / "panel_status_extra.py").write_text("EXTRA = 1\n", encoding="utf-8")
        text = self.script.read_text(encoding="utf-8")
        self.assertEqual(text.count('    "panel_status_clicks",\n)'), 1)
        self.script.write_text(text.replace('    "panel_status_clicks",\n)',
                                            '    "panel_status_clicks",\n    "panel_status_extra",\n)'),
                               encoding="utf-8")
        # checked at the end of the script (it is an error in the script's own text, which this test is for):
        # the run's id is taken by then, but its arm timer never starts
        self.assert_load_fails("parts in PARTS that never ran: panel_status_extra")
        self.assertEqual(jf.Timer.pending, [])

    def test_a_part_runs_only_once(self) -> None:
        env = self.load()
        for name in (PARTS[0], "panel_status_other"):
            with self.subTest(name=name), jf.running(self.layout):
                with self.assertRaisesRegex(ImportError, "%s is not in PARTS or has already run" % name):
                    env["_run_part"](name)


class PartText(unittest.TestCase):
    """What test_panel_status_contract.py holds the script to, each part is held to as well."""

    def test_no_part_commands_a_plant_turnout_or_paints_yard_ladders(self) -> None:
        for path in FILES[1:]:
            text = path.read_text(encoding="utf-8")
            with self.subTest(part=path.name):
                self.assertNotIn("setCommandedState(", text)
                self.assertNotIn("IT:HART:YL:", text)
                self.assertNotIn("apply_maintain_mqtt", text)
                self.assertNotIn("_reload_mqtt_retain", text)

    def test_parts_are_utf8_text_with_no_coding_line_or_future_import(self) -> None:
        # The script compiles each part from its decoded text, as JMRI compiles the script; Jython refuses a
        # coding line in text that is already decoded ("encoding declaration in Unicode string"). A __future__
        # import would stay on in JMRI's shared engine (test_jython_no_print_function.py).
        coding = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")
        for path in FILES[1:]:
            text = path.read_bytes().decode("utf-8")
            with self.subTest(part=path.name):
                self.assertFalse(any(coding.match(line) for line in text.splitlines()[:2]))
                self.assertNotRegex(text, r"(?m)^\s*from\s+__future__\s+import")

    def test_each_part_is_named_after_the_script(self) -> None:
        self.assertTrue(PARTS)
        for name in PARTS:
            self.assertTrue(name.startswith("panel_status_"), name)


if __name__ == "__main__":
    unittest.main()
