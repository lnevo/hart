from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "rewrite_button_icon_paths.py"


def _load():
    spec = importlib.util.spec_from_file_location("rewrite_button_icon_paths", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


SAMPLE = """
<BUTTON PRIMARY="/Users/lnevo/hart/cats/resources/buttons/lamp_left_idle.png" ALTERNATE="/Users/lnevo/hart/cats/resources/buttons/lamp_left_active.png"/>
<BUTTON PRIMARY="C:/Users/lnevo/hart/cats/resources/buttons/lamp_right_idle.png" ALTERNATE="C:/Users/lnevo/hart/cats/resources/buttons/lamp_right_active.png"/>
"""


class RewriteButtonIconPaths(unittest.TestCase):
    def test_pi_user_files_not_hart_clone_or_preference_prefix(self) -> None:
        mod = _load()
        out = mod.rewrite(SAMPLE, "/home/pi/JMRI_UserFiles")
        self.assertIn(
            'PRIMARY="/home/pi/JMRI_UserFiles/resources/buttons/lamp_left_idle.png"',
            out,
        )
        self.assertIn(
            'ALTERNATE="/home/pi/JMRI_UserFiles/resources/buttons/lamp_right_active.png"',
            out,
        )
        self.assertNotIn("preference:", out)
        self.assertNotIn("/home/pi/hart/", out)
        self.assertNotIn("/Users/lnevo/hart/", out)

    def test_windows_user_files(self) -> None:
        mod = _load()
        out = mod.rewrite(SAMPLE, "C:/Users/lnevo/JMRI_UserFiles")
        self.assertIn(
            'PRIMARY="C:/Users/lnevo/JMRI_UserFiles/resources/buttons/lamp_left_idle.png"',
            out,
        )
        self.assertNotIn("preference:", out)
        self.assertNotIn("/hart/cats/resources/buttons", out)


if __name__ == "__main__":
    unittest.main()
