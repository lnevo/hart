"""The share-card recipes' pure parts: the bridge function found by name, the roster rows, the paperwork forms, the
composites' document steps and their errors."""
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_share_cards  # noqa: E402,F401  (loads the kit before the recipes, as the package does)
from share_card_recipes.editor_view import SHOWN_FUNCTION, function_lines, shown_lines  # noqa: E402
from share_card_recipes import CardError  # noqa: E402
from share_card_recipes.panel_image import ROSTER_ROWS, roster_rows  # noqa: E402
from share_card_recipes import composites, forms  # noqa: E402

SOURCE = """#include "x.h"
static bool helper(void);

/**
 * Map appearance name to aspect.
 */
static bool appearanceToLcosAspect(const char *name, byte *aspect_out) {
  if (name == NULL) {
    return false;
  }
  return true;
}

static bool helper(void) { return true; }
""".splitlines()


class FunctionLines(unittest.TestCase):
    def test_doc_comment_to_closing_brace(self) -> None:
        self.assertEqual(function_lines(SOURCE, SHOWN_FUNCTION), (4, 12))

    def test_lines_move_with_the_source(self) -> None:
        self.assertEqual(function_lines(["// new line", ""] + SOURCE, SHOWN_FUNCTION), (6, 14))

    def test_a_function_without_a_doc_comment_starts_at_its_definition(self) -> None:
        self.assertEqual(function_lines(SOURCE[6:], SHOWN_FUNCTION), (1, 6))

    def test_missing_function_is_a_card_error(self) -> None:
        with self.assertRaisesRegex(CardError, "0 times"):
            function_lines(SOURCE, "noSuchFunction")

    def test_unclosed_function_is_a_card_error(self) -> None:
        with self.assertRaisesRegex(CardError, "no closing brace"):
            function_lines(SOURCE[:9], SHOWN_FUNCTION)


class ShownLines(unittest.TestCase):
    def test_a_function_longer_than_the_code_area_is_cut_at_its_last_row(self):
        self.assertEqual(shown_lines(SOURCE, SHOWN_FUNCTION, rows=5), (4, 8))

    def test_a_function_that_fits_is_shown_whole(self):
        self.assertEqual(shown_lines(SOURCE, SHOWN_FUNCTION, rows=25), (4, 12))


class RosterRows(unittest.TestCase):
    def test_every_row_drawn_in_order(self) -> None:
        items = [{"kind": k, "publicName": n, "cp": "CP 1", "hardware": "<LCC>"} for k, n in ROSTER_ROWS]
        html = roster_rows(items)
        self.assertEqual(html.count("<tr>"), len(ROSTER_ROWS))
        self.assertIn("&lt;LCC&gt;", html)
        self.assertLess(html.index("Switch 1"), html.index("OS Switch 3"))

    def test_missing_rows_are_named(self) -> None:
        with self.assertRaisesRegex(CardError, "no signal Mast 2L, signal Mast 4RA"):
            roster_rows([{"kind": k, "publicName": n} for k, n in ROSTER_ROWS if k != "signal"])


