"""gen_ctc_track_plan (the USS CTC board generator): unit tests on the board's geometry, signal jewels, the panel XML
edits, the BRICK SIDI block, apply(), the parked target, the lever columns and what the live importer reads.

Split out of test_gen_ctc_track_plan.py on 2026-11-26 with no change in the tests, so each file stays under the size
limit (tools/audit/check_py_sizes.py). The fixture board and the module under test come from that file, which says
who uses the generator, and keeps the golden snapshot, the icon and the main() tests.
"""
from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path
from unittest import mock

from test_gen_ctc_track_plan import FIXTURE_CELLS, fixture_board, gen  # its folder is on sys.path under discover


class Geometry(unittest.TestCase):
    def test_cell_to_pixel(self):
        self.assertEqual(gen.ux(1), gen.OX)
        self.assertEqual(gen.ux(3), gen.OX + 2 * gen.CELL_W)
        self.assertEqual(gen.bar_y(5), gen.OY)
        self.assertEqual(gen.bar_y(7), gen.OY + 2 * gen.CELL_H)

    def test_shifted_cells_move_west_and_others_do_not(self):
        x, y = sorted(gen.SHIFT_CELLS)[0]
        self.assertEqual(gen.ux(x, y), gen.ux(x) - gen.SHIFT_WEST * gen.CELL_W)
        self.assertEqual(gen.ux(x, 1), gen.ux(x))     # same column, a row that does not shift

    def test_turnout_urls_swap_closed_and_thrown_when_inverted(self):
        plain, inv = gen.turnout_urls(False), gen.turnout_urls(True)
        self.assertEqual(plain["closed"], "preference:ctc/icons/pts-closed.gif")
        self.assertEqual(inv["closed"], plain["thrown"])
        self.assertEqual(inv["thrown"], plain["closed"])
        self.assertEqual(inv["unknown"], plain["unknown"])
        self.assertEqual(inv["inconsistent"], plain["inconsistent"])

    def test_sig_url_marks_west_facing(self):
        self.assertEqual(gen.sig_url("d1", "stop", "E"), "preference:ctc/icons/sig-d1-stop.gif")
        self.assertEqual(gen.sig_url("h2", "stop", "W"), "preference:ctc/icons/sig-h2-stop-w.gif")

    def test_signal_xy_hangs_west_facing_icons_to_the_left_of_the_stem(self):
        self.assertEqual(gen.signal_xy(100, 50, "E", "h2"), (100, 47))
        self.assertEqual(gen.signal_xy(100, 50, "W", "h2"), (100 - gen.MAST_ICON[0] + 1, 47))
        self.assertEqual(gen.signal_xy(100, 50, "W", "d1"), (100 - gen.HEAD_ICON[0] + 1, 47))

    def test_signal_pos_uses_the_cell_stem(self):
        x, y = gen.signal_pos(3, 7, "E", "h2")
        self.assertEqual((x, y), (gen.ux(3, 7) + 8, gen.bar_y(7) + 2 - 3))
        x, _ = gen.signal_pos(3, 7, "W", "d1")
        self.assertEqual(x, gen.ux(3, 7) + 2 - gen.HEAD_ICON[0] + 1)

    def test_bresenham_lines(self):
        self.assertEqual(gen._bresenham(0, 0, 3, 0), [(0, 0), (1, 0), (2, 0), (3, 0)])
        self.assertEqual(gen._bresenham(2, 2, 2, 2), [(2, 2)])
        self.assertEqual(gen._bresenham(3, 3, 0, 0), [(3, 3), (2, 2), (1, 1), (0, 0)])
        line = gen._bresenham(0, 0, 10, 3)
        self.assertEqual((line[0], line[-1]), ((0, 0), (10, 3)))
        self.assertEqual(len(line), 11)

    def test_norm_name(self):
        self.assertEqual(gen._norm_name("Track Foo, PA"), "Track Foo")
        self.assertEqual(gen._norm_name("East Ext"), "Track East Ext")
        self.assertEqual(gen._norm_name(None), "")
        self.assertEqual(gen._norm_name("Track Scale"), "Track Scale")

    def test_is_switch_os(self):
        with fixture_board():
            for name in ("OS Switch 1", "OS Switch 23a", "OS 5", "Track 7", "OS Switch 9, PA"):
                self.assertTrue(gen._is_switch_os(name), name)
            for name in ("Track Scale", "Track S-R", "Main", ""):
                self.assertFalse(gen._is_switch_os(name), name)

    def test_throat_cell_prefers_left_then_vertical_then_frog_then_right(self):
        frog = (5, 5)
        self.assertEqual(gen._throat_cell({(4, 5), (5, 4), (6, 5), frog}, frog), (4, 5))
        self.assertEqual(gen._throat_cell({(5, 4), (6, 5), frog}, frog), (5, 4))
        self.assertEqual(gen._throat_cell({(6, 5), frog}, frog), frog)
        self.assertEqual(gen._throat_cell({(6, 5)}, frog), (6, 5))
        self.assertEqual(gen._throat_cell({(9, 5), (7, 5)}, frog), (7, 5))
        self.assertEqual(gen._throat_cell(set(), frog), frog)

    def test_os_jewel_xy_steps_six_pixels_off_the_frog(self):
        frog = (5, 5)
        jx, jy = gen._jewel_xy(*frog)
        self.assertEqual(gen._os_jewel_xy((4, 5), frog), (gen._jewel_xy(4, 5)[0] - 6, gen._jewel_xy(4, 5)[1]))
        self.assertEqual(gen._os_jewel_xy((6, 5), frog), (gen._jewel_xy(6, 5)[0] + 6, gen._jewel_xy(6, 5)[1]))
        self.assertEqual(gen._os_jewel_xy((5, 4), frog), (gen._jewel_xy(5, 4)[0], gen._jewel_xy(5, 4)[1] - 6))
        self.assertEqual(gen._os_jewel_xy((5, 6), frog), (gen._jewel_xy(5, 6)[0], gen._jewel_xy(5, 6)[1] + 6))
        self.assertEqual(gen._os_jewel_xy(frog, frog), (jx - gen.CELL_W, jy))

    def test_overlaps(self):
        self.assertTrue(gen._overlaps((0, 0, 10, 10), (9, 9, 5, 5)))
        self.assertFalse(gen._overlaps((0, 0, 10, 10), (10, 0, 5, 5)))     # touching edges do not overlap
        self.assertFalse(gen._overlaps((0, 0, 10, 10), (0, 11, 5, 5)))

    def test_signal_and_points_rects_follow_the_board_data(self):
        with fixture_board():
            sigs, pts = gen.signal_rects(), gen.points_rects()
        self.assertEqual(len(sigs), 2)
        self.assertEqual(sigs[0][2:], gen.MAST_ICON)
        self.assertEqual(sigs[1][2:], gen.HEAD_ICON)
        self.assertEqual(pts, [(gen.ux(4, 7) + 5, gen.bar_y(7) + 5) + gen.POINTS_ICON])


