"""apply_le_sml_facing.py copies its result to the JMRI profile only for the checkout's own tables.xml: a generated
panel named by --panel (a cut-over candidate or a sandbox copy) never reaches ~/JMRI_UserFiles (HOME is a temp
folder)."""
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
from hartlib import paths  # noqa: E402


class ProfileSync(unittest.TestCase):
    def run_facing(self, home: Path, panel: Path) -> subprocess.CompletedProcess:
        env = {**os.environ, "HOME": str(home), "HART_GUARD_JMRI_RUNNING": "0"}
        env.pop("HART_TABLES", None)
        return subprocess.run([sys.executable, str(SCRIPTS / "apply_le_sml_facing.py"), "--panel", str(panel)],
                              env=env, capture_output=True, text=True, timeout=120)

    def test_a_generated_copy_is_never_copied_to_the_profile(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            (home / "JMRI_UserFiles").mkdir(parents=True)
            profile = home / "JMRI_UserFiles" / "tables.xml"
            profile.write_text("<layout-config/>")
            panel = Path(d) / "tables.xml"
            shutil.copy(paths.REPO_TABLES_XML, panel)      # the checkout's tables: the generated panel
            before = panel.read_bytes()
            done = self.run_facing(home, panel)
            self.assertEqual(1, done.returncode, done.stdout + done.stderr)
            self.assertIn("a generated panel that is not the checkout's tables.xml", done.stderr)
            self.assertEqual("<layout-config/>", profile.read_text())
            self.assertEqual(before, panel.read_bytes())

    def test_an_unreadable_panel_stops_with_its_name(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            home.mkdir()
            panel = Path(d) / "broken.xml"
            panel.write_text("<layout-config>")
            done = self.run_facing(home, panel)
            self.assertEqual(1, done.returncode)
            self.assertIn("broken.xml: cannot read its main Layout Editor panel", done.stderr)


if __name__ == "__main__":
    unittest.main()