class PaperworkForms(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        patch = mock.patch.object(forms, "PAPERWORK", self.dir)
        patch.start()
        self.addCleanup(patch.stop)

    def _write(self, text: str) -> None:
        (self.dir / "x.html").write_text(text, encoding="utf-8")

    def test_style_and_body_split_with_the_site_filled_in(self) -> None:
        self._write("<style>\nbody{a:1}\n.b{c:2}\n</style>\n<div>\n<img src=\"{site}play/x.svg\"></div>\n")
        self.assertEqual(forms.form("x", "http://s/www/"),
                         forms.Form('<div>\n<img src="http://s/www/play/x.svg"></div>', "body{a:1}\n.b{c:2}\n"))

    def test_a_missing_form_is_named(self) -> None:
        with self.assertRaisesRegex(CardError, "x: no form at"):
            forms.form("x", "")

    def test_a_form_without_its_style_block_first_is_a_card_error(self) -> None:
        for text in ("<div></div>\n", "<style>body{}</style>\n<div></div>\n",
                     "<style>\na{}\n</style>\n<style>\nb{}\n</style>\n<div></div>\n"):
            self._write(text)
            with self.subTest(text=text), self.assertRaisesRegex(CardError, "one <style> block"):
                forms.form("x", "")


class PaperworkCards(unittest.TestCase):
    def test_every_form_card_draws_its_own_page(self) -> None:
        drawn: dict[str, tuple[str, str]] = {}
        with mock.patch.object(make_share_cards, "draw", side_effect=lambda n, b, s: drawn.setdefault(n, (b, s))), \
                mock.patch.object(make_share_cards, "card", side_effect=lambda im: im), \
                mock.patch.object(make_share_cards, "_site", "http://s/www/"):
            for name, recipe in (("ap-exam", forms.ap_exam), ("ap-exam-run", forms.ap_exam_run),
                                 ("play-neville", forms.play_neville)):
                recipe()
                body, style = drawn[name]
                self.assertTrue(body.startswith('<div class="desk">'), name)
                self.assertIn("Special+Elite", style)
                self.assertNotIn("{site}", body)
        self.assertIn('src="http://s/www/play/neville.svg"', drawn["play-neville"][0])


class TrackPlanFigures(unittest.TestCase):
    FIG = '<div class="plan"><svg viewBox="0 0 200 100" role="img" aria-label="L">{}</svg></div>'

    def test_each_level_is_captioned_and_the_scale_bar_dropped(self) -> None:
        text = "".join(self.FIG.format(f'<path d="M{i}"/><line class="scale" x1="0"/>') for i in range(3))
        out = composites._plan_figures(text)
        self.assertEqual(out.count('style="width:880px"'), 3)
        self.assertNotIn("scale", out)
        self.assertLess(out.index("Staging"), out.index("Main level"))
        self.assertLess(out.index("Main level"), out.index("Upper level"))

    def test_a_missing_level_is_a_card_error(self) -> None:
        with self.assertRaisesRegex(CardError, "has 2 plan drawings"):
            composites._plan_figures(self.FIG.format("") * 2)


class SlideSwap(unittest.TestCase):
    def _deck(self, folder: Path, presentation: str) -> Path:
        doc = folder / "deck.pptx"
        with zipfile.ZipFile(doc, "w") as z:
            z.writestr("ppt/presentation.xml", presentation)
            z.writestr("ppt/slides/slide1.xml", "<one/>")
        return doc

    def test_the_first_two_slides_change_places(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            doc = self._deck(Path(tmp), '<p:sldIdLst><p:sldId id="1"/><p:sldId id="2"/><p:sldId id="3"/></p:sldIdLst>')
            composites._swap_first_slides(doc, Path(tmp) / "copy.pptx")
            with zipfile.ZipFile(Path(tmp) / "copy.pptx") as z:
                self.assertEqual(z.read("ppt/presentation.xml").decode(),
                                 '<p:sldIdLst><p:sldId id="2"/><p:sldId id="1"/><p:sldId id="3"/></p:sldIdLst>')
                self.assertEqual(z.read("ppt/slides/slide1.xml"), b"<one/>")

    def test_a_deck_of_one_slide_is_a_card_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            doc = self._deck(Path(tmp), '<p:sldIdLst><p:sldId id="1"/></p:sldIdLst>')
            with self.assertRaisesRegex(CardError, "1 slide ids"):
                composites._swap_first_slides(doc, Path(tmp) / "copy.pptx")

    def test_slides_apart_in_the_list_are_a_card_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            doc = self._deck(Path(tmp), '<p:sldIdLst><p:sldId id="1"/>\n<p:sldId id="2"/></p:sldIdLst>')
            with self.assertRaisesRegex(CardError, "side by side"):
                composites._swap_first_slides(doc, Path(tmp) / "copy.pptx")


class QuickLook(unittest.TestCase):
    def test_no_qlmanage_is_a_card_error(self) -> None:
        with mock.patch.object(composites.subprocess, "run", side_effect=FileNotFoundError("qlmanage")), \
                self.assertRaisesRegex(CardError, "crew-tt23: qlmanage not found"):
            composites._quicklook("crew-tt23", Path("deck.pptx"))

    def test_a_failed_drawing_names_the_document_and_the_error(self) -> None:
        fail = subprocess.CalledProcessError(1, ["qlmanage"], stderr=b"no generator\n")
        with mock.patch.object(composites.subprocess, "run", side_effect=fail), \
                self.assertRaisesRegex(CardError, "could not draw deck.pptx: no generator$"):
            composites._quicklook("crew-tt23", Path("deck.pptx"))


class Bands(unittest.TestCase):
    def test_a_band_keeps_the_card_shape(self) -> None:
        from PIL import Image
        im = Image.new("RGB", (2400, 3000))
        self.assertEqual(composites._top_band(im, 50).size, (2400, 1260))
        self.assertEqual(composites._top_band(im, 50, 84, 2316).size, (2232, 1172))


if __name__ == "__main__":
    unittest.main()
