"""The drawn share thumbnails: every recipe has a card entry, and the pure drawing helpers hold."""
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import make_share_cards as gen  # noqa: E402
import share_cards  # noqa: E402


class Recipes(unittest.TestCase):
    def test_every_recipe_builds_an_image_some_page_uses(self):
        entries = [*share_cards.load().values(), *share_cards.load_links().values()]
        used = {Path(card["image"]).stem for card in entries}
        self.assertEqual(sorted(set(gen.CARDS) - used), [])

    def test_every_recipe_says_which_card_it_makes(self):
        for name, fn in gen.CARDS.items():
            self.assertTrue(fn.__doc__.strip().startswith(name + ":"), name)

    def test_captured_sources_are_in_the_repo(self):
        for name in ("panel-frame.png", "track-scale-weighed.png"):
            self.assertTrue((gen.SOURCES / name).is_file(), name)


class Drawing(unittest.TestCase):
    def _sheet(self, *rows):
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (400, 300), "white")
        for y in rows:
            ImageDraw.Draw(im).rectangle((100, y, 300, y + 3), fill="black")
        return im

    def test_station_crop_keeps_a_drawing_clear_of_the_window(self):
        out = gen._crop_drawing(self._sheet(120, 160), (0, 50, 400, 250), "sheet", pad=10)
        self.assertEqual(out.size, (221, 64))

    def test_station_crop_stops_when_a_heading_reaches_the_window_top(self):
        with self.assertRaises(SystemExit):
            gen._crop_drawing(self._sheet(52, 120), (0, 50, 400, 250), "sheet")

    def test_station_crop_stops_when_the_drawing_runs_past_the_window_bottom(self):
        with self.assertRaises(SystemExit):
            gen._crop_drawing(self._sheet(120, 248), (0, 50, 400, 250), "sheet")

    def test_station_crop_stops_on_a_blank_window(self):
        with self.assertRaises(SystemExit):
            gen._crop_drawing(self._sheet(), (0, 50, 400, 250), "sheet")

    def test_route_map_names_every_station_in_the_plan(self):
        svg = gen._jfn_svg()
        for name in ("West Staging", "Carrow", "Brae", "Dunmere", "Ferris Junction", "Linden", "East Staging",
                     "Hollis Mill", "Oakhaven", "Pell Creek", "Northwood", "Sawyer", "Kessock", "Fiddle"):
            self.assertIn(">" + name + "<", svg)

    def test_code_colouring_keeps_a_pointer_assignment_as_code(self):
        self.assertIn("<span class=c>", gen._highlight(" * Red→Stop"))
        line = gen._highlight("    *aspect_out = (byte)SIGNAL_STOP;")
        self.assertNotIn("<span class=c>", line)
        self.assertIn("<span class=K>SIGNAL_STOP</span>", line)

    def test_code_colouring_escapes_markup(self):
        self.assertIn("&lt;", gen._highlight("if (a < b) {"))


if __name__ == "__main__":
    unittest.main()
