"""Behaviour tests for publications/rebuild_local_station_maps.py.

rebuild_station_map_full imports ARIAL_BOLD, BG, GEORGIA, GEORGIA_BOLD, INK, _color_chip, _dot,
_font, _label, _line and _sw_badge from it; those are covered here.

The drawers are snapshotted as the list of drawing calls they make (line, polygon, ellipse,
text ...), not as pixels. Pixels would change with the Pillow version and with whether the
Mac-only fonts exist; the call list does not. Fonts are replaced by a stand-in that only knows
its file name and size, and text width is len * size / 2. Nothing is written into the checkout.
Golden data: tests/golden/w4c/maps_*.txt.
"""
import contextlib
import io
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "publications"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docx import Document  # noqa: E402
from PIL import Image  # noqa: E402

import rebuild_local_station_maps as rlsm  # noqa: E402
from golden_support import check_golden  # noqa: E402

TEST_ID = "test_local_station_maps_behaviour"
DEPENDS = "the draw_* functions in rebuild_local_station_maps.py, with stand-in fonts and a call-recording canvas"


class FakeFont:
    def __init__(self, path, size):
        self.path = path
        self.size = size

    def __repr__(self):
        return f"Font({Path(self.path).name},{self.size})"


def fmt(value):
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, (list, tuple)):
        return "(" + ",".join(fmt(v) for v in value) + ")"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}={fmt(v)}" for k, v in sorted(value.items())) + "}"
    return repr(value) if isinstance(value, str) else str(value)


class Recorder:
    """Stands in for ImageDraw.Draw: logs each primitive instead of painting it."""

    def __init__(self):
        self.calls = []

    PRIMITIVES = frozenset(
        {"ellipse", "line", "polygon", "rectangle", "rounded_rectangle", "text"}
    )

    def textlength(self, text, font=None):
        return len(text) * font.size / 2

    def textbbox(self, xy, text, font=None, anchor=None, **kw):
        return (xy[0], xy[1], xy[0] + self.textlength(text, font), xy[1] + font.size)

    def multiline_textbbox(self, xy, text, font=None, **kw):
        lines = text.split("\n")
        width = max(self.textlength(line, font) for line in lines)
        return (xy[0], xy[1], xy[0] + width, xy[1] + font.size * len(lines))

    def __getattr__(self, name):
        if name not in self.PRIMITIVES:
            raise AttributeError(
                f"Recorder does not know ImageDraw.{name}; add it to PRIMITIVES if a drawer now uses it"
            )

        def record(*args, **kwargs):
            self.calls.append(f"{name} {fmt(args)} {fmt(kwargs)}")

        return record


def draw_with_recorder(drawer, meta):
    """Run a drawer; return (image, call log lines)."""
    rec = Recorder()
    compass = []

    def canvas(width=1600, height=1100):
        return Image.new("RGB", (width, height), rlsm.BG), rec

    def paste(img, **kw):
        compass.append(f"compass {fmt(kw)}")

    with mock.patch.object(rlsm, "_font", lambda path, size: FakeFont(path, size)), \
            mock.patch.object(rlsm, "_canvas", canvas), \
            mock.patch.object(rlsm, "_paste_compass", paste):
        img = drawer(meta)
    return img, rec.calls + compass


def meta_for(key, **extra):
    base = next(m for m in rlsm.MAPS if m["key"] == key)
    return {**base, **extra}


