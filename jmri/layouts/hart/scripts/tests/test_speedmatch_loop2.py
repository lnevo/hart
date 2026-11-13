"""Speed-match routes: loop 2 (S-R, Scale, Barn) beside loop 1 -- sensor and row names, guards,
the lineup, the logged route, the events converter, and placing Switch 13 from timed laps."""
from __future__ import annotations

import csv
import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_speedmatch import SM, analyze, make_job  # noqa: E402

sys.path.insert(0, str(SM))
import correct  # noqa: E402

sys.path.insert(0, str(SM.parent))
import infer_block_lengths as ibl  # noqa: E402

DATA = SM.parents[1] / "data"
TABLES = SM.parents[1] / "output" / "tables.xml"
BS_NAMES = set(re.findall(r"<userName>(BS [^<]*)</userName>", TABLES.read_text()))
CSV_ROWS = {r["user_name"]: r for r in csv.DictReader(open(DATA / "block_lengths.csv", newline=""))}
LEGS = {(r["switch"], r["os_block"]): r for r in csv.DictReader(open(DATA / "switch_legs.csv", newline=""))}


class Routes(unittest.TestCase):
    def test_loop1_keeps_its_aliases(self):
        self.assertIs(analyze.ROUTES["loop1"], analyze.LOOP)
        self.assertEqual(analyze.ORDER, analyze.route_order("loop1"))

    def test_every_name_exists(self):
        for route in analyze.ROUTES:
            order = analyze.route_order(route)
            self.assertEqual(len(set(order)), len(order), route)
            for sensor, row in analyze.route_loop(route):
                self.assertIn(sensor, BS_NAMES, sensor)
                self.assertIn(row, CSV_ROWS, row)

    def test_loop2_order(self):
        o = analyze.route_order("loop2")
        self.assertEqual(len(o), 22)
        self.assertEqual(o[:7], ["BS Switch 5", "BS Scale", "BS Switch 7", "BS Barn", "BS Switch 13",
                                 "BS Switch 15", "BS S-R"])
        self.assertEqual(o[-1], "BS Brick-Plane")

    def test_unknown_route(self):
        with self.assertRaises(ValueError):
            analyze.route_loop("loop9")

    def test_sr_stubs_share_the_detector_and_are_counted(self):
        stubs = [r for r in CSV_ROWS.values() if r["flag"] == "stub" and r["occupancy_sensor"] == "BS S-R"]
        self.assertEqual(sorted(r["user_name"] for r in stubs), ["Track S-R East", "Track S-R West"])
        got = analyze.load_lengths(DATA / "block_lengths.csv", ("assigned", "estimate"),
                                   analyze.route_loop("loop2"))
        want = (float(CSV_ROWS["Track S-R"]["inches"]) + 2 * 15.748) * 25.4
        self.assertAlmostEqual(got["BS S-R"], want, places=3)

    def test_trusted_default_leaves_untrusted_rows_none(self):
        got = analyze.load_lengths(analyze.DEFAULT_LENGTHS, analyze.DEFAULT_TRUSTED, analyze.route_loop("loop2"))
        self.assertEqual(set(got), set(analyze.route_order("loop2")))