class Jewels(unittest.TestCase):
    def placer(self, sigs):
        with mock.patch.object(gen, "signal_rects", return_value=sigs), \
                mock.patch.object(gen, "points_rects", return_value=[]):
            return gen.JewelPlacer()

    def test_a_clear_jewel_stays_where_it_is(self):
        p = self.placer([])
        self.assertEqual(p.place((100, 100), 6, {(5, 6)}), (100, 100))
        self.assertEqual(p.taken, [(100, 100, gen.JEWEL, gen.JEWEL)])

    def test_a_jewel_over_a_signal_slides_along_its_row_to_clear_ground(self):
        sig = (100, 100, 6, 20)
        p = self.placer([sig])
        usual = (100, 100)
        # the block's stretch of the row spans several cells so there is room to slide
        cells = {(5, 6), (6, 6), (7, 6), (8, 6)}
        x, y = p.place(usual, 6, cells)
        self.assertEqual(y, 100)
        self.assertNotEqual(x, 100)
        self.assertFalse(gen._overlaps((x, y, gen.JEWEL, gen.JEWEL), sig))

    def test_a_jewel_with_no_room_stays_put_under_the_signal(self):
        p = self.placer([(0, 90, 400, 40)])
        self.assertEqual(p.place((100, 100), 6, {(5, 6)}), (100, 100))

    def test_a_jewel_does_not_pass_one_already_placed(self):
        p = self.placer([(100, 100, 6, 20)])
        p.taken.append((100 + gen.JEWEL - 1, 100, gen.JEWEL, gen.JEWEL))      # blocks the east side
        x, _ = p.place((100, 100), 6, {(5, 6), (6, 6), (7, 6), (8, 6)})
        self.assertLess(x, 100 + gen.JEWEL)

    def test_the_operating_rows_below_os_y_are_not_moved(self):
        p = self.placer([(100, gen.OS_Y, 50, 50)])
        self.assertEqual(p.place((100, gen.OS_Y), 12, {(5, 12)}), (100, gen.OS_Y))


