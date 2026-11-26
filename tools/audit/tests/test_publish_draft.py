"""publish_draft.py: what counts as a drawing change, and the date and revision it sets."""
from __future__ import annotations

import contextlib
import datetime
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("publish_draft", ROOT / "tools/schematic/publish_draft.py")
PD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PD)
from hartlib import track_names  # noqa: E402  (publish_draft put tools/hartlib/src on the path)

TODAY = datetime.date(2026, 12, 1)
REAL_STAMP_FILE = PD.stamp_file
REAL_HARTLIB = PD.HARTLIB


def setUpModule() -> None:
    # The --check stamp lives in the real cache folder: a test that mocks the drawing must never read or write it
    # (CheckStamp points it at a temp file).
    patcher = mock.patch.object(PD, "stamp_file", lambda: None)
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


def sheet(track="M0,0", box_w=330, rev=1, col_w=104):
    """A sheet shaped like the plugin's: drawing, then the title box and the field column last."""
    return (f'<svg>\n<path d="{track}"/>\n'
            f'<rect x="24" y="728" width="{box_w}" height="64" fill="#fff" stroke="#000" stroke-width="1.5"/>\n'
            f'<text x="34" y="748" font-size="14">SYSTEM SCHEMATIC</text>\n'
            f'<rect x="{24 + box_w}" y="728" width="{col_w}" height="64"/>\n'
            f'<text x="362" y="763.8" font-size="9.5" letter-spacing="1">REV {rev}</text>\n</svg>\n')


def page_prefs(data, section):
    """A preferences.json in `data` whose main_upper section (the page's) is `section`, as PD.page_prefs names it."""
    (data / "preferences.json").write_text(json.dumps({"_sections": True, "staging": {"s": 1}, "main_upper": section}))
    return PD.layer_files.Section("preferences", PD.INPUTS[-1][1], data)


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
        self.assertEqual(PD.next_fields({"revision": 1}, TODAY), ("2026-12-01", 2))
        self.assertEqual(PD.next_fields({"revision": "3"}, TODAY), ("2026-12-01", 4))
        self.assertEqual(PD.next_fields({}, TODAY), ("2026-12-01", 1))
        self.assertEqual(PD.next_fields(None, TODAY), ("2026-12-01", 1))

    def test_lettered_revision_is_left_alone(self) -> None:
        for rev in ("A", "2b", True):
            self.assertIsNone(PD.next_fields({"revision": rev}, TODAY))

    def test_set_fields_keeps_the_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = page_prefs(Path(tmp), {"title": ["x"], "date": "2026-11-14", "revision": 1})
            PD.set_fields(p, "2026-12-01", 2)
            self.assertEqual(json.loads(p.path.read_text()), {"_sections": True, "staging": {"s": 1},
                             "main_upper": {"title": ["x"], "date": "2026-12-01", "revision": 2}})

    def test_the_page_is_main_uppers_section(self) -> None:
        self.assertEqual((PD.page_prefs().path, PD.page_prefs().sheet), (PD.DATA / "preferences.json", PD.INPUTS[-1][1]))
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "sheet.preferences.json").write_text("{}")
            with mock.patch.object(PD, "DATA", Path(tmp)), self.assertRaisesRegex(ValueError, "move its keys there"):
                PD.page_prefs()

    def test_publishing_stops_when_main_has_no_preferences_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(PD, "REPO", Path(tmp)), \
                mock.patch.object(PD, "on_main", return_value=None), \
                self.assertRaisesRegex(PD.PublishError, "is not on main, so the revision cannot be counted"):
            PD.prefs_on_main(page_prefs(Path(tmp), {"revision": 1}))

    def test_publishing_stops_with_one_line_when_main_has_no_page_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(PD, "REPO", Path(tmp)), \
                mock.patch.object(PD, "on_main", return_value='{"_sections": true, "staging": {}}'), \
                self.assertRaisesRegex(PD.PublishError, "no section 'main_upper'.*nothing written"):
            PD.prefs_on_main(page_prefs(Path(tmp), {"revision": 1}))