class Guards(unittest.TestCase):
    def test_default_is_every_block_sensor_off_the_route(self):
        for route in analyze.ROUTES:
            g = make_job.guard_for(route)
            self.assertEqual(set(g), BS_NAMES - set(analyze.route_order(route)), route)
            self.assertEqual(len(g), len(set(g)))
            self.assertEqual(make_job.guards(["default"], route), g)

    def test_loop2_guards_loop1_only_sensors(self):
        g = make_job.guard_for("loop2")
        for n in ("BS Main East", "BS East Main Ext", "BS Switch 7b", "BS S-1"):
            self.assertIn(n, g)
        for n in ("BS S-R", "BS Scale", "BS Barn", "BS Switch 13", "BS Switch 33"):
            self.assertNotIn(n, g)
        self.assertIn("BS S-R", make_job.DEFAULT_GUARD)  # and the other way round

    def test_default_guard_is_loop1(self):
        self.assertEqual(make_job.DEFAULT_GUARD, make_job.guard_for("loop1"))

    def test_job_carries_route_guard_and_order(self):
        d = Path(tempfile.mkdtemp())
        make_job.main(["steps", "--loco", "L", "--direction", "forward", "--route", "loop2",
                       "--steps", "32,48", "--guard", "default", "--out", str(d / "j.py")])
        ns: dict = {}
        exec(compile((d / "j.py").read_text().split(make_job.RUNNER_MARK)[0], "job", "exec"), ns)
        self.assertEqual(ns["ROUTE"], "loop2")
        self.assertEqual(ns["ORDER"], analyze.route_order("loop2"))
        self.assertEqual(ns["REF"], "BS Switch 5")
        self.assertEqual(ns["GUARD"], make_job.guard_for("loop2"))
        self.assertEqual(set(ns["LENGTHS"]), set(analyze.route_order("loop2")))
        self.assertIn('L("CFG route=%s', (d / "j.py").read_text())

    def test_default_route_is_loop1(self):
        d = Path(tempfile.mkdtemp())
        make_job.main(["steps", "--loco", "L", "--direction", "forward", "--guard", "default",
                       "--out", str(d / "j.py")])
        ns: dict = {}
        exec(compile((d / "j.py").read_text().split(make_job.RUNNER_MARK)[0], "job", "exec"), ns)
        self.assertEqual(ns["ROUTE"], "loop1")
        self.assertEqual(ns["ORDER"], analyze.ORDER)
        self.assertEqual(ns["GUARD"], make_job.DEFAULT_GUARD)

    def test_stoptest_trigger_must_be_on_the_route(self):
        d = Path(tempfile.mkdtemp())
        args = ["stoptest", "--loco", "L", "--direction", "forward", "--step", "30", "--guard", "default",
                "--out", str(d / "s.py")]
        with self.assertRaises(SystemExit):
            make_job.main(args + ["--trigger", "BS Switch 13"])  # loop2 sensor, loop1 route
        make_job.main(args + ["--route", "loop2", "--trigger", "BS Switch 13"])
        self.assertTrue((d / "s.py").exists())


class Lineup(unittest.TestCase):
    def leg(self, route, number, state):
        rows = [r for (sw, _), r in LEGS.items() if sw == str(number)]
        self.assertTrue(rows, number)
        return [r[state + "_leg"] for r in rows]

    def test_every_switch_exists_and_states_are_valid(self):
        for route, lineup in analyze.ROUTE_LINEUP.items():
            self.assertEqual(len({n for n, _ in lineup}), len(lineup), route)
            for n, state in lineup:
                self.assertIn(state, ("closed", "thrown"))
                self.assertTrue(any(sw == str(n) for sw, _ in LEGS), n)

    def test_loop2_legs(self):
        lu = dict(analyze.ROUTE_LINEUP["loop2"])
        self.assertEqual(lu[5], "thrown")
        self.assertIn("Track Scale", self.leg("loop2", 5, "thrown"))
        self.assertEqual(self.leg("loop2", 13, lu[13]), ["Track Barn"])
        self.assertEqual(self.leg("loop2", 15, lu[15]), ["Track S-R"])
        self.assertIn("OS Switch 23b", self.leg("loop2", 31, lu[31]))
        self.assertIn("OS Switch 31", self.leg("loop2", 33, lu[33]))
        self.assertEqual(LEGS[("7", "OS Switch 7")]["closed_leg"], "Track Scale")
        self.assertEqual(lu[1], "thrown")
        self.assertIn("Track Brick-Plane", self.leg("loop2", 1, "thrown"))

    def test_loop1_legs(self):
        lu = dict(analyze.ROUTE_LINEUP["loop1"])
        self.assertEqual(self.leg("loop1", 5, lu[5]), ["Track East Main Ext"])
        self.assertIn("Track Brick-Plane", self.leg("loop1", 1, lu[1]))
        self.assertIn("Track Main East", self.leg("loop1", 33, lu[33]))
        self.assertIn("Track K-2", self.leg("loop1", 37, lu[37]))
        self.assertIn("Track K-1", self.leg("loop1", 39, lu[39]))

    def test_lineup_text(self):
        txt = make_job.lineup_text("loop2")
        self.assertIn("Switch 13  closed", txt)
        self.assertIn("Switch 5   thrown", txt)
        buf = io.StringIO()
        with redirect_stdout(buf):
            make_job.main(["lineup", "--route", "loop2"])
        self.assertEqual(buf.getvalue().strip(), txt)


