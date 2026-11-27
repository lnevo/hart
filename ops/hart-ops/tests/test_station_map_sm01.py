"""Behaviour tests for publications/rebuild_station_map.py (SM-01), station_compass.py and pub_fonts.py.

The Mac system fonts are not on every test host, so the drawing tests load the PIL default
font in their place. Pixel-exact output is checked by rebuilding the PNGs and comparing hashes.
"""
import json
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

PUB = Path(__file__).resolve().parents[1] / "publications"
sys.path.insert(0, str(PUB))

from PIL import ImageFont  # noqa: E402

import pub_fonts  # noqa: E402
import rebuild_station_map as rsm  # noqa: E402
import station_compass  # noqa: E402


def default_font(path, size):
    return ImageFont.load_default()


def stand_in_fonts():
    return mock.patch.multiple(
        "rebuild_station_map", _font=default_font
    ), mock.patch.object(station_compass, "font", default_font)


class Fonts(unittest.TestCase):
    def test_missing_font_raises_a_named_error(self):
        with self.assertRaises(pub_fonts.FontMissing) as ctx:
            pub_fonts.font("/nonexistent/none.ttf", 12)
        self.assertIn("/nonexistent/none.ttf", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, OSError)


class Compass(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(station_compass, "font", default_font)
        patcher.start()
        self.addCleanup(patcher.stop)

    def gold_side(self, north):
        """Which side of centre the gold needle tip lies on."""
        size = 200
        img = station_compass.compass_rose(size, north).convert("RGB")
        c = size // 2
        probes = {"right": (c + 40, c), "up": (c, c - 40), "down": (c, c + 40), "left": (c - 40, c)}
        gold = (station_compass.COMPASS_GOLD_L, station_compass.COMPASS_GOLD_D)
        return [side for side, xy in probes.items() if img.getpixel(xy) in gold]

    def test_gold_needle_points_north(self):
        for north in ("right", "up", "down"):
            with self.subTest(north=north):
                self.assertEqual(self.gold_side(north), [north])

    def test_unknown_north_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            station_compass.compass_rose(100, "left")
        self.assertIn("'left'", str(ctx.exception))

    def test_paste_centres_the_rose(self):
        from PIL import Image

        base = Image.new("RGB", (300, 300), (255, 255, 255))
        station_compass.paste_compass(base, cx=150, cy=150, size=100, north="up")
        self.assertEqual(base.getpixel((150, 150)), station_compass.COMPASS_RING)
        self.assertEqual(base.getpixel((10, 10)), (255, 255, 255))


class MapText(unittest.TestCase):
    def write(self, data):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "sm01.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def good(self):
        return json.loads(rsm.DATA.read_text(encoding="utf-8"))

    def test_repo_file_loads(self):
        text = rsm.load_map_text()
        self.assertEqual(text["publication"]["pub_id"], "SM-01")
        self.assertEqual(len(text["industries"]), 4)

    def test_missing_top_level_key(self):
        data = self.good()
        del data["labels"]
        with self.assertRaisesRegex(rsm.StationMapDataError, "missing 'labels'"):
            rsm.load_map_text(self.write(data))

    def test_missing_spine_station(self):
        data = self.good()
        del data["spine_y"]["barn"]
        with self.assertRaisesRegex(rsm.StationMapDataError, "spine_y is missing barn"):
            rsm.load_map_text(self.write(data))

    def test_empty_industries(self):
        data = self.good()
        data["industries"] = []
        with self.assertRaisesRegex(rsm.StationMapDataError, "industries is empty"):
            rsm.load_map_text(self.write(data))


class Drawing(unittest.TestCase):
    def setUp(self):
        for patcher in stand_in_fonts():
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_frame_scales(self):
        f = rsm._frame(1400, 2450, include_title=True, include_footer=True, fill=False)
        self.assertEqual((f.s, f.s_y, f.header_bottom, f.foot_y), (1.0, 1.0, 110, 2290))
        filled = rsm._frame(1000, 2400, include_title=False, include_footer=False, fill=True)
        self.assertEqual(filled.margin_x, 36)
        self.assertAlmostEqual(filled.s, (1000 - 72) / 660)
        self.assertAlmostEqual(filled.s_y, (2400 - 24 - 8 - 28) / 1890)

    def test_spine_stations_are_inked_in_order(self):
        f = rsm._frame(1400, 2450, include_title=True, include_footer=True, fill=False)
        sp = rsm._spine(f, rsm.TEXT["spine_y"])
        ys = [sp.y[k] for k in rsm.SPINE_KEYS]
        self.assertEqual(ys, sorted(ys))
        img = rsm.draw_subdivision_map()
        self.assertEqual(img.size, (1400, 2450))
        for key in ("brick", "plane", "barn", "east_lower", "princess"):
            with self.subTest(station=key):
                self.assertEqual(img.getpixel((int(sp.mx), int(sp.y[key]))), rsm.INK)

    def test_diagram_only_has_no_footer_rule(self):
        img = rsm.draw_subdivision_map(width=1000, height=2400, include_title=False,
                                       include_footer=False, fill=True)
        self.assertEqual(img.getpixel((500, 2400 - 160)), rsm.BG)


class Outputs(unittest.TestCase):
    def setUp(self):
        for patcher in stand_in_fonts():
            patcher.start()
            self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_rebuild_png_writes_the_four_pngs_where_it_is_told(self):
        from PIL import Image

        d = self.dir / "assets"
        out = rsm.rebuild_png(d / "map.png", plain=d / "plain.png", diagram=d / "diagram.png",
                              compass=d / "rose.png")
        self.assertEqual(out, d / "map.png")
        sizes = {p.name: Image.open(p).size for p in d.iterdir()}
        self.assertEqual(sizes, {"map.png": (1400, 2450), "plain.png": (1400, 2450),
                                 "diagram.png": (1000, 2400), "rose.png": (220, 220)})

    def test_rebuild_docx_embeds_the_png_under_the_masthead(self):
        import zipfile

        from docx import Document

        png = self.dir / "map.png"
        rsm.draw_subdivision_map(width=140, height=245).save(png, "PNG")
        out = rsm.rebuild_docx(png, self.dir / "sm01.docx")
        texts = [p.text for p in Document(str(out)).paragraphs if p.text]
        self.assertEqual(texts[:3], [rsm.TEXT["masthead"]["railroad"], rsm.TEXT["masthead"]["division"],
                                     rsm.PUBLICATION["title"]])
        with zipfile.ZipFile(out) as z:
            media = [n for n in z.namelist() if n.startswith("word/media/")]
            self.assertEqual([z.read(n) for n in media], [png.read_bytes()])


class CompassFontLoader(unittest.TestCase):
    def test_paste_compass_uses_the_given_loader(self):
        from PIL import Image

        calls = []

        def loader(path, size):
            calls.append(path)
            return ImageFont.load_default()

        with mock.patch.object(station_compass, "font", side_effect=AssertionError("strict loader used")):
            station_compass.paste_compass(Image.new("RGB", (300, 300)), cx=150, cy=150, size=200, load_font=loader)
        self.assertEqual(calls, [pub_fonts.ARIAL_BOLD])

    def test_local_maps_hand_their_fallback_loader_to_the_compass(self):
        from PIL import Image

        import rebuild_local_station_maps as rlsm

        with mock.patch.object(rlsm, "_font", default_font), \
                mock.patch.object(station_compass, "font", side_effect=AssertionError("strict loader used")):
            rlsm._hooks().paste_compass(Image.new("RGB", (300, 300)), cx=150, cy=150, size=200, north="up")
