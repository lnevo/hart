"""validate_cats_panel.py: the default list holds the live desks (generated since the CATS cut-over) and the other HART
panels in cats/panels, nothing else."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "cats/scripts"))

import validate_cats_panel as V  # noqa: E402


class DefaultPanels(unittest.TestCase):
    def test_live_desks_and_generated_panels_are_checked(self):
        seen = []
        saved = V.check
        V.check = lambda p: seen.append(p.relative_to(ROOT).as_posix()) or []
        argv, sys.argv = sys.argv, ["validate_cats_panel.py"]
        try:
            self.assertEqual(V.main(), 0)
        finally:
            V.check, sys.argv = saved, argv
        self.assertIn("cats/panels/HART_CTC.xml", seen)
        self.assertIn("cats/panels/HART_ABS.xml", seen)
        self.assertFalse([p for p in seen if "generated/" in p])
        self.assertTrue(all(Path(p).name.startswith("HART") for p in seen), seen)

    def test_a_layout_editor_file_fails(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write("<layout-config><LayoutEditor/></layout-config>")
        try:
            self.assertTrue(V.check(Path(f.name)))
        finally:
            Path(f.name).unlink()


if __name__ == "__main__":
    unittest.main()
