"""The drawn share thumbnails: every recipe has a card entry, and the pure drawing helpers hold."""
import io
import sys
import unittest
from unittest import mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import make_share_cards as gen  # noqa: E402
import share_cards  # noqa: E402
from share_card_recipes import CardError  # noqa: E402


class Recipes(unittest.TestCase):
    def test_every_recipe_builds_an_image_some_page_uses(self):
        entries = [*share_cards.load().values(), *share_cards.load_links().values()]
        used = {Path(card["image"]).stem for card in entries}
        self.assertEqual(sorted(set(gen.CARDS) - used), [])

    def test_every_recipe_says_which_card_it_makes(self):
        for name, fn in gen.CARDS.items():
            self.assertTrue(fn.__doc__.strip().startswith(name + ":"), name)

    def test_a_recipe_module_imported_first_loads(self):
        # review of the split: the recipes and make_share_cards import each other; the package loads it first
        import subprocess
        for mod in ("composites", "page_figures"):
            done = subprocess.run([sys.executable, "-c", f"import share_card_recipes.{mod}, make_share_cards as k; "
                                   "print(len(k.CARDS))"], cwd=SCRIPTS, capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stdout.strip()), (0, str(len(gen.CARDS))), done.stderr)

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
        with self.assertRaises(CardError):
            gen._crop_drawing(self._sheet(52, 120), (0, 50, 400, 250), "sheet")

    def test_station_crop_stops_when_the_drawing_runs_past_the_window_bottom(self):
        with self.assertRaises(CardError):
            gen._crop_drawing(self._sheet(120, 248), (0, 50, 400, 250), "sheet")

    def test_station_crop_stops_on_a_blank_window(self):
        with self.assertRaises(CardError):
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


class ExamRunTitleTest(unittest.TestCase):
    def test_shot_passes_extra_flags_to_chrome(self):
        with mock.patch.object(gen, "_chrome", return_value="chrome"), \
                mock.patch.object(gen.subprocess, "run") as run, \
                mock.patch.object(gen, "_tmp", Path("/tmp")), \
                mock.patch("PIL.Image.open"):
            gen.shot("file:///x.html", flags=("--force-prefers-reduced-motion",))
        cmd = run.call_args.args[0]
        self.assertIn("--force-prefers-reduced-motion", cmd)
        self.assertEqual(cmd[-1], "file:///x.html")

    def test_title_capture_fills_the_frame_with_the_canvas_and_stills_the_train(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(gen, "_tmp", Path(tmp)), \
                mock.patch.object(gen, "shot", return_value="im") as shot, \
                mock.patch.object(gen, "card", side_effect=lambda im: im):
            self.assertEqual(gen.link_exam_run_title(), "im")
            html = (Path(tmp) / "link-exam-run-title.html").read_text(encoding="utf-8")
        self.assertIn('<base href="', html)
        self.assertIn(f"#xwTitleCv{{position:fixed!important;left:0!important;top:0!important;width:{gen.W}px", html)
        self.assertEqual(shot.call_args.kwargs["flags"], ("--force-prefers-reduced-motion",))

    def test_play_title_capture_loads_the_play_page_from_its_own_folder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(gen, "_tmp", Path(tmp)), \
                mock.patch.object(gen, "shot", return_value="im") as shot, \
                mock.patch.object(gen, "card", side_effect=lambda im: im):
            self.assertEqual(gen.link_play_title(), "im")
            html = (Path(tmp) / "link-play-title.html").read_text(encoding="utf-8")
        self.assertIn(f'<base href="{(gen.PORTAL / "play").as_uri()}/">', html)
        self.assertIn('src="title-art.js"', html)
        self.assertIn("#xwTitleCv{position:fixed!important", html)
        self.assertEqual(shot.call_args.kwargs["flags"], ("--force-prefers-reduced-motion",))

    def test_title_capture_stops_when_the_head_tag_changes(self):
        with mock.patch.object(gen.Path, "read_text", return_value="<html><head lang=en></head></html>"):
            with self.assertRaises(CardError):
                gen.link_exam_run_title()


class BuiltViews(unittest.TestCase):
    """review of #1151: a page shot reads the files the site build makes (ADR-036) as built now, never a missing or
    stale www/ copy, and a view that does not build stops the card instead of saving the page's error state."""

    def setUp(self):
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for patch in (mock.patch.object(gen, "_tmp", Path(tmp.name)), mock.patch.object(gen, "_views", {}),
                      mock.patch.object(gen, "_view_errors", [])):
            patch.start()
            self.addCleanup(patch.stop)
        self.handler = gen._Quiet.__new__(gen._Quiet)
        self.handler.directory = str(gen.REPO)

    def test_a_view_is_served_from_this_runs_build(self):
        with mock.patch.dict(gen.site_views.VIEWS, {"data/wiring-inventory.json": lambda: '{"nodes": []}\n'}):
            path = Path(self.handler.translate_path("/www/data/wiring-inventory.json"))
        self.assertTrue(path.is_relative_to(gen._tmp))
        self.assertEqual(path.read_text(encoding="utf-8"), '{"nodes": []}\n')
        self.assertEqual(gen._view_errors, [])

    def test_a_view_that_does_not_build_stops_the_shot(self):
        boom = mock.Mock(side_effect=gen.site_views.build_wiring_json.WiringDataError("'blocks' has no entries"))
        with mock.patch.dict(gen.site_views.VIEWS, {"data/wiring-inventory.json": boom}):
            path = Path(self.handler.translate_path("/www/data/wiring-inventory.json"))
        self.assertFalse(path.exists(), "nothing is served in its place")
        with mock.patch.object(gen, "_chrome", return_value="chrome"), mock.patch.object(gen.subprocess, "run"), \
                mock.patch("PIL.Image.open"), self.assertRaisesRegex(gen.ShareCardError, "'blocks' has no entries"):
            gen.shot("http://x/behind/wiring.html")


class MainExitTest(unittest.TestCase):
    def test_a_card_error_exits_with_its_message(self):
        name = next(iter(gen.CARDS))
        boom = mock.Mock(side_effect=gen.ShareCardError("Google Chrome not found"))
        with mock.patch.dict(gen.CARDS, {name: boom}), mock.patch.object(gen, "serving"), \
                mock.patch.object(sys, "argv", ["make_share_cards.py", name, "--out", "/nonexistent-dir-f2"]), \
                mock.patch.object(gen.Path, "mkdir"), mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(gen.main(), 1)
        self.assertIn("make_share_cards: Google Chrome not found", err.getvalue())
