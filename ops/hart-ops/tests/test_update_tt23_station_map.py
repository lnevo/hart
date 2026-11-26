"""publications/update_tt23_station_map.py on a small stand-in deck (the real deck is never touched)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "publications"))

from PIL import Image  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE  # noqa: E402
from pptx.util import Inches  # noqa: E402

import update_tt23_station_map as tt23  # noqa: E402


def textbox(slide, text: str, left: float, top: float) -> None:
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(2.0), Inches(0.3))
    box.text_frame.text = text


def stand_in_deck(path: Path) -> Path:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(11), Inches(8.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    textbox(slide, "Publication TT-23", 0.5, 7.6)
    textbox(slide, "Revision A", 0.5, 7.8)
    textbox(slide, "Official Publication", 0.5, 8.0)
    textbox(slide, "Old map title", 0.5, 0.5)  # left-panel chrome: removed
    textbox(slide, "Timetable", 4.0, 0.5)  # right of the panel: kept
    slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.4), Inches(7.5), Inches(2.73), Inches(0.02))
    prs.save(str(path))
    return path


def texts(slide) -> list[str]:
    return [t for sh in slide.shapes if (t := tt23._shape_text(sh))]


class UpdateDeck(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.png = self.tmp / "panel.png"
        Image.new("RGB", (8, 12), "white").save(self.png)
        patcher = mock.patch.object(tt23, "_render_panel_png", return_value=self.png)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_left_panel_gets_the_map_and_a_compact_footer(self) -> None:
        deck = stand_in_deck(self.tmp / "tt23.pptx")
        with mock.patch("builtins.print"):
            tt23.update_pptx(deck, archive_original=False)
        slide = Presentation(str(deck)).slides[0]
        self.assertEqual(sorted(texts(slide)), sorted([tt23.PUB_REV_LINE, tt23.OFFICIAL_LINE, "Timetable"]))
        by_text = {tt23._shape_text(sh): sh for sh in slide.shapes if sh.has_text_frame}
        self.assertAlmostEqual(by_text[tt23.PUB_REV_LINE].top / tt23.EMU, 8.00, places=3)
        self.assertAlmostEqual(by_text[tt23.OFFICIAL_LINE].top / tt23.EMU, 8.18, places=3)
        self.assertTrue(by_text[tt23.OFFICIAL_LINE].text_frame.paragraphs[0].runs[0].font.bold)
        rules = [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]
        self.assertEqual(len(rules), 1)
        self.assertAlmostEqual(rules[0].top / tt23.EMU, tt23.FOOTER_BAND_TOP, places=3)
        pictures = [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.PICTURE]
        self.assertEqual(len(pictures), 1)
        self.assertAlmostEqual(pictures[0].width / tt23.EMU, tt23.SLOT_W, places=3)

    def test_missing_deck_is_named(self) -> None:
        with self.assertRaisesRegex(tt23.TT23Missing, "nope.pptx: the TT-23 deck is missing"):
            tt23.update_pptx(self.tmp / "nope.pptx")

    def test_missing_original_map_stops_after_the_backup(self) -> None:
        deck = stand_in_deck(self.tmp / "tt23.pptx")
        backup = self.tmp / "backup.pptx"
        with mock.patch.object(tt23, "BACKUP_PPTX", backup), \
                mock.patch.object(tt23, "ORIG_MAP", self.tmp / "orig.png"), \
                mock.patch.object(tt23, "ASSETS", self.tmp):
            with self.assertRaisesRegex(tt23.TT23Missing, "orig.png missing"):
                tt23.update_pptx(deck)
        self.assertTrue(backup.exists())

    def test_main_exits_1_with_the_message(self) -> None:
        with mock.patch.object(tt23, "update_pptx", side_effect=tt23.TT23Missing("x.pptx: gone")), \
                mock.patch("sys.stderr") as err:
            with self.assertRaises(SystemExit) as caught:
                tt23.main()
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("x.pptx: gone", "".join(c.args[0] for c in err.write.call_args_list))


class ShapeText(unittest.TestCase):
    def test_set_shape_text_keeps_one_run_and_blanks_the_rest(self) -> None:
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(0, 0, Inches(1), Inches(1))
        para = box.text_frame.paragraphs[0]
        para.add_run().text = "Publication "
        para.add_run().text = "TT-23"
        box.text_frame.add_paragraph().add_run().text = "extra"
        tt23._set_shape_text(box, "New")
        self.assertEqual(tt23._shape_text(box), "New")


if __name__ == "__main__":
    unittest.main()
