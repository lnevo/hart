"""cats_inspect.py sends each subcommand to its inspector and reads a panel without writing it."""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import cats_inspect  # noqa: E402

# A plant at (2,1) in OS Switch 1: points LEFT, legs RIGHT (to Track Main) and BOTTOM (to Track Siding).
PANEL = """<CATS WIDTH="4" HEIGHT="2"><TRACKPLAN>
  <SECTION X="1" Y="1"><TRACKGROUP><TRACK>HORIZONTAL</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="LEFT"><BLOCK NAME="Track West"/></SEC_EDGE><SEC_EDGE EDGE="RIGHT"/></SECTION>
  <SECTION X="2" Y="1"><TRACKGROUP><TRACK>HORIZONTAL</TRACK><TRACK>LOWERBACKSLASH</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="LEFT"><SWITCHPOINTS><ROUTEINFO ROUTEID="RIGHT" NORMAL="true"/></SWITCHPOINTS></SEC_EDGE>
    <SEC_EDGE EDGE="RIGHT"><BLOCK NAME="OS Switch 1"/></SEC_EDGE><SEC_EDGE EDGE="BOTTOM"/></SECTION>
  <SECTION X="3" Y="1"><TRACKGROUP><TRACK>HORIZONTAL</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="LEFT"><BLOCK NAME="OS Switch 1"/></SEC_EDGE><SEC_EDGE EDGE="RIGHT"><BLOCK NAME="OS Switch 1"/></SEC_EDGE></SECTION>
  <SECTION X="4" Y="1"><TRACKGROUP><TRACK>HORIZONTAL</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="LEFT"><BLOCK NAME="Track Main"/></SEC_EDGE><SEC_EDGE EDGE="RIGHT"/></SECTION>
  <SECTION X="2" Y="2"><TRACKGROUP><TRACK>UPPERSLASH</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="TOP"/><SEC_EDGE EDGE="LEFT"/></SECTION>
  <SECTION X="1" Y="2"><TRACKGROUP><TRACK>HORIZONTAL</TRACK></TRACKGROUP>
    <SEC_EDGE EDGE="RIGHT"/><SEC_EDGE EDGE="LEFT"><BLOCK NAME="Track Siding"/></SEC_EDGE></SECTION>
  <SECTION X="3" Y="2"><SEC_NAME NAME="Brick"/></SECTION>
</TRACKPLAN></CATS>"""


class Dispatch(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.panel = Path(self.tmp.name) / "panel.xml"
        self.panel.write_text(PANEL, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cats_inspect.main(list(argv))
        return rc, out.getvalue()

    def test_each_subcommand_reaches_its_inspector(self) -> None:
        for cmd, func in (("edges", cats_inspect.cmd_edges), ("grid", cats_inspect.cmd_grid),
                          ("trace", cats_inspect.cmd_trace)):
            self.assertIs(cats_inspect.parser().parse_args([cmd, str(self.panel)]).func, func)

    def test_edges_counts_joints_and_totals_two_panels(self) -> None:
        rc, out = self.run_cli("edges", str(self.panel))
        self.assertEqual(rc, 0)
        self.assertIn("--- panel.xml  sections=6", out)
        self.assertNotIn("=== TOTAL", out)
        rc, out = self.run_cli("edges", str(self.panel), str(self.panel))
        self.assertIn("=== TOTAL", out)

    def test_grid_lists_cells_labels_and_blocks(self) -> None:
        rc, out = self.run_cli("grid", str(self.panel))
        self.assertEqual(rc, 0)
        self.assertIn("(2,1) HORIZONTAL+LOWERBACKSLASH", out)
        self.assertIn("LEFT=SP{RIGHT*}", out)
        self.assertIn("(3,2) LABEL 'Brick'", out)
        self.assertIn("-- named blocks (4): OS Switch 1, Track Main, Track Siding, Track West", out)

    def test_trace_one_leg(self) -> None:
        rc, out = self.run_cli("trace", str(self.panel), "2", "1", "BOTTOM")
        self.assertEqual((rc, out.strip()), (0, "Track Siding"))

    def test_trace_every_plant(self) -> None:
        rc, out = self.run_cli("trace", str(self.panel))
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"\(2,1\) OS Switch 1 +points LEFT  RIGHT->Track Main  BOTTOM->Track Siding")

    def test_trace_needs_a_whole_cell_and_leg(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as e:
            cats_inspect.main(["trace", str(self.panel), "2", "1"])
        self.assertEqual(e.exception.code, 2)

    def test_no_subcommand_is_an_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as e:
            cats_inspect.main([])
        self.assertEqual(e.exception.code, 2)

    def test_the_panel_is_not_written(self) -> None:
        before = self.panel.read_bytes()
        for cmd in ("edges", "grid", "trace"):
            self.run_cli(cmd, str(self.panel))
        self.assertEqual(self.panel.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
