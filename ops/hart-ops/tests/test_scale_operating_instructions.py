"""Behaviour tests for publications/rebuild_scale_operating_instructions.py (EQ-01)."""
import sys
import tempfile
import unittest
from pathlib import Path

PUB = Path(__file__).resolve().parents[1] / "publications"
sys.path.insert(0, str(PUB))

from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

import rebuild_scale_operating_instructions as eq  # noqa: E402


class Content(unittest.TestCase):
    def test_section_layout_is_applied_to_headings(self):
        h1 = [i for i, b in enumerate(eq.CONTENT) if b["kind"] == "h1"]
        self.assertGreaterEqual(len(h1), 3)
        self.assertEqual(eq.CONTENT[h1[0]].get("space_before"), "0")
        self.assertTrue(eq.CONTENT[h1[1]].get("column_break_before"))
        self.assertEqual(eq.CONTENT[h1[2] - 1], {"kind": "spacer"})
        self.assertNotIn("spacer_before", eq.CONTENT[h1[2]])

    def test_unknown_block_kind_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Unknown block kind: table"):
            eq._block_paragraphs({"kind": "table"}, None)

    def test_steps_restart_numbering(self):
        doc = Document(str(eq.CANONICAL))
        numbering = doc.part.numbering_part._element
        before = len(numbering.findall(qn("w:num")))
        paras = eq._block_paragraphs({"kind": "steps", "items": ["one", "two"]}, numbering)
        self.assertEqual(len(paras), 2)
        self.assertEqual(len(numbering.findall(qn("w:num"))), before + 1)
        ids = {p.find(qn("w:pPr")).find(qn("w:numPr")).find(qn("w:numId")).get(qn("w:val")) for p in paras}
        self.assertEqual(len(ids), 1)

    def test_missing_abstract_numbering_is_named(self):
        doc = Document()
        numbering = doc.part.numbering_part._element
        with self.assertRaisesRegex(RuntimeError, "abstractNum 99 not found"):
            eq._new_list_num(numbering, "99")


class Masthead(unittest.TestCase):
    def test_lines_are_replaced_by_prefix(self):
        doc = Document()
        for line in ("Scale Operating Instructions  ·  Revision C", "Effective 1 May 2020",
                     "Publication EQ-9", "Revision C", "Unrelated line"):
            doc.add_paragraph(line)
        eq._update_masthead(doc)
        texts = [p.text for p in doc.paragraphs]
        self.assertEqual(texts, [eq.PUBLICATION["title_line"], eq.PUBLICATION["effective"],
                                 eq.PUBLICATION["eq"], eq.PUBLICATION["revision"], "Unrelated line"])

    def test_missing_official_publication_line_is_named(self):
        doc = Document()
        doc.add_paragraph("no masthead here")
        with self.assertRaisesRegex(RuntimeError, "Official Publication paragraph not found"):
            eq._strip_body_after_official(doc)


class Rebuild(unittest.TestCase):
    def test_writes_to_the_given_path_only(self):
        canonical_bytes = eq.CANONICAL.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "eq01.docx"
            self.assertEqual(eq.rebuild(out), out)
            doc = Document(str(out))
            texts = [p.text for p in doc.paragraphs]
            self.assertIn(eq.PUBLICATION["title_line"], texts)
            first_h1 = next(b["text"] for b in eq.CONTENT if b["kind"] == "h1")
            self.assertIn(first_h1, texts)
            cols = doc.element.body.find(qn("w:sectPr")).find(qn("w:cols"))
            self.assertEqual(cols.get(qn("w:num")), "2")
        self.assertEqual(eq.CANONICAL.read_bytes(), canonical_bytes)
