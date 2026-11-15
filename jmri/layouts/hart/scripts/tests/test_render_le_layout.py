"""render_le_layout.load_geometry skips hidden track segments and draws circle arcs as JMRI does."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import render_le_layout  # noqa: E402
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

    def test_the_repo_signals_file_reads(self):
        kinds = render_le_layout.mast_kinds(render_le_layout.KINDS_FILE)
        self.assertTrue(kinds)
        self.assertTrue(set(kinds.values()) <= set(render_le_layout.KIND_COLOUR))

    def test_a_file_it_cannot_use_stops(self):
        for text in ("not json", '{"masts": []}', '{"signals": [{"mast": "2L", "kind": "phantom"}]}',
                     '{"signals": [{"kind": "field"}]}', '{"signals": ["2L"]}'):
            with self.subTest(text=text), self.assertRaises(SystemExit):
                render_le_layout.mast_kinds(self.write(text))
        with self.assertRaises(SystemExit):
            render_le_layout.mast_kinds("/nonexistent/signals.json")
        with self.assertRaises(SystemExit):                       # one mast, two kinds
            render_le_layout.mast_kinds(self.write('{"signals": [{"mast": "4LA", "kind": "virtual"}, '
                                                   '{"mast": "4LA", "kind": "planned"}]}'))


if __name__ == "__main__":
    unittest.main()
