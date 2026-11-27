"""Behaviour tests for the shared OOXML helpers (publications/hart_ooxml.py), the master's destination colours
(crew_master.swatches) where the cards and publications read them, hart_pub_helpers and the waybill work lines."""
from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "card_pipeline"))
sys.path.insert(0, str(HERE / "publications"))

from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Inches  # noqa: E402
from PIL import Image  # noqa: E402

import card_template_cc_label as ctcc  # noqa: E402
import card_template_waybill as ctw  # noqa: E402
import crew_master  # noqa: E402
import hart_ooxml  # noqa: E402
import hart_pub_helpers as hph  # noqa: E402
import rebuild_operator_primer as primer  # noqa: E402

MASTER = crew_master.load()


def cell():
    return Document().add_table(rows=1, cols=1).rows[0].cells[0]


class Ooxml(unittest.TestCase):
    def test_shade_cell_keeps_each_attribute_order(self):
        c = cell()
        hart_ooxml.shade_cell(c, "AABBCC")
        hart_ooxml.shade_cell(c, "112233", auto_color=True)
        shd = c._tc.tcPr.findall(qn("w:shd"))
        self.assertEqual([a.split("}")[1] for a in shd[0].attrib], ["fill", "val"])
        self.assertEqual([a.split("}")[1] for a in shd[1].attrib], ["val", "color", "fill"])
        self.assertEqual(shd[1].get(qn("w:color")), "auto")

    def test_shade_cell_rejects_a_fill_that_is_not_rrggbb(self):
        with self.assertRaisesRegex(ValueError, "#FFC0CB"):
            hart_ooxml.shade_cell(cell(), "#FFC0CB")

    def test_set_cell_width_leaves_one_tcw(self):
        c = cell()
        c.width = Inches(0.52)          # python-docx writes its own tcW (749)
        hart_ooxml.set_cell_width(c, 748)
        widths = c._tc.tcPr.findall(qn("w:tcW"))
        self.assertEqual(len(widths), 1)
        self.assertEqual(widths[0].get(qn("w:w")), "748")
        self.assertEqual(widths[0].get(qn("w:type")), "dxa")

    def test_set_cell_margins_replaces_the_old_margins(self):
        c = cell()
        hart_ooxml.set_cell_margins(c, top=1, left=2, bottom=3, right=4)
        hart_ooxml.set_cell_margins(c, top=9)
        mars = c._tc.tcPr.findall(qn("w:tcMar"))
        self.assertEqual(len(mars), 1)
        self.assertEqual([(e.tag.split("}")[1], e.get(qn("w:w"))) for e in mars[0]],
                         [("top", "9"), ("left", "0"), ("bottom", "0"), ("right", "0")])

    def test_set_row_height_leaves_one_exact_height_in_whole_twips(self):
        row = Document().add_table(rows=1, cols=1).rows[0]
        hart_ooxml.set_row_height(row, 16)
        hart_ooxml.set_row_height(row, 17.33)
        heights = row._tr.trPr.findall(qn("w:trHeight"))
        self.assertEqual(len(heights), 1)
        self.assertEqual((heights[0].get(qn("w:val")), heights[0].get(qn("w:hRule"))), ("346", "exact"))

    def test_clear_table_borders_sets_six_nil_edges(self):
        t = Document().add_table(rows=1, cols=1)
        hart_ooxml.clear_table_borders(t)
        edges = t._tbl.tblPr.find(qn("w:tblBorders"))
        self.assertEqual([e.get(qn("w:val")) for e in edges], ["nil"] * 6)


class MasterColours(unittest.TestCase):
    def test_swatches_are_rrggbb_in_master_order(self):
        sw = crew_master.swatches(MASTER)
        self.assertEqual(list(sw), [c["id"] for c in MASTER["colors"]])
        self.assertEqual(sw["pink"].fill, "FFC0CB")
        self.assertEqual(sw["blue"].ink, "FFFFFF")

    def test_fill_hex_names_a_missing_colour(self):
        with self.assertRaisesRegex(KeyError, "no color 'mauve'"):
            crew_master.fill_hex(MASTER, "mauve")

    def test_cards_take_the_master_fill(self):
        sw = crew_master.swatches(MASTER)
        self.assertEqual(ctcc.sts_color_hex()["pink"], sw["pink"].fill)
        self.assertEqual(ctcc.sts_color_hex()["mediumblue"], sw["blue"].fill)
        self.assertEqual(ctcc.sts_color_hex()["white"], "FFFFFF")      # STS-only

    def test_primer_legend_is_the_master_colours(self):
        sw = crew_master.swatches(MASTER)
        self.assertEqual([(r[0], r[1], r[2], r[3]) for r in primer.BLOCK_LEGEND],
                         [(s.label, s.fill, s.ink, s.dest) for s in sw.values()])