class BuildGeometry(unittest.TestCase):
    def setUp(self):
        with fixture_board():
            self.turnouts, self.tracks, self.lamps, self.texts = gen.build_geometry(FIXTURE_CELLS)

    def test_one_turnout_dot_per_plant(self):
        self.assertEqual(self.turnouts, [("Switch 1", gen.ux(4, 7) + 5, gen.bar_y(7) + 5, False)])

    def test_tracks_are_drawn_only_on_the_board_rows(self):
        ys = {t[1] for t in self.tracks}
        self.assertTrue(all(gen.bar_y(5) - 10 <= y <= gen.bar_y(12) + 30 for y in ys), ys)
        gifs = [t[2] for t in self.tracks]
        self.assertIn("cell-us.gif", gifs)
        self.assertIn("cell-lb.gif", gifs)
        self.assertIn("stock-v.gif", gifs)
        # a block's RIGHT edge with no cell beyond it ends in a bumper: cells (2, 6) and (4, 7)
        self.assertEqual(gifs.count("stock-end.gif"), 2)

    def test_the_shift_hole_is_filled_with_main_track(self):
        stock_h = gen.STOCK_H
        for x, y in gen.SHIFT_CELLS:
            self.assertIn((gen.OX + (x - 1) * gen.CELL_W + stock_h[1], gen.bar_y(y) + stock_h[2], stock_h[0], 0),
                          self.tracks)

    def test_lamps_one_per_occupancy_sensor_os_first(self):
        sensors = [lamp[0] for lamp in self.lamps]
        # Track Main East has no occupancy edge, so FALLBACK_LABEL_SENSORS gives its label a lamp
        self.assertEqual(sorted(sensors), ["BS A", "BS B", "BS Main East", "BS OS 1"])
        self.assertEqual(self.lamps[0][0], "BS OS 1")               # OS cuts are placed before the track lamps
        self.assertEqual(self.lamps[0][3], "OS Switch 1")
        self.assertNotIn("BS Far", sensors)                         # row 20 is off the board

    def test_labels_skip_desk_titles_and_hidden_names_and_keep_stations(self):
        by_text = {t[2]: t for t in self.texts}
        self.assertIn("BRICK", by_text)
        self.assertEqual(by_text["BRICK"][1], gen.STATION_Y)
        self.assertEqual(by_text["BRICK"][4], gen.WHITE)
        self.assertNotIn("DS-CTC  Rev A  Eff 2026-11-12", by_text)
        self.assertNotIn("Track Main East", by_text)                # in HIDE_TRACK_LABELS
        self.assertIn("Track B", by_text)                           # ", PA" dropped
        self.assertEqual(by_text["Track B"][4], gen.CREAM)
        self.assertEqual([t[2] for t in self.texts].count("Main"), 2)
        self.assertEqual(self.texts[0][2], "HART RAILROAD - NEVILLE ISLAND")

    def test_geometry_with_no_cells_still_draws_plants_and_headings(self):
        with fixture_board():
            turnouts, tracks, lamps, texts = gen.build_geometry({})
        self.assertEqual(len(turnouts), 1)
        self.assertEqual(lamps, [])
        self.assertEqual(len(tracks), len(gen.SHIFT_CELLS))         # only the shift fill
        self.assertEqual(len(texts), 3)


