"""Behaviour tests for card_pipeline/generate_card_template.py.

Other scripts (generate_single_card, generate_all_cards, generate_cc_waybill_labels,
generate_waybill_cards) call build_card, build_waybill_card, build_cc_waybill_label,
keep_sticker_grid, strip_grid_guides, add_document_tail, insert_before_sect,
ensure_sect_pr_last, CARD_SLOTS, STICKER_SHEET and require_sticker_sheet; those are covered here.

The sticker sheet and the logo/icons are Apostrophe's or private files, so tests use a
stand-in 3x3 table and point every image path at a file that does not exist: cards then carry
text placeholders and the snapshots do not depend on any photo or template.
Golden data: tests/golden/w4c/card_*.txt.
"""
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "card_pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docx import Document  # noqa: E402
from docx.enum.text import WD_BREAK  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

import card_template_docx as ctd  # noqa: E402
import card_template_layout as ctl  # noqa: E402
import card_template_sheet as cts  # noqa: E402
import card_template_cc_label as ctcc  # noqa: E402
import card_template_waybill as ctw  # noqa: E402
import generate_card_template as gct  # noqa: E402
from golden_support import check_golden, docx_summary  # noqa: E402

TEST_ID = "test_card_template_behaviour"
DEPENDS = "build_* in generate_card_template.py fed the frozen records in this test (no template, logo or photos)"
NO_FILE = Path("/nonexistent/w4c-fixture.png")


def no_images():
    """Patch every image path the card builders look at to a file that is not there."""
    return mock.patch.multiple(
        gct,
        LOGO=NO_FILE,
        ICON_ROAD_NAME=NO_FILE,
        ICON_ROAD_NUM=NO_FILE,
        ICON_DESC=NO_FILE,
    )


def fresh_cell():
    doc = Document()
    table = doc.add_table(rows=1, cols=1)
    return doc, table.rows[0].cells[0]


def fake_sheet(path: Path, cols: int = 3) -> Path:
    doc = Document()
    doc.add_paragraph("template intro")
    doc.add_table(rows=3, cols=cols)
    doc.save(path)
    return path


class GoldenCards(unittest.TestCase):
    def snapshot(self, name, builder, **kwargs):
        with no_images():
            doc, cell = fresh_cell()
            builder(cell, **kwargs)
        check_golden(self, name, docx_summary(cell._tc), depends_on=DEPENDS, test_id=TEST_ID)

    def test_equipment_card_mail_merge(self):
        self.snapshot("card_equipment_merge.txt", gct.build_card, advance_record=True, idx=3)

    def test_equipment_card_first_slot_has_no_next_field(self):
        with no_images():
            _, cell = fresh_cell()
            gct.build_card(cell, advance_record=False, idx=0)
        self.assertNotIn(" NEXT ", docx_summary(cell._tc))

    def test_equipment_card_filled_record(self):
        record = {"Type": "boxcar", "RoadName": "Test Road", "RoadNumber": "1234",
                  "Description": "50' plug door boxcar, red"}
        self.snapshot("card_equipment_record.txt", gct.build_card,
                      advance_record=False, idx=1, record=record)

    def test_equipment_card_blank_work_orders(self):
        record = {"Type": "work", "Blank": True, "Orders": ["Pick up 2 hoppers", "Set out 1 tank"]}
        self.snapshot("card_equipment_blank.txt", gct.build_card,
                      advance_record=False, idx=2, record=record)

    def test_waybill_inbound_loaded(self):
        record = {"Industry": "Test Industry A", "Flow": "IN", "Commodity": "Coal", "Spots": "1-2",
                  "CarType": "Hopper", "LoadSummary": "Coal", "RouteFrom": "Test Mine (Town, PA)",
                  "RouteChain": "CSX"}
        self.snapshot("card_waybill_in_loaded.txt", gct.build_waybill_card, idx=4, record=record)

    def test_waybill_outbound_loaded(self):
        record = {"Industry": "Test Industry A", "Flow": "OUT", "Commodity": "Plastic Resins",
                  "Spots": "5", "CarType": "Covered Hopper", "RouteTo": "Test Plant (Town, OH)",
                  "RouteChain": "POHC"}
        self.snapshot("card_waybill_out_loaded.txt", gct.build_waybill_card, idx=5, record=record)

    def test_waybill_interchange(self):
        record = {"Industry": "INTERCHANGE", "CardKind": "interchange", "Flow": "IN",
                  "Commodity": "Lumber", "Spots": "—", "CarType": "Flatcar",
                  "RouteFrom": "Test Mill (Town, ME)", "RouteTo": "Test Yard (City, NJ)",
                  "RouteChain": "CSX", "LoadSummary": "Lumber"}
        self.snapshot("card_waybill_interchange.txt", gct.build_waybill_card, idx=6, record=record)

    def test_waybill_inbound_empty(self):
        record = {"Industry": "Test Industry B", "CardKind": "inbound_empty", "Flow": "IN",
                  "Commodity": "EMPTY", "Spots": "3", "CarType": "Tank Car", "RouteChain": "POHC"}
        self.snapshot("card_waybill_in_empty.txt", gct.build_waybill_card, idx=7, record=record)

    def test_waybill_outbound_empty(self):
        record = {"Industry": "Test Industry B", "CardKind": "outbound_empty", "Flow": "OUT",
                  "Commodity": "EMPTY", "RouteTo": "Test Yard", "RouteChain": "CSX"}
        self.snapshot("card_waybill_out_empty.txt", gct.build_waybill_card, idx=8, record=record)

    def test_cc_waybill_freight(self):
        record = {"BillKind": "freight", "Color": "Red", "ToLocation": "Test Dock",
                  "Station": "Test Station, Chemical Unload", "Track": "Track 4", "Spot": "2",
                  "Consignment": "Chemicals", "CarCode": "T", "FromLocation": "Test Works",
                  "FromStation": "Test Origin (City, PA)", "ShipmentCode": "TST-001"}
        self.snapshot("card_cc_freight.txt", gct.build_cc_waybill_label, idx=0, record=record)

    def test_cc_waybill_empty_in_staging(self):
        record = {"BillKind": "empty", "Color": "unknown-colour", "ToLocation": "Test Yard",
                  "Track": "Staging", "Flow": "in", "CarCode": "XM", "Consignment": "Boxcar loads",
                  "Description": "Load at Test Works"}
        self.snapshot("card_cc_empty.txt", gct.build_cc_waybill_label, idx=1, record=record)


