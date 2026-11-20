"""Smoke tests: the card and publication scripts run their main path and write their files.

Each test runs a script's main() in this process with its output paths pointed at a temp
directory, so nothing is written into the checkout. The sticker sheet is Apostrophe's file
and is not in git, so a small stand-in (a 3x3 table) replaces it.
"""
import contextlib
import csv
import io
import sys
import tempfile
import unittest
import unittest.mock as mock
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "card_pipeline"))
sys.path.insert(0, str(HERE / "publications"))

from docx import Document  # noqa: E402

import apply_visual_review  # noqa: E402
import generate_card_template as gct  # noqa: E402
import generate_waybill_cards as gwc  # noqa: E402
import rebuild_local_station_maps as rlsm  # noqa: E402


def run_quietly(fn):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        fn()
    return out.getvalue()


def fake_sticker_sheet(path: Path) -> Path:
    doc = Document()
    doc.add_table(rows=3, cols=3)
    doc.save(path)
    return path


class CardTemplateSmoke(unittest.TestCase):
    def test_main_writes_the_template_docx(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sheet = fake_sticker_sheet(tmp / "sheet.docx")
            out = tmp / "out" / "template.docx"
            with mock.patch.object(gct, "STICKER_SHEET", sheet), \
                    mock.patch.object(gct, "require_sticker_sheet", lambda: sheet), \
                    mock.patch.object(gct, "OUTPUT_DIR", out.parent), \
                    mock.patch.object(gct, "OUTPUT", out):
                text = run_quietly(gct.main)
            self.assertTrue(out.is_file())
            self.assertIn("Wrote", text)
            Document(out)  # opens as a Word file


class WaybillSmoke(unittest.TestCase):
    def test_main_writes_waybill_docx_and_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sheet = fake_sticker_sheet(tmp / "sheet.docx")
            out = tmp / "out" / "waybills.docx"
            csv_out = tmp / "out" / "waybills.csv"
            out.parent.mkdir()
            with mock.patch.object(gct, "STICKER_SHEET", sheet), \
                    mock.patch.object(gct, "require_sticker_sheet", lambda: sheet), \
                    mock.patch.object(gwc, "OUTPUT_DIR", out.parent), \
                    mock.patch.object(gwc, "OUTPUT", out), \
                    mock.patch.object(gwc, "WAYBILL_CSV", csv_out):
                text = run_quietly(gwc.main)
            self.assertTrue(out.is_file())
            self.assertIn("Wrote", text)
            with csv_out.open(newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertTrue(rows)
            self.assertTrue(Document(out).tables)


class StationMapsSmoke(unittest.TestCase):
    def test_main_writes_a_png_and_docx_per_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            maps = [dict(m) for m in rlsm.MAPS]
            for m in maps:
                m["png"] = tmp / "assets" / m["png"].name
                m["docx"] = tmp / "docs" / m["docx"].name
            with mock.patch.object(rlsm, "MAPS", maps), \
                    mock.patch.object(rlsm, "ASSETS", tmp / "assets"), \
                    mock.patch.object(rlsm, "DOCS", tmp / "docs"):
                run_quietly(rlsm.main)
            drawn = [m for m in maps if not m.get("skip")]
            self.assertTrue(drawn)
            for m in drawn:
                self.assertTrue(m["png"].is_file(), m["png"])
                self.assertTrue(m["docx"].is_file(), m["docx"])


class VisualReviewSmoke(unittest.TestCase):
    def test_apply_review_rewrites_the_metadata_csv(self):
        source = next(iter(apply_visual_review.VISUAL))
        review = apply_visual_review.VISUAL[source]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            roster = tmp / "roster.xml"
            root = ET.Element("operations-config")
            cars = ET.SubElement(root, "cars")
            ET.SubElement(cars, "car", id=review.get("roster_id", "X1"), roadName="NW",
                          roadNumber="1", type="Flatcar", length="40", weight="1",
                          weightTons="2")
            ET.ElementTree(root).write(roster)
            meta = tmp / "image_metadata.csv"
            with meta.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=apply_visual_review.CSV_COLUMNS)
                w.writeheader()
                w.writerow({"source_image": source})
                w.writerow({"source_image": "unreviewed.png", "car_type": "Locomotive"})
            with mock.patch.object(apply_visual_review, "ROSTER_XML", roster), \
                    mock.patch.object(apply_visual_review, "METADATA_CSV", meta):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = apply_visual_review.main()
            self.assertEqual(code, 0)
            with meta.open(newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["match_confidence"], "visual_review")
            self.assertEqual(rows[1]["source_image"], "unreviewed.png")


if __name__ == "__main__":
    unittest.main()