class Editing(unittest.TestCase):
    def test_reposition_levers_slides_a_lever_group_onto_its_slot(self):
        text = ('<sensoricon sensor="IS1:LEVER" x="20" y="379" />\n'
                '<sensoricon sensor="IS1:SWNI" x="16" y="340" />\n'
                '<sensoricon sensor="IS9:LEVER" x="20" y="379" />\n'
                '<multisensoricon x="20" y="492"><a sensor="IS2:CB"/></multisensoricon>\n'
                '<multisensoricon x="20" y="492"><a sensor="IS9:CB"/></multisensoricon>')
        with mock.patch.object(gen, "UID_SLOT", {1: 1, 2: 1}):
            out = gen.reposition_levers(text)
        self.assertIn('sensor="IS1:LEVER" x="85"', out)
        self.assertIn('sensor="IS1:SWNI" x="81"', out)
        self.assertIn('sensor="IS9:LEVER" x="20"', out)           # not a slot UID: untouched
        self.assertIn('<multisensoricon x="85" y="492"><a sensor="IS2:CB"/>', out)
        self.assertIn('<multisensoricon x="20" y="492"><a sensor="IS9:CB"/>', out)

    def test_reposition_levers_is_a_no_op_on_a_group_already_in_place(self):
        text = '<sensoricon sensor="IS1:LEVER" x="12" y="379" />'
        with mock.patch.object(gen, "UID_SLOT", {1: 0}):
            self.assertEqual(gen.reposition_levers(text), text)

    def test_fix_brick_signal_levers_is_idempotent(self):
        base = ('<multisensoricon x="5" y="492" level="10"><a sensor="IS4:CB"/></multisensoricon>\n'
                '<multisensoricon x="5" y="492" level="10"><a sensor="IS2:CB"/></multisensoricon>\n'
                '<sensoricon sensor="IS6:NGK" x="170" y="454" level="10"></sensoricon>\n')
        once = gen.fix_brick_signal_levers(base)
        self.assertIn('x="20" y="492"', once)                    # IS4 lever column
        self.assertIn('x="85" y="492"', once)                    # IS2 lever column
        self.assertTrue(gen._has_knockout_at(once, 180))
        self.assertEqual(gen.fix_brick_signal_levers(once), once)

    def test_knockout_helpers(self):
        ko = gen.KNOCKOUT.format(x=50)
        self.assertTrue(gen._has_knockout_at(ko, 50))
        self.assertFalse(gen._has_knockout_at(ko, 51))
        swapped = gen._replace_knockout_at("a" + ko + "b", 50, "NEW")
        self.assertEqual(swapped, "aNEWb")
        self.assertEqual(gen._replace_knockout_at("nothing here", 50, "NEW"), "nothing here")
        sens = '<sensoricon sensor="IS4:LDGK" x="1">x</sensoricon>'
        self.assertEqual(gen._replace_sensoricon("[" + sens + "]", "IS4:LDGK", "NEW"), "[NEW]")

    def test_store_format_locks_items_and_rewrites_fonts_and_degrees(self):
        panel = ('<positionablelabel x="1" y="0" level="1" editable="true" fontname="Dialog.bold">\n'
                 '  <icon url="a.gif" scale="1.0" />\n</positionablelabel>')
        out = gen.store_format(panel)
        self.assertIn('editable="false"', out)
        self.assertIn('fontFamily="Dialog" fontname="Dialog"', out)
        self.assertIn('<icon url="a.gif" degrees="0" scale="1.0"', out)

    def test_store_format_head_and_mast_icons(self):
        head = ('<signalheadicon signalhead="IH1" degrees="0" x="1">\n'
                '  <lunar url="u" scale="1"><rotation>0</rotation></lunar>\n'
                '  <flashlunar url="u" scale="1"><rotation>0</rotation></flashlunar>\n</signalheadicon>')
        out = gen.store_format(head)
        self.assertNotIn("degrees", out)
        self.assertNotIn("lunar", out)
        mast = '<signalmasticon signalmast="M" degrees="0" clickmode="3" litmode="false" x="1"/>'
        self.assertEqual(gen.store_format(mast),
                         '<signalmasticon signalmast="M" clickmode="3" litmode="false" degrees="0" x="1"/>')

    def test_store_format_outdents_the_background_plate(self):
        self.assertEqual(gen.store_format('<a>\n        <positionablelabel x="0" y="0" level="1" b/>'),
                         '<a>\n    <positionablelabel x="0" y="0" level="1" b/>')


