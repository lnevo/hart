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
from unittest import mock

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

    def test_no_draft_mark(self) -> None:
        # the mark came off when the owner approved the helix-join release (2026-11-17)
        self.assertFalse(hasattr(PD, "mark") or hasattr(PD, "DRAFT"))
        for f in [ROOT / "docs/ops/schematic-system-draft.svg", *sorted((ROOT / "docs/ops/stations").glob("*.svg"))]:
            with self.subTest(sheet=f.name):
                self.assertNotIn(">DRAFT<", f.read_text())


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
                with contextlib.redirect_stdout(io.StringIO()):
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


class Calls(unittest.TestCase):
    def test_an_unknown_option_publishes_nothing(self) -> None:
        for argv in (["--help"], ["--chek"], ["--check", "--preview", "/tmp/x"]):
            with self.subTest(argv=argv), mock.patch.object(PD, "draw", side_effect=AssertionError("drew")), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(PD.main(argv), 2)
            self.assertIn("--check | --preview DIR", out.getvalue())

    def test_a_current_drawing_prints_no_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, pdf_file = Path(tmp) / "schematic-system-draft.svg", Path(tmp) / "schematic-system-draft.pdf"
            target.write_text("<svg>same</svg>\n")
            pdf_file.write_bytes(b"%PDF old")
            with mock.patch.object(PD, "OUT", Path(tmp)), mock.patch.object(PD, "REPO", Path(tmp)), \
                    mock.patch.object(PD, "on_main", return_value=None), \
                    mock.patch.object(PD, "pdf", side_effect=AssertionError("printed")), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                PD.publish("<svg>same</svg>\n", target, None, "{}")
            self.assertIn("left as they are", out.getvalue())
            self.assertEqual(pdf_file.read_bytes(), b"%PDF old")
            pdf_file.unlink()                       # no PDF yet: printed although the SVG is current
            printed = []
            with mock.patch.object(PD, "OUT", Path(tmp)), mock.patch.object(PD, "on_main", return_value=None), \
                    mock.patch.object(PD, "pdf", lambda svg, out: (printed.append(out), out.write_bytes(b"%PDF"))), \
                    contextlib.redirect_stdout(io.StringIO()):
                PD.publish("<svg>same</svg>\n", target, None, "{}")
            self.assertEqual(len(printed), 1)
            self.assertEqual(pdf_file.read_bytes(), b"%PDF")


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

    def test_skips_off_the_pin(self) -> None:
        def off_pin():
            raise SystemExit("submodule is at aaaaaaaa, pinned bbbbbbbb")
        real, self.bs.pd.plugin = self.bs.pd.plugin, off_pin
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(self.bs.main(["--check"]), 0)
        finally:
            self.bs.pd.plugin = real
        self.assertIn("SKIPPED", out.getvalue())

    def test_skip_fails_when_required(self) -> None:
        os.environ["SCHEMATIC_REQUIRED"] = "1"
        self.assertEqual(self.without_plugin(), 1)

    def run_with(self, committed, masts=None):
        """main(["--check"]) against `committed` as the signals file, from the staging device map's masts (or `masts`
        rows, in staging_device_map.load_signal_masts' shape, with the device map's tracks)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "staging.signals.json").write_text(committed)
            real_data, real_facts = self.bs.pd.DATA, self.bs.staging_facts
            for f in ("staging.plan_overrides.json",):
                (tmp / f).write_text((real_data / f).read_text())
            if masts is not None:
                chains = real_facts()[1]
                self.bs.staging_facts = lambda: (masts, chains)
            self.bs.pd.DATA = tmp
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    return self.bs.main(["--check"])
            finally:
                self.bs.pd.DATA, self.bs.staging_facts = real_data, real_facts

    def test_current_passes(self) -> None:
        committed = (self.bs.pd.DATA / "staging.signals.json").read_text()
        self.assertEqual(self.run_with(committed), 0)

    def test_stale_fails(self) -> None:
        self.assertEqual(self.run_with('{"signals": [], "unplaced": []}\n'), 1)   # layers.load reads it too

    def test_written_from_the_staging_masts(self) -> None:
        masts = self.bs.sdm.load_signal_masts()
        self.assertEqual(len(masts), 49)
        got = json.loads((self.bs.pd.DATA / "staging.signals.json").read_text())
        self.assertEqual(got["signals"], self.bs.sdm.signal_rows(masts))
        self.assertEqual((got["source"], got["unplaced"]), (self.bs.sdm.SIGNALS_SOURCE, []))

    def test_a_run_not_in_the_plan_fails(self) -> None:
        masts = self.bs.sdm.load_signal_masts()
        first = next(i for i, m in enumerate(masts) if m["signal"] == "2L")       # a turnout mast, switch 1 to 23
        anchor = next(i for i, m in enumerate(masts) if m["signal"] == "16L")     # an anchor 40 cm in
        self.assertEqual((masts[first]["kind"], masts[anchor]["kind"]), ("turnout", "anchor"))
        for i, field, value, why in ((first, "schematic_edge", "e9999", "not in the plan graph"),
                                     (first, "names", ["Nowhere"], "carries"), (first, "run", ["1", "99"], "runs"),
                                     (first, "toward", "23", "toward '23'"),
                                     (first, "edge_cm", 560.0, "edge_cm 560.0 is not the length"),
                                     (first, "cm_from_toward", 5.0, "cm_from_toward 5.0"),
                                     (anchor, "cm_from_toward", 41.0, "cm_from_toward 41.0")):
            bad = [dict(m) for m in masts]
            bad[i][field] = value
            with self.subTest(field=field, mast=bad[i]["signal"]):
                with self.assertRaises(SystemExit) as e:
                    self.run_with('{"signals": []}', bad)
                self.assertIn(why, str(e.exception.code))


class PreviewFolder(unittest.TestCase):
    def test_refuses_a_folder_in_the_repo(self) -> None:
        with self.assertRaises(SystemExit):
            PD.main(["--preview", str(PD.OUT)])


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

    def test_only_the_misread_turnout_is_short(self) -> None:
        """Part 0's third end point is unreadable in the .any file; any other turnout short of three is new."""
        parts = json.loads((PD.GRAPHS / "parts.json").read_text())
        turnouts = {p["name"] for p in parts if len(p["eps"]) >= 3}
        self.assertEqual([i for i, p in enumerate(parts) if p["name"] in turnouts and len(p["eps"]) < 3], [0])

