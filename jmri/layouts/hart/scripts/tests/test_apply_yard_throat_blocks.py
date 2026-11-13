from __future__ import annotations

import importlib.util
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "apply_yard_throat_blocks", SCRIPTS / "apply_yard_throat_blocks.py"
)
throat = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(throat)

SYS = "IF$vsm:basic:one-low($1021)"


def masts_with(uname: str) -> ET.Element:
    return ET.fromstring(
        "<signalmasts><virtualsignalmast>"
        f"<systemName>{SYS}</systemName><userName>{uname}</userName>"
        "</virtualsignalmast></signalmasts>"
    )


class EnsureVirtualMastTest(unittest.TestCase):
    def test_existing_mast_with_expected_name_is_left_alone(self):
        masts = masts_with("Mast 10RA")
        self.assertEqual(
            0, throat._ensure_virtual_mast(masts, {SYS}, SYS, "Mast 10RA")
        )
        self.assertEqual(1, len(masts))

    def test_old_name_stops_instead_of_adding_a_second_mast(self):
        masts = masts_with("Mast 9LA")
        with self.assertRaisesRegex(ValueError, "Mast 9LA"):
            throat._ensure_virtual_mast(masts, {SYS}, SYS, "Mast 10RA")
        self.assertEqual(1, len(masts))

    def test_missing_mast_is_added(self):
        masts = ET.Element("signalmasts")
        self.assertEqual(1, throat._ensure_virtual_mast(masts, set(), SYS, "Mast 10RA"))
        self.assertEqual("Mast 10RA", masts[0].findtext("userName"))

    def test_eh_exit_icons_face_eastbound(self):
        for row in throat.EH_EXIT_MASTS:
            self.assertTrue(row[3].endswith(("R", "RA", "RB")), row)
            self.assertEqual(90, row[6], row)


if __name__ == "__main__":
    unittest.main()
