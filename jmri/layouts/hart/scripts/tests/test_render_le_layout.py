"""render_le_layout and its parts: load_geometry skips hidden track segments, draws circle arcs as JMRI does and stops
on numbers it cannot read; the drawing steps; --kinds; the command's errors."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import render_le_layout  # noqa: E402  first: it puts hartlib on the path for its parts
    import render_le_draw  # noqa: E402
except ModuleNotFoundError as exc:  # CI has no Pillow
    raise unittest.SkipTest(f"render_le_layout needs {exc.name}")

PANEL = """<?xml version="1.0" encoding="UTF-8"?>
<layout-config>
  <LayoutEditor name="HART Railroad" class="jmri.jmrit.display.layoutEditor.configurexml.LayoutEditorXml">
    <positionablepoint ident="A1" type="ANCHOR" x="0.0" y="0.0" />
    <positionablepoint ident="A2" type="ANCHOR" x="10.0" y="0.0" />
    <positionablepoint ident="A3" type="ANCHOR" x="10.0" y="10.0" />
    <tracksegment ident="F1" blockname="Track K-1" connect1name="A1" type1="POS_POINT" connect2name="A2" type2="POS_POINT" mainline="no" hidden="no" />
    <tracksegment ident="F2" blockname="Track K-1" connect1name="A2" type1="POS_POINT" connect2name="A3" type2="POS_POINT" mainline="no" hidden="yes" />
  </LayoutEditor>
