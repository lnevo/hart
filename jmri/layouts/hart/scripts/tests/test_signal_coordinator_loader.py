"""signal_coordinator.py's sibling modules, loaded through jython_siblings.py, run against jmri_fake.

JMRI runs the script from preference:jython with no __file__ and that folder off sys.path, and keeps
imported modules across runs. The loader puts the folder on sys.path, reloads every sibling on a
re-run (so a redeploy never mixes a new script with old modules) and stops with an error that names
the module and the folder when one is missing or comes from elsewhere.
"""
from __future__ import annotations

import contextlib
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import coordinator  # noqa: E402

SIBLINGS = coordinator.sibling_modules()


class Loader(unittest.TestCase):
    def setUp(self) -> None:
        import __main__

        saved = getattr(__main__, "digicon_sml_controller", None)

        def restore():
            if saved is not None:
                __main__.digicon_sml_controller = saved
            elif hasattr(__main__, "digicon_sml_controller"):
                del __main__.digicon_sml_controller

        self.addCleanup(restore)
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.folder = Path(holder.name) / "jython"
        self.script = jf.stage_jython(coordinator.SCRIPT, self.folder)
        self.layout = jf.Layout(mqtt=False)
        self.layout.jython_dir = self.folder

    def load(self) -> jf.ScriptGlobals:
        return jf.load_script(self.script, self.layout)

    def assert_load_fails(self, *parts: str) -> None:
        with self.assertRaises(ImportError) as caught:
            self.load()
        self.assertEqual(type(caught.exception).__name__, "SiblingModuleError")
        for part in parts:
            self.assertIn(part, str(caught.exception))

    def test_siblings_load_from_the_jython_folder(self) -> None:
        env = self.load()
        self.assertEqual(env["SIBLING_MODULES"], SIBLINGS)
        for name in SIBLINGS:
            self.assertEqual(Path(sys.modules[name].__file__).resolve().parent, self.folder.resolve(), name)
        self.assertNotIn(str(self.folder), sys.path)          # load_script takes the script's entry out again
        self.assertEqual(env["DigiconMqttSml"].__mro__[1].__name__, "SmlBeans")

    def test_a_rerun_picks_up_a_changed_sibling(self) -> None:
        first = self.load()
        beans = self.folder / "sml_beans.py"
        text = beans.read_text(encoding="utf-8")
        self.assertEqual(text.count("\nHOLD_WAIT_MS = 3000\n"), 1)
        beans.write_text(text.replace("\nHOLD_WAIT_MS = 3000\n", "\nHOLD_WAIT_MS = 4321\n"), encoding="utf-8")
        second = self.load()
        self.assertEqual(first["HOLD_WAIT_MS"], 3000)
        self.assertEqual(second["HOLD_WAIT_MS"], 4321)
        # Every sibling that imports it was reloaded after sml_beans, so it holds the new value too.
        for name in SIBLINGS:
            if hasattr(sys.modules[name], "HOLD_WAIT_MS"):
                self.assertEqual(sys.modules[name].HOLD_WAIT_MS, 4321, name)
        # The re-run's class is built from the reloaded mixins, not the first run's.
        self.assertIs(second["SmlBeans"], sys.modules["sml_beans"].SmlBeans)
        self.assertIsNot(second["SmlBeans"], first["SmlBeans"])

    def test_a_missing_sibling_stops_the_script(self) -> None:
        for name in (SIBLINGS[0], SIBLINGS[-1]):
            with self.subTest(name=name):
                moved = self.folder / f"{name}.py"
                kept = self.folder.parent / f"{name}.py"
                moved.rename(kept)
                try:
                    self.assert_load_fails(f"{name}.py is missing from {self.folder}")
                finally:
                    kept.rename(moved)

    def test_a_sibling_from_another_folder_stops_the_script(self) -> None:
        other = self.folder.parent / "other"
        other.mkdir()
        (other / f"{SIBLINGS[0]}.py").write_text("X = 1\n", encoding="utf-8")
        saved = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), saved))
        sys.path[:0] = [str(other), str(self.folder)]      # the jython folder is on the path, behind another copy
        self.assert_load_fails(f"{SIBLINGS[0]} was loaded from", str(other), f"not from {self.folder}")

    def test_no_jython_folder_stops_the_script(self) -> None:
        self.layout.jython_dir = self.folder.parent / "absent"
        with self.assertRaises(ImportError) as caught:
            jf.load_script(self.script, self.layout)
        self.assertIn("no jython_siblings.py in the jython folder", str(caught.exception))
        self.assertIn("absent", str(caught.exception))


    def test_no_shared_loader_stops_the_script(self) -> None:
        (self.folder / jf.SIBLING_LOADER.name).unlink()
        with self.assertRaises(ImportError) as caught:
            self.load()
        self.assertIn("no jython_siblings.py in the jython folder", str(caught.exception))

    def test_a_rerun_reloads_the_shared_loader(self) -> None:
        self.load()
        loader = self.folder / jf.SIBLING_LOADER.name
        loader.write_text(loader.read_text(encoding="utf-8") + "\nRELOADED = True\n", encoding="utf-8")
        self.load()
        self.assertTrue(sys.modules["jython_siblings"].RELOADED)

    def test_a_sibling_whose_bytes_do_not_decode_stops_the_script(self) -> None:
        # the loader compiles each file's bytes, as an import reads them (Jython 2.7 applies PEP 263)
        first = self.folder / f"{SIBLINGS[0]}.py"
        first.write_bytes(first.read_bytes() + b'\nBAD = "\xff"\n')
        self.assert_load_fails(f"{SIBLINGS[0]}.py in {self.folder} does not compile")

    def test_every_sibling_is_ascii_or_declares_its_encoding(self) -> None:
        # JMRI runs the script from a string, but imports the modules: Jython 2.7 applies PEP 263 to them and
        # refuses a non-ASCII byte in a file with no coding line (seen in PanelPro 2026-11-22).
        coding = re.compile(rb"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")
        for path in coordinator.files()[1:]:
            data = path.read_bytes()
            declared = any(coding.match(line) for line in data.splitlines()[:2])
            self.assertTrue(data.isascii() or declared, f"{path.name} has non-ASCII bytes and no coding line")

    def test_a_sibling_that_does_not_compile_stops_before_any_reload(self) -> None:
        self.load()
        before = {name: sys.modules[name] for name in SIBLINGS}
        last = self.folder / f"{SIBLINGS[-1]}.py"
        last.write_text(last.read_text(encoding="utf-8") + "\ndef broken(:\n", encoding="utf-8")
        beans = self.folder / "sml_beans.py"
        beans.write_text(beans.read_text(encoding="utf-8") + "\nRELOADED = True\n", encoding="utf-8")
        self.assert_load_fails(f"{SIBLINGS[-1]}.py in {self.folder} does not compile")
        self.assertFalse(hasattr(sys.modules["sml_beans"], "RELOADED"))     # nothing was reloaded first
        self.assertIs(sys.modules["sml_beans"], before["sml_beans"])

    def test_a_sibling_that_fails_to_import_names_the_module(self) -> None:
        last = self.folder / f"{SIBLINGS[-1]}.py"
        last.write_text(last.read_text(encoding="utf-8") + "\nraise RuntimeError('boom at import')\n",
                        encoding="utf-8")
        self.assert_load_fails(f"cannot import {SIBLINGS[-1]} from {self.folder}", "boom at import")

    def test_no_sibling_calls_await(self) -> None:
        # jmri_fake renames Jython's .await( only in the script it loads; a module with it fails to import here.
        for path in coordinator.files()[1:]:
            self.assertNotIn(".await(", path.read_text(encoding="utf-8"), path.name)


