"""gen_ctc_track_plan (the USS CTC board generator): golden outputs and unit tests on its pieces and error paths.

Who uses it: the USS CTC machine is parked (hartlib.parked), so nothing live runs it as a build step. The one live
caller is tools/audit/check_layout_facts.py (in tools/check.sh), which imports it for build_geometry() and CREAM.
The other callers are tests: test_uss_switch_levers.py (rebuild of the committed files, byte-identical),
test_ctc_signal_heads.py, test_uss_board_cells.py, parked/tests/test_occupancy_lamps_display_only.py, and
cats/scripts/tests/test_generated_desk_from_scratch.py (runs it with --xml-only and expects the files unchanged).
refresh_bean_comments.py only lists the file as a path it edits. These tests cover the importer's parts and the rest
of the generator, so it keeps working until the machine is unparked.

The input is a small fixture, not the live board: the module's data tables (PLANTS, SIGNALS, the lever columns) are
patched for each test, and the writes go into temp dirs, so a change to switches.csv, mast_cells.csv or the frozen
board grid does not move these tests. (The live data is held by test_uss_switch_levers, test_ctc_signal_heads and
test_uss_board_cells, including a rebuild of the committed files that must be byte-identical.)

The golden file golden/gen_ctc_track_plan.json holds what the generator writes for the fixture today: the board's
XML block, line by line, and a pixel digest of each icon GIF it draws. Refresh it after an intended change to the
script with
`UPDATE_GOLDEN=1 python3 -m unittest discover -s jmri/layouts/hart/scripts/tests -p test_gen_ctc_track_plan.py`
and read the diff before committing it.

Not covered: render_preview's drawing (only that it writes a PNG of the right size); it needs a JMRI install for its
icons and fonts.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import gen_ctc_track_plan as gen  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden/gen_ctc_track_plan.json"

# the fixture board: three lever slots (slot 1 has no switch: a blank plate; slot 2 has no signal levers), one
# plant (Switch 1 on OS Switch 1) and two signals
FIXTURE_COLUMNS = dict(
    N_SLOTS=3,
    BLANK_SLOTS={1},
    SWITCH_ONLY_SLOTS={2},
    SLOT_SW_NUM={0: 1, 2: 5},
    SLOT_LOCK_UID={0: 2, 2: 6},
    UID_SLOT={1: 0, 2: 0, 5: 2, 6: 2},
    PLANTS={(4, 7): ("Switch 1", False)},
    OS_FROG={"OS Switch 1": (4, 7)},
    SIGNALS=[("Mast 1", 3, 7, "E", "h2", None), ("Mast 2", 2, 6, "W", "d1", "IH9")],
    STATION_NAMES={"BRICK"},
)
FIXTURE_CELLS = {
    (1, 6): dict(tracks=["HORIZONTAL"], name="Track A", blocks=[("LEFT", "Track A", "BS A")]),
    (2, 6): dict(tracks=["HORIZONTAL", "UPPERSLASH"], name=None, blocks=[("RIGHT", "Track A", "BS A")]),
    (3, 7): dict(tracks=["HORIZONTAL"], name=None, blocks=[("LEFT", "OS Switch 1", "BS OS 1")]),
    (4, 7): dict(tracks=["HORIZONTAL", "LOWERBACKSLASH"], name=None, blocks=[("RIGHT", "OS Switch 1", "BS OS 1")]),
    (5, 8): dict(tracks=["VERTICAL"], name="Track B, PA", blocks=[("TOP", "Track B", "BS B")]),
    (6, 2): dict(tracks=[], name="BRICK", blocks=[]),
    (7, 2): dict(tracks=[], name="DS-CTC  Rev A  Eff 2026-11-12", blocks=[]),
    (8, 9): dict(tracks=["HORIZONTAL"], name="Track Main East", blocks=[]),
    (1, 20): dict(tracks=["HORIZONTAL"], name=None, blocks=[("RIGHT", "Track Far", "BS Far")]),  # off the board rows
}


def fixture_board():
    """Patch the module's board data to the fixture; use as a context manager."""
    stack = contextlib.ExitStack()
    for name, value in FIXTURE_COLUMNS.items():
        stack.enter_context(mock.patch.object(gen, name, value))
    return stack


def sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:12]


def icon_digest(folder: Path) -> dict:
    """File name -> size and a hash of the decoded pixels (so it does not depend on the GIF encoder's bytes)."""
    from PIL import Image
    out = {}
    for p in sorted(folder.glob("*.gif")):
        with Image.open(p) as raw:
            im = raw.convert("RGBA")
        out[p.name] = dict(size=list(im.size), pixels=sha(im.tobytes()))
    return out


def written_icons(folder: Path) -> dict:
    """write_cell_icons into folder, with no JMRI install to copy stock icons from."""
    with mock.patch.object(gen, "THIN_DIR", folder), mock.patch.object(gen, "JMRI_RES", folder / "no-jmri"):
        gen.write_cell_icons()
    return icon_digest(folder)