CFG = "CFG route=loop2 k=5 rel=0.0200 max=12 settle=2 low_max=48 high_span=3 warm=1@64"


def synthetic_log(lengths, laps=4, steps=(32, 48), t0=1000.0):
    """Runner log lines of one loop2 run at constant speed per lap, block times in proportion to
    the planted lengths; the loco enters Switch 5 first."""
    order = analyze.route_order("loop2")
    out = ["%.3f RUN loco=L direction=forward" % t0, "%.3f %s" % (t0, CFG)]
    t = t0 + 1
    for si, step in enumerate(steps):
        out.append("%.3f STEP %d" % (t, step))
        for lap in range(laps):
            v = 100.0 + 10 * si + 3 * lap  # a different speed every lap
            for s in order:
                out.append("%.3f SENS %s ACTIVE" % (t, s))
                out.append("%.3f SENS %s INACTIVE" % (t + 0.1, s))
                t += lengths[s[3:]] / v
        out.append("%.3f SENS %s ACTIVE" % (t, order[0]))
    return out


def planted():
    """Planted loop2 block lengths summing to the plan loop, and the plan-frame centres."""
    names = list(ibl.route_rows("loop2"))
    raw = {n: 150.0 + 37.0 * (i % 7) + (900.0 if i % 4 == 1 else 0.0) for i, n in enumerate(names)}
    scale = ibl.PLAN_LOOP2_MM / sum(raw.values())
    lengths = {n: v * scale for n, v in raw.items()}
    pos, centre = ibl.PLAN_LOOP2_TURNOUT_MM["Switch 5"] - lengths["Switch 5"] / 2, {}
    for n in names:
        centre[n] = pos + lengths[n] / 2
        pos += lengths[n]
    return lengths, centre


