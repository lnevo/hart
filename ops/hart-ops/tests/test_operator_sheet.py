"""Behaviour tests for card_pipeline/generate_operator_sheet.py: the spurs file it reads and the sheet it writes.

The sheet build reads the repo's spot_assignments.csv and logos; the spurs file is a copy written to a temporary
folder, so the tests run without the external/sts-helpers submodule. One test reads the real spurs file and skips
when the submodule is not checked out.
"""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "card_pipeline"))

from docx import Document  # noqa: E402

import generate_waybill_cards  # noqa: E402,F401  (loads the card pipeline siblings first)
import generate_operator_sheet as gos  # noqa: E402

SPURS_TEXT = """Calgon Carbon - 5 - Purple
Kosmos Cement - 5 - Pink
Ferrel Gas - 3 - Red

A Stucki Co - 3 - Green
Aristech Plastics - 7 - Yellow
Shenango Coke Works - 2 - Black
Nowhere Works - 1 - Chartreuse
"""


def body_text(path: Path) -> str:
    return "\n".join(el.text for el in Document(str(path)).element.body.iter() if el.tag.endswith("}t") and el.text)


class SpursTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def spurs(self, text: str = SPURS_TEXT) -> Path:
        path = self.tmp / "spurs"
        path.write_text(text, encoding="utf-8")
        return path

    def test_styles_come_back_for_each_known_colour(self):
        styles = gos.load_industry_styles(self.spurs())
        self.assertEqual(sorted(styles), sorted(gos.SHEET_INDUSTRY_ORDER))
        self.assertEqual(styles["Aristech Plastics"]["accent"], "FFD400")
        self.assertEqual(styles["Aristech Plastics"]["text"], "000000")
        self.assertEqual(styles["Calgon Carbon"]["logo"], "calgon.png")
        self.assertEqual(styles["Calgon Carbon"]["logo_width"], 2.05)

    def test_unknown_colour_is_skipped(self):
        self.assertNotIn("Nowhere Works", gos.load_industry_styles(self.spurs()))

    def test_industry_without_a_logo_gets_none(self):
        styles = gos.load_industry_styles(self.spurs("Test Works - 1 - Blue\n"))
        self.assertEqual(styles["Test Works"], {"accent": styles["Test Works"]["accent"], "text": "0000CD",
                                                "logo": None, "logo_width": 0.0})

    def test_missing_file_is_a_named_error(self):
        with self.assertRaises(gos.SpursFileMissingError) as caught:
            gos.load_industry_styles(self.tmp / "absent")
        self.assertIn("absent", str(caught.exception))
        self.assertIsInstance(caught.exception, gos.CardPipelineError)

    def test_line_with_one_dash_is_a_named_error(self):
        with self.assertRaises(gos.SpursLineError):
            gos.load_industry_styles(self.spurs("Calgon Carbon - Purple\n"))

    def test_spur_file_points_at_the_sts_helpers_seed(self):
        self.assertEqual(gos.SPUR_FILE.relative_to(gos.car_repo.HART_ROOT).as_posix(),
                         "external/sts-helpers/seed/inputs/spurs")

    @unittest.skipUnless(gos.SPUR_FILE.is_file(), "external/sts-helpers is not checked out")
    def test_real_spurs_file_gives_every_sheet_industry(self):
        styles = gos.load_industry_styles()
        for industry in gos.SHEET_INDUSTRY_ORDER:
            self.assertIn(industry, styles)

    def test_generate_writes_industry_and_yard_pages(self):
        out = self.tmp / "sheet.docx"
        pages = gos.generate(out, self.spurs())
        text = body_text(out)
        self.assertEqual(pages, len(gos.SHEET_INDUSTRY_ORDER) + len(gos.YARD_PAGES))
        for yard in gos.YARD_PAGES:
            self.assertIn(yard["title"], text)
        self.assertIn("No numbered spots.", text)
        self.assertIn("TRACKS & SPOTS", text)

    def test_generate_without_an_industry_colour_is_a_named_error(self):
        spurs = self.spurs(SPURS_TEXT.replace("Kosmos Cement - 5 - Pink\n", ""))
        with self.assertRaises(gos.IndustryColourMissingError) as caught:
            gos.generate(self.tmp / "sheet.docx", spurs)
        self.assertIn("Kosmos Cement", str(caught.exception))
        self.assertFalse((self.tmp / "sheet.docx").exists())


if __name__ == "__main__":
    unittest.main()
