"""Behaviour tests for the station map renderers in ops/station_maps/scripts (Barn, Shenango,
South Yard) and the ring compasses they draw through station_compass.draw_sheet_compass.

The checks read pixels where the drawing puts track, frogs and needles; those do not depend
on which fonts are installed. Fonts come from sheet_kit, which warns and uses the PIL default
when the Mac fonts are absent; the warnings are swallowed here.
"""
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw, ImageFont

HART = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(HART / "ops/station_maps/scripts"))
sys.path.insert(0, str(HART / "ops/hart-ops/publications"))

import pub_fonts  # noqa: E402
import render_barn_station_map as barn  # noqa: E402
import render_shenango_station_map as shenango  # noqa: E402
import render_south_yard_station_map as south_yard  # noqa: E402
import sheet_kit  # noqa: E402
import station_compass  # noqa: E402

WHITE = (255, 255, 255)


def quiet() -> mock._patch:
    """Swallow the renderers' 'wrote ...' lines and font warnings."""
    return mock.patch.multiple(sys, stdout=io.StringIO(), stderr=io.StringIO())


def px(img: Image.Image, pt: tuple[float, float]) -> tuple[int, int, int]:
    return img.getpixel((round(pt[0]), round(pt[1])))


def default_font(path: str, size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default()


class SheetCompass(unittest.TestCase):
    def draw(self, style: str, turned: bool = False) -> Image.Image:
        img = Image.new("RGB", (300, 300), WHITE)
        station_compass.draw_sheet_compass(ImageDraw.Draw(img), 150, 150, 74, style=style,  # type: ignore[arg-type]
                                           turned=turned, load_font=default_font)
        return img

    def test_kite_points_gold_north_up(self) -> None:
        img = self.draw("kite")
        self.assertEqual(img.getpixel((150, 100)), station_compass.SHEET_GOLD)
        self.assertEqual(img.getpixel((150, 200)), station_compass.KITE_SOUTH)

    def test_split_needle_turns_with_the_plan(self) -> None:
        upright, turned = self.draw("split"), self.draw("split", turned=True)
        # East of the needle's spine, 30 px from the centre: gold above when upright, below when turned.
        self.assertEqual(upright.getpixel((153, 120)), station_compass.SHEET_GOLD)
        self.assertEqual(upright.getpixel((153, 180)), station_compass.SPLIT_SOUTH_D)
        self.assertEqual(turned.getpixel((153, 180)), station_compass.SHEET_GOLD)
        self.assertEqual(turned.getpixel((147, 180)), station_compass.SPLIT_GOLD_D)
        self.assertEqual(upright.getpixel((150, 150)), station_compass.SPLIT_RING)

    def test_letters_come_from_the_hook_in_arial_bold(self) -> None:
        sizes: list[tuple[str, int]] = []

        def loader(path: str, size: int) -> ImageFont.ImageFont:
            sizes.append((path, size))
            return ImageFont.load_default()

        d = ImageDraw.Draw(Image.new("RGB", (300, 300), WHITE))
        station_compass.draw_sheet_compass(d, 150, 150, 50, style="kite", load_font=loader)
        station_compass.draw_sheet_compass(d, 150, 150, 74, style="split", load_font=loader)
        self.assertEqual(sizes, [(pub_fonts.ARIAL_BOLD, station_compass.KITE_LETTER_PX),
                                 (pub_fonts.ARIAL_BOLD, station_compass.SPLIT_LETTER_PX)])

    def test_kite_has_no_turned_form_and_styles_are_checked(self) -> None:
        d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        with self.assertRaises(ValueError):
            station_compass.draw_sheet_compass(d, 5, 5, 4, style="kite", turned=True, load_font=default_font)
        with self.assertRaises(ValueError) as cm:
            station_compass.draw_sheet_compass(d, 5, 5, 4, style="rose", load_font=default_font)  # type: ignore[arg-type]
        self.assertIn("rose", str(cm.exception))


class SheetKitLoadFont(unittest.TestCase):
    def test_looks_up_the_file_name_in_the_sheet_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sheet_kit, "SANS_DIRS", (Path(tmp),)), \
                    mock.patch.object(sheet_kit, "find_font", return_value=None) as find, quiet():
                sheet_kit.load_font("/elsewhere/Arial Bold.ttf", 14)
        find.assert_called_once_with(["Arial Bold.ttf", "Arial.ttf"], 14, (Path(tmp),))

    def test_bold_missing_falls_back_to_arial_regular(self) -> None:
        regular = object()
        with mock.patch.object(sheet_kit, "find_font",
                               side_effect=lambda names, size, dirs: regular if "Arial.ttf" in names else None):
            self.assertIs(sheet_kit.load_font("/x/Arial Bold.ttf", 14), regular)

    def test_regular_is_looked_up_once(self) -> None:
        with mock.patch.object(sheet_kit, "find_font", return_value=None) as find, quiet():
            sheet_kit.load_font("/x/Arial.ttf", 14)
        self.assertEqual(find.call_args.args[0], ["Arial.ttf"])

    def test_missing_font_warns_with_the_name(self) -> None:
        err = io.StringIO()
        with mock.patch.object(sheet_kit, "SANS_DIRS", ()), mock.patch.object(sys, "stderr", err):
            font = sheet_kit.load_font("/x/Arial Bold.ttf", 14)
        self.assertIn("Arial Bold.ttf", err.getvalue())
        self.assertTrue(hasattr(font, "getbbox"))