class RunsAndLocate(unittest.TestCase):
    def test_cfg_route_is_logged_and_replayed(self):
        lengths, _ = planted()
        runs = analyze.parse_log(synthetic_log(lengths))
        self.assertEqual(runs[0]["cfg"]["route"], "loop2")
        mm = {"BS " + n: v for n, v in lengths.items()}
        res = analyze.summarize_runs(runs, mm, use_logged=True)
        self.assertEqual(res[0]["route"], "loop2")
        row = res[0]["rows"][0]
        self.assertGreater(row["n"], 0)
        self.assertEqual(row["travel"], "east")
        self.assertAlmostEqual(row["median"], 100.0, delta=8)

    def test_log_without_route_is_loop1(self):
        line = "1.0 CFG k=5 rel=0.0200 max=12"
        runs = analyze.parse_log(["0.5 RUN loco=L direction=forward", line])
        self.assertNotIn("route", runs[0]["cfg"])

    def test_profile_csv_has_route_and_correct_filters_on_it(self):
        lengths, _ = planted()
        runs = analyze.parse_log(synthetic_log(lengths))
        mm = {"BS " + n: v for n, v in lengths.items()}
        d = Path(tempfile.mkdtemp())
        sm = analyze.summarize_runs(runs, mm)
        analyze.write_outputs(analyze.latest_runs(sm), None, d, sm)
        rows = list(csv.DictReader(open(d / "profile.csv", newline="")))
        self.assertEqual({r["route"] for r in rows}, {"loop2"})
        self.assertEqual(correct.read_profile(d / "profile.csv", "L", "forward")[0], {})  # loop1 default
        got, _ = correct.read_profile(d / "profile.csv", "L", "forward", route="loop2")
        self.assertTrue(got)

    def test_locate_finds_switch_13_from_a_synthetic_run(self):
        lengths, centre = planted()
        runs = analyze.parse_log(synthetic_log(lengths))
        rows = analyze.block_events(runs, "loop2")
        self.assertEqual({r["lap_index"] for r in rows if r["step"] == 32}, {0, 1, 2})  # the first lap is cut by the settle events
        out = Path(tempfile.mkdtemp()) / "ev.csv"
        analyze.write_events(rows, out)
        rows = list(csv.DictReader(open(out, newline="")))
        names = list(ibl.route_rows("loop2"))
        # pins taken at the planted centres, so the fit is exact
        pins = {s: centre[s] for s in ibl.PLAN_LOOP2_TURNOUT_MM}
        res = ibl.pinned(ibl.infer(rows, loop_mm=ibl.PLAN_LOOP2_MM, ref=ibl.route_ref("loop2"), blocks=names),
                         ibl.PLAN_LOOP2_MM, pins, ibl.route_from_sw5("loop2"))
        for n in names:
            self.assertAlmostEqual(res[n][0], lengths[n], delta=3, msg=n)
        loc = ibl.locate(res, ibl.PLAN_LOOP2_MM, pins, ibl.route_from_sw5("loop2"))
        self.assertAlmostEqual(loc["Switch 13"][0], centre["Switch 13"], delta=3)
        self.assertAlmostEqual(loc["Switch 7"][0], centre["Switch 7"], delta=3)
        self.assertAlmostEqual(loc["Switch 13"][1], centre["Switch 15"] - centre["Switch 13"], delta=3)

    def test_events_skip_a_missed_sensor(self):
        lengths, _ = planted()
        log = [l for l in synthetic_log(lengths) if "SENS BS Scale ACTIVE" not in l]
        rows = analyze.block_events(analyze.parse_log(log), "loop2")
        self.assertNotIn("Scale", {r["block"] for r in rows})
        self.assertNotIn("Switch 5", {r["block"] for r in rows})  # its next sensor is Switch 7, not Scale

    def test_plan_constants(self):
        self.assertEqual(set(ibl.PLAN), {"loop1", "loop2"})
        self.assertEqual(ibl.PLAN["loop1"], (ibl.PLAN_LOOP_MM, ibl.PLAN_TURNOUT_MM))
        self.assertEqual(ibl.PLAN["loop2"][0], 35428.7)
        for s in ("Switch 23b", "Switch 31"):
            self.assertNotIn(s, ibl.PLAN["loop2"][1])
        self.assertEqual(ibl.route_from_sw5("loop2")[0], "Switch 5")
        self.assertEqual(ibl.route_from_sw5("loop1")[0], "Switch 5")

    def test_apply_leaves_loop1_rows_unless_overwrite(self):
        lengths, _ = planted()
        result = {s: (v, 5.0, 4) for s, v in lengths.items()}
        owned = set(ibl.SENSOR_ROWS)
        _, rows, mm = ibl.plan_rows(result, ibl.CSV, "loop2", set(result) - owned)
        self.assertEqual(set(mm), {ibl.route_rows("loop2")[s] for s in set(result) - owned})
        self.assertIn("Track S-R", mm)
        self.assertNotIn("Track East Lead", mm)
        _, _, mm2 = ibl.plan_rows(result, ibl.CSV, "loop2")
        self.assertIn("Track East Lead", mm2)


if __name__ == "__main__":
    unittest.main()