class GoldenDrawings(unittest.TestCase):
    def snapshot(self, name, key, **extra):
        img, calls = draw_with_recorder(rlsm.DRAWERS[key], meta_for(key, **extra))
        self.assertGreater(len(calls), 20, f"{key} drew almost nothing")
        text = f"size={img.size}\ncalls={len(calls)}\n" + "\n".join(calls) + "\n"
        check_golden(self, name, text, depends_on=DEPENDS, test_id=TEST_ID)
        return calls

    def test_west_yard(self):
        calls = self.snapshot("maps_west_yard.txt", "west_yard")
        self.assertTrue(any(c.startswith("text") and "'WEST YARD'" in c for c in calls))

    def test_south_yard(self):
        self.snapshot("maps_south_yard.txt", "south_yard")

    def test_industries_is_titled_from_the_meta(self):
        calls = self.snapshot("maps_east_end.txt", "industries")
        self.assertTrue(any("'EAST END'" in c for c in calls))

    def test_shenango(self):
        self.snapshot("maps_shenango.txt", "shenango")

    def test_shenango_rotated_differs_and_keeps_its_labels_upright(self):
        _, plain = draw_with_recorder(rlsm.draw_shenango, meta_for("shenango"))
        img, rotated = draw_with_recorder(rlsm.draw_shenango, meta_for("shenango", rotate180=True))
        self.assertNotEqual(plain, rotated)
        texts = lambda calls: sum(1 for c in calls if c.startswith("text"))  # noqa: E731
        self.assertEqual(texts(plain), texts(rotated))
        text = f"size={img.size}\ncalls={len(rotated)}\n" + "\n".join(rotated) + "\n"
        check_golden(self, "maps_shenango_rotated.txt", text, depends_on=DEPENDS, test_id=TEST_ID)

    def test_chrome_minimal_and_full(self):
        rec = Recorder()
        with mock.patch.object(rlsm, "_font", lambda path, size: FakeFont(path, size)):
            box = rlsm._chrome(rec, width=1000, height=800, title="Some Map", minimal=True)
            minimal_calls = list(rec.calls)
            rec.calls.clear()
            full_box = rlsm._chrome(rec, width=1000, height=800, title="Some Map",
                                    subtitle="Sub", pub_id="SM-99", revision="Z")
        self.assertEqual(box, (68, 90, 932, 744))
        self.assertEqual(len(minimal_calls), 3)
        self.assertEqual(full_box, (68, 120, 932, 708))
        joined = "\n".join(rec.calls)
        self.assertIn("Publication SM-99", joined)
        self.assertIn("'SOME MAP'", minimal_calls[0])
        self.assertIn("'Sub'", joined)
        check_golden(self, "maps_chrome_full.txt", joined + "\n", depends_on=DEPENDS, test_id=TEST_ID)


class DrawingPrimitives(unittest.TestCase):
    def test_line_is_a_constant_width_polygon(self):
        rec = Recorder()
        rlsm._line(rec, (0, 0), (10, 0), w=4)
        self.assertEqual(len(rec.calls), 1)
        self.assertTrue(rec.calls[0].startswith("polygon (((0.00,2.00),(10.00,2.00),(10.00,-2.00),(0.00,-2.00)))"))

    def test_zero_length_line_draws_nothing(self):
        rec = Recorder()
        rlsm._line(rec, (3, 3), (3, 3))
        self.assertEqual(rec.calls, [])

    def test_outset_moves_along_the_segment(self):
        self.assertEqual(rlsm._outset((0, 0), (10, 0), 3), (3.0, 0.0))
        self.assertEqual(rlsm._outset((1, 1), (1, 1), 3), (1, 1))

    def test_dot_is_a_filled_circle_box(self):
        rec = Recorder()
        rlsm._dot(rec, (10, 20), r=5)
        self.assertIn("ellipse ((5,15,15,25))", rec.calls[0])

    def test_arrow_points_in_each_direction(self):
        expected = {
            "right": "((10,10),(0,4.50),(0,15.50))",
            "left": "((10,10),(20,4.50),(20,15.50))",
            "up": "((10,10),(4.50,20),(15.50,20))",
            "down": "((10,10),(4.50,0),(15.50,0))",
        }
        for direction, pts in expected.items():
            rec = Recorder()
            rlsm._arrow(rec, (10, 10), direction=direction, size=10)
            self.assertTrue(rec.calls[0].startswith(f"polygon ({pts})"), (direction, rec.calls))

    def test_badges_size_to_the_text(self):
        rec = Recorder()
        font = FakeFont("x.ttf", 20)
        rlsm._sw_badge(rec, (100, 100), "12", font)
        # text width 12*... "12" -> 2*20/2 = 20; box = 20 + 14 wide, 20 + 6 high
        self.assertIn("rounded_rectangle", rec.calls[0])
        self.assertIn("(83.00,87.00,117.00,113.00)", rec.calls[0])
        rec = Recorder()
        rlsm._cp_box(rec, (100, 100), "CP", font)
        self.assertIn("rectangle", rec.calls[0])
        self.assertIn("(82.00,86.00,118.00,114.00)", rec.calls[0])

    def test_color_chip_and_hollow_dot_call_the_draw(self):
        rec = Recorder()
        rlsm._color_chip(rec, (50, 50), "ff0000", size=10)
        rlsm._hollow(rec, (50, 50), r=6, w=2)
        self.assertEqual(len(rec.calls), 2)

    def test_color_chip_rejects_a_hash_prefixed_colour(self):
        with self.assertRaises(ValueError):
            rlsm._color_chip(Recorder(), (0, 0), "#ff0000")

    def test_font_falls_back_when_the_file_is_missing(self):
        font = rlsm._font("/nonexistent/none.ttf", 12)
        self.assertTrue(hasattr(font, "getbbox"))

    def test_canvas_is_a_white_rgb_image_of_the_asked_size(self):
        img, draw = rlsm._canvas(30, 20)
        self.assertEqual((img.size, img.mode, img.getpixel((0, 0))), ((30, 20), "RGB", rlsm.BG))
        self.assertIsNotNone(draw)