class TextHelpers(unittest.TestCase):
    def test_keep_address_together_uses_nbsp_inside_parentheses_only(self):
        self.assertEqual(
            ctd.keep_address_together("Dow (Midland, MI) plant"),
            "Dow (Midland, MI) plant",
        )
        self.assertEqual(ctd.keep_address_together(""), "")
        self.assertEqual(ctd.keep_address_together("plain text"), "plain text")

    def test_split_on_commas_ignores_commas_in_parentheses(self):
        self.assertEqual(
            ctd.split_on_commas("Aristech, Chemical Unload"), ["Aristech", "Chemical Unload"]
        )
        self.assertEqual(
            ctd.split_on_commas("Dow Chemical (Midland, MI)"), ["Dow Chemical (Midland, MI)"]
        )

    def test_split_on_commas_drops_empty_parts_and_handles_blank(self):
        self.assertEqual(ctd.split_on_commas(""), [])
        self.assertEqual(ctd.split_on_commas("a,, b ,"), ["a", "b"])
        self.assertEqual(ctd.split_on_commas(","), [","])

    def test_split_on_commas_survives_an_unbalanced_close_paren(self):
        self.assertEqual(ctd.split_on_commas("a), b"), ["a)", "b"])

    def test_via_interchange_label(self):
        self.assertEqual(ctw._via_interchange_label("CSX"), "Via CSX Interchange")
        self.assertEqual(ctw._via_interchange_label("POHC Interchange"), "Via POHC Interchange")
        self.assertEqual(ctw._via_interchange_label("via NS"), "via NS")
        self.assertEqual(ctw._via_interchange_label("  "), "")
        self.assertEqual(ctw._via_interchange_label(None), "")

    def test_write_label_lines_blank_gives_dash_and_many_lines_give_breaks(self):
        doc = Document()
        p = doc.add_paragraph()
        ctd.write_label_lines(p, [])
        self.assertEqual(p.text, "—")
        p2 = doc.add_paragraph()
        ctd.write_label_lines(p2, ["one", "two"], bold=True)
        self.assertEqual(p2.text, "one\ntwo")
        self.assertTrue(all(r.bold for r in p2.runs if r.text not in ("", "\n")))

    def test_text_sets_font_size_bold_and_colour(self):
        doc = Document()
        run = doc.add_paragraph().add_run()
        ctd.text(run, "hi", bold=True, size=9, color=(1, 2, 3))
        self.assertEqual(run.text, "hi")
        self.assertTrue(run.bold)
        self.assertEqual(run.font.size.pt, 9)
        self.assertEqual(str(run.font.color.rgb), "010203")

    def test_sts_colour_names_are_hex(self):
        for name, hex_ in ctcc.sts_color_hex().items():
            self.assertRegex(hex_, r"^[0-9A-F]{6}$", name)


