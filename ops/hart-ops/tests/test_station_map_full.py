"""The whole-railroad station map: where the Barn crossover (switch 7) is drawn."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "publications"))
import rebuild_station_map_full as full  # noqa: E402


class BarnCrossover(unittest.TestCase):
    def test_main_east_end_sits_under_switch_9(self):
        top, bottom = full.barn_crossover(1030, 370, 490)
        self.assertEqual(bottom, (1030, 490))

    def test_runs_at_45_degrees_like_switch_23(self):
        top, bottom = full.barn_crossover(1030, 370, 490)
        self.assertEqual(top[1], 370)
        self.assertEqual(bottom[0] - top[0], bottom[1] - top[1])


class EngineLead(unittest.TestCase):
    EH = {3: 300, 2: 258, 1: 216}

    def test_eh3_between_9_and_11_is_half_its_first_length(self):
        sw13, sw11, _, _ = full.engine_lead(1030, 370, self.EH)
        self.assertEqual(sw11, (1030 + 132, 300))
        self.assertEqual(sw13[1], 370)

    def test_both_diverging_lines_run_at_45_degrees_parallel_with_switch_7(self):
        sw13, sw11, eh1, eh2 = full.engine_lead(1030, 370, self.EH)
        for low, high in ((sw13, sw11), (sw13, eh1), ((1030, 300), eh2)):
            self.assertEqual(low[0] - high[0], low[1] - high[1])
        top, bottom = full.barn_crossover(1030, 370, 490)
        self.assertEqual(bottom[0] - top[0], bottom[1] - top[1])  # same slope, same hand


class SwitchNumbers(unittest.TestCase):
    def test_full_map_labels_switches_like_the_local_maps(self):
        from local_station_maps import kit
        self.assertIs(full.SWNUM, kit.SWNUM)


class Fonts(unittest.TestCase):
    def test_fonts_load_on_draw_in_field_order(self):
        from unittest import mock
        calls = []
        with mock.patch.object(full, "_font", lambda path, size: calls.append((path, size)) or size):
            fonts = full.load_fonts()
        self.assertEqual(fonts, (24, 38, 20, 18, 28, 17, 19))
        self.assertEqual(calls[0], (full.ARIAL_BOLD, 24))
        self.assertEqual(calls[4], (full.GEORGIA_BOLD, 28))


class Draw(unittest.TestCase):
    def test_map_spans_west_stubs_to_the_shenango_octagon(self):
        a = full.anchors()
        self.assertEqual(a.xp - a.x112, 200 + full.P_GAP)
        img = full.draw()
        self.assertEqual(img.size, (int(a.x_vert + 70), int(full.ME_LOW + 110)))
        # Main West is drawn in ink across the map at its row.
        self.assertNotEqual(img.getpixel((int(a.x_stub) + 10, full.Y0)), full.BG)

    def test_industry_names_are_the_crew_master_destinations(self):
        parts = full._industry_parts()
        self.assertEqual([p[0] for p in parts], ["Track S-1", "Track S-2", "Track S-3", "Track S-4"])
        self.assertEqual(len(parts[1][1]), 2)

    def test_an_industry_colour_missing_from_the_crew_master_names_the_track(self):
        import crew_master
        master = crew_master.load()
        master = dict(master, colors=[c for c in master["colors"] if c["id"] != "pink"])
        with self.assertRaisesRegex(full.FullMapError, "Track S-3: colour pink"):
            full._industry_parts(master)

    def test_brick_lead_off_the_west_lead_row_is_refused(self):
        from unittest import mock
        from PIL import ImageDraw, Image
        pen = full._Pen(ImageDraw.Draw(Image.new("RGB", (10, 10))), None)
        with mock.patch.object(full, "VERT", full.VERT + 1):
            with self.assertRaisesRegex(full.FullMapError, "not on the West Lead row"):
                full._draw_west_yard(pen, full.anchors())

    def test_ladder_x_interpolates_between_its_ends(self):
        ladder = full._Ladder((0.0, 0.0), (10.0, 100.0))
        self.assertEqual(ladder.x_at(50.0), 5.0)


if __name__ == "__main__":
    unittest.main()
