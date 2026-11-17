"""approval: fingerprints of the approved panels and desks."""
import dataclasses
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import approval  # noqa: E402
import check_approved  # noqa: E402

DESK = "<DOCUMENT VERSION='3.1'><LINE NAME='a' X='1' Y='2'/><LINE NAME='b' X='3' Y='4'/></DOCUMENT>"
TABLES = ("<?xml version='1.0'?><layoutconfig><LayoutEditor name='HART Railroad' x='0' y='0'>"
          "<layoutturnout ident='TO1' x='1'/><positionablelabel text='hi' x='2'/></LayoutEditor></layoutconfig>")


class FingerprintTest(unittest.TestCase):
    def test_attribute_order_and_whitespace_do_not_matter(self):
        a = ET.fromstring("<D a='1' b='2'>\n  <L x='1' y='2'/>\n</D>")
        b = ET.fromstring("<D b='2' a='1'><L y='2' x='1'/></D>")
        self.assertEqual(approval.fingerprint(a, "D"), approval.fingerprint(b, "D"))

    def test_shape_head_children_panel(self):
        fp = approval.fingerprint(ET.fromstring(DESK), "DOCUMENT")
        self.assertEqual([w for _, w in fp], ["DOCUMENT DOCUMENT", "LINE a", "LINE b", "panel"])

    def test_compare_names_the_changed_element(self):
        want = approval.fingerprint(ET.fromstring(DESK), "DOCUMENT")
        got = approval.fingerprint(ET.fromstring(DESK.replace("X='3'", "X='9'")), "DOCUMENT")
        self.assertIsNone(approval.compare(want, want))
        self.assertEqual(approval.compare(want, got), "element 2 is LINE b, approved LINE b (changed)")

    def test_compare_counts_elements_when_one_is_added(self):
        want = approval.fingerprint(ET.fromstring(DESK), "DOCUMENT")
        got = approval.fingerprint(ET.fromstring(DESK.replace("</DOCUMENT>", "<LINE NAME='c'/></DOCUMENT>")), "DOCUMENT")
        self.assertIn("3 elements, approved 2", approval.compare(want, got))

    def test_parse_refuses_a_bad_line_and_a_missing_panel_hash(self):
        with self.assertRaisesRegex(approval.ApprovalError, "line 1: not"):
            approval.parse_fingerprint("nonsense\n", "f")
        h = "a" * 64
        with self.assertRaisesRegex(approval.ApprovalError, "no panel hash"):
            approval.parse_fingerprint(f"{h} one\n{h} two\n", "f")

    def test_format_round_trips(self):
        fp = approval.fingerprint(ET.fromstring(DESK), "DOCUMENT")
        text = approval.format_fingerprint(fp, "# note\n")
        self.assertEqual(approval.parse_fingerprint(text, "f"), fp)


class OutputTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        (self.dir / "desk.xml").write_text(DESK, encoding="utf-8")
        (self.dir / "tables.xml").write_text(TABLES, encoding="utf-8")
        self.desk = approval.Output("desk", "the test desk", self.dir / "desk.xml", self.dir / "desk.sha256", "DOCUMENT")
        self.panel = approval.Output("panel", "the test panel", self.dir / "tables.xml", self.dir / "panel.sha256",
                                     "LayoutEditor", "HART Railroad")

    def test_approve_then_check_passes_for_desk_and_panel(self):
        for out in (self.desk, self.panel):
            approval.approve(out, date="2026-01-01")
            approval.check(out)

    def test_drift_names_the_output_the_element_and_how_to_reapprove(self):
        approval.approve(self.desk)
        (self.dir / "desk.xml").write_text(DESK.replace("Y='2'", "Y='7'"), encoding="utf-8")
        with self.assertRaises(approval.ApprovalError) as cm:
            approval.check(self.desk)
        msg = str(cm.exception)
        self.assertIn("desk:", msg)
        self.assertIn("LINE a (changed)", msg)
        self.assertIn("check_approved.py --approve desk", msg)

    def test_panel_edit_is_caught(self):
        approval.approve(self.panel)
        (self.dir / "tables.xml").write_text(TABLES.replace("x='1'", "x='5'"), encoding="utf-8")
        with self.assertRaisesRegex(approval.ApprovalError, "layoutturnout TO1"):
            approval.check(self.panel)

    def test_missing_fingerprint_says_how_to_record_it(self):
        with self.assertRaisesRegex(approval.ApprovalError, "--approve"):
            approval.check(self.desk)

    def test_missing_output_and_missing_panel_are_errors(self):
        gone = dataclasses.replace(self.desk, source=self.dir / "nope.xml")
        with self.assertRaisesRegex(approval.ApprovalError, "cannot read"):
            approval.load_root(gone)
        other = dataclasses.replace(self.panel, panel="Other")
        with self.assertRaisesRegex(approval.ApprovalError, "no Layout Editor panel named 'Other'"):
            approval.load_root(other)

    def test_invalid_xml_is_an_error(self):
        (self.dir / "desk.xml").write_text("<DOCUMENT", encoding="utf-8")
        with self.assertRaisesRegex(approval.ApprovalError, "not valid XML"):
            approval.load_root(self.desk)


class LiveOutputsTest(unittest.TestCase):
    def test_the_recorded_outputs_are_the_approved_ones(self):
        for out in approval.OUTPUTS:
            with self.subTest(out.key):
                approval.check(out)

    def test_cli_rejects_an_unknown_key(self):
        with self.assertRaises(SystemExit):
            check_approved.main(["nope"])


if __name__ == "__main__":
    unittest.main()