def current_golden() -> dict:
    with fixture_board():
        block = gen.build_block(FIXTURE_CELLS)
    with tempfile.TemporaryDirectory() as t:
        icons = written_icons(Path(t))
    return dict(block=block.split("\n"), icons=icons)


class Golden(unittest.TestCase):
    def test_board_block_and_icons_match_the_golden_snapshot(self):
        got = current_golden()
        if os.environ.get("UPDATE_GOLDEN") == "1":
            GOLDEN.parent.mkdir(exist_ok=True)
            GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            self.skipTest(f"UPDATE_GOLDEN set: wrote {GOLDEN}")
        self.assertTrue(GOLDEN.is_file(), f"{GOLDEN} is missing: UPDATE_GOLDEN=1 writes it")
        want = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(got["icons"], want["icons"],
                         "an icon GIF differs from the golden snapshot (UPDATE_GOLDEN=1 refreshes it after an intended change)")
        bad = [i + 1 for i, (a, b) in enumerate(zip(got["block"], want["block"])) if a != b]
        self.assertFalse(bad, f"board XML lines differ from the golden snapshot: {bad[:10]} "
                              f"(UPDATE_GOLDEN=1 refreshes it after an intended change)")
        self.assertEqual(len(got["block"]), len(want["block"]), "the board XML has a different number of lines")

    def test_block_has_the_expected_parts(self):
        with fixture_board():
            block = gen.build_block(FIXTURE_CELLS)
        counts = {tag: len(re.findall(rf"<{tag}\b", block))
                  for tag in ("turnouticon", "sensoricon", "signalmasticon", "signalheadicon", "multisensoricon")}
        # one turnout dot; the signals draw one mast and one head icon
        self.assertEqual(counts["turnouticon"], 1)
        self.assertEqual(counts["signalmasticon"], 1)
        self.assertEqual(counts["signalheadicon"], 1)
        # the blank slot 1 has no levers: only slots 0 and 2 get a lock toggle
        self.assertEqual(sorted(re.findall(r'sensor="IS(\d+):LOCKTOGGLE"', block)), ["2", "6"])
        # slot 2 is switch-only: its signal plate (6) is not drawn, the switch plate (5) is
        self.assertIn('text="5"', block)
        self.assertNotIn('text="6"', block)
        self.assertIn('text="1"', block)
        self.assertIn('text="2"', block)

    def test_icons_are_written_for_every_cell_kind(self):
        with tempfile.TemporaryDirectory() as t:
            names = set(written_icons(Path(t)))
        self.assertEqual(names, {"cell-us.gif", "cell-ls.gif", "cell-ub.gif", "cell-lb.gif", "stock-h.gif",
                                 "stock-v.gif", "stock-end.gif", "pts-closed.gif", "pts-thrown.gif",
                                 "pts-unknown.gif", "pts-inconsistent.gif"})


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