class Preview(unittest.TestCase):
    def test_writes_only_into_the_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prefs = PD.page_prefs().path.read_text()
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
            self.assertEqual(PD.page_prefs().path.read_text(), prefs)
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

    def test_a_loop_mast_names_the_leg_of_its_half(self) -> None:
        """The 107 Loop's halves: Loop 1 leaves from leg B, Loop 2 from leg C (mast_rule.LOOP_HALF); a loop edge's
        rows must name one of its legs, other rows none."""
        self.assertEqual((self.bs.loop_leg("Track 107 Loop 1"), self.bs.loop_leg("Track 107 Loop 2")), ("B", "C"))
        with self.assertRaisesRegex(self.bs.SignalsError, "not one of its halves"):
            self.bs.loop_leg("Track 107 Loop")
        loop = dict(u="S", up="B", v="S", vp="C")
        row = dict(mast="108LB", _edge="e33")
        self.assertEqual(self.bs.leg_problems(dict(row, leg="C"), loop), [])
        for bad in ({}, {"leg": "A"}):
            self.assertRegex(self.bs.leg_problems(dict(row, **bad), loop)[0], "is a loop at legs B and C")
        plain = dict(u="S", up="B", v="T", vp="A")
        self.assertEqual(self.bs.leg_problems(row, plain), [])
        self.assertRegex(self.bs.leg_problems(dict(row, leg="B"), plain)[0], "is no loop")

    def test_the_committed_loop_masts_name_their_legs(self) -> None:
        rows = PD.layer_files.read("signals", "main_upper")["signals"]
        legs = {r["mast"]: r.get("leg") for r in rows if r["_edge"] == "e33"}
        self.assertEqual(legs, {"A83": "C", "A84": "B", "108LA": "B", "108LB": "C"})

    def test_skips_without_the_plugin(self) -> None:
        self.assertEqual(self.without_plugin(), 0)

    def refused(self, argv):
        """main(argv) for arguments that must stop before the plugin is loaded and write no signals file."""
        with tempfile.TemporaryDirectory() as tmp:
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(self.bs.pd, "DATA", Path(tmp)), mock.patch.object(self.bs, "generate") as generate, \
                    mock.patch.object(self.bs.pd, "plugin") as plugin, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = self.bs.main(argv)
            generate.assert_not_called()
            plugin.assert_not_called()
            self.assertEqual(os.listdir(tmp), [])
        return status, out.getvalue(), err.getvalue()

    def test_unknown_argument_is_refused(self) -> None:
        for argv in (["--chek"], ["--check", "--verbose"], ["staging"]):
            status, out, err = self.refused(argv)
            self.assertEqual(status, 2, argv)
            self.assertIn(repr(argv[-1]), err)
            self.assertEqual(out, "")

    def test_help_prints_the_usage(self) -> None:
        for argv in (["--help"], ["-h"], ["--check", "--help"], ["--help", "--check"], ["--chek", "-h"]):
            status, out, err = self.refused(argv)
            self.assertEqual(status, 0, argv)
            self.assertIn("build_signals.py [--check]", out)
            self.assertEqual(err, "")

    def test_help_without_a_docstring(self) -> None:
        """python -OO strips the docstring; --help still prints the usage line, not 'None'."""
        with mock.patch.object(self.bs, "__doc__", None):
            status, out, err = self.refused(["--check", "--help"])
        self.assertEqual((status, out, err), (0, "build_signals.py [--check]\n", ""))

    def test_skips_off_the_pin(self) -> None:
        def off_pin():
            raise self.bs.pd.PluginMissing("submodule is at aaaaaaaa, pinned bbbbbbbb")
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
        """main(["--check"]) against `committed` as signals.json's staging section, from the staging device map's masts (or `masts`
        rows, in staging_device_map.load_signal_masts' shape, with the device map's tracks)."""
        with tempfile.TemporaryDirectory() as root:
            tmp = Path(root) / "schematic"
            tmp.mkdir()
            real_data, real_facts = self.bs.pd.DATA, self.bs.staging_facts
            for f in real_data.iterdir():       # both levels (staging, main_upper) solve from these
                if f.is_file():
                    (tmp / f.name).write_bytes(f.read_bytes())
            track_names.repo_inputs(tmp)     # the name store's plan graphs and owner rows: the repo's, by opt-in
            PD.layer_files.write({("signals", "staging"): committed}, tmp)
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
        committed = PD.layer_files.read("signals", "staging", self.bs.pd.DATA)
        self.assertEqual(self.run_with(committed), 0)

    def test_stale_fails(self) -> None:
        self.assertEqual(self.run_with({"signals": [], "unplaced": []}), 1)   # layers.load reads it too

    def test_a_solve_that_cannot_read_its_own_output_stops_clearly(self) -> None:
        # the staging band is solved, and the solve reads signals.json, which build_signals writes
        with mock.patch.object(self.bs.sdm, "staging_band", side_effect=ValueError("Expecting value: line 1")):
            with self.assertRaises(self.bs.SignalsError) as e:
                self.bs.staging_facts()
        self.assertIn("signals.json, which this script writes", str(e.exception))
        self.assertIn("git checkout --", str(e.exception))
        self.assertIsInstance(e.exception.__cause__, ValueError)

    def test_written_from_the_staging_masts(self) -> None:
        masts = self.bs.sdm.load_signal_masts()
        self.assertEqual(len(masts), 30)
        got = PD.layer_files.read("signals", "staging", self.bs.pd.DATA)
        self.assertEqual(got["signals"], self.bs.sdm.signal_rows(masts))
        self.assertEqual((got["source"], got["unplaced"]), (self.bs.sdm.SIGNALS_SOURCE, []))

    def test_a_run_not_in_the_plan_fails(self) -> None:
        masts = self.bs.sdm.load_signal_masts()
        first = next(i for i, m in enumerate(masts) if m["signal"] == "2L")       # a turnout mast, switch 1 to 23
        anchor = next(i for i, m in enumerate(masts) if m["signal"] == "67")      # an anchor at the K-1/K-2 turnback
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
                    self.run_with({"signals": []}, bad)
                self.assertIn(why, str(e.exception.code))


