"""The Pi keeps one tables.xml, in JMRI_UserFiles."""
from __future__ import annotations

import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "cats/scripts/pi/apply_hart_package_local.sh"

class PiTablesTest(unittest.TestCase):
    def test_deploy_moves_tables_out_of_hart(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('mv -f "$HART/tables.xml" "$UF/tables.xml"', source)
        self.assertNotIn('cp -f "$HART/tables.xml"', source)

    def test_nothing_runs_from_the_deploy_drop(self) -> None:
        for path in SCRIPT.parent.iterdir():
            if path.name in {"apply_hart_package_local.sh", "install_desktop_icons.sh", "README_CATS.txt"}:
                continue
            self.assertNotIn("/home/pi/hart", path.read_text(encoding="utf-8"), path.name)

    def test_deploy_installs_panels_then_empties_the_drop(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"$CATS_HOME/panels/"', source)
        self.assertLess(source.index('"$CATS_HOME/panels/"'), source.index('find "$HART" -mindepth 1 -delete'))

if __name__ == "__main__":
    unittest.main()