</layout-config>
"""


class HiddenSegments(unittest.TestCase):
    def test_hidden_segment_is_not_drawn(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "panel.xml"
            src.write_text(PANEL)
            pp, _legs, _turnouts, segs, _signals, _stations = render_le_layout.load_geometry(src)
        self.assertEqual([(a, b) for a, b, _m, _blk in segs], [((0.0, 0.0), (10.0, 0.0))])
        # the anchor only the hidden segment reaches is not drawn either
        self.assertEqual(sorted(pp), ["A1", "A2"])


ARC = PANEL.replace('mainline="no" hidden="yes" />', 'mainline="no" hidden="no" arc="yes" flip="no" circle="yes" angle="90" />')


class Arcs(unittest.TestCase):
    def test_arc_runs_end_to_end_and_bows_left_of_its_way(self):
        pts = render_le_layout.arc_points((0.0, 0.0), (10.0, 0.0), 90.0, False)
        self.assertAlmostEqual(pts[0][0], 0.0)
        self.assertAlmostEqual(pts[-1][0], 10.0)
        self.assertLess(pts[len(pts) // 2][1], 0.0)       # going east, the arc bows north (up the screen)
        flipped = render_le_layout.arc_points((0.0, 0.0), (10.0, 0.0), 90.0, True)
        self.assertGreater(flipped[len(flipped) // 2][1], 0.0)

    def test_curves_draw_an_arc_segment_as_pieces(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "panel.xml"
            src.write_text(ARC)
            chords = render_le_layout.load_geometry(src)[3]
            curves = render_le_layout.load_geometry(src, curves=True)[3]
        self.assertEqual(len(chords), 2)
        self.assertEqual(len(curves), 1 + 16)
        self.assertEqual(curves[1][0], (10.0, 0.0))
        self.assertAlmostEqual(curves[-1][1][0], 10.0)
        self.assertAlmostEqual(curves[-1][1][1], 10.0)


class ReviewFixes(unittest.TestCase):
    def test_arc_with_no_angle_is_drawn_as_90_degrees(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "panel.xml"
            src.write_text(ARC.replace(' angle="90"', ""))
            curves = render_le_layout.load_geometry(src, curves=True)[3]
        want = render_le_layout.arc_points((10.0, 0.0), (10.0, 10.0), 90.0, False)
        self.assertEqual([c[0] for c in curves[1:]] + [curves[-1][1]], want)

    def test_curve_shape_is_a_circle_and_open_shapes_stay_open(self):
        import math
        R = 10 / math.cos(math.pi / 8)
        pts = [(R * math.cos(math.pi / 8 + i * math.pi / 4), R * math.sin(math.pi / 8 + i * math.pi / 4), "Curve")
               for i in range(8)]
        outline = render_le_layout.shape_outline(pts, "Closed")
        for q in outline:
            self.assertAlmostEqual(math.hypot(*q), 10.0, delta=0.4)
        line = render_le_layout.shape_outline([(0, 0, "Straight"), (10, 0, "Curve")], "Open")
        self.assertEqual(line[0], (0, 0))
        self.assertEqual(line[-1], (10, 0))                 # two points: a line, not dropped, not closed

    def test_labels_count_toward_the_picture(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "panel.xml"
            src.write_text(PANEL.replace("</LayoutEditor>", '<positionablelabel x="-200" y="0" text="FAR WEST" '
                                         'size="10" style="1"/></LayoutEditor>'))
            geometry = render_le_layout.load_geometry(src)
            decor = render_le_layout.load_decor(src)
            outs = []
            for i, dec in enumerate((None, decor)):
                out = Path(d) / f"{i}.png"
                with contextlib.redirect_stdout(io.StringIO()):
                    render_le_layout.render_view(*geometry, out, "t", "", decor=dec)
                outs.append(out)
            from PIL import Image
            sizes = []
            for o in outs:
                with Image.open(o) as im:
                    sizes.append(im.size)
            (w0, h0), (w1, h1) = sizes
            self.assertGreater(w1 / h1, w0 / h0)        # the picture widened to take in the label far to the west



class MastKinds(unittest.TestCase):
    """--kinds: mast user names to kinds from a schematic signals file; a file it cannot use stops."""

    def write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(Path(f.name).unlink)
        return f.name

    def test_kinds_by_mast_user_name(self):
        path = self.write('{"signals": [{"mast": "2L", "kind": "field"}, {"mast": "4LA", "kind": "virtual"}]}')
        self.assertEqual(render_le_layout.mast_kinds(path), {"Mast 2L": "field", "Mast 4LA": "virtual"})

    def test_the_default_signals_file_is_hartlibs(self):
        from hartlib import layer_files, paths
        self.assertEqual(render_le_layout.KINDS_FILE, layer_files.path("signals"))
        self.assertEqual(render_le_layout.KINDS_FILE.parent, paths.LAYOUT_DATA / "schematic")

    def test_the_repo_signals_file_reads(self):
        kinds = render_le_layout.mast_kinds(render_le_layout.KINDS_FILE)
        self.assertTrue(kinds)
        self.assertTrue(set(kinds.values()) <= set(render_le_layout.KIND_COLOUR))

    def test_the_repo_sections_read_by_sheet(self):
        staging = render_le_layout.mast_kinds(render_le_layout.KINDS_FILE)
        main_upper = render_le_layout.mast_kinds(render_le_layout.KINDS_FILE, "main_upper")
        self.assertTrue(staging and main_upper)
        self.assertNotEqual(staging, main_upper)
        self.assertTrue(all(name.startswith("Mast ") for name in [*staging, *main_upper]))
        with self.assertRaisesRegex(render_le_layout.MastKindsError, "no section 'upper'"):
            render_le_layout.mast_kinds(render_le_layout.KINDS_FILE, "upper")

    def test_a_sheet_for_a_plain_file_stops(self):
        path = self.write('{"signals": [{"mast": "2L", "kind": "field"}]}')
        with self.assertRaisesRegex(render_le_layout.MastKindsError, "--kinds-sheet main_upper: .* has no sections"):
            render_le_layout.mast_kinds(path, "main_upper")

    def test_a_sectioned_file_without_plan_overrides_beside_it_takes_mast(self):
        path = self.write('{"_sections": true, "staging": {"signals": [{"mast": "2L", "kind": "field"}]}}')
        self.assertEqual(render_le_layout.mast_kinds(path), {"Mast 2L": "field"})
        with self.assertRaisesRegex(render_le_layout.MastKindsError, "no section 'main_upper'"):
            render_le_layout.mast_kinds(path, "main_upper")

    def test_a_file_it_cannot_use_stops(self):
        for text in ("not json", '{"masts": []}', '{"signals": [{"mast": "2L", "kind": "phantom"}]}',
                     '{"signals": [{"kind": "field"}]}', '{"signals": ["2L"]}'):
            with self.subTest(text=text), self.assertRaises(render_le_layout.MastKindsError):
                render_le_layout.mast_kinds(self.write(text))
        with self.assertRaises(render_le_layout.MastKindsError):
            render_le_layout.mast_kinds("/nonexistent/signals.json")
        with self.assertRaises(render_le_layout.MastKindsError):                       # one mast, two kinds
            render_le_layout.mast_kinds(self.write('{"signals": [{"mast": "4LA", "kind": "virtual"}, '
                                                   '{"mast": "4LA", "kind": "planned"}]}'))


class ViewSteps(unittest.TestCase):
    def test_segments_are_named_and_still_unpack(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "panel.xml"
            src.write_text(PANEL, encoding="utf-8")
            seg = render_le_layout.load_geometry(src)[3][0]
        self.assertEqual((seg.a, seg.b, seg.main, seg.block), ((0.0, 0.0), (10.0, 0.0), False, "Track K-1"))
        a, b, main, block = seg
        self.assertEqual((a, block), ((0.0, 0.0), "Track K-1"))

    def test_crossover_diagonals_are_the_pair_that_crosses(self):
        a, b, c, dd = (0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)
        self.assertEqual(render_le_draw._xover_diagonals(a, b, c, dd, "LH_XOVER"), (a, c, b, dd))
        # legs stored mirrored: A-D and B-C cross, whatever the type says
        self.assertEqual(render_le_draw._xover_diagonals(a, b, dd, c, "LH_XOVER"), (a, c, b, dd))
        flat = (0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)   # all on one line: only a touch counts
        self.assertTrue(render_le_draw._crosses(*flat[:2], (1.0, 0.0), (4.0, 0.0)))
        far = (0.0, 0.0), (10.0, 0.0), (5.0, 10.0), (5.0, 1.0)   # D inside A-B-C: neither pair crosses
        self.assertEqual(render_le_draw._xover_diagonals(*far, "RH_XOVER"), (far[0], far[3], far[1], far[2]))
        self.assertEqual(render_le_draw._xover_diagonals(*far, "LH_XOVER"), (far[0], far[2], far[1], far[3]))

    def test_frame_maps_panel_points_inside_the_margins(self):
        f = render_le_draw._frame([(100.0, 50.0), (300.0, 150.0)], 2000, None)
        pad, top = render_le_layout.PAD, render_le_layout.TOP
        self.assertEqual(f.pt((100.0 - pad, 50.0 - pad)), (pad, top))
        self.assertEqual(f.width, round((200 + 2 * pad) * f.scale + 2 * pad))
        self.assertEqual(render_le_draw._frame([(0.0, 0.0), (5000.0, 0.0)], 2000, None).scale, 1.0)  # never below 1
        self.assertEqual(render_le_draw._frame([(0.0, 0.0), (10.0, 0.0)], 2000, 0.5).scale, 0.5)

    def test_an_empty_window_writes_nothing_and_half_a_window_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "panel.xml"
            src.write_text(PANEL, encoding="utf-8")
            geometry = render_le_layout.load_geometry(src)
            out = Path(d) / "out.png"
            render_le_layout.render_view(*geometry, out, "t", "", 5000.0, 6000.0)
            self.assertFalse(out.exists())
            with self.assertRaisesRegex(ValueError, "xmin given without xmax"):
                render_le_layout.render_view(*geometry, out, "t", "", 0.0, None)


class PanelErrors(unittest.TestCase):
    """A panel item whose numbers do not read, or a file without the panel, is a RenderError naming it; the command
    says so and returns 1."""

    def load(self, text, **kw):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "panel.xml"
            src.write_text(text, encoding="utf-8")
            return render_le_layout.load_geometry(src, **kw)

    def test_a_mast_icon_with_a_bad_number_stops(self):
        bad = PANEL.replace("</LayoutEditor>", '<signalmasticon signalmast="Mast 2L" x="ten" y="0"/></LayoutEditor>')
        with self.assertRaisesRegex(render_le_layout.RenderError, r'signalmast="Mast 2L".*x=\'ten\' is not a number'):
            self.load(bad)

    def test_a_station_icon_with_a_bad_number_stops(self):
        bad = PANEL.replace("</LayoutEditor>", '<sensoricon sensor="MoveToA_stored" x="1" y="?"/></LayoutEditor>')
        with self.assertRaisesRegex(render_le_layout.RenderError, r'sensor="MoveToA_stored".*y=\'\?\''):
            self.load(bad)

    def test_an_anchor_with_no_x_stops(self):
        with self.assertRaisesRegex(render_le_layout.RenderError, r'ident="A1"\>: no x'):
            self.load(PANEL.replace('ident="A1" type="ANCHOR" x="0.0"', 'ident="A1" type="ANCHOR"'))

    def test_icons_read_with_their_defaults(self):
        good = PANEL.replace("</LayoutEditor>", '<signalmasticon signalmast="Mast 2L" x="3" y="4" degrees="450"/>'
                             '<sensoricon sensor="MoveToYard_stored" x="5" y="6"/></LayoutEditor>')
        _pp, _legs, _t, _segs, signals, stations = self.load(good)
        self.assertEqual((signals[0]["x"], signals[0]["degrees"]), (3.0, 90))
        self.assertEqual(stations, [{"name": "Yard", "x": 5.0, "y": 6.0}])

    def test_a_file_without_the_panel_stops(self):
        with self.assertRaisesRegex(render_le_layout.RenderError, "no Layout Editor panel named Other"):
            self.load(PANEL, panel="Other")

    def test_the_command_reports_and_returns_one(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "panel.xml"
            src.write_text(PANEL, encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = render_le_layout.main([str(src), str(Path(d) / "o.png"), "--panel", "Other"])
            self.assertEqual(rc, 1)
            self.assertIn("no Layout Editor panel named Other", err.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(render_le_layout.main([str(src), str(Path(d) / "o.png")]), 0)
            self.assertTrue((Path(d) / "o.png").is_file())

    def test_the_sources_are_the_three_parts(self):
        self.assertEqual([p.name for p in render_le_layout.SOURCES],
                         ["render_le_layout.py", "render_le_geometry.py", "render_le_draw.py"])
        self.assertTrue(all(p.is_file() for p in render_le_layout.SOURCES))


if __name__ == "__main__":
    unittest.main()