class NamedErrors(unittest.TestCase):
    """The library functions raise PublishError and its kinds; only main() turns them into an exit."""

    def test_no_submodule_is_plugin_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(PD, "REPO", Path(tmp)), \
                mock.patch.dict(os.environ, {}, clear=False) as env:
            env.pop("SCHEMATIC_PLUGIN", None)
            with self.assertRaisesRegex(PD.PluginMissing, "git submodule update --init"):
                PD.plugin()
        self.assertTrue(issubclass(PD.PluginMissing, PD.PublishError))
        self.assertFalse(issubclass(PD.PublishError, SystemExit))

    def test_main_exits_with_the_message(self) -> None:
        with mock.patch.object(PD, "run", side_effect=PD.PublishError("nothing written")), \
                self.assertRaises(SystemExit) as stop:
            PD.main([])
        self.assertEqual(stop.exception.code, "nothing written")

    def test_a_failed_drawing_exits_with_the_plugins_status(self) -> None:
        with mock.patch.object(PD, "run", side_effect=PD.DrawFailed(3)):
            self.assertEqual(PD.main(["--check"]), 3)

    def test_a_failed_draw_is_draw_failed(self) -> None:
        failed = mock.Mock(returncode=4, stdout="", stderr="bad sheet\n")
        with mock.patch.object(PD, "plugin", return_value=Path("plugin")), \
                mock.patch.object(PD.subprocess, "run", return_value=failed), \
                contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(PD.DrawFailed) as stop:
            PD.draw()
        self.assertEqual(stop.exception.returncode, 4)
        self.assertIn("bad sheet", out.getvalue())

    def test_no_chrome_is_a_publish_error(self) -> None:
        screenshot = sys.modules["screenshot"]
        with mock.patch.object(screenshot.shutil, "which", return_value=None):
            with self.assertRaises(screenshot.ChromeMissing):
                screenshot.find_chrome()
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(PD.PublishError) as stop:
                PD.pdf(Path(tmp) / "a.svg", Path(tmp) / "a.pdf")
        self.assertEqual(str(stop.exception), "Google Chrome not found")
        self.assertIsInstance(stop.exception.__cause__, screenshot.ChromeMissing)


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

    def test_no_turnout_is_short(self) -> None:
        """The plan reader (the schematic-maps plugin's `schematic anyplan`) reads every turnout's three end points
        (the old reader lost part 0's in 5.3b): a turnout part with fewer is a misread."""
        parts = json.loads((PD.GRAPHS / "parts.json").read_text())
        turnouts = {p["name"] for p in parts if len(p["eps"]) >= 3}
        self.assertEqual([i for i, p in enumerate(parts) if p["name"] in turnouts and len(p["eps"]) < 3], [])

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
            target = Path(tmp) / "schematic-system-draft.svg"
            target.write_text(sheet())
            prefs = page_prefs(Path(tmp), {"date": "2026-11-14", "revision": 1})
            on_main = lambda p: sheet() if p == target else json.dumps({"_sections": True, "main_upper": {"revision": 1}})
            with mock.patch.object(PD, "OUT", Path(tmp)), mock.patch.object(PD, "on_main", side_effect=on_main), \
                    mock.patch.object(PD, "draw", return_value=sheet()), \
                    mock.patch.object(PD, "pdf", lambda svg, out: out.write_bytes(b"%PDF")), \
                    contextlib.redirect_stdout(io.StringIO()):
                PD.publish(sheet(), target, prefs, prefs.path.read_text(), stations=["barn.svg"])
            self.assertEqual(prefs.read()["revision"], 2)

    def test_check_reports_bad_map_data_as_a_difference(self) -> None:
        with mock.patch.object(PD, "draw", return_value="<svg/>"), mock.patch.object(PD, "draw_stations", return_value={}), \
                mock.patch.object(PD, "stations_differ", return_value=[]), \
                mock.patch.object(PD.map_revision, "drift", side_effect=ValueError("no entry for x")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(PD.main(["--check"]), 1)
        self.assertIn("no entry for x", out.getvalue())

    def test_bad_map_data_stops_publishing_before_any_write(self) -> None:
        with mock.patch.object(PD, "draw", side_effect=AssertionError("drew")), \
                mock.patch.object(PD.map_revision, "planned", side_effect=ValueError("no entry for x")), \
                self.assertRaisesRegex(SystemExit, "nothing written"):
            PD.main([])


class CheckStamp(unittest.TestCase):
    """--check skips the drawing when its inputs match the last pass (the stamp), and draws on any change to the
    plugin, the hartlib code that builds its view, a layer file, a graph, the published SVG or a station sheet, and
    when the stamp is missing or unreadable."""

    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp))
        self.plugin, data, out = tmp / "plugin", tmp / "data", tmp / "ops"
        self.hartlib = tmp / "hartlib_src"
        for d in (self.plugin / "schematic", data / "inputs", out / "stations", self.hartlib / "hartlib"):
            d.mkdir(parents=True)
        (self.plugin / "schematic/sheet.py").write_text("SOLVE = 1\n")
        (self.plugin / "schematic/__pycache__").mkdir()
        (self.hartlib / "hartlib/track_names.py").write_text("RULE = 1\n")
        (data / "preferences.json").write_text("{}\n")
        (data / "inputs/staging.json").write_text("{}\n")
        (out / "schematic-system-draft.svg").write_text("<svg/>")
        (out / "stations/barn.svg").write_text("<svg>barn</svg>")
        self.data, self.out, self.stamp = data, out, tmp / "cache/publish_draft.check"
        self.drawn = 0

        def draw():
            self.drawn += 1
            return "<svg/>"
        for name, value in (("plugin", lambda: self.plugin), ("DATA", data), ("OUT", out), ("HARTLIB", self.hartlib),
                            ("STATIONS", out / "stations"), ("stamp_file", lambda: self.stamp), ("draw", draw),
                            ("draw_stations", lambda: {"barn.svg": "<svg>barn</svg>"})):
            patcher = mock.patch.object(PD, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def check(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return PD.compare_drawing()

    def test_a_pass_records_and_the_same_inputs_draw_nothing(self) -> None:
        self.assertEqual(self.check(), (True, []))
        self.assertEqual(self.drawn, 1)
        self.assertTrue(self.stamp.exists())
        self.assertEqual(self.check(), (True, []))
        self.assertEqual(self.drawn, 1)

    def test_the_hartlib_hashed_is_the_one_imported(self) -> None:
        self.assertEqual(REAL_HARTLIB, ROOT / "tools/hartlib/src")
        self.assertTrue((REAL_HARTLIB / "hartlib/layer_files.py").is_file())

    def test_python_caches_are_not_inputs(self) -> None:
        self.check()
        (self.plugin / "schematic/__pycache__/sheet.cpython-313.pyc").write_bytes(b"\0")
        self.check()
        self.assertEqual(self.drawn, 1)

    def test_a_name_the_view_resolves_differently_draws_again(self) -> None:
        # preferences.json names tracks by block ID (naming-layers step 5b); a generated name comes from
        # devices_generated.csv, which is not hashed whole, so the merged view the plugin reads is
        name = ["Brick-Plane"]
        with mock.patch.object(PD.layer_files, "merged", side_effect=lambda data, kind: {"turnbacks": list(name)}):
            self.check()
            self.check()
            self.assertEqual(self.drawn, 1)
            name[0] = "Brick West"
            self.check()
        self.assertEqual(self.drawn, 2)

    def test_any_input_change_draws_again(self) -> None:
        for change in (lambda: (self.plugin / "schematic/sheet.py").write_text("SOLVE = 2\n"),
                       lambda: (self.plugin / "schematic/new.py").write_text(""),
                       lambda: (self.hartlib / "hartlib/track_names.py").write_text("RULE = 2\n"),
                       lambda: (self.hartlib / "hartlib/new.py").write_text(""),
                       lambda: (self.data / "preferences.json").write_text('{"x": 1}\n'),
                       lambda: (self.data / "inputs/staging.json").write_text('{"x": 1}\n'),
                       lambda: (self.out / "stations/barn.svg").write_text("<svg>barn</svg>\n"),
                       lambda: (self.out / "schematic-system-draft.svg").write_text("<svg/>\n")):
            self.check()
            drawn = self.drawn
            change()
            self.check()
            self.assertEqual(self.drawn, drawn + 1)

    def test_a_failed_check_records_nothing(self) -> None:
        (self.out / "schematic-system-draft.svg").write_text("<svg>old</svg>")
        self.assertEqual(self.check(), (False, []))
        self.assertFalse(self.stamp.exists())
        self.assertEqual(self.check(), (False, []))
        self.assertEqual(self.drawn, 2)

    def test_a_station_difference_records_nothing(self) -> None:
        (self.out / "stations/barn.svg").write_text("<svg>old</svg>")
        self.assertEqual(self.check(), (True, ["barn.svg"]))
        self.assertFalse(self.stamp.exists())

    def test_a_missing_or_unreadable_stamp_draws(self) -> None:
        self.check()
        self.stamp.unlink()
        self.check()
        self.assertEqual(self.drawn, 2)
        self.stamp.write_text("not a digest\n")
        self.check()
        self.assertEqual(self.drawn, 3)
        self.stamp.unlink()
        self.stamp.mkdir()                       # an OSError other than a missing file
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.check()
        self.assertEqual(self.drawn, 4)
        self.assertIn("drawing to compare", err.getvalue())

    def test_checkouts_taking_turns_keep_their_digests(self) -> None:
        layer = self.data / "preferences.json"
        for text in ("{}\n", '{"b": 1}\n', "{}\n", '{"b": 1}\n'):     # two checkouts' inputs, in turn
            layer.write_text(text)
            self.check()
        self.assertEqual(self.drawn, 2)
        for n in range(PD.STAMP_KEEP + 2):
            layer.write_text(f'{{"n": {n}}}\n')
            self.check()
        self.assertEqual(len(PD.read_stamp(self.stamp)), PD.STAMP_KEEP)

    def test_a_file_that_cannot_be_read_draws_and_records_nothing(self) -> None:
        with mock.patch.object(PD, "check_digest", side_effect=FileNotFoundError("gone")), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(self.check(), (True, []))
        self.assertEqual(self.drawn, 1)
        self.assertFalse(self.stamp.exists())
        self.assertIn("drawing to compare", err.getvalue())

    def test_another_python_on_path_draws_again(self) -> None:
        self.check()
        with mock.patch.object(PD.shutil, "which", return_value="/no/such/python3"):
            self.check()
        self.assertEqual(self.drawn, 2)
        with mock.patch.dict(os.environ, {"PYTHONPATH": "/elsewhere"}):
            self.check()
        self.assertEqual(self.drawn, 3)

    def test_an_edit_during_the_drawing_records_nothing(self) -> None:
        def edit_then_draw():
            self.drawn += 1
            (self.data / "preferences.json").write_text('{"edited": 1}\n')
            return "<svg/>"
        with mock.patch.object(PD, "draw", edit_then_draw):
            self.assertEqual(self.check(), (True, []))
        self.assertFalse(self.stamp.exists())

    def test_the_cache_off_turns_the_stamp_off(self) -> None:
        with mock.patch.dict(os.environ, {"SCHEMATIC_CACHE": ""}):
            self.assertIsNone(REAL_STAMP_FILE())
        with mock.patch.dict(os.environ, {"SCHEMATIC_CACHE": str(self.stamp.parent)}):
            self.assertEqual(REAL_STAMP_FILE(), self.stamp)

    def test_check_reports_a_hit_as_current(self) -> None:
        self.check()
        with mock.patch.object(PD.map_revision, "drift", return_value=[]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(PD.main(["--check"]), 0)
        self.assertEqual(self.drawn, 1)
        self.assertIn("not drawn again", out.getvalue())
        self.assertIn("published draft is current", out.getvalue())


class MainBase(unittest.TestCase):
    """Publishing counts the revision from where the branch left main; when git cannot find that commit it stops,
    not compares with HEAD (where a committed drawing change equals itself and gets no new revision)."""

    def setUp(self) -> None:
        PD.main_base.cache_clear()                 # main_base answers once per run; each test is its own run
        self.addCleanup(PD.main_base.cache_clear)

    @staticmethod
    def git(merge_base, calls, has_main=True, shallow=False, listed=(0, "docs/ops/x.svg\n", ""),
            show=(0, "text on main", "")):
        """A git that answers merge-base, the two rev-parse questions asked after a failure, ls-tree and show."""
        def run(cmd, **kwargs):
            calls.append(cmd[3:])                                  # past git -C <repo>
            answer = {"merge-base": merge_base, "ls-tree": listed, "show": show,
                      "rev-parse": (0, "true\n" if shallow else "false\n", "") if "--is-shallow-repository" in cmd
                      else (0 if has_main else 1, "", "")}[cmd[3]]
            return mock.Mock(returncode=answer[0], stdout=answer[1], stderr=answer[2])
        return run

    def test_the_file_is_read_at_the_merge_base(self) -> None:
        calls = []
        with mock.patch.object(PD.subprocess, "run", self.git((0, "abc123\n", ""), calls)):
            self.assertEqual(PD.on_main(PD.REPO / "docs/ops/x.svg"), "text on main")
        self.assertEqual(calls, [["merge-base", "HEAD", "origin/main"],
                                 ["ls-tree", "--name-only", "abc123", "--", "docs/ops/x.svg"],
                                 ["show", "abc123:docs/ops/x.svg"]])

    def test_the_merge_base_is_asked_once(self) -> None:
        calls = []
        with mock.patch.object(PD.subprocess, "run", self.git((0, "abc123\n", ""), calls)):
            PD.main_base()
            for name in ("x.svg", "y.svg", "z.json"):
                PD.on_main(PD.REPO / "docs/ops" / name)
        self.assertEqual([c[0] for c in calls].count("merge-base"), 1)
        self.assertEqual([c[1] for c in calls if c[0] == "show"],
                         ["abc123:docs/ops/x.svg", "abc123:docs/ops/y.svg", "abc123:docs/ops/z.json"])

    def test_a_file_not_on_main_is_none(self) -> None:
        calls = []
        with mock.patch.object(PD.subprocess, "run", self.git((0, "abc123\n", ""), calls, listed=(0, "", ""))):
            self.assertIsNone(PD.on_main(PD.REPO / "docs/ops/new.svg"))
        self.assertNotIn("show", [c[0] for c in calls])

    def test_a_git_failure_reading_the_file_stops(self) -> None:
        # read as "not on main", a failed read would count the revision from nothing (or skip the change)
        failures = {"ls-tree fails": {"listed": (128, "", "fatal: bad object abc123")},
                    "show fails": {"show": (128, "", "fatal: unable to read 0123abcd")},
                    "show fails silently": {"show": (1, "", "")}}
        for name, answers in failures.items():
            PD.main_base.cache_clear()
            with self.subTest(name), mock.patch.object(PD.subprocess, "run",
                                                       self.git((0, "abc123\n", ""), [], **answers)), \
                    self.assertRaises(PD.PublishError) as stop:
                PD.on_main(PD.REPO / "docs/ops/x.svg")
            message = str(stop.exception)
            self.assertIn("git could not read docs/ops/x.svg at abc123", message)
            self.assertIn(next(iter(answers.values()))[2] or "exit 1", message)
            self.assertIn("`python3 tools/schematic/publish_draft.py` again", message)

    def test_a_failed_merge_base_stops_and_names_the_fix(self) -> None:
        failures = {
            "no origin/main": ((128, "", "fatal: Not a valid object name origin/main"), {"has_main": False},
                               "`git fetch origin main:refs/remotes/origin/main`"),
            "shallow clone, no common commit": ((1, "", ""), {"shallow": True}, "`git fetch --unshallow origin`"),
            "unrelated history": ((1, "", ""), {}, "`make wt TOPIC=<topic>`"),
            "empty answer": ((0, "\n", ""), {}, "`make wt TOPIC=<topic>`")}
        for name, (result, state, fix) in failures.items():
            calls = []
            PD.main_base.cache_clear()
            with self.subTest(name), mock.patch.object(PD.subprocess, "run", self.git(result, calls, **state)), \
                    self.assertRaises(PD.PublishError) as stop:
                PD.on_main(PD.REPO / "docs/ops/x.svg")
            message = str(stop.exception)
            self.assertIn("`git merge-base HEAD origin/main` failed", message)
            self.assertIn(fix, message)                                            # the step that fits this failure
            self.assertEqual(message.count("run `git fetch"), 1 if "fetch" in fix else 0)
            self.assertIn("then run `python3 tools/schematic/publish_draft.py` again", message)
            self.assertIn("nothing written", message)
            self.assertEqual({c[0] for c in calls}, {"merge-base", "rev-parse"})   # never falls back to HEAD
            self.assertIn(result[2] or f"exit {result[0]}", message)               # git's own reason, when it gave one

    def test_publishing_stops_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prefs = page_prefs(Path(tmp), {"date": "2026-11-14", "revision": 1})
            before = {p: p.read_text() for p in (prefs.path,)}
            wrote = AssertionError("wrote")
            with mock.patch.object(PD.subprocess, "run", self.git((1, "", ""), [], shallow=True)), \
                    mock.patch.object(PD, "page_prefs", return_value=prefs), \
                    mock.patch.object(PD.map_revision, "planned"), \
                    mock.patch.object(PD.map_revision, "apply", side_effect=wrote), \
                    mock.patch.object(PD, "draw", side_effect=AssertionError("drew")), \
                    mock.patch.object(PD, "draw_stations", side_effect=AssertionError("drew")), \
                    mock.patch.object(PD, "write_stations", side_effect=wrote), \
                    mock.patch.object(PD, "set_fields", side_effect=wrote), \
                    mock.patch.object(PD, "pdf", side_effect=wrote), \
                    self.assertRaisesRegex(SystemExit, "git fetch --unshallow origin"):
                PD.main([])
            self.assertEqual({p: p.read_text() for p in (prefs.path,)}, before)

    def test_check_never_asks_for_the_merge_base(self) -> None:
        # CI checks out one commit with no origin/main (actions/checkout's default depth), and runs --check
        with mock.patch.object(PD, "main_base", side_effect=AssertionError("asked")), \
                mock.patch.object(PD, "_git", side_effect=AssertionError("ran git")), \
                mock.patch.object(PD, "draw", return_value="<svg/>"), \
                mock.patch.object(PD, "draw_stations", return_value={}), \
                mock.patch.object(PD, "stations_differ", return_value=[]), \
                mock.patch.object(PD.map_revision, "drift", return_value=[]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertIn(PD.main(["--check"]), (0, 1))

    def test_preview_never_asks_for_the_merge_base(self) -> None:
        # a preview shows the drawing as it stands: it compares nothing with main, so it runs without origin/main
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(PD, "main_base", side_effect=AssertionError("asked")), \
                mock.patch.object(PD, "_git", side_effect=AssertionError("ran git")), \
                mock.patch.object(PD, "on_main", side_effect=AssertionError("read main")), \
                mock.patch.object(PD, "draw", return_value="<svg/>"), \
                mock.patch.object(PD, "draw_stations", return_value={"a.svg": "<svg>a</svg>"}), \
                mock.patch.object(PD, "pdf"), \
                mock.patch.object(PD, "set_fields", side_effect=AssertionError("wrote")), \
                contextlib.redirect_stdout(io.StringIO()):
            folder = Path(tmp).resolve() / "out"
            self.assertEqual(PD.main(["--preview", str(folder)]), 0)
            self.assertEqual((folder / "schematic-system-draft.svg").read_text(), "<svg/>")
            self.assertEqual(sorted(p.name for p in (folder / "stations").iterdir()), ["a.svg"])


if __name__ == "__main__":
    unittest.main()
