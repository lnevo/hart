"""hartlib.jmri_profile: the saved panel windows of user-interface.xml take tables.xml's sizes and nothing else in the
file changes; its errors are hartlib errors with their cause kept; and it imports with only the modules the host
packages carry beside it."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from hartlib import jmri_profile, paths  # noqa: E402
from hartlib.errors import HartlibError  # noqa: E402

# The modules the deploy packages carry (HARTLIB_HOST_MODULES in tools/hosts/deploy/common.sh).
HOST_MODULES = ("__init__.py", "errors.py", "jmri_profile.py")
TABLES = """<?xml version="1.0" encoding="UTF-8"?>
<layout-config>
  <LayoutEditor class="x" name="HART Railroad" windowwidth="1920" windowheight="1032"/>
  <LayoutEditor class="x" name="Main Level" windowwidth="1920" windowheight="385"/>
</layout-config>
"""
UI = """<windowDetails>
  <window xmlns="" class="jmri.jmrit.display.layoutEditor.LayoutEditor:Main Level" height="408.0" locX="-69.0" locY="406.0" width="1920.0">
  </window>
  <window xmlns="" class="jmri.jmrit.withrottle.UserInterface" height="250.0" width="400.0"/>
  <window xmlns="" class="jmri.jmrit.display.layoutEditor.LayoutEditor:HART Railroad" locX="0.0"/>
</windowDetails>
"""


class Files(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path


class Resize(Files):
    def test_saved_panel_windows_take_the_tables_size(self) -> None:
        sizes = jmri_profile.panel_sizes(self.write("tables.xml", TABLES))
        self.assertEqual(sizes, {"HART Railroad": ("1920", "1032"), "Main Level": ("1920", "385")})
        new, changes = jmri_profile.resize(UI, sizes)
        self.assertEqual(changes, [("Main Level", "1920.0x408.0", "1920.0x385.0"),
                                   ("HART Railroad", "?x?", "1920.0x1032.0")])    # a window with no size gets one
        self.assertIn('Main Level" height="385.0" locX="-69.0" locY="406.0" width="1920.0">', new)
        self.assertIn('HART Railroad" locX="0.0" width="1920.0" height="1032.0"/>', new)
        self.assertIn('UserInterface" height="250.0" width="400.0"/>', new)        # not a panel
        self.assertEqual(jmri_profile.resize(new, sizes), (new, []))

    def test_saved_windows_unescape_the_panel_name(self) -> None:
        text = UI.replace("LayoutEditor:Main Level", "LayoutEditor:P&amp;CV Yard")
        self.assertEqual(jmri_profile.saved_windows(text), ["P&CV Yard", "HART Railroad"])

    def test_the_real_tables_give_every_panel_a_size(self) -> None:
        sizes = jmri_profile.panel_sizes(paths.REPO_TABLES_XML)
        self.assertIn("HART Railroad", sizes)
        self.assertTrue(all(w and h for w, h in sizes.values()))


class Write(Files):
    def test_a_backup_holds_the_file_as_it_was(self) -> None:
        ui = self.write("user-interface.xml", UI)
        copy = jmri_profile.write_user_interface(ui, "<windowDetails/>", backup=True)
        assert copy is not None
        self.assertRegex(copy.name, r"^user-interface\.xml\.hart-\d{8}-\d{6}\.bak$")
        self.assertEqual(copy.parent, ui.parent)
        self.assertEqual(copy.read_text(encoding="utf-8"), UI)
        self.assertEqual(ui.read_text(encoding="utf-8"), "<windowDetails/>")

    def test_no_backup_unless_asked(self) -> None:
        ui = self.write("user-interface.xml", UI)
        self.assertIsNone(jmri_profile.write_user_interface(ui, "<windowDetails/>"))
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["user-interface.xml"])


class Errors(Files):
    def test_errors_are_hartlib_errors_not_exits_and_keep_their_cause(self) -> None:
        for call, message in (
                (lambda: jmri_profile.panel_sizes(self.dir / "missing.xml"), "cannot read"),
                (lambda: jmri_profile.panel_sizes(self.write("bad.xml", "<layout-config>")), "cannot read"),
                (lambda: jmri_profile.read_user_interface(self.dir / "missing.xml"), "cannot read")):
            with self.subTest(message=message), self.assertRaisesRegex(jmri_profile.WindowSizesError, message) as cm:
                call()
            self.assertIsInstance(cm.exception, HartlibError)
            self.assertNotIsInstance(cm.exception, SystemExit)
            self.assertIsNotNone(cm.exception.__cause__)

    def test_files_with_nothing_to_set_stop(self) -> None:
        cases = (
            (lambda: jmri_profile.panel_sizes(self.write("t.xml", "<layout-config/>")), "no Layout Editor panel"),
            (lambda: jmri_profile.panel_sizes(self.write("t.xml", '<layout-config><LayoutEditor name="Bare"/>'
                                                                  '</layout-config>')), "Bare has no window size"),
            (lambda: jmri_profile.read_user_interface(self.write("u.xml", "<other/>")), "no <windowDetails>"))
        for call, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(jmri_profile.WindowSizesError, message):
                call()

    def test_a_startup_error_is_a_hartlib_and_a_value_error(self) -> None:
        profile = self.write("profile.xml", "<startup/>")
        with self.assertRaises(jmri_profile.StartupPatchError) as cm:
            jmri_profile.load_tables_from(profile, "preference:tables.xml")
        self.assertIsInstance(cm.exception, HartlibError)
        self.assertIsInstance(cm.exception, ValueError)


class HostCopy(Files):
    def test_it_imports_with_only_the_modules_the_packages_carry(self) -> None:
        """A package has no checkout (hartlib.paths would not import): the module needs nothing else of hartlib."""
        dest = self.dir / "src/hartlib"
        dest.mkdir(parents=True)
        for name in HOST_MODULES:
            shutil.copy2(SRC / "hartlib" / name, dest / name)
        tables = self.write("tables.xml", TABLES)
        code = ("import sys; sys.path.insert(0, sys.argv[1]); from hartlib import jmri_profile; "
                "print(sorted(jmri_profile.panel_sizes(sys.argv[2])))")
        done = subprocess.run([sys.executable, "-I", "-c", code, str(self.dir / "src"), str(tables)],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "['HART Railroad', 'Main Level']")


if __name__ == "__main__":
    unittest.main()