CTC_BLOCK = """<ctcCodeButtonData>
      <UniqueID>%d</UniqueID>
      <SIDI_TrafficDirection>BOTH</SIDI_TrafficDirection>
      <SIDI_LeftRightTrafficSignals>
        <signal>Old</signal>
      </SIDI_LeftRightTrafficSignals>
      <SIDI_RightLeftTrafficSignals />
      <TRL_LeftRules>
        <rule>L</rule>
      </TRL_LeftRules>
      <TRL_RightRules />
    </ctcCodeButtonData>"""


class BrickSidi(unittest.TestCase):
    def test_sidi_signal_list_empty_and_full(self):
        self.assertEqual(gen._sidi_signal_list("T", []), "      <T />")
        self.assertEqual(gen._sidi_signal_list("T", ["A", "B"]),
                         "      <T>\n        <signal>A</signal>\n        <signal>B</signal>\n      </T>")

    def test_set_sidi_lists_sets_direction_and_swaps_rules_once(self):
        out = gen._set_sidi_lists(CTC_BLOCK % 13, "RIGHT", ["Mast 2L"], [], swap_trl=True)
        self.assertIn("<SIDI_TrafficDirection>RIGHT</SIDI_TrafficDirection>", out)
        self.assertIn("<signal>Mast 2L</signal>", out)
        self.assertNotIn("<signal>Old</signal>", out)
        self.assertIn("<SIDI_RightLeftTrafficSignals />", out)
        self.assertIn("<TRL_LeftRules />", out)
        self.assertIn("<TRL_RightRules>\n        <rule>L</rule>\n      </TRL_RightRules>", out)

    def test_set_sidi_lists_without_swap_leaves_the_rules(self):
        out = gen._set_sidi_lists(CTC_BLOCK % 13, "LEFT", [], ["M"], swap_trl=False)
        self.assertIn("<TRL_LeftRules>", out)
        self.assertIn("<TRL_RightRules />", out)

    def test_patch_brick_sidi_patches_the_two_lever_blocks_and_is_idempotent(self):
        text = "<x>" + CTC_BLOCK % 13 + CTC_BLOCK % 14 + CTC_BLOCK % 15 + "</x>"
        once = gen.patch_brick_sidi(text)
        self.assertIn("<signal>Mast 2L</signal>", once)
        self.assertIn("<signal>Mast 4RA</signal>", once)
        self.assertIn("<signal>Mast 4RB</signal>", once)
        self.assertEqual(once.count("<signal>Old</signal>"), 1)            # UID 15 untouched
        self.assertEqual(gen.patch_brick_sidi(once), once)

    def test_patch_brick_sidi_without_those_blocks_changes_nothing(self):
        self.assertEqual(gen.patch_brick_sidi("<x>" + CTC_BLOCK % 99 + "</x>"), "<x>" + CTC_BLOCK % 99 + "</x>")


class Apply(unittest.TestCase):
    PANEL = ('<paneleditor class="x" name="USS CTC" x="1" y="2" height="3" width="4">\n'
             '    <positionablelabel x="0" y="9" level="3"><icon url="preference:ctc/icons/old.gif" scale="1"/>'
             '</positionablelabel>\n'
             '    <turnouticon turnout="Gone" x="1" y="1"><closed url="a"/></turnouticon>\n'
             '    <sensoricon sensor="BS Gone" x="1" y="1"><active url="a"/></sensoricon>\n'
             '    <sensoricon sensor="IS5:CB" x="1" y="1"><active url="a"/></sensoricon>\n'
             '    <positionablelabel x="3" y="3" level="4" text="BRICK" size="12"></positionablelabel>\n'
             '    <positionablelabel x="3" y="3" level="4" text="Keep me" size="12"></positionablelabel>\n'
             '    <signalmasticon signalmast="Old"/>\n'
             '  </paneleditor>\n')

    def applied(self):
        with fixture_board():
            return gen.apply(self.PANEL, FIXTURE_CELLS)

    def test_apply_drops_generated_items_and_keeps_the_rest(self):
        out = self.applied()
        for gone in ("Gone", "BS Gone", "old.gif", 'sensor="IS5:CB" x="1"'):
            self.assertNotIn(gone, out)
        self.assertIn('text="Keep me"', out)
        self.assertEqual(out.count('<turnouticon turnout="Switch 1"'), 1)

    def test_apply_sets_the_panel_size_and_places_the_block_before_the_close_tag(self):
        out = self.applied()
        self.assertIn(f'x="40" y="40" height="{gen.PANEL_H}" width="{gen.PANEL_W}"', out)
        self.assertTrue(out.rstrip().endswith("</paneleditor>"))
        self.assertLess(out.index("Panel-left-7.gif"), out.rindex("</paneleditor>"))

    def test_apply_is_idempotent_through_the_generator(self):
        once = self.applied()
        with fixture_board():
            twice = gen.apply(once, FIXTURE_CELLS)
        self.assertEqual(twice, once)

    def test_apply_without_the_close_tag_stops(self):
        with fixture_board(), self.assertRaises(ValueError):
            gen.apply("<paneleditor></x>", FIXTURE_CELLS)

    def test_apply_on_a_text_with_no_paneleditor_open_tag_still_adds_the_block(self):
        with fixture_board():
            out = gen.apply("</paneleditor>", FIXTURE_CELLS)
        self.assertIn("Panel-left-7.gif", out)