class FieldHelpers(unittest.TestCase):
    def test_merge_field_writes_a_complex_field(self):
        doc = Document()
        p = doc.add_paragraph()
        ctd.merge_field(p, "RoadName", bold=True, size=9)
        xml = p._p.xml
        self.assertIn("MERGEFIELD RoadName", xml)
        self.assertIn("«RoadName»", xml)
        for kind in ("begin", "separate", "end"):
            self.assertIn(f'w:fldCharType="{kind}"', xml)

    def test_next_record_writes_a_next_field(self):
        doc = Document()
        p = doc.add_paragraph()
        ctd.next_record(p)
        self.assertIn(" NEXT ", p._p.xml)

    def test_linebreak_adds_a_break_run(self):
        doc = Document()
        p = doc.add_paragraph()
        ctd.linebreak(p)
        self.assertEqual(p.text, "\n")


class OoxmlHelpers(unittest.TestCase):
    def test_cell_helpers_set_attributes(self):
        _, cell = fresh_cell()
        ctd.shade(cell, "AABBCC")
        ctd.width(cell, 1234)
        ctd.pad(cell, top=1, left=2, bottom=3, right=4)
        ctd.pad(cell, top=9)  # a second pad replaces the first
        tc_pr = cell._tc.tcPr
        self.assertEqual(tc_pr.find(qn("w:shd")).get(qn("w:fill")), "AABBCC")
        self.assertEqual(tc_pr.find(qn("w:tcW")).get(qn("w:w")), "1234")
        mar = tc_pr.findall(qn("w:tcMar"))
        self.assertEqual(len(mar), 1)
        self.assertEqual(mar[0].find(qn("w:top")).get(qn("w:w")), "9")
        self.assertEqual(mar[0].find(qn("w:left")).get(qn("w:w")), "0")

    def test_row_h_is_exact(self):
        doc = Document()
        t = doc.add_table(rows=1, cols=1)
        ctd.row_h(t.rows[0], 321)
        ctd.row_h(t.rows[0], 400)
        h = t.rows[0]._tr.trPr.findall(qn("w:trHeight"))
        self.assertEqual(len(h), 1)
        self.assertEqual((h[0].get(qn("w:val")), h[0].get(qn("w:hRule"))), ("400", "exact"))

    def test_grid_replaces_the_table_grid(self):
        doc = Document()
        t = doc.add_table(rows=1, cols=2)
        ctd.grid(t, [100, 200, 300])
        cols = t._tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))
        self.assertEqual([c.get(qn("w:w")) for c in cols], ["100", "200", "300"])

    def test_table_widths(self):
        doc = Document()
        t = doc.add_table(rows=1, cols=1)
        ctd.tbl_width_pct(t, 80)
        self.assertEqual(t._tbl.tblPr.find(qn("w:tblW")).get(qn("w:w")), "4000")
        ctd.tbl_width_dxa(t, 3000, center=True)
        pr = t._tbl.tblPr
        self.assertEqual((pr.find(qn("w:tblW")).get(qn("w:w")), pr.find(qn("w:tblW")).get(qn("w:type"))),
                         ("3000", "dxa"))
        self.assertEqual(pr.find(qn("w:jc")).get(qn("w:val")), "center")
        t2 = doc.add_table(rows=1, cols=1)
        ctd.tbl_width_dxa(t2, 10, center=False)
        self.assertIsNone(t2._tbl.tblPr.find(qn("w:jc")))

    def test_borders_nil_for_zero_and_single_otherwise(self):
        doc = Document()
        t = doc.add_table(rows=1, cols=1)
        ctd.borders(t, outer=18, inner_h=0, color="112233")
        b = t._tbl.tblPr.find(qn("w:tblBorders"))
        self.assertEqual(b.find(qn("w:top")).get(qn("w:val")), "single")
        self.assertEqual(b.find(qn("w:top")).get(qn("w:color")), "112233")
        self.assertEqual(b.find(qn("w:insideH")).get(qn("w:val")), "nil")
        ctd.borders(t, outer=0)
        self.assertEqual(len(t._tbl.tblPr.findall(qn("w:tblBorders"))), 1)

    def test_cell_rules(self):
        _, cell = fresh_cell()
        ctd.bottom_rule(cell, size=4)
        b = cell._tc.tcPr.find(qn("w:tcBorders"))
        self.assertEqual(b.find(qn("w:bottom")).get(qn("w:val")), "single")
        self.assertEqual(b.find(qn("w:top")).get(qn("w:val")), "nil")
        ctd.box(cell)
        b = cell._tc.tcPr.find(qn("w:tcBorders"))
        self.assertEqual([e.get(qn("w:val")) for e in b], ["single"] * 4)
        ctd.hrule(cell)
        b = cell._tc.tcPr.find(qn("w:tcBorders"))
        vals = {e.tag.split("}")[1]: e.get(qn("w:val")) for e in b}
        self.assertEqual(vals, {"left": "nil", "right": "nil", "top": "single", "bottom": "single"})
        self.assertEqual(len(cell._tc.tcPr.findall(qn("w:tcBorders"))), 1)

    def test_add_round_frame_embeds_unique_z_index(self):
        doc = Document()
        p = doc.add_paragraph()
        ctd.add_round_frame(p, 7, width_pt=100, height_pt=200, left_pt=1.5, top_pt=2)
        xml = p._p.xml
        self.assertIn('id="cardframe7"', xml)
        self.assertIn("z-index:-251650007", xml)
        self.assertIn("width:100.00pt;height:200.00pt", xml)

    def test_tighten_cell_drops_empty_paragraphs_around_a_nested_table(self):
        _, cell = fresh_cell()
        cell.add_table(rows=1, cols=1)
        ctd.tighten_cell(cell)
        children = [c.tag for c in cell._tc if c.tag in (qn("w:p"), qn("w:tbl"))]
        self.assertEqual(children[-1], qn("w:p"))
        self.assertEqual(children.count(qn("w:tbl")), 1)
        spacing = cell._tc.findall(qn("w:p"))[-1].find(qn("w:pPr")).find(qn("w:spacing"))
        self.assertEqual(spacing.get(qn("w:line")), "20")

    def test_tighten_cell_leaves_a_cell_without_a_table_alone(self):
        _, cell = fresh_cell()
        before = cell._tc.xml
        ctd.tighten_cell(cell)
        self.assertEqual(cell._tc.xml, before)

    def test_minimize_cell_tail_only_shrinks_an_empty_last_paragraph(self):
        _, cell = fresh_cell()
        cell.add_table(rows=1, cols=1)
        ctd.minimize_cell_tail(cell)
        last = cell._tc.findall(qn("w:p"))[-1]
        self.assertEqual(last.find(qn("w:pPr")).find(qn("w:spacing")).get(qn("w:line")), "20")
        _, cell2 = fresh_cell()
        cell2.paragraphs[0].add_run("keep")
        before = cell2._tc.xml
        ctd.minimize_cell_tail(cell2)
        self.assertEqual(cell2._tc.xml, before)

    def test_tighten_revision_cell_sets_exact_line_and_zero_padding(self):
        _, cell = fresh_cell()
        cell.paragraphs[0].add_run("Rev A")
        cell.add_paragraph("")
        ctd.tighten_revision_cell(cell, 99)
        self.assertEqual(len(cell._tc.findall(qn("w:p"))), 1)
        sp = cell.paragraphs[0]._p.pPr.find(qn("w:spacing"))
        self.assertEqual((sp.get(qn("w:line")), sp.get(qn("w:lineRule"))), ("99", "exact"))


