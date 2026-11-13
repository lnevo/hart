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


class RearMastsTest(unittest.TestCase):
    def test_each_rear_mast_protects_its_station(self):
        root = ET.parse(throat.DEFAULT).getroot()
        le = throat._le(root)
        segs = {ts.get("ident"): ts for ts in le.findall("tracksegment")}
        points = {pt.get("ident"): pt for pt in le.findall("positionablepoint")}
        for row in throat.REAR_MASTS:
            pt = points[row["anchor"]]
            _sys, uname, direction, *_ = row["virtual"]
            self.assertEqual(uname, pt.get(f"{direction}signalmast"), row["anchor"])
            # An anchor's eastbound slot protects its connect1 side (as A45 8RA).
            side = "connect1name" if direction == "eastbound" else "connect2name"
            self.assertEqual(row["station"], segs[pt.get(side)].get("blockname"), row["anchor"])
            other = "connect2name" if side == "connect1name" else "connect1name"
            self.assertEqual(row["throat"], segs[pt.get(other)].get("blockname"), row["anchor"])

    def test_switch_leg_masts_stay_on_their_turnouts(self):
        le = throat._le(ET.parse(throat.DEFAULT).getroot())
        slots = {
            (to.get("ident"), c.tag): (c.text or "").strip()
            for to in le.findall("layoutturnout")
            for c in to
        }
        self.assertEqual("Mast 36RB", slots[("TO113", "signalDMast")])
        self.assertEqual("Mast 40LB", slots[("TOL29", "signalCMast")])


class TidyXmlTest(unittest.TestCase):
    def parent(self) -> ET.Element:
        return ET.fromstring("<p>\n  <a />\n  <b />\n</p>")

    def test_append_keeps_one_element_per_line(self):
        p = self.parent()
        throat._insert_tidy(p, len(p), ET.Element("c"))
        self.assertEqual("<p>\n  <a />\n  <b />\n  <c />\n</p>", ET.tostring(p, encoding="unicode"))

    def test_insert_at_start_and_remove_last(self):
        p = self.parent()
        throat._insert_tidy(p, 0, ET.Element("z"))
        throat._remove_tidy(p, p.find("b"))
        self.assertEqual("<p>\n  <z />\n  <a />\n</p>", ET.tostring(p, encoding="unicode"))


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

    def test_stop_on_old_name_leaves_file_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / "tables.xml"
            text = throat.DEFAULT.read_text(encoding="utf-8")
            # Old slot name, plus a pending throat edit that runs first.
            text = text.replace(
                "<signalCMast>Mast 10RA</signalCMast>", "<signalCMast>Mast 9LA</signalCMast>", 1
            )
            text = text.replace('blockname="Track S-2 West"', 'blockname="Track S-2"', 1)
            copy.write_text(text, encoding="utf-8")
            before = copy.read_bytes()
            with self.assertRaisesRegex(ValueError, "Mast 9LA"):
                throat.apply(copy)
            self.assertEqual(before, copy.read_bytes())

    def test_scale_east_run_is_a_no_op(self):
        edits, before, after = self.run_on_copy(throat.apply_scale_east)
        self.assertEqual(0, edits)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
