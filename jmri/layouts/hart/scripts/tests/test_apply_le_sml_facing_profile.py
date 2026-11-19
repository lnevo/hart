"""apply_le_sml_facing.py runs on a generated panel only and copies its result to the JMRI profile only for the
checkout's own tables.xml: a panel that is not generated is refused, and a generated panel named by --panel (a
cut-over candidate or a sandbox copy) never reaches ~/JMRI_UserFiles (HOME is a temp folder)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import paths, tables  # noqa: E402


class ProfileSync(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.home = self.dir / "home"
        (self.home / "JMRI_UserFiles").mkdir(parents=True)
        self.profile = self.home / "JMRI_UserFiles" / "tables.xml"
        self.profile.write_text("<layout-config/>")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_facing(self, panel: Path, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "HOME": str(self.home), "HART_GUARD_JMRI_RUNNING": "0"}
        env.pop("HART_TABLES", None)
        return subprocess.run([sys.executable, str(SCRIPTS / "apply_le_sml_facing.py"), "--panel", str(panel), *args],
                              env=env, capture_output=True, text=True, timeout=120)

    def assert_untouched(self, panel: Path, before: bytes) -> None:
        self.assertEqual("<layout-config/>", self.profile.read_text())
        self.assertEqual(before, panel.read_bytes())

    def test_a_generated_copy_is_never_copied_to_the_profile(self) -> None:
        panel = self.dir / "tables.xml"
        shutil.copy(paths.REPO_TABLES_XML, panel)      # the checkout's tables: the generated panel
        before = panel.read_bytes()
        done = self.run_facing(panel)
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn("not the checkout's tables.xml, so it is not copied", done.stderr)
        self.assert_untouched(panel, before)

    def test_a_panel_that_is_not_generated_is_refused(self) -> None:
        root = tables.read(paths.REPO_TABLES_XML)
        le = tables.layout_editor(root)
        le.remove(le.find(f"positionablelabel[@text='{tables.GENERATED_PANEL_MARKER}']"))
        panel = self.dir / "hand.xml"
        panel.write_bytes(tables.Tables(root=root).tobytes())
        empty = self.dir / "empty.xml"
        empty.write_text("<layout-config/>")
        for path, said in ((panel, "'HART Railroad' panel is not a generated one"),
                           (empty, "no main Layout Editor panel")):
            before = path.read_bytes()
            for args in ((), ("--no-pref",)):
                with self.subTest(path=path.name, args=args):
                    done = self.run_facing(path, *args)
                    self.assertEqual(1, done.returncode)
                    self.assertIn(said, done.stderr)
                    self.assert_untouched(path, before)

    def test_an_unreadable_panel_stops_with_its_name(self) -> None:
        panel = self.dir / "broken.xml"
        panel.write_text("<layout-config>")
        done = self.run_facing(panel)
        self.assertEqual(1, done.returncode)
        self.assertIn("broken.xml: cannot read it", done.stderr)


if __name__ == "__main__":
    unittest.main()
