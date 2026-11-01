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

    def test_hosts_have_no_hart_folder(self) -> None:
        for folder in (SCRIPT.parent, SCRIPT.parent.parent / "windows"):
            for path in folder.iterdir():
                if path.suffix in {".sh", ".bat", ".ps1", ".desktop", ".txt"} or path.name == "JMRI_CATS":
                    source = path.read_text(encoding="utf-8", errors="replace")
                    self.assertNotIn("/home/pi/hart", source, path.name)
                    self.assertNotIn("USERPROFILE%\\hart", source, path.name)
                    self.assertNotIn("USERPROFILE 'hart", source, path.name)

    def test_pi_drop_stays_in_tmp_and_is_removed(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("/tmp/hart-deploy.*)", source)
        self.assertIn("""trap 'rm -rf "$HART"' EXIT""", source)


if __name__ == "__main__":
    unittest.main()