class SheetGeometry(unittest.TestCase):
    """The pitch and ladder helpers the drawers share (local_station_maps.kit)."""

    def test_ladder_pitch_is_three_quarter_inch_along_the_diagonal(self):
        from local_station_maps import kit

        self.assertEqual((kit.DOT_R, kit.STEP_2LED, kit.STEP_1LED), (18.75, 75.0, 150.0))
        self.assertAlmostEqual(kit.LADDER_DX_STEP**2 + kit.LADDER_TRACK_GAP**2, kit.STEP_1LED**2)

    def test_yard_rows_are_one_pitch_apart_and_main_east_closer(self):
        from local_station_maps import kit

        ys = kit._yard_rows(100.0)
        gaps = [b - a for a, b in zip(ys, ys[1:])]
        self.assertEqual(len(ys), 7)
        for gap in gaps[:5]:
            self.assertAlmostEqual(gap, kit.LADDER_TRACK_GAP)
        self.assertAlmostEqual(gaps[5], kit.LADDER_TRACK_GAP * 0.72)
        self.assertAlmostEqual(ys[6] - ys[0], kit.YARD_BLOCK_H)

    def test_ladder_x_follows_the_line_and_survives_a_flat_ladder(self):
        from local_station_maps import kit

        self.assertEqual(kit._ladder_x_at((0.0, 0.0), (10.0, 100.0), 50.0), 5.0)
        # A ladder less than 1 px tall divides by 1, not by zero.
        self.assertEqual(kit._ladder_x_at((0.0, 0.0), (10.0, 0.0), 0.5), 5.0)

    def test_east_end_rows_take_the_names_from_the_crew_master(self):
        from local_station_maps import east_end

        rows = east_end.industry_rows()
        self.assertEqual([r.track for r in rows], [t for t, _, _ in east_end.TRACK_INDUSTRIES])
        two = rows[1]
        self.assertEqual(len(two.colors), 2)
        self.assertIn(" · ", two.industry)


class Tables(unittest.TestCase):
    def test_every_map_has_a_drawer_and_unique_output_paths(self):
        pngs = [m["png"] for m in rlsm.MAPS]
        docxs = [m["docx"] for m in rlsm.MAPS]
        self.assertEqual(len(set(pngs)), len(pngs))
        self.assertEqual(len(set(docxs)), len(docxs))
        for meta in rlsm.MAPS:
            self.assertIn(meta["key"], rlsm.DRAWERS)

    def test_switch_numbers_are_unique(self):
        self.assertEqual(len(set(rlsm.SWNUM.values())), len(rlsm.SWNUM))


