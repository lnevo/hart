from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

HART_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = HART_ROOT / "scripts" / "add_yard_ladder_le_icons.py"
BUTTONS = HART_ROOT.parents[2] / "cats" / "resources" / "buttons"


def _load():
    spec = importlib.util.spec_from_file_location("add_yard_ladder_le_icons", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class YardLadderTriangles(unittest.TestCase):
    def test_source_pngs_exist(self) -> None:
        mod = _load()
        for name in mod.ICON_FILES:
            path = BUTTONS / name
            self.assertTrue(path.is_file(), path)

    def test_one_pair_rotated_for_west(self) -> None:
        mod = _load()
        self.assertEqual(mod.ICON_SCALE, "1.0")
        self.assertEqual(mod.FACE_URLS["closed"], "preference:resources/buttons/triangle_idle.png")
        self.assertEqual(mod.FACE_URLS["thrown"], "preference:resources/buttons/triangle_active.png")
        self.assertEqual(mod.SIDE_DEGREES["L"], "180")
        self.assertEqual(mod.SIDE_DEGREES["R"], "0")
        self.assertEqual(mod.LEFT_DX, -22)
        self.assertEqual(mod._xy_for("IT:HART:YL:L1"), (921, 293))
        self.assertEqual(mod._xy_for("IT:HART:YL:R1"), (1020, 293))
        for n, y in (("2", 344), ("3", 391), ("4", 438), ("5", 480)):
            self.assertEqual(mod._xy_for(f"IT:HART:YL:L{n}"), (921, y))
        for url in mod.FACE_URLS.values():
            self.assertNotIn("USS/sensor", url)
            self.assertNotIn("CSD/JOP", url)
            self.assertNotIn("preference:hart/icons", url)

    def test_deploy_tables_use_preference_buttons(self) -> None:
        tables = HART_ROOT / "output" / "tables.xml"
        text = tables.read_text(encoding="utf-8")
        self.assertIn("preference:resources/buttons/triangle_idle.png", text)
        self.assertNotIn("preference:hart/icons/triangle", text)


if __name__ == "__main__":
    unittest.main()
