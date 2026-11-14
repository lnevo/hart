"""publish_draft.py: what counts as a drawing change, and the date and revision it sets."""
from __future__ import annotations

import contextlib
import datetime
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("publish_draft", ROOT / "tools/schematic/publish_draft.py")
PD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PD)

TODAY = datetime.date(2026, 12, 1)


def sheet(track="M0,0", box_w=330, rev=1, col_w=104):
    """A sheet shaped like the plugin's: drawing, then the title box and the field column last."""
    return (f'<svg>\n<path d="{track}"/>\n'
            f'<rect x="24" y="728" width="{box_w}" height="64" fill="#fff" stroke="#000" stroke-width="1.5"/>\n'
            f'<text x="34" y="748" font-size="14">SYSTEM SCHEMATIC</text>\n'
            f'<rect x="{24 + box_w}" y="728" width="{col_w}" height="64"/>\n'
            f'<text x="362" y="763.8" font-size="9.5" letter-spacing="1">REV {rev}</text>\n</svg>\n')


class DrawingChange(unittest.TestCase):
    def test_title_block_is_not_a_drawing_change(self) -> None:
        self.assertEqual(PD.drawing_only(sheet(rev=1)), PD.drawing_only(sheet(rev=2, col_w=140)))

    def test_track_is(self) -> None:
        self.assertNotEqual(PD.drawing_only(sheet()), PD.drawing_only(sheet(track="M1,0")))

    def test_draft_follows_the_box(self) -> None:
        self.assertIn('<text x="344" y="784"', PD.mark(sheet()))
        self.assertIn('<text x="366" y="784"', PD.mark(sheet(box_w=352)))


class Fields(unittest.TestCase):
    def test_counts_from_main(self) -> None:
        self.assertEqual(PD.next_fields(json.dumps({"revision": 1}), TODAY), ("2026-12-01", 2))
        self.assertEqual(PD.next_fields(json.dumps({"revision": "3"}), TODAY), ("2026-12-01", 4))
        self.assertEqual(PD.next_fields(json.dumps({}), TODAY), ("2026-12-01", 1))
        self.assertEqual(PD.next_fields(None, TODAY), ("2026-12-01", 1))

    def test_lettered_revision_is_left_alone(self) -> None:
        for rev in ("A", "2b", True):
            self.assertIsNone(PD.next_fields(json.dumps({"revision": rev}), TODAY))

    def test_set_fields_keeps_the_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "page.preferences.json"
            p.write_text(json.dumps({"title": ["x"], "date": "2026-11-14", "revision": 1}))
            PD.set_fields(p, "2026-12-01", 2)
            self.assertEqual(json.loads(p.read_text()), {"title": ["x"], "date": "2026-12-01", "revision": 2})


class Lengths(unittest.TestCase):
    def read(self, rows):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "block_lengths.csv"
            csv_path.write_text("user_name,occupancy_sensor,inches,flag,old_source\n" + rows)
            old = PD.LENGTHS
            try:
                PD.LENGTHS = csv_path
                return PD.measured_lengths()
            finally:
                PD.LENGTHS = old

    def test_track_rows_only(self) -> None:
        self.assertEqual(self.read("Track S-1,Block 2-7,212,assigned,\nOS Switch 3,Block 4-1,10,estimate,switch\n"
                                   "Track EH-1,Block 13-7, 24 ,estimate,\nTrack X,Block 9-9,,estimate,\n"),
                         {"S-1": 212.0, "EH-1": 24.0})

    def test_bad_rows_stop(self) -> None:
        with self.assertRaises(SystemExit):
            self.read("Track S-1,Block 2-7,~24,assigned,\n")
        with self.assertRaises(SystemExit):
            self.read("Track S-1,Block 2-7,212,assigned,\nTrack S-1,Block 2-8,200,assigned,\n")