class Barn(unittest.TestCase):
    def test_plan_geometry_follows_the_one_slope(self) -> None:
        self.assertEqual(barn.SW7_BOT[1], barn.Y_MAIN)
        self.assertAlmostEqual(barn.SW7_BOT[0] - barn.SW7_TOP[0], (barn.Y_MAIN - barn.Y_BARN) * barn.RUN / barn.RISE)
        self.assertEqual(barn.SW7_MID, ((barn.SW7_TOP[0] + barn.SW7_BOT[0]) / 2, (barn.Y_BARN + barn.Y_MAIN) / 2))
        self.assertAlmostEqual(barn.SW11[1], barn.Y_EH3)
        self.assertAlmostEqual(barn.EH1_JOIN[1], barn.Y_EH1)
        self.assertAlmostEqual(barn.EH2_JOIN[1], barn.Y_EH2)
        self.assertEqual(sorted(b.number for b in barn.BADGES), ["11", "13", "7", "9"])

    def test_render_draws_frogs_track_and_compass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sub" / "barn.png"
            with quiet():
                barn.render(out)
            img = Image.open(out).convert("RGB")
        self.assertEqual(img.size, (sheet_kit.W, sheet_kit.H))
        for frog in barn.FROGS:
            self.assertEqual(px(img, frog), sheet_kit.TRACK, frog)
        # A rail between frogs, and blank sheet between Barn and the EH tracks.
        self.assertEqual(px(img, (barn.X_EAST - 40, barn.Y_MAIN)), sheet_kit.TRACK)
        self.assertEqual(px(img, (7.3 * barn.IN, (barn.Y_EH3 + barn.Y_BARN) / 2)), WHITE)
        cx, cy, r = barn.COMPASS
        self.assertEqual(px(img, (cx, cy - r / 2)), station_compass.SHEET_GOLD)

    def test_docx_takes_the_west_yard_template_with_the_barn_title(self) -> None:
        with mock.patch.object(sheet_kit, "write_sheet_docx") as write, quiet():
            barn._write_docx(Path("m.png"), Path("d.docx"))
        args, kw = write.call_args
        self.assertEqual(args, (barn.DOCX_TEMPLATE, Path("m.png"), Path("d.docx")))
        self.assertEqual(kw["media_names"], ("station_map_west_yard.png", "station_map_barn.png"))
        self.assertIn("Barn", kw["title"])

    def test_main_stops_with_the_template_name_when_it_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(barn, "render"), mock.patch.object(barn, "HOPS", root), \
                    mock.patch.object(barn, "ROOT", root), \
                    mock.patch.object(barn, "DOCX_TEMPLATE", root / "none.docx"):
                with self.assertRaises(SystemExit) as cm:
                    barn.main()
            self.assertIn(str(root / "none.docx"), str(cm.exception))
            self.assertIsInstance(cm.exception.__cause__, sheet_kit.SheetTemplateMissing)


