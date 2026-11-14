"""Static export of recorded speed-match runs for the website."""
from __future__ import annotations

import json
import re
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


def labels(d, runs=None, skip=None):
    f = Path(d) / "labels.json"
    f.write_text(json.dumps({"runs": runs or {}, "skip": skip or {}}))
    return f


STEPRUN = "\n".join([
    "%.3f RUN loco=CSX 2121 direction=forward" % T,
    "%.3f CFG route=loop1 mode=distance steps=8 target_mm=6000 min_blocks=2 max_s=60 rel=0.03 warm_s=0 warm_step=48 cv3=26 cv4=24 mid=x" % T,
    "%.3f STEP 8" % (T + 1),
    "%.3f STOP all steps complete" % (T + 2),
    "%.3f END" % (T + 2),
]) + "\n"


class Export(unittest.TestCase):
    def test_unlabelled_log_stops_the_export(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "steprun_CSX_1_forward_20260101_000000.log").write_text("%.3f RUN loco=1 direction=forward\n" % T)
            (Path(d) / "moveto_CSX_1_20260101_000000.log").write_text("%.3f x\n" % T)
            with self.assertRaises(SystemExit):
                ex.export(d, Path(d) / "out", labels(d))

    def test_moveto_logs_are_not_read(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "moveto_CSX_1_20260101_000000.log").write_text("%.3f x\n" % T)
            self.assertEqual(ex.read_published(d), [])

    def test_a_log_with_no_readable_line_is_named_and_leaves_the_output_as_it_was(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out"
            (out / "runs").mkdir(parents=True)
            (out / "index.json").write_text('{"runs": []}')
            name = "steprun_CSX_2121_forward_20260101_000000.log"
            (Path(d) / name).write_text("not a log line\n")
            lab = labels(d, {name: {"level": "used", "headline": "Used", "text": "x"}})
            with self.assertRaises(SystemExit) as cm:
                ex.export(d, out, lab)
            self.assertIn(name, str(cm.exception))
            self.assertEqual((out / "index.json").read_text(), '{"runs": []}')
            self.assertFalse((Path(d) / "out.new").exists())

    def test_runs_of_other_sessions_are_kept(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out"
            (out / "runs").mkdir(parents=True)
            (out / "runs" / "older.json").write_text("{}")
            (out / "index.json").write_text(json.dumps({"runs": [{"id": "older", "file": "runs/older.json", "start": 1.0}]}))
            logs = Path(d) / "logs"; logs.mkdir()
            name = "steprun_CSX_2121_forward_20260101_000000.log"
            (logs / name).write_text(STEPRUN)
            skipped = "stoptest_CSX_2121_reverse_20260101_000100.log"
            (logs / skipped).write_text("%.3f STOP x\n" % T)
            lab = labels(d, {name: {"level": "used", "headline": "Used", "text": "x"}}, {skipped: "spoiled"})
            idx = ex.export(logs, out, lab)
            self.assertEqual([r["id"] for r in idx], [name[:-4], "older"])
            self.assertTrue((out / "runs" / "older.json").exists())
            self.assertTrue((out / "runs" / (name[:-4] + ".json")).exists())
            self.assertFalse((out / "runs" / (skipped[:-4] + ".json")).exists())

    def test_an_unknown_level_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                ex.load_labels(labels(d, {"a.log": {"level": "maybe", "headline": "", "text": ""}}))


class SharedMarkup(unittest.TestCase):
    """The website page repeats the live page's panels; every id app.js looks up must be in both."""
    def test_every_id_app_js_uses_is_on_both_pages(self):
        app = (DASH / "static" / "app.js").read_text()
        ids = set(re.findall(r'\$\("([\w-]+)"\)', app))
        ids -= set(re.findall(r'if \(\$\("([\w-]+)"\)\)', app))  # guarded: only one page has it
        self.assertTrue(ids)
        repo = DASH.parents[5]
        for page in (DASH / "static" / "index.html", repo / "www" / "ai" / "speed-runs.html"):
            html = page.read_text()
            have = set(re.findall(r'id="([\w-]+)"', html))
            self.assertEqual(sorted(ids - have), [], page.name)


if __name__ == "__main__":
    unittest.main()
