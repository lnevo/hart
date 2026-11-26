"""approval: fingerprints of the approved panels and desks."""
import contextlib
import dataclasses
import io
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
        self.assertEqual(approval.compare(want, got), "child 2 is LINE b, approved LINE b (changed)")

    def test_compare_counts_elements_when_one_is_added(self):
        want = approval.fingerprint(ET.fromstring(DESK), "DOCUMENT")
        got = approval.fingerprint(ET.fromstring(DESK.replace("</DOCUMENT>", "<LINE NAME='c'/></DOCUMENT>")), "DOCUMENT")
        self.assertIn("3 children, approved 2", approval.compare(want, got))

    def test_parse_refuses_a_bad_line_and_a_missing_panel_hash(self):
        with self.assertRaisesRegex(approval.ApprovalError, "line 1: not"):
            approval.parse_fingerprint("nonsense\n", "f", "DOCUMENT")
        h = "a" * 64
        with self.assertRaisesRegex(approval.ApprovalError, "no panel hash"):
            approval.parse_fingerprint(f"{h} one\n{h} two\n", "f", "DOCUMENT")

    def test_format_round_trips(self):
        fp = approval.fingerprint(ET.fromstring(DESK), "DOCUMENT")
        text = approval.format_fingerprint(fp, "# note\n")
        self.assertEqual(approval.parse_fingerprint(text, "f", "DOCUMENT"), fp)


class RobustnessTest(unittest.TestCase):
    def fp(self, text, drop=frozenset()):
        return approval.fingerprint(ET.fromstring(text), "D", drop)

    def test_view_attributes_are_left_out_of_the_head_and_the_whole(self):
        a = "<LayoutEditor name='P' x='0' y='0' windowwidth='1900' mainlinetrackwidth='4'><t a='1'/></LayoutEditor>"
        b = a.replace("x='0'", "x='9'").replace("1900", "1500")
        self.assertEqual(self.fp(a, approval.VIEW_ATTRS), self.fp(b, approval.VIEW_ATTRS))
        self.assertNotEqual(self.fp(a), self.fp(b))
        c = a.replace("mainlinetrackwidth='4'", "mainlinetrackwidth='6'")
        self.assertNotEqual(self.fp(a, approval.VIEW_ATTRS), self.fp(c, approval.VIEW_ATTRS))

    def test_meaningful_text_spaces_count_but_layout_whitespace_does_not(self):
        self.assertNotEqual(self.fp("<D><t> hi </t></D>"), self.fp("<D><t>hi</t></D>"))
        self.assertEqual(self.fp("<D>\n <t>hi</t>\n</D>"), self.fp("<D><t>hi</t></D>"))

    def test_comments_and_instructions_are_skipped(self):
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        root = ET.fromstring("<D><!-- c --><?pi x?><t a='1'/></D>", parser)
        plain = self.fp("<D><t a='1'/></D>")
        got = approval.fingerprint(root, "D")
        self.assertEqual(got, plain)
        self.assertNotIn("0x", " ".join(w for _, w in got))

    def test_trackplan_children_are_named_by_place(self):
        text = ("<DOCUMENT><TRACKPLAN COLUMNS='4'><SECTION X='2' Y='1'><SEC_NAME NAME='WEST'/></SECTION>"
                "<SECTION X='5' Y='1'/></TRACKPLAN></DOCUMENT>")
        got = approval.fingerprint(ET.fromstring(text), "DOCUMENT")
        self.assertEqual([w for _, w in got], ["DOCUMENT DOCUMENT", "TRACKPLAN #0", "TRACKPLAN/SECTION 2,1 WEST",
                                               "TRACKPLAN/SECTION 5,1", "panel"])
        moved = approval.fingerprint(ET.fromstring(text.replace("X='5'", "X='6'")), "DOCUMENT")
        self.assertIn("child 3 is TRACKPLAN/SECTION 6,1", approval.compare(got, moved))

    def test_the_first_line_must_be_the_root(self):
        h = "a" * 64
        with self.assertRaisesRegex(approval.ApprovalError, "first line"):
            approval.parse_fingerprint(f"{h} LINE a\n{h} panel\n", "f", "DOCUMENT")

    def test_a_root_attribute_change_is_named(self):
        want = self.fp("<D a='1'><t/></D>")
        self.assertEqual(approval.compare(want, self.fp("<D a='2'><t/></D>")), "the root's own attributes changed")


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


class SourceTest(unittest.TestCase):
    def test_the_live_panel_reads_this_checkouts_tables_not_hart_tables(self):
        live = next(o for o in approval.OUTPUTS if o.key == "le-panel")
        self.assertEqual(live.source, approval.paths.REPO_TABLES_XML)

    def test_the_outputs_are_the_live_panel_and_the_two_desks(self):
        # the trial cut-over copy (le-candidate) is retired
        self.assertEqual([o.key for o in approval.OUTPUTS], ["le-panel", "cats-ctc", "cats-abs"])
        for o in approval.OUTPUTS:
            self.assertTrue(o.approved.is_file(), o.approved)
            self.assertNotIn("trial", o.source.parts, o.key)


class CliTest(unittest.TestCase):
    def refused(self, *argv):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            check_approved.main(list(argv))

    def test_unknown_key_is_refused(self):
        self.refused("nope")

    def test_a_bare_approve_is_refused_and_so_is_approve_with_check(self):
        self.refused("--approve")
        self.refused("--approve", "--all", "cats-ctc")
        self.refused("--approve", "--check", "cats-ctc")
        self.refused("--all")


if __name__ == "__main__":
    unittest.main()
