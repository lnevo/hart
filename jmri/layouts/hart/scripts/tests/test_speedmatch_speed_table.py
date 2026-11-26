"""speedmatch/speed_table.py (analyze.py speed-by-step) and analyze.py's named errors. No JMRI, no layout."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SM = ROOT / "jmri/layouts/hart/scripts/speedmatch"
PROFILE = ROOT / "docs/jmri/speedmatching/profile-2026-11-08"
sys.path.insert(0, str(SM))
sys.path.insert(0, str(SM / "dashboard"))
import analyze  # noqa: E402
import dashsources  # noqa: E402  REF_CSV: the speed table the dashboard and the Pi bundle read
import speed_table as st  # noqa: E402

LOGS_2026_11_08 = {"steprun_2121_b.log": "CSX 2121", "steprun_2121_c.log": "CSX 2121",
                   "steprun_2121_d.log": "CSX 2121", "steprun_2738_b.log": "CSX 2738"}
LOOP_2026_11_08_MM = 31292.8


def tmpdir() -> Path:
    return Path(tempfile.mkdtemp())


def quiet_main(argv: list[str]) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        analyze.main(argv)
    return out.getvalue()


class SpeedByStep(unittest.TestCase):
    def test_the_2026_11_08_table_comes_out_byte_identical(self) -> None:
        out = tmpdir() / "sbs.csv"
        argv = ["speed-by-step", "--laps", str(PROFILE / "results.csv"), "--laps", str(PROFILE / "manual_laps.csv"),
                "--loop-mm", str(LOOP_2026_11_08_MM), "--out", str(out)]
        for log, loco in LOGS_2026_11_08.items():
            argv += ["--log-loco", "%s=%s" % (log, loco)]
        quiet_main(argv)
        self.assertEqual(out.read_bytes(), dashsources.REF_CSV.read_bytes())

    def test_rows_average_the_laps_of_each_loco_and_step(self) -> None:
        rows = st.speed_by_step([st.Lap("B", 8, 100.0), st.Lap("A", 8, 50.0), st.Lap("A", 8, 40.0),
                                 st.Lap("A", 4, 200.0)], 1000.0)
        self.assertEqual([(r.loco, r.step) for r in rows], [("A", 4), ("A", 8), ("B", 8)])
        a8 = rows[1]
        self.assertEqual((a8.laps, a8.mean_lap_s, a8.mean_mm_s, a8.stdev_mm_s), (2, 45.0, 22.5, 3.5))
        self.assertEqual(a8.mph_ho, round(22.5 * 87 / 1000 * 2.23694, 1))
        self.assertIsNone(rows[0].stdev_mm_s)
        out = tmpdir() / "t.csv"
        st.write_table(rows, out)
        self.assertEqual(out.read_text().splitlines()[1], "A,4,1,200.0,5.0,,1.0")

    def test_bad_laps_and_lengths_are_refused(self) -> None:
        with self.assertRaisesRegex(st.SpeedTableError, "no laps"):
            st.speed_by_step([], 1000.0)
        with self.assertRaisesRegex(st.SpeedTableError, "above 0 mm"):
            st.speed_by_step([st.Lap("A", 8, 10.0)], 0.0)
        with self.assertRaisesRegex(st.SpeedTableError, "a lap takes time"):
            st.speed_by_step([st.Lap("A", 8, 0.0)], 1000.0)

    def test_a_lap_csv_needs_its_columns_numbers_and_locos(self) -> None:
        d = tmpdir()
        (d / "cols.csv").write_text("log,lap_s\nx.log,10\n")
        with self.assertRaisesRegex(st.SpeedTableError, "needs columns step, lap_s and loco or log"):
            st.read_laps(d / "cols.csv", {})
        (d / "log.csv").write_text("log,step,lap_s\nx.log,8,10\n")
        with self.assertRaisesRegex(st.SpeedTableError, "line 2: log 'x.log' has no loco"):
            st.read_laps(d / "log.csv", {})
        self.assertEqual(st.read_laps(d / "log.csv", {"x.log": "A"}), [st.Lap("A", 8, 10.0)])
        (d / "num.csv").write_text("loco,step,lap_s\nA,8,ten\n")
        with self.assertRaisesRegex(st.SpeedTableError, "num.csv line 2"):
            st.read_laps(d / "num.csv", {})

    def test_log_loco_needs_an_equals_sign(self) -> None:
        self.assertEqual(st.log_loco_map(["a.log=CSX 1"]), {"a.log": "CSX 1"})
        for bad in ("a.log", "=CSX 1", "a.log="):
            with self.assertRaisesRegex(st.SpeedTableError, "give LOG=LOCO"):
                st.log_loco_map([bad])

    def test_the_cli_stops_with_the_message(self) -> None:
        d = tmpdir()
        (d / "empty.csv").write_text("loco,step,lap_s\n")
        with self.assertRaisesRegex(SystemExit, "no laps"):
            quiet_main(["speed-by-step", "--laps", str(d / "empty.csv"), "--loop-mm", "1000", "--out",
                        str(d / "o.csv")])
        self.assertFalse((d / "o.csv").exists())

    def test_a_route_without_trusted_lengths_is_refused(self) -> None:
        order = analyze.route_order("loop1")
        lengths: dict[str, float | None] = {s: 100.0 for s in order}
        self.assertAlmostEqual(st.route_mm("loop1", lengths), 100.0 * len(order))
        lengths[order[2]] = None
        with self.assertRaisesRegex(st.SpeedTableError, order[2]):
            st.route_mm("loop1", lengths)


def lap_log(step_events: list[tuple[float, str]]) -> list[str]:
    lines = ["1.0 RUN loco=L direction=forward", "1.5 CFG route=loop1", "2.0 STEP 32"]
    for t, s in step_events:  # each sensor clears again, so its next lighting is a new ACTIVE
        lines += ["%.1f SENS %s ACTIVE" % (t, s), "%.1f SENS %s INACTIVE" % (t + 0.1, s)]
    return lines


class RunLaps(unittest.TestCase):
    """A lap in a runner log: the first sensor lit again after the mid sensor, inside one step."""

    def test_laps_need_the_mid_sensor_between_two_passes(self) -> None:
        ref, mid = analyze.route_order("loop1")[0], analyze.route_mid("loop1")
        other = analyze.route_order("loop1")[3]
        log = lap_log([(10.0, ref), (20.0, other), (20.5, ref),  # a retrigger before mid: no lap
                       (40.0, mid), (110.0, ref), (150.0, mid), (205.0, ref)])
        laps = st.run_laps(analyze.parse_log(log))
        self.assertEqual(laps, [st.Lap("L", 32, 100.0), st.Lap("L", 32, 95.0)])

    def test_a_step_change_starts_the_timing_again(self) -> None:
        ref, mid = analyze.route_order("loop1")[0], analyze.route_mid("loop1")
        log = lap_log([(10.0, ref), (50.0, mid)]) + ["60.0 STEP 48", "70.0 SENS %s ACTIVE" % ref]
        self.assertEqual(st.run_laps(analyze.parse_log(log + ["80.0 SENS %s ACTIVE" % mid])), [])
        self.assertEqual(st.run_laps(analyze.parse_log(log)), [])


class NamedErrors(unittest.TestCase):
    def test_routes_json_unreadable_or_stale(self) -> None:
        d = tmpdir()
        with self.assertRaisesRegex(analyze.RoutesError, "cannot read"):
            analyze.load_routes(d / "missing.json")
        data = json.loads(analyze.ROUTES_JSON.read_text())
        data["ids"]["loop1"] = data["ids"]["loop1"][::-1]
        (d / "routes.json").write_text(json.dumps(data))
        with self.assertRaisesRegex(analyze.RoutesError, "does not match ROUTE_BLOCKS / ROUTE_MID_BLOCK for loop1"):
            analyze.load_routes(d / "routes.json")

    def test_old_extension_names_are_a_log_error(self) -> None:
        with self.assertRaisesRegex(analyze.LogError, "old.log uses the old names"):
            analyze.parse_log(["1.0 SENS BS East Main Ext ACTIVE"], source="old.log")

    def test_a_sensor_off_the_route_is_a_log_error(self) -> None:
        with self.assertRaisesRegex(analyze.LogError, "x.log logs sensor\\(s\\) not on route loop1: BS Nowhere"):
            analyze.parse_log(lap_log([(3.0, "BS Nowhere")]), source="x.log")

    def test_every_named_error_is_a_value_error(self) -> None:
        for err in (analyze.RoutesError, analyze.UnknownRouteError, analyze.LengthsError, analyze.LogError,
                    st.SpeedTableError):
            self.assertTrue(issubclass(err, analyze.AnalyzeError), err)
            self.assertTrue(issubclass(err, ValueError), err)

    def test_the_cli_turns_a_log_error_into_its_message(self) -> None:
        d = tmpdir()
        (d / "old.log").write_text("1.0 SENS BS West Main Ext ACTIVE\n")
        with self.assertRaisesRegex(SystemExit, "old.log uses the old names"):
            quiet_main([str(d / "old.log"), "--out", str(d)])


if __name__ == "__main__":
    unittest.main()
