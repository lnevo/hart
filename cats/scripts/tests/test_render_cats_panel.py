"""render_cats_panel draws a TRACKPLAN's cells and refuses a panel it cannot draw with a PanelError."""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import digicon_lib  # noqa: E402
import render_cats_panel as rcp  # noqa: E402

PLAN = """<PANEL><TRACKPLAN>
  <SECTION X="3" Y="2"><TRACKGROUP><TRACK>HORIZONTAL</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="LEFT"><BLOCK NAME="Track West"/></SEC_EDGE><SEC_EDGE EDGE="RIGHT"><BLOCK NAME="Track West"/></SEC_EDGE></SECTION>
  <SECTION X="4" Y="2"><TRACKGROUP><TRACK>HORIZONTAL</TRACK><TRACK>LOWERBACKSLASH</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="LEFT"><SWITCHPOINTS/></SEC_EDGE><SEC_EDGE EDGE="RIGHT"/></SECTION>
  <SECTION X="5" Y="3"><SEC_NAME NAME="West"/></SECTION>
</TRACKPLAN></PANEL>"""


class Panel(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, text: str) -> Path:
        p = self.dir / "panel.xml"
        p.write_text(text, encoding="utf-8")
        return p


class TrackLine(unittest.TestCase):
    def test_every_digicon_kind_joins_its_two_edges_in_left_right_top_bottom_order(self) -> None:
        order = ("LEFT", "RIGHT", "TOP", "BOTTOM")
        for kind, ends in digicon_lib.TRACK_ENDS.items():
            line = rcp.track_line(kind)
            assert line is not None
            self.assertEqual(set(line), set(ends), kind)
            self.assertLess(order.index(line[0]), order.index(line[1]), kind)
        self.assertEqual(rcp.track_line("UPPERBACKSLASH"), ("RIGHT", "TOP"))

    def test_a_kind_digicon_does_not_know_is_not_drawn(self) -> None:
        self.assertIsNone(rcp.track_line("CROSSING"))
        self.assertIsNone(rcp.track_line(""))


class Draw(Panel):
    def test_the_image_spans_the_cells_and_draws_track_points_and_grid(self) -> None:
        src = self.write(PLAN)
        img = rcp.draw(src, rcp.read_sections(src))
        self.assertEqual(img.size, (rcp.PAD_X * 2 + 3 * rcp.CELL, rcp.PAD_Y + rcp.PAD_Y // 2 + 2 * rcp.CELL))
        x0, y0 = rcp.PAD_X, rcp.PAD_Y                           # cell (3, 2)
        mid = y0 + rcp.CELL // 2
        self.assertEqual(img.getpixel((x0 + 20, mid)), rcp.TRACK)
        self.assertEqual(img.getpixel((x0 + rcp.CELL + 40, mid)), rcp.PLANT)   # plant cell (4, 2)
        self.assertEqual(img.getpixel((x0 + rcp.CELL, mid)), rcp.POINTS)       # its points on the LEFT edge
        self.assertEqual(img.getpixel((x0, y0 + rcp.CELL + 50)), rcp.GRIDLINE)
        self.assertEqual(img.getpixel((x0 + 2 * rcp.CELL + 30, y0 + 1)), rcp.BG)

    def test_render_writes_the_png_and_makes_its_folder(self) -> None:
        out = self.dir / "sub" / "out.png"
        with redirect_stdout(io.StringIO()) as said:
            self.assertEqual(rcp.main([str(self.write(PLAN)), str(out)]), 0)
        self.assertTrue(out.is_file())
        self.assertIn("sections=3", said.getvalue())


class Refused(Panel):
    def assert_refused(self, text: str, why: str) -> None:
        src = self.write(text)
        with self.assertRaisesRegex(rcp.PanelError, why):
            rcp.draw(src, rcp.read_sections(src))
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(rcp.main([str(src), str(self.dir / "out.png")]), 1)
        self.assertIn(str(src), err.getvalue())
        self.assertFalse((self.dir / "out.png").exists())

    def test_no_trackplan(self) -> None:
        self.assert_refused("<PANEL/>", "no TRACKPLAN")

    def test_no_sections(self) -> None:
        self.assert_refused("<PANEL><TRACKPLAN/></PANEL>", "no SECTION")

    def test_a_section_without_a_cell(self) -> None:
        self.assert_refused('<PANEL><TRACKPLAN><SECTION X="1"/></TRACKPLAN></PANEL>', "not a grid cell")

    def test_not_xml(self) -> None:
        self.assert_refused("{}", "cannot read the panel")

    def test_missing_file(self) -> None:
        with self.assertRaisesRegex(rcp.PanelError, "cannot read the panel"):
            rcp.read_sections(self.dir / "absent.xml")

    def test_wrong_argument_count_is_usage(self) -> None:
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(rcp.main(["only.xml"]), 2)
        self.assertIn("usage", err.getvalue())


if __name__ == "__main__":
    unittest.main()