class PubHelpers(unittest.TestCase):
    def test_import_reads_no_file(self):
        hph._master.cache_clear()
        with mock.patch.object(crew_master, "load", side_effect=AssertionError("read at import")):
            importlib.reload(hph)
        hph._master.cache_clear()

    def map_png(self, tmp: Path) -> Path:
        path = tmp / "map.png"
        Image.new("RGB", (20, 50), "white").save(path)
        return path

    def test_back_page_cells_have_one_width_and_one_lead_pad(self):
        doc = Document()
        with tempfile.TemporaryDirectory() as tmp:
            hph.add_diagram_and_timetable_page(doc, map_path=self.map_png(Path(tmp)))
        for tc in doc.element.body.iter(qn("w:tc")):
            self.assertLessEqual(len(tc.tcPr.findall(qn("w:tcW"))), 1)
        lead = doc.paragraphs[0]
        self.assertEqual(lead.paragraph_format.space_before.pt, 12)
        self.assertIsNotNone(lead._p.pPr.find(qn("w:pageBreakBefore")))
        rows = crew_master.tt23_rows(MASTER)
        self.assertEqual(len(doc.tables[0].rows[0].cells[1].tables[0].rows), 1 + len(rows))

    def test_back_page_without_the_map_names_it(self):
        with self.assertRaisesRegex(FileNotFoundError, "nope.png"):
            hph.add_diagram_and_timetable_page(Document(), map_path="/nonexistent/nope.png")

    def test_pinned_color_key_floats_to_the_page_bottom(self):
        doc = Document()
        hph.add_abridged_color_key(doc, pin_to_bottom=True, compact=True, page_height_in=8.0)
        tbl_pr = doc.tables[0]._tbl.tblPr
        tblp = tbl_pr.find(qn("w:tblpPr"))
        expected = int((8.0 - 0.42 - hph.abridged_color_key_height_in(compact=True)) * 1440)
        self.assertEqual(tblp.get(qn("w:tblpY")), str(expected))
        self.assertEqual(tbl_pr.find(qn("w:tblOverlap")).get(qn("w:val")), "never")
        island = crew_master.color_key(MASTER)[1]
        self.assertEqual(len(doc.tables[0].rows), 2 + len(island))


    def test_missing_map_is_a_publication_asset_error(self):
        with self.assertRaises(hph.PublicationAssetError):
            hph.add_station_map_page(Document(), map_path="/nonexistent/nope.png")

    def test_unpinned_color_key_has_a_heading_and_every_swatch(self):
        doc = Document()
        hph.add_abridged_color_key(doc, heading="Colors")
        self.assertEqual(doc.paragraphs[0].text, "COLORS")
        offline, island = crew_master.color_key(MASTER)
        table = doc.tables[0]
        self.assertEqual(len(table.rows), 1 + len(island))
        fills = [[shd.get(qn("w:fill")) for shd in row.cells[0]._tc.tcPr.findall(qn("w:shd"))][-1]
                 for row in table.rows[1:1 + len(offline)]]
        self.assertEqual(fills, [fill for fill, _ in offline])
        self.assertEqual([row.cells[3].text for row in table.rows[1:]], [dest for _, dest in island])

    def test_more_interchange_than_island_colours_is_refused(self):
        groups = ([("FF0000", "A"), ("00FF00", "B")], [("0000FF", "C")])
        with mock.patch.object(crew_master, "color_key", lambda m: groups):
            with self.assertRaisesRegex(hph.ColorKeyError, "2 interchange colours and 1 island"):
                hph.add_abridged_color_key(Document())


class WorkLines(unittest.TestCase):
    def lines(self, **kw):
        base = dict(commodity="Cement", route_from="", route_to="", route_chain="", flow="IN",
                    is_interchange=False, is_outbound_empty=False, is_inbound_empty=False)
        return ctw._work_lines(**{**base, **kw})

    def test_outbound_empty_returns_to_its_yard_then_via(self):
        out = self.lines(is_outbound_empty=True, route_to="Scully Yard", route_chain="CSX")
        self.assertEqual([(w.kind, w.text) for w in out],
                         [("line", "Return to Scully Yard"), ("gap", ""), ("line", "Via CSX Interchange")])

    def test_outbound_empty_without_a_yard_returns_to_interchange(self):
        self.assertEqual(self.lines(is_outbound_empty=True)[0].text, "Return to Interchange")

    def test_inbound_empty_is_an_empty_load(self):
        out = self.lines(is_inbound_empty=True)
        self.assertEqual(out, [ctw.WorkLine("load", ctw.EMPTY, ctw.LOAD_SIZE_EMPTY, True, ctw.VALUE_CLR)])

    def test_long_route_takes_the_small_size(self):
        out = self.lines(route_from="X" * 37)
        self.assertEqual(out[2].size, ctw.ROUTE_SIZE_LONG)
        self.assertEqual(self.lines(route_from="Short")[2].size, ctw.ROUTE_SIZE)


if __name__ == "__main__":
    unittest.main()
