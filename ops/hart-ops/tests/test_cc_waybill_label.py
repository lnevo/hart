"""card_pipeline/card_template_waybill.py: the CC/WB shipment label's rows and text choices."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "card_pipeline"))

from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

import card_template_waybill as ctw  # noqa: E402

NO = Path("/nonexistent/x.png")
IMAGES = ctw.CardImages(logo=NO, road_name=NO, road_num=NO, desc=NO)


def label(record: dict):
    doc = Document()
    cell = doc.add_table(rows=1, cols=1).rows[0].cells[0]
    ctw.build_cc_waybill_label(cell, idx=0, record=record, images=IMAGES)
    return cell


def row_heights(cell) -> list[int]:
    table = cell.tables[0]
    return [int(r._tr.trPr.find(qn("w:trHeight")).get(qn("w:val"))) for r in table.rows]


class TrackSpot(unittest.TestCase):
    def test_staging_flow_is_named(self) -> None:
        self.assertEqual(ctw._cc_track_spot({"Track": "Staging", "Flow": " in "}), "STAGING  ·  IN")

    def test_track_and_spot_join(self) -> None:
        self.assertEqual(ctw._cc_track_spot({"Track": "T4", "Spot": "2"}), "T4  ·  2")

    def test_one_of_them_or_a_dash(self) -> None:
        self.assertEqual(ctw._cc_track_spot({"Spot": "2"}), "2")
        self.assertEqual(ctw._cc_track_spot({"Track": "Staging"}), "Staging")
        self.assertEqual(ctw._cc_track_spot({}), "—")


class Fields(unittest.TestCase):
    def test_empty_bill_names_what_to_load(self) -> None:
        fields = ctw._cc_fields({"CarCode": "XM", "Description": "Load at A, then B"}, is_empty=True)
        self.assertEqual([f.label for f in fields], ["ASSIGNMENT", "CAR TYPE", "LOADS", "SHIPMENT"])
        self.assertEqual(fields[2].lines, ["—"])
        self.assertGreater(len(fields[3].lines), 1)

    def test_freight_bill_names_contents_and_origin(self) -> None:
        fields = ctw._cc_fields({"Consignment": "Coal"}, is_empty=False)
        self.assertEqual([f.label for f in fields], ["CONTENTS", "CAR TYPE", "FROM", "FROM STA."])
        self.assertEqual([f.lines for f in fields], [["Coal"], ["—"], ["—"], ["—"]])

    def test_value_size_steps_down_with_length(self) -> None:
        self.assertEqual(ctw._cc_value_size(["short"]), 7.5)
        self.assertEqual(ctw._cc_value_size(["x" * 19]), 6.5)
        self.assertEqual(ctw._cc_value_size(["x" * 20, "y" * 9]), 5.5)


class Rows(unittest.TestCase):
    def test_spacer_takes_what_the_frame_has_left(self) -> None:
        heights = row_heights(label({"BillKind": "freight", "Station": "One place"}))
        self.assertEqual(len(heights), 8)
        self.assertEqual(heights[2], ctw.CC_H_DEST)
        self.assertEqual(sum(heights), ctw.CC_FRAME_CONTENT_TWIPS)

    def test_wrapped_station_takes_the_taller_row_and_a_shorter_spacer(self) -> None:
        plain = row_heights(label({"Station": "One place"}))
        wrapped = row_heights(label({"Station": "Test Station, Chemical Unload"}))
        self.assertEqual(wrapped[2], ctw.CC_H_DEST_WRAPPED)
        self.assertEqual(plain[4] - wrapped[4], ctw.CC_H_DEST_WRAPPED - ctw.CC_H_DEST)

    def test_title_and_form_id(self) -> None:
        cell = label({"BillKind": "Empty"})
        all_text = "\n".join(p.text for t in cell.tables for row in t.rows for c in row.cells
                             for p in c.paragraphs)
        self.assertIn(ctw.CC_FORM_ID, all_text)
        nested = cell.tables[0].rows[0].cells[0].tables[0].rows[0].cells[1].tables[0]
        self.assertEqual(nested.rows[0].cells[0].text, "EMPTY")
        self.assertIn("HART", cell.tables[0].rows[0].cells[0].tables[0].rows[0].cells[0].text)


if __name__ == "__main__":
    unittest.main()