class DocxOutput(unittest.TestCase):
    def build(self, meta):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            png = tmp / "map.png"
            Image.new("RGB", (80, 50), (255, 255, 255)).save(png)
            meta = {**meta, "docx": tmp / "map.docx"}
            result = rlsm.rebuild_docx(meta, png)
            self.assertEqual(result, meta["docx"])
            return Document(result)

    def test_eight_by_five_sheet_is_a_full_bleed_landscape_picture(self):
        doc = self.build({"sheet": "8x5", "png_only": True, "title": "T", "pub_id": "SM-1", "revision": "A",
                          "effective": "x"})
        sec = doc.sections[0]
        self.assertEqual((sec.page_width.inches, sec.page_height.inches), (8.0, 5.0))
        self.assertEqual(sec.left_margin.inches, 0.0)
        self.assertEqual(len(doc.inline_shapes), 1)
        self.assertEqual(doc.inline_shapes[0].width.inches, 8.0)
        self.assertEqual([p.text for p in doc.paragraphs if p.text], [])

    def test_png_only_flag_alone_also_takes_the_sheet_path(self):
        doc = self.build({"png_only": True, "title": "T", "pub_id": "SM-1", "revision": "A", "effective": "x"})
        self.assertEqual(doc.sections[0].page_width.inches, 8.0)

    def test_letter_page_has_title_block_and_picture(self):
        doc = self.build({"title": "Test Map", "subtitle": "A subtitle", "pub_id": "SM-9", "revision": "Q",
                          "effective": "1 January 2030", "minimal_chrome": True})
        texts = [p.text for p in doc.paragraphs if p.text]
        self.assertEqual(texts[0], "HART RAILROAD")
        self.assertIn("Station Map  ·  Test Map", texts)
        self.assertIn("A subtitle", texts)
        self.assertEqual(doc.sections[0].page_width.inches, 8.5)
        self.assertEqual(doc.inline_shapes[0].width.inches, 7.4)
        self.assertEqual(doc.sections[0].footer.paragraphs[0].text, "")

    def test_letter_page_without_minimal_chrome_gets_a_publication_footer(self):
        doc = self.build({"title": "Test Map", "pub_id": "SM-9", "revision": "Q",
                          "effective": "1 January 2030"})
        footer = " ".join(p.text for p in doc.sections[0].footer.paragraphs)
        self.assertIn("SM-9", footer)
        self.assertNotIn("A subtitle", [p.text for p in doc.paragraphs])

    def test_missing_key_gives_keyerror_not_a_half_written_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            png = tmp / "map.png"
            Image.new("RGB", (8, 5)).save(png)
            with self.assertRaises(KeyError):
                rlsm.rebuild_docx({"docx": tmp / "x.docx", "pub_id": "SM-1"}, png)
            self.assertFalse((tmp / "x.docx").exists())


class MainRun(unittest.TestCase):
    def run_main(self, maps, drawers):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fixed = []
            for m in maps:
                fixed.append({**m, "png": tmp / "a" / m["png"].name, "docx": tmp / "d" / m["docx"].name})
            with mock.patch.object(rlsm, "MAPS", fixed), \
                    mock.patch.object(rlsm, "DRAWERS", drawers), \
                    mock.patch.object(rlsm, "ASSETS", tmp / "a"), \
                    mock.patch.object(rlsm, "DOCS", tmp / "d"), \
                    contextlib.redirect_stdout(buf):
                rlsm.main()
            written = sorted(p.relative_to(tmp).as_posix() for p in tmp.rglob("*") if p.is_file())
            report = buf.getvalue().replace(str(tmp), "<tmp>")
        return written, report

    def tiny(self, meta):
        return Image.new("RGB", (40, 25), (255, 255, 255))

    def test_main_writes_drawn_maps_and_reports_skipped_ones(self):
        maps = [meta_for("west_yard"), meta_for("shenango", skip=True)]
        drawers = {"west_yard": self.tiny, "shenango": self.tiny}
        written, report = self.run_main(maps, drawers)
        self.assertEqual(
            written,
            ["a/station_map_west_yard.png", "d/Neville_Island_Station_Map_West_Yard.docx"],
        )
        self.assertIn("Wrote <tmp>/a/station_map_west_yard.png", report)
        self.assertIn("(SM-02 Rev A)", report)
        self.assertIn("Skipped SM-05 (station_map_shenango.png): drawn in the hart repo", report)

    def test_main_names_the_missing_drawer(self):
        with self.assertRaises(KeyError) as cm:
            self.run_main([meta_for("west_yard")], {})
        self.assertIn("west_yard", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