class Shenango(unittest.TestCase):
    def render(self, rotated: bool) -> Image.Image:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "s.png"
            with quiet():
                shenango.render(out, rotated)
            return Image.open(out).convert("RGB")

    def test_turn_maps_plan_points_about_the_plan_centre(self) -> None:
        d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        with quiet():
            upright, turned = shenango.Sheet(d, False), shenango.Sheet(d, True)
        self.assertEqual(upright.at((578, 405)), (578, 405))
        self.assertEqual(turned.at((578, 405)), (sheet_kit.W - 578, shenango.CY - 405))

    def test_both_sheets_put_frogs_where_the_turn_says(self) -> None:
        upright, turned = self.render(False), self.render(True)
        frogs = shenango.X_113 + [(shenango.X_SW115, shenango.Y_W), (shenango.X_SW115, shenango.Y_E)]
        for x, y in frogs:
            self.assertEqual(upright.getpixel((x, y)), sheet_kit.TRACK, (x, y))
            self.assertEqual(turned.getpixel((sheet_kit.W - x, shenango.CY - y)), sheet_kit.TRACK, (x, y))
        self.assertNotEqual(upright.tobytes(), turned.tobytes())

    def test_compass_moves_and_turns_with_the_plan(self) -> None:
        upright, turned = self.render(False), self.render(True)
        y = shenango.COMPASS_Y
        self.assertEqual(upright.getpixel((shenango.COMPASS_X + 3, y - 30)), station_compass.SHEET_GOLD)
        self.assertEqual(turned.getpixel((shenango.COMPASS_X_ROT + 3, y + 30)), station_compass.SHEET_GOLD)

    def test_docx_title_says_rotated_for_the_rotated_sheet(self) -> None:
        with mock.patch.object(sheet_kit, "write_sheet_docx") as write, quiet():
            shenango._write_docx(Path("m.png"), Path("X_Rotated.docx"), "station_map_shenango_rotated.png")
            shenango._write_docx(Path("m.png"), Path("X.docx"), "station_map_shenango.png")
        titles = [c.kwargs["title"] for c in write.call_args_list]
        self.assertTrue(titles[0].endswith("(rotated)"))
        self.assertFalse(titles[1].endswith("(rotated)"))


class SouthYard(unittest.TestCase):
    def test_missing_source_sheet_is_a_named_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "none.png", Path(tmp) / "out.png"
            with self.assertRaises(south_yard.SourceSheetMissing) as cm:
                south_yard.render(out, src)
            self.assertIn(str(src), str(cm.exception))
            self.assertFalse(out.exists())

    def test_render_covers_the_old_marks_and_stamps_the_switches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "sheet.png", Path(tmp) / "out.png"
            Image.new("RGB", (sheet_kit.W, sheet_kit.H), (200, 0, 0)).save(src)
            with quiet():
                south_yard.render(out, src)
            img = Image.open(out).convert("RGB")
        for frog in south_yard.FROGS:
            self.assertEqual(px(img, frog), sheet_kit.TRACK, frog)
        x, y, w, h = south_yard.OLD_LABELS[1]  # the old Barn label, clear of the new marks
        self.assertEqual(img.getpixel((x + w + south_yard.PAD_LABEL - 1, y + h)), WHITE)
        self.assertEqual(img.getpixel((south_yard.TRACK_NAME_COVER_X[1], south_yard.TRACK_NAMES[0][0])), WHITE)
        self.assertEqual(img.getpixel((5, 5)), (200, 0, 0))  # the rest of the sheet is untouched


if __name__ == "__main__":
    unittest.main()