class SheetAssembly(unittest.TestCase):
    def test_page4_grid_finds_the_three_column_table(self):
        doc = Document()
        doc.add_table(rows=1, cols=2)
        three = doc.add_table(rows=1, cols=3)
        self.assertIs(cts._page4_grid(doc.element.body), three._tbl)

    def test_page4_grid_error_names_the_missing_table(self):
        doc = Document()
        doc.add_table(rows=1, cols=2)
        with self.assertRaisesRegex(ValueError, "page 4 sticker grid"):
            cts._page4_grid(doc.element.body)

    def test_keep_sticker_grid_keeps_only_the_grid_and_sets_margins(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Document(fake_sheet(Path(tmp) / "s.docx"))
        cts.keep_sticker_grid(doc)
        body = doc.element.body
        self.assertEqual(len(body.findall(qn("w:tbl"))), 1)
        self.assertEqual(len(body.findall(qn("w:p"))), 0)
        self.assertEqual(body[-1].tag, qn("w:sectPr"))
        sec = doc.sections[0]
        self.assertEqual(sec.top_margin.twips, ctl.PAGE_MAR_TOP)
        self.assertEqual(sec.left_margin.twips, ctl.PAGE_MAR_LEFT)
        self.assertEqual(sec.right_margin.twips, ctl.PAGE_MAR_RIGHT)
        self.assertEqual(sec.bottom_margin.twips, ctl.PAGE_MAR_BOTTOM)

    def test_keep_sticker_grid_without_a_three_column_table_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Document(fake_sheet(Path(tmp) / "s.docx", cols=2))
        with self.assertRaisesRegex(ValueError, "not found in template"):
            cts.keep_sticker_grid(doc)

    def test_strip_grid_guides_clears_cell_borders_and_style(self):
        doc = Document()
        t = doc.add_table(rows=2, cols=2, style="Table Grid")
        cts.strip_grid_guides(t)
        self.assertIsNone(t._tbl.tblPr.find(qn("w:tblStyle")))
        self.assertEqual(t._tbl.tblPr.find(qn("w:tblLook")).get(qn("w:val")), "0000")
        for row in t.rows:
            for cell in row.cells:
                b = cell._tc.tcPr.find(qn("w:tcBorders"))
                self.assertEqual({e.get(qn("w:val")) for e in b}, {"nil"})

    def test_sectpr_helpers(self):
        doc = Document()
        body = doc.element.body
        sect = body.find(qn("w:sectPr"))
        body.insert(0, sect)  # misplace it at the front
        cts.ensure_sect_pr_last(body)
        self.assertEqual(body[-1].tag, qn("w:sectPr"))
        marker = OxmlElement("w:p")
        cts.insert_before_sect(body, marker)
        self.assertIs(body[-1].getprevious(), marker)

    def test_add_document_tail_adds_one_minimal_paragraph_once(self):
        doc = Document()
        body = doc.element.body
        for p in list(body.findall(qn("w:p"))):
            body.remove(p)
        cts.add_document_tail(body)
        self.assertEqual(len(body.findall(qn("w:p"))), 1)
        cts.add_document_tail(body)
        self.assertEqual(len(body.findall(qn("w:p"))), 1)
        self.assertEqual(body[-1].tag, qn("w:sectPr"))

    def test_add_document_tail_removes_a_trailing_page_break(self):
        doc = Document()
        body = doc.element.body
        para = doc.add_paragraph()
        para.add_run().add_break(WD_BREAK.PAGE)
        self.assertTrue(body.findall(".//" + qn("w:br")))
        cts.add_document_tail(body)
        self.assertFalse(body.findall(".//" + qn("w:br")))


class MainEntryPoint(unittest.TestCase):
    def run_main(self, tmp: Path, sheet: Path):
        out = tmp / "out" / "template.docx"
        with mock.patch.object(gct, "require_sticker_sheet", lambda: sheet), \
                mock.patch.object(gct, "OUTPUT_DIR", out.parent), \
                mock.patch.object(gct, "OUTPUT", out), \
                mock.patch("builtins.print"), no_images():
            gct.main()
        return out

    def test_main_fills_nine_slots_and_only_the_first_has_no_next_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out = self.run_main(tmp, fake_sheet(tmp / "sheet.docx"))
            doc = Document(out)
        xml = doc.element.body.xml
        self.assertEqual(xml.count("MERGEFIELD Type"), 9)
        self.assertEqual(xml.count(" NEXT "), 8)
        self.assertEqual(len(ctl.CARD_SLOTS), 9)

    def test_main_golden_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out = self.run_main(tmp, fake_sheet(tmp / "sheet.docx"))
            summary = docx_summary(Document(out).element.body)
        check_golden(self, "card_template_main.txt", summary,
                     depends_on="main() in generate_card_template.py on a 3x3 stand-in sheet, no images",
                     test_id=TEST_ID)

    def test_main_stops_with_a_clear_message_when_the_sheet_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.docx"
            with mock.patch("car_paths.STICKER_SHEET", missing):
                with self.assertRaises(gct.car_paths.CardPipelineError) as cm:
                    gct.require_sticker_sheet()
        self.assertIn("Missing the sticker sheet template", str(cm.exception))
        self.assertIn("apostrophegames.com", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