class Icons(unittest.TestCase):
    def test_resolve_icon(self):
        self.assertEqual(gen.resolve_icon("program:resources/icons/a.gif"), gen.JMRI_RES / "icons/a.gif")
        self.assertEqual(gen.resolve_icon("preference:ctc/icons/pts-closed.gif"), gen.THIN_DIR / "pts-closed.gif")
        self.assertIsNone(gen.resolve_icon("http://x/a.gif"))

    def test_stock_icons_are_cut_from_the_jmri_install_when_it_is_there(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            res = Path(t) / "res"
            block = res / "icons/USS/track/block"
            block.mkdir(parents=True)
            line = Image.new("RGBA", (24, 8), (0, 0, 0, 255))        # black background is punched out
            line.paste((255, 255, 255, 255), (0, 2, 24, 5))
            line.save(block / "line025.gif")
            Image.new("RGBA", (26, 16), (255, 255, 255, 255)).save(block / "eotwht.gif")
            out = Path(t) / "out"
            with mock.patch.object(gen, "THIN_DIR", out), mock.patch.object(gen, "JMRI_RES", res):
                gen.write_cell_icons()
            with Image.open(out / "stock-h.gif") as raw:
                h = raw.convert("RGBA")
            self.assertEqual(h.size, (24, 8))
            self.assertEqual(h.getpixel((5, 0))[3], 0)               # background transparent
            self.assertEqual(h.getpixel((5, 3))[3], 255)             # the white bar stays
            for name, size in (("stock-v.gif", (8, 24)), ("stock-end.gif", (26, 16))):
                with Image.open(out / name) as im:
                    self.assertEqual(im.size, size, name)

    def test_save_gif_maps_colours_to_the_palette(self):
        from PIL import Image
        im = Image.new("RGBA", (4, 1), (0, 0, 0, 0))
        for x, rgba in enumerate([(255, 255, 255, 255), (255, 170, 40, 255), (255, 40, 40, 255)], start=1):
            im.putpixel((x, 0), rgba)
        with tempfile.TemporaryDirectory() as t:
            gen._save_gif(im, Path(t) / "a.gif")
            with Image.open(Path(t) / "a.gif") as back:
                back = back.convert("RGBA")
                got = [back.getpixel((x, 0)) for x in range(4)]
        self.assertEqual(got[0][3], 0, "pixel 0 is transparent")
        self.assertEqual(got[1:], [(255, 255, 255, 255), (255, 170, 40, 255), (255, 40, 40, 255)])

    def test_install_preference_icons_copies_into_user_files_and_profiles(self):
        with tempfile.TemporaryDirectory() as t:
            home = Path(t) / "home"
            thin = Path(t) / "thin"
            gui = Path(t) / "GUIObjects.xml"
            thin.mkdir()
            (thin / "a.gif").write_bytes(b"GIF-A")
            gui.write_bytes(b"<gui/>")
            (home / "JMRI_UserFiles" / "x.jmri").mkdir(parents=True)
            with mock.patch.object(Path, "home", return_value=home), \
                    mock.patch.object(gen, "THIN_DIR", thin), mock.patch.object(gen, "GUI_XML", gui):
                written = gen.install_preference_icons()
            base = home / "JMRI_UserFiles"
            self.assertEqual(sorted(written), sorted([base / "ctc/icons/a.gif", base / "ctc/GUIObjects.xml",
                                                      base / "x.jmri/ctc/icons/a.gif",
                                                      base / "x.jmri/ctc/GUIObjects.xml"]))
            self.assertEqual((base / "ctc/icons/a.gif").read_bytes(), b"GIF-A")
            self.assertEqual((base / "x.jmri/ctc/GUIObjects.xml").read_bytes(), b"<gui/>")

    def test_install_preference_icons_with_nothing_to_copy_or_nowhere_to_copy(self):
        with tempfile.TemporaryDirectory() as t:
            home, thin = Path(t) / "home", Path(t) / "thin"
            thin.mkdir()
            with mock.patch.object(Path, "home", return_value=home), mock.patch.object(gen, "THIN_DIR", thin):
                self.assertEqual(gen.install_preference_icons(), [])          # no JMRI_UserFiles
                (home / "JMRI_UserFiles").mkdir(parents=True)
                self.assertEqual(gen.install_preference_icons(), [])          # no GIFs
                self.assertFalse((home / "JMRI_UserFiles/ctc").exists())

    def test_render_preview_writes_a_png_at_double_scale(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "sub" / "p.png"
            with mock.patch.object(gen, "JMRI_RES", Path(t) / "no-jmri"), \
                    mock.patch.object(gen, "THIN_DIR", Path(t) / "no-thin"), \
                    contextlib.redirect_stdout(io.StringIO()) as printed:
                gen.render_preview('<sensoricon sensor="IS1:LEVER" x="1" y="2"/>', out)
            with Image.open(out) as png:
                self.assertEqual(png.size, (gen.PANEL_W * 2, 560 * 2))
            self.assertIn("preview", printed.getvalue())


class Main(unittest.TestCase):
    """main() on temp copies: the arguments, the refusals and what it writes."""

    GUI_TEXT = '<layout>\n  <paneleditor name="USS CTC" x="1" y="1" height="1" width="1">\n  </paneleditor>\n</layout>\n'
    TABLES_TEXT = ('<tables>\n<other/>\n  <paneleditor name="USS CTC" x="1" y="1" height="1" width="1">\n'
                   '  </paneleditor>\n</tables>\n')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.gui = self.dir / "GUIObjects.xml"
        self.tables = self.dir / "tables.xml"
        self.gui.write_text(self.GUI_TEXT, encoding="utf-8")
        self.tables.write_text(self.TABLES_TEXT, encoding="utf-8")
        repo_before = gen.OUTPUT_TABLES.read_bytes()
        self.addCleanup(lambda: self.assertEqual(gen.OUTPUT_TABLES.read_bytes(), repo_before,
                                                 "a test changed the repo's tables.xml"))

    def run_main(self, *argv, running=False, cells=None, **patches):
        with contextlib.ExitStack() as stack:
            stack.enter_context(fixture_board())
            stack.enter_context(mock.patch.object(sys, "argv", ["gen_ctc_track_plan.py", *argv]))
            stack.enter_context(mock.patch.object(gen.hl_tables, "jmri_running", return_value=running))
            stack.enter_context(mock.patch.object(gen.facts, "load_uss_cells", return_value=FIXTURE_CELLS if cells is None else cells))
            stack.enter_context(mock.patch.object(gen, "ensure_columns", side_effect=lambda t: t))
            # whatever PARKED says, a run without --tables must land on the temp copy, never the repo's tables.xml
            patches.setdefault("OUTPUT_TABLES", self.tables)
            patches.setdefault("parked_target", lambda p: False)
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(gen, name, value))
            out = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            gen.main()
        return out.getvalue()

    def test_xml_only_rewrites_the_gui_and_the_tables_panel(self):
        out = self.run_main("--xml-only", "--gui", str(self.gui), "--tables", str(self.tables),
                            parked_target=lambda p: False)
        for path in (self.gui, self.tables):
            text = path.read_text(encoding="utf-8")
            self.assertIn("Panel-left-7.gif", text, path)
            self.assertIn('<turnouticon turnout="Switch 1"', text, path)
        self.assertIn("<other/>", self.tables.read_text(encoding="utf-8"))      # outside the panel untouched
        self.assertIn('editable="false"', self.tables.read_text(encoding="utf-8"))     # the Store's form
        self.assertIn('editable="true"', self.gui.read_text(encoding="utf-8"))         # the generator's own form
        self.assertIn(f"{self.gui}: Digicon track plan regenerated", out)
        self.assertIn("paneleditor replaced, Brick SIDI updated", out)

    def test_a_second_run_changes_nothing(self):
        args = ("--xml-only", "--gui", str(self.gui), "--tables", str(self.tables))
        self.run_main(*args, parked_target=lambda p: False)
        first = (self.gui.read_bytes(), self.tables.read_bytes())
        self.run_main(*args, parked_target=lambda p: False)
        self.assertEqual((self.gui.read_bytes(), self.tables.read_bytes()), first)

    def test_a_running_jmri_stops_a_full_run_before_anything_is_written(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--gui", str(self.gui), running=True)
        self.assertIn("PanelPro or CATS is open", str(cm.exception.code))
        self.assertEqual(self.gui.read_text(encoding="utf-8"), self.GUI_TEXT)

    def test_xml_only_does_not_care_that_jmri_runs(self):
        self.run_main("--xml-only", "--gui", str(self.gui), running=True)
        self.assertIn("Panel-left-7.gif", self.gui.read_text(encoding="utf-8"))

    def test_the_source_tables_are_refused(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--xml-only", "--gui", str(self.gui), "--tables", str(gen.SOURCE_TABLES))
        self.assertEqual(str(cm.exception.code), "refusing to write tables/tables.xml")
        self.assertEqual(self.gui.read_text(encoding="utf-8"), self.GUI_TEXT)

    def test_a_gui_without_a_panel_fails_loudly(self):
        # apply() adds the block before the close tag, so a file with no panel at all cannot be regenerated
        self.gui.write_text("<layout/>", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_main("--xml-only", "--gui", str(self.gui))

    def test_tables_without_a_panel_fail_loudly(self):
        self.tables.write_text("<tables/>", encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "no paneleditor in"):
            self.run_main("--xml-only", "--gui", str(self.gui), "--tables", str(self.tables),
                          parked_target=lambda p: False)

    def test_a_parked_target_is_left_alone(self):
        out = self.run_main("--xml-only", "--gui", str(self.gui), "--tables", str(self.tables),
                            parked_target=lambda p: True)
        self.assertEqual(self.tables.read_text(encoding="utf-8"), self.TABLES_TEXT)
        self.assertNotIn("paneleditor replaced", out)

    def test_the_default_tables_are_used_when_none_is_given(self):
        self.run_main("--xml-only", "--gui", str(self.gui), OUTPUT_TABLES=self.tables, parked_target=lambda p: False)
        self.assertIn("Panel-left-7.gif", self.tables.read_text(encoding="utf-8"))

    def test_the_preview_is_written_when_asked(self):
        png = self.dir / "p.png"
        with mock.patch.object(gen, "JMRI_RES", self.dir / "no-jmri"):
            out = self.run_main("--xml-only", "--gui", str(self.gui), "--preview", str(png))
        self.assertTrue(png.is_file())
        self.assertIn("preview", out)


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
        cols = gen.uss_columns({"1": self.sw("1", 0, 1, True), "5": self.sw("1", 2, 5, False)})
        self.assertEqual(cols["n_slots"], 3)
        self.assertEqual(cols["blank"], {1})
        self.assertEqual(cols["switch_only"], {2})
        self.assertEqual(cols["sw_num"], {0: 1, 2: 5})
        self.assertEqual(cols["lock_uid"], {0: 2, 2: 6})
        self.assertEqual(cols["uid_slot"], {1: 0, 2: 0, 5: 2, 6: 2})

    def test_a_level_outside_the_board_stops_naming_it(self):
        with self.assertRaisesRegex(SystemExit, r"level\(s\) \['2'\]"):
            gen.uss_columns({"1": self.sw("1", 0, 1, True), "9": self.sw("2", 1, 3, True)})


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
