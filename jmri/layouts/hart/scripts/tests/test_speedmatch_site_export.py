"""Static export of recorded speed-match runs for the website."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "speedmatch" / "dashboard"
sys.path.insert(0, str(DASH))
import export_site_runs as ex  # noqa: E402

T = 1794300000.0


class StopTestView(unittest.TestCase):
    def test_seconds_after_the_command_and_rest_block(self):
        lines = [
            "%.3f STOPTEST loco=CSX 2738 direction=forward step=96 trigger=BS K-1" % T,
            "%.3f SENS BS K-2 ACTIVE" % (T + 3),
            "%.3f STOPCMD trigger BS K-1" % (T + 10),
            "%.3f SENS BS K-1 ACTIVE" % (T + 10),
            "%.3f SENS BS West Ext ACTIVE" % (T + 12.5),
            "%.3f STOP quiet" % (T + 20),
        ]
        v = ex.stoptest_view(lines, "stoptest_CSX_2738_forward_x.log")
        self.assertEqual((v["loco"], v["direction"], v["step"], v["trigger"]), ("CSX 2738", "forward", 96, "BS K-1"))
        self.assertEqual(v["rows"], [{"sensor": "BS K-1", "t_rel": 0.0}, {"sensor": "BS West Ext", "t_rel": 2.5}])
        self.assertEqual(v["rest"], "BS West Ext")
        self.assertTrue(v["started"])

    def test_log_that_never_started_takes_loco_from_the_name(self):
        v = ex.stoptest_view(["%.3f STOP guard already ACTIVE: BS X" % T], "stoptest_CSX_2121_reverse_1.log")
        self.assertEqual((v["loco"], v["direction"], v["started"]), ("CSX 2121", "reverse", False))


class Export(unittest.TestCase):
    def test_unlabelled_log_stops_the_export(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "steprun_CSX_1_forward_20260101_000000.log").write_text("%.3f RUN loco=1 direction=forward\n" % T)
            (Path(d) / "moveto_CSX_1_20260101_000000.log").write_text("%.3f x\n" % T)
            with self.assertRaises(SystemExit):
                ex.export(d, Path(d) / "out")

    def test_moveto_logs_are_not_read(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "moveto_CSX_1_20260101_000000.log").write_text("%.3f x\n" % T)
            self.assertEqual(ex.read_published(d), [])


if __name__ == "__main__":
    unittest.main()
