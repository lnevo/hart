"""The one-off edits of the hand-drawn Layout Editor panel refuse a generated panel (LE cut-over, Phase 3).

apply_yard_throat_blocks.py (F46-W-0 and the throat pixels), apply_le_cleanup.py, add_yard_ladder_le_icons.py and
add_digicon_le_signal_icons.py pin idents and pixels of the hand-drawn panel. On a panel that holds the generated-
panel marker each stops before reading further or writing anything, the profile included (HOME is a temp folder).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import paths, tables  # noqa: E402

ONE_OFFS = ("apply_yard_throat_blocks.py", "apply_le_cleanup.py", "add_yard_ladder_le_icons.py",
            "add_digicon_le_signal_icons.py")


class HandDrawnOnly(unittest.TestCase):
    def test_each_one_off_refuses_a_generated_panel_and_writes_nothing(self) -> None:
        doc = tables.load(paths.REPO_TABLES_XML)
        tables.layout_editor(doc.root).insert(1, tables.generated_marker_label())
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            home.mkdir()
            panel = Path(d) / "tables.xml"
            panel.write_bytes(doc.tobytes())
            before = panel.read_bytes()
            env = {**os.environ, "HOME": str(home), "HART_GUARD_JMRI_RUNNING": "0"}
            env.pop("HART_TABLES", None)
            for script in ONE_OFFS:
                with self.subTest(script=script):
                    done = subprocess.run([sys.executable, str(SCRIPTS / script), "--panel", str(panel)],
                                          env=env, capture_output=True, text=True, timeout=120)
                    self.assertNotEqual(0, done.returncode)
                    self.assertIn(f"{script}: the 'HART Railroad' panel", done.stderr)
                    self.assertIn("is generated", done.stderr)
                    self.assertEqual(before, panel.read_bytes())
            self.assertEqual([], list(home.rglob("*")))


if __name__ == "__main__":
    unittest.main()