class Preview(unittest.TestCase):
    def test_writes_only_into_the_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prefs = PD.page_prefs().read_text()
            target = (PD.OUT / "schematic-system-draft.svg").read_text()
            printed = []
            real_pdf, PD.pdf = PD.pdf, lambda svg, out: printed.append(out)
            try:
                self.assertEqual(PD.preview(sheet(), Path(tmp) / "out"), 0)
            finally:
                PD.pdf = real_pdf
            self.assertEqual((Path(tmp) / "out/schematic-system-draft.svg").read_text(), sheet())
            self.assertEqual(printed, [Path(tmp) / "out/schematic-system-draft.pdf"])
            self.assertEqual(PD.page_prefs().read_text(), prefs)
            self.assertEqual((PD.OUT / "schematic-system-draft.svg").read_text(), target)

    def test_graphs_are_in_the_repo(self) -> None:
        for graph, _ in PD.INPUTS:
            self.assertTrue((PD.GRAPHS / graph).is_file(), graph)
        self.assertTrue(PD.GRAPHS.is_relative_to(PD.REPO))


class SignalsCheck(unittest.TestCase):
    def setUp(self) -> None:
        spec = importlib.util.spec_from_file_location("build_signals", ROOT / "tools/schematic/build_signals.py")
        self.bs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.bs)
        self.env = {k: os.environ.pop(k) for k in ("SCHEMATIC_PLUGIN", "SCHEMATIC_REQUIRED") if k in os.environ}

    def tearDown(self) -> None:
        os.environ.update(self.env)

    def without_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            real, self.bs.pd.REPO = self.bs.pd.REPO, Path(tmp)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    return self.bs.main(["--check"])
            finally:
                self.bs.pd.REPO = real

    def test_skips_without_the_plugin(self) -> None:
        self.assertEqual(self.without_plugin(), 0)

    def test_skip_fails_when_required(self) -> None:
        os.environ["SCHEMATIC_REQUIRED"] = "1"
        self.assertEqual(self.without_plugin(), 1)

    def run_with(self, plugin_says, committed):
        """main() with the plugin replaced by a script that prints plugin_says and writes {"fresh": 1}."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "bin").mkdir()
            tool = tmp / "bin/schematic"
            tool.write_text(f"#!/bin/sh\nprintf '%s\\n' '{plugin_says}'\necho '{{\"fresh\": 1}}' > \"$5\"\n")
            tool.chmod(0o755)
            (tmp / "staging.signals.json").write_text(committed)
            real = self.bs.pd.plugin, self.bs.pd.DATA
            self.bs.pd.plugin, self.bs.pd.DATA = (lambda: tmp), tmp
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    return self.bs.main(["--check"])
            finally:
                self.bs.pd.plugin, self.bs.pd.DATA = real

    def test_current_passes(self) -> None:
        self.assertEqual(self.run_with("3 masts placed {} | 0 problems", '{"fresh": 1}\n'), 0)

    def test_stale_fails(self) -> None:
        self.assertEqual(self.run_with("3 masts placed {} | 0 problems", '{"old": 1}\n'), 1)

    def test_unplaced_masts_fail(self) -> None:
        with self.assertRaises(SystemExit) as e:
            self.run_with("2 masts placed {} | 1 problems", '{"fresh": 1}\n')
        self.assertIn("not placed", str(e.exception.code))


class Inputs(unittest.TestCase):
    def test_parts_hold_track_positions_only(self) -> None:
        parts = json.loads((PD.GRAPHS / "parts.json").read_text())
        self.assertTrue(parts)
        for p in parts:
            self.assertEqual(set(p), {"name", "eps"})
            for e in p["eps"]:
                self.assertEqual(set(e), {"x", "y", "z"})
                self.assertLess(max(abs(e[k]) for k in "xyz"), 5000)
                self.assertTrue(abs(e["x"]) > 1e-6 or abs(e["y"]) > 1e-6, "endpoint at the origin: corrupt read")

if __name__ == "__main__":
    unittest.main()
