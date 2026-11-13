from __future__ import annotations

import importlib.util
import shutil
import tempfile
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

    def test_eh_exit_icons_face_eastbound_in_script_and_tables(self):
        tables = ET.parse(throat.DEFAULT).getroot()
        icons = {
            ic.get("signalmast"): ic.get("degrees")
            for ic in tables.iter("signalmasticon")
            if ic.get("hidden") == "yes"
        }
        for row in throat.EH_EXIT_MASTS:
            self.assertEqual(90, row[6], row)
            self.assertEqual("90", icons.get(row[3]), row[3])

    def test_existing_icon_gets_its_direction_back(self):
        le = ET.fromstring(
            '<LayoutEditor><signalmasticon signalmast="Mast 10RA" hidden="yes" '
            'x="1" y="2" degrees="270" /></LayoutEditor>'
        )
        self.assertEqual(1, throat._ensure_hidden_icon(le, "Mast 10RA", 598, 268, 90))
        icon = le.find("signalmasticon")
        self.assertEqual(("1", "2", "90"), (icon.get("x"), icon.get("y"), icon.get("degrees")))
        self.assertEqual(0, throat._ensure_hidden_icon(le, "Mast 10RA", 598, 268, 90))

    def test_turnout_slot_with_old_name_stops(self):
        to = ET.fromstring(
            '<layoutturnout ident="TO10"><signalCMast>Mast 9LA</signalCMast></layoutturnout>'
        )
        with self.assertRaisesRegex(ValueError, "TO10 signalCMast holds 'Mast 9LA'"):
            throat._ensure_turnout_mast(to, "signalCMast", "Mast 10RA")
        self.assertEqual(1, len(to))
        self.assertEqual(0, throat._ensure_turnout_mast(to, "signalCMast", "Mast 9LA"))


class CurrentTablesTest(unittest.TestCase):
    """The script describes tables.xml as it is; a run on it changes nothing."""

    def run_on_copy(self, fn) -> tuple[int, bytes, bytes]:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / "tables.xml"
            shutil.copyfile(throat.DEFAULT, copy)
            before = copy.read_bytes()
            edits = fn(copy)
            return edits, before, copy.read_bytes()

    def test_default_run_is_a_no_op(self):
        edits, before, after = self.run_on_copy(throat.apply)
        self.assertEqual(0, edits)
        self.assertEqual(before, after)

    def test_scale_east_run_is_a_no_op(self):
        edits, before, after = self.run_on_copy(throat.apply_scale_east)
        self.assertEqual(0, edits)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