class ParkedTarget(unittest.TestCase):
    def test_the_checkouts_tables_are_left_alone_while_uss_is_parked(self):
        from hartlib import parked
        with mock.patch.object(parked, "PARKED", frozenset({"uss"})), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertTrue(gen.parked_target(gen.OUTPUT_TABLES))
        self.assertIn("the USS CTC machine is parked", out.getvalue())

    def test_other_files_and_an_unparked_machine_are_written(self):
        from hartlib import parked
        with mock.patch.object(parked, "PARKED", frozenset({"uss"})):
            self.assertFalse(gen.parked_target(Path("/nonexistent/other-tables.xml")))
        with mock.patch.object(parked, "PARKED", frozenset({"nx"})):
            self.assertFalse(gen.parked_target(gen.OUTPUT_TABLES))


class LeverColumns(unittest.TestCase):
    """uss_columns on switch rows built for the test; the other error paths are in test_uss_switch_levers."""

    @staticmethod
    def sw(level, slot, ctc_is, signals):
        return mock.Mock(level=level, uss_slot=slot, ctc_is=ctc_is, ctc_signals=signals)

    def test_columns_from_switch_rows(self):
        cols = gen.uss_columns({"1": self.sw(1, 0, 1, True), "5": self.sw(1, 2, 5, False)})
        self.assertEqual(cols["n_slots"], 3)
        self.assertEqual(cols["blank"], {1})
        self.assertEqual(cols["switch_only"], {2})
        self.assertEqual(cols["sw_num"], {0: 1, 2: 5})
        self.assertEqual(cols["lock_uid"], {0: 2, 2: 6})
        self.assertEqual(cols["uid_slot"], {1: 0, 2: 0, 5: 2, 6: 2})

    def test_a_level_outside_the_board_stops_naming_it(self):
        with self.assertRaisesRegex(SystemExit, r"level\(s\) 2: "):
            gen.uss_columns({"1": self.sw(1, 0, 1, True), "9": self.sw(2, 1, 3, True)})


class ImportersCall(unittest.TestCase):
    """The parts check_layout_facts.py (the one live importer) reads: build_geometry's four lists and CREAM."""

    def test_build_geometry_returns_turnouts_tracks_lamps_texts_of_fixed_shape(self):
        with fixture_board():
            turnouts, tracks, lamps, texts = gen.build_geometry(FIXTURE_CELLS)
        self.assertTrue(all(len(t) == 4 for t in turnouts))
        self.assertTrue(all(len(t) == 4 for t in tracks))
        self.assertTrue(all(len(t) == 4 for t in lamps))
        self.assertTrue(all(len(t) == 5 for t in texts))

    def test_cream_is_the_label_colour_the_check_looks_for(self):
        self.assertEqual(gen.CREAM, dict(red=220, green=220, blue=180))
        self.assertTrue(any(r"red=\"220\" green=\"220\" blue=\"180\"" in p.pattern for p in gen.STRIP))


if __name__ == "__main__":
    unittest.main()