class ScriptGlobalsPatches(unittest.TestCase):
    """A test's write to the script's globals reaches the siblings that share that object, and only those."""

    def test_patch_reaches_siblings_holding_the_same_object(self) -> None:
        shared, own, new = object(), object(), object()
        same = types.SimpleNamespace(Thread=shared)
        different = types.SimpleNamespace(Thread=own)
        neither = types.SimpleNamespace()
        env = jf.ScriptGlobals(Thread=shared)
        env.siblings = (same, different, neither)
        env["Thread"] = new
        self.assertIs(env["Thread"], new)
        self.assertIs(same.Thread, new)
        self.assertIs(different.Thread, own)
        self.assertFalse(hasattr(neither, "Thread"))

    def test_a_new_name_reaches_no_sibling(self) -> None:
        holder = types.SimpleNamespace(controller=None)
        env = jf.ScriptGlobals()
        env.siblings = (holder,)
        env["controller"] = 1
        self.assertIsNone(holder.controller)

    def test_fileutil_knows_only_the_jython_folder(self) -> None:
        layout = jf.Layout(mqtt=False)
        with jf.jmri_modules(layout), contextlib.redirect_stdout(None):
            import jmri

            with self.assertRaisesRegex(ValueError, "no jython folder set"):
                jmri.util.FileUtil.getExternalFilename("preference:jython")
            layout.jython_dir = Path("/x/jython")
            self.assertEqual(jmri.util.FileUtil.getExternalFilename("preference:jython"), "/x/jython")
            with self.assertRaisesRegex(ValueError, "preference:scripts"):
                jmri.util.FileUtil.getExternalFilename("preference:scripts")


if __name__ == "__main__":
    unittest.main()