class StationSheets(unittest.TestCase):
    """docs/ops/stations follows the drawn station sheets exactly: changed, missing and dropped sheets all differ."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old, PD.STATIONS = PD.STATIONS, Path(self.tmp.name) / "stations"
        self.addCleanup(setattr, PD, "STATIONS", self.old)

    def test_written_sheets_are_current(self) -> None:
        sheets = {"a.svg": "<svg>a</svg>", "b.svg": "<svg>b</svg>"}
        PD.write_stations(sheets, PD.STATIONS)
        self.assertEqual(PD.stations_differ(sheets), [])

    def test_changed_new_and_dropped_differ(self) -> None:
        PD.write_stations({"a.svg": "<svg>a</svg>", "gone.svg": "<svg>g</svg>"}, PD.STATIONS)
        self.assertEqual(PD.stations_differ({"a.svg": "<svg>A</svg>", "new.svg": "<svg>n</svg>"}),
                         ["a.svg", "gone.svg", "new.svg"])

    def test_writing_removes_dropped_sheets(self) -> None:
        PD.write_stations({"gone.svg": "x"}, PD.STATIONS)
        PD.write_stations({"a.svg": "y"}, PD.STATIONS)
        self.assertEqual(sorted(f.name for f in PD.STATIONS.iterdir()), ["a.svg"])



class StationMapRevision(unittest.TestCase):
    """The station maps carry the schematic's revision: a station-only drawing change moves it, and the site pages
    are checked and written with it (map_revision)."""

    def test_a_station_sheets_drawing_change_counts_but_its_title_block_does_not(self) -> None:
        main = {"a.svg": sheet(rev=1), "b.svg": sheet(rev=1)}
        with mock.patch.object(PD, "on_main", side_effect=lambda p: main.get(p.name)):
            self.assertEqual(PD.stations_changed({"a.svg": sheet(rev=2), "b.svg": sheet(track="M1,0", rev=1),
                                                  "new.svg": sheet()}), ["b.svg", "new.svg"])

    def test_a_station_change_alone_moves_the_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, prefs = Path(tmp) / "schematic-system-draft.svg", Path(tmp) / "page.preferences.json"
            target.write_text(sheet())
            prefs.write_text(json.dumps({"date": "2026-11-14", "revision": 1}))
            on_main = lambda p: sheet() if p == target else json.dumps({"revision": 1})
            with mock.patch.object(PD, "OUT", Path(tmp)), mock.patch.object(PD, "on_main", side_effect=on_main), \
                    mock.patch.object(PD, "draw", return_value=sheet()), \
                    mock.patch.object(PD, "pdf", lambda svg, out: out.write_bytes(b"%PDF")), \
                    contextlib.redirect_stdout(io.StringIO()):
                PD.publish(sheet(), target, prefs, prefs.read_text(), stations=["barn.svg"])
            self.assertEqual(json.loads(prefs.read_text())["revision"], 2)

    def test_check_reports_bad_map_data_as_a_difference(self) -> None:
        with mock.patch.object(PD, "draw", return_value="<svg/>"), mock.patch.object(PD, "draw_stations", return_value={}), \
                mock.patch.object(PD, "stations_differ", return_value=[]), \
                mock.patch.object(PD, "stale_lengths", return_value=[]), \
                mock.patch.object(PD.map_revision, "drift", side_effect=ValueError("no entry for x")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(PD.main(["--check"]), 1)
        self.assertIn("no entry for x", out.getvalue())

    def test_bad_map_data_stops_publishing_before_any_write(self) -> None:
        with mock.patch.object(PD, "draw", side_effect=AssertionError("drew")), \
                mock.patch.object(PD, "stale_lengths", return_value=[]), \
                mock.patch.object(PD.map_revision, "planned", side_effect=ValueError("no entry for x")), \
                self.assertRaisesRegex(SystemExit, "nothing written"):
            PD.main([])


if __name__ == "__main__":
    unittest.main()
