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


if __name__ == "__main__":
    unittest.main()
